"""Search + fetch sources for the research pipeline.

All four DuckDuckGo modes plus Wikipedia. Everything is free — no API keys.

Every function is defensive: if the underlying library is missing or errors
out, we return an empty list rather than raising. The pipeline degrades
gracefully — one missing source doesn't kill the whole research run.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx

from kira.core.logger import get_logger

from kira.tools.research.types import (
    ExtractedPage,
    ImageHit,
    Reliability,
    SourceHit,
    VideoHit,
)


logger = get_logger("tools.research.sources")


DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Apple Silicon Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) KIRA/0.1"
)

# Domains we treat with elevated trust for reliability tagging.
_HIGH_TRUST = {
    "wikipedia.org", "nature.com", "science.org", "arxiv.org",
    "docs.python.org", "developer.mozilla.org", "who.int", "nist.gov",
    "nih.gov", "ietf.org", "w3.org", "kernel.org", "reuters.com",
    "apnews.com", "bbc.com", "bbc.co.uk", "theguardian.com",
    "gov.in", "nic.in",
}
_LOW_TRUST_HINTS = ("blogspot.", "medium.com/@", "reddit.com", "quora.com")


def classify_reliability(url: str) -> Reliability:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return "medium"
    # Strip common subdomain prefixes for matching
    host = host.split(":")[0]
    for high in _HIGH_TRUST:
        if host == high or host.endswith("." + high):
            return "high"
    for hint in _LOW_TRUST_HINTS:
        if hint in url:
            return "low"
    return "medium"


# ---- DuckDuckGo -----------------------------------------------------------


def _ddgs():
    try:
        from duckduckgo_search import DDGS  # type: ignore
        return DDGS()
    except Exception as e:
        raise RuntimeError(
            "duckduckgo-search is required (pip install duckduckgo-search)"
        ) from e


def _sync_text(query: str, max_results: int) -> list[SourceHit]:
    try:
        with _ddgs() as ddgs:
            rows = ddgs.text(query, max_results=max_results) or []
    except Exception as e:
        logger.warning(f"ddg text failed: {e}")
        return []
    hits: list[SourceHit] = []
    for r in rows:
        url = r.get("href") or r.get("url") or ""
        if not url:
            continue
        hits.append(
            SourceHit(
                url=url,
                title=r.get("title", "") or "",
                snippet=r.get("body", "") or "",
                reliability=classify_reliability(url),
            )
        )
    return hits


def _sync_news(query: str, max_results: int) -> list[SourceHit]:
    try:
        with _ddgs() as ddgs:
            rows = ddgs.news(query, max_results=max_results) or []
    except Exception as e:
        logger.warning(f"ddg news failed: {e}")
        return []
    hits: list[SourceHit] = []
    for r in rows:
        url = r.get("url") or r.get("href") or ""
        if not url:
            continue
        hits.append(
            SourceHit(
                url=url,
                title=r.get("title", "") or "",
                snippet=r.get("body", "") or "",
                reliability=classify_reliability(url),
            )
        )
    return hits


def _sync_images(query: str, max_results: int) -> list[ImageHit]:
    try:
        with _ddgs() as ddgs:
            rows = ddgs.images(query, max_results=max_results) or []
    except Exception as e:
        logger.warning(f"ddg images failed: {e}")
        return []
    hits: list[ImageHit] = []
    for r in rows:
        img = r.get("image") or ""
        if not img:
            continue
        hits.append(
            ImageHit(
                url=img,
                alt=r.get("title", "") or "",
                source=r.get("source") or r.get("url", "") or "",
                thumbnail=r.get("thumbnail"),
                width=r.get("width"),
                height=r.get("height"),
            )
        )
    return hits


def _sync_videos(query: str, max_results: int) -> list[VideoHit]:
    try:
        with _ddgs() as ddgs:
            rows = ddgs.videos(query, max_results=max_results) or []
    except Exception as e:
        logger.warning(f"ddg videos failed: {e}")
        return []
    hits: list[VideoHit] = []
    for r in rows:
        url = r.get("content") or r.get("url") or ""
        if not url:
            continue
        hits.append(
            VideoHit(
                url=url,
                title=r.get("title", "") or "",
                thumbnail=r.get("image") or r.get("thumbnail", "") or "",
                duration=str(r.get("duration") or ""),
                source=r.get("uploader") or r.get("publisher", "") or "",
            )
        )
    return hits


async def ddg_text(query: str, max_results: int = 8) -> list[SourceHit]:
    return await asyncio.to_thread(_sync_text, query, max_results)


async def ddg_news(query: str, max_results: int = 6) -> list[SourceHit]:
    return await asyncio.to_thread(_sync_news, query, max_results)


async def ddg_images(query: str, max_results: int = 8) -> list[ImageHit]:
    return await asyncio.to_thread(_sync_images, query, max_results)


async def ddg_videos(query: str, max_results: int = 6) -> list[VideoHit]:
    return await asyncio.to_thread(_sync_videos, query, max_results)


# ---- Wikipedia ------------------------------------------------------------


async def wikipedia_summary(query: str) -> SourceHit | None:
    try:
        import wikipediaapi  # type: ignore
    except Exception as e:
        logger.debug(f"wikipedia-api missing: {e}")
        return None

    def _do() -> SourceHit | None:
        wiki = wikipediaapi.Wikipedia(user_agent="KIRA/0.1", language="en")
        page = wiki.page(query)
        if not page.exists():
            return None
        summary = (page.summary or "")[:1200]
        return SourceHit(
            url=page.fullurl,
            title=page.title,
            snippet=summary,
            reliability="high",
        )

    try:
        return await asyncio.to_thread(_do)
    except Exception as e:
        logger.debug(f"wiki lookup failed: {e}")
        return None


# ---- Content extraction ---------------------------------------------------


async def extract_url(url: str, timeout_sec: float = 8.0) -> ExtractedPage | None:
    """Fetch a URL and pull clean text via trafilatura, with a BeautifulSoup
    fallback for metadata."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout_sec,
            headers={"User-Agent": DEFAULT_UA},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.debug(f"fetch {url}: {e}")
        return None

    text = ""
    metadata_title = ""
    metadata_author = ""
    metadata_date = ""
    metadata_desc = ""
    images: list[str] = []

    # Primary: trafilatura for main article extraction.
    try:
        import trafilatura  # type: ignore

        text = trafilatura.extract(html, include_comments=False,
                                   include_tables=False,
                                   favor_precision=True) or ""
        md = trafilatura.extract_metadata(html)
        if md:
            metadata_title = getattr(md, "title", "") or ""
            metadata_author = getattr(md, "author", "") or ""
            metadata_date = getattr(md, "date", "") or ""
            metadata_desc = getattr(md, "description", "") or ""
    except Exception as e:
        logger.debug(f"trafilatura failed on {url}: {e}")

    # Fallback: BeautifulSoup for title + og:image
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(html, "html.parser")
        if not metadata_title and soup.title:
            metadata_title = (soup.title.string or "").strip()
        if not metadata_desc:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                metadata_desc = meta_desc.get("content", "") or ""
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            images.append(og["content"])
        if not text:
            body = soup.get_text(" ", strip=True)
            text = body[:4000]
    except Exception as e:
        logger.debug(f"bs4 failed on {url}: {e}")

    if not text and not metadata_title:
        return None

    return ExtractedPage(
        url=url,
        title=metadata_title,
        author=metadata_author,
        published=metadata_date,
        description=metadata_desc,
        text=text[:20000],
        images=images,
    )
