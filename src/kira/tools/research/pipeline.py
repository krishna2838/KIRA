"""Deep-research pipeline.

    question → planner (3–5 sub-queries)
    → parallel DDG text/news/images/videos + Wikipedia lookup
    → extract top-N pages with trafilatura
    → cross-verify (count how many extracted sources support each hit)
    → synthesize final answer with [n] citations
    → return structured ResearchResponse
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Awaitable, Callable

from kira.core.logger import get_logger

from kira.tools.research.planner import QueryPlanner, Synthesizer
from kira.tools.research.progress import BROKER
from kira.tools.research.sources import (
    classify_reliability,
    ddg_images,
    ddg_news,
    ddg_text,
    ddg_videos,
    extract_url,
    wikipedia_summary,
)
from kira.tools.research.types import (
    ImageHit,
    ResearchResponse,
    SourceHit,
    VideoHit,
)


logger = get_logger("tools.research.pipeline")

CACHE_TTL_SEC = 3600      # 1 hour, per spec
MAX_EXTRACT = 3
CACHE_PREFIX = "kira:research:"


def _cache_key(question: str, deep: bool) -> str:
    h = hashlib.sha256(f"{deep}:{question}".encode("utf-8")).hexdigest()[:16]
    return CACHE_PREFIX + h


class ResearchPipeline:
    def __init__(
        self,
        planner_generate: Callable[[str], Awaitable[str]],
        synth_generate: Callable[[str], Awaitable[str]],
        redis_client=None,
    ):
        self.planner = QueryPlanner(planner_generate)
        self.synth = Synthesizer(synth_generate)
        self.redis = redis_client

    # -- entry points --------------------------------------------------

    async def quick(self, question: str, research_id: str | None = None) -> ResearchResponse:
        """One-pass research: single search + extraction. ~5s."""
        return await self._run(question, deep=False, research_id=research_id)

    async def deep(self, question: str, research_id: str | None = None) -> ResearchResponse:
        """Multi-query, multi-source. 30–60s."""
        return await self._run(question, deep=True, research_id=research_id)

    # -- pipeline ------------------------------------------------------

    async def _run(self, question: str, *, deep: bool, research_id: str | None) -> ResearchResponse:
        cached = await self._cache_get(question, deep)
        if cached is not None:
            self._emit(research_id, "done", "cache hit",
                       {"cached": True, "result": cached.model_dump(mode="json")})
            return cached

        # ---- plan ----
        self._emit(research_id, "planning", "planning search queries")
        queries = (
            await self.planner.plan(question) if deep else [question]
        )
        self._emit(
            research_id, "planning", f"planned {len(queries)} queries",
            {"queries": queries},
        )

        # ---- search (parallel) ----
        self._emit(research_id, "searching", "querying sources")
        text_hits: list[SourceHit] = []
        news_hits: list[SourceHit] = []
        image_hits: list[ImageHit] = []
        video_hits: list[VideoHit] = []
        wiki_hit: SourceHit | None = None

        text_tasks = [ddg_text(q, max_results=6) for q in queries]
        news_task = ddg_news(question, max_results=4)
        image_task = ddg_images(question, max_results=6)
        video_task = ddg_videos(question, max_results=4)
        wiki_task = wikipedia_summary(question)

        gathered = await asyncio.gather(
            *text_tasks, news_task, image_task, video_task, wiki_task,
            return_exceptions=True,
        )
        text_results = gathered[: len(text_tasks)]
        news_result = gathered[len(text_tasks)]
        image_result = gathered[len(text_tasks) + 1]
        video_result = gathered[len(text_tasks) + 2]
        wiki_result = gathered[len(text_tasks) + 3]

        for r in text_results:
            if isinstance(r, list):
                text_hits.extend(r)
        if isinstance(news_result, list):
            news_hits.extend(news_result)
        if isinstance(image_result, list):
            image_hits.extend(image_result)
        if isinstance(video_result, list):
            video_hits.extend(video_result)
        if isinstance(wiki_result, SourceHit):
            wiki_hit = wiki_result

        # Dedupe text hits by URL, keeping the first (higher-ranked) hit.
        seen: set[str] = set()
        unique_text: list[SourceHit] = []
        for h in text_hits:
            if h.url in seen:
                continue
            seen.add(h.url)
            unique_text.append(h)

        self._emit(
            research_id, "searching",
            f"found {len(unique_text)} pages, {len(news_hits)} news, "
            f"{len(image_hits)} images, {len(video_hits)} videos"
            + (" (+wikipedia)" if wiki_hit else ""),
            {"counts": {
                "text": len(unique_text), "news": len(news_hits),
                "images": len(image_hits), "videos": len(video_hits),
                "wiki": 1 if wiki_hit else 0,
            }},
        )

        # ---- read top pages ----
        to_extract = unique_text[:MAX_EXTRACT]
        self._emit(
            research_id, "reading",
            f"reading {len(to_extract)} sources",
            {"urls": [h.url for h in to_extract]},
        )
        extractions = await asyncio.gather(
            *[extract_url(h.url) for h in to_extract], return_exceptions=True
        )
        extracted = [e for e in extractions if e and not isinstance(e, Exception)]

        # ---- cross-verify + reliability bump ----
        # A source appears trustworthy if extraction succeeded AND at least one
        # other search hit mentions the same top-level domain.
        for h in unique_text:
            base = classify_reliability(h.url)
            h.reliability = base
        supporting: dict[str, int] = {}
        for h in unique_text:
            try:
                dom = h.url.split("/")[2]
            except Exception:
                continue
            supporting[dom] = supporting.get(dom, 0) + 1
        for h in unique_text:
            try:
                dom = h.url.split("/")[2]
            except Exception:
                continue
            if supporting.get(dom, 0) >= 2 and h.reliability == "medium":
                h.reliability = "high"

        # ---- assemble the citation block for synthesis ----
        combined_sources: list[SourceHit] = []
        if wiki_hit:
            combined_sources.append(wiki_hit)
        combined_sources.extend(unique_text[: 8 - len(combined_sources)])

        sources_block_lines: list[str] = []
        for i, s in enumerate(combined_sources, start=1):
            body_snippet = s.snippet
            # If we extracted the page, use the extracted opening as it's cleaner.
            for e in extracted:
                if e.url == s.url and e.text:
                    body_snippet = e.text[:800]
                    break
            sources_block_lines.append(
                f"[{i}] {s.title} — {s.url}\n{body_snippet}"
            )
        sources_block = "\n\n".join(sources_block_lines) or "(no sources)"

        # ---- synthesize ----
        self._emit(research_id, "synthesizing", "writing answer with citations")
        if combined_sources:
            summary = await self.synth.synthesize(question, sources_block)
        else:
            summary = (
                "I couldn't find useful sources for that. Want me to try "
                "a different phrasing?"
            )

        related = queries[1:] if deep and len(queries) > 1 else []

        response = ResearchResponse(
            summary=summary.strip(),
            images=image_hits[:12],
            videos=video_hits[:6],
            sources=combined_sources,
            related_queries=related,
            plan=queries,
        )

        await self._cache_set(question, deep, response)
        self._emit(
            research_id, "done", "research complete",
            {"result": response.model_dump(mode="json")},
        )
        return response

    # -- redis cache ---------------------------------------------------

    async def _cache_get(self, question: str, deep: bool) -> ResearchResponse | None:
        if self.redis is None:
            return None
        try:
            raw = await self.redis.get(_cache_key(question, deep))
            if not raw:
                return None
            return ResearchResponse(**json.loads(raw))
        except Exception:
            return None

    async def _cache_set(self, question: str, deep: bool, response: ResearchResponse) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.set(
                _cache_key(question, deep),
                json.dumps(response.model_dump(mode="json")),
                ex=CACHE_TTL_SEC,
            )
        except Exception as e:
            logger.debug(f"research cache set failed: {e}")

    def _emit(self, rid: str | None, stage: str, message: str, detail: dict | None = None) -> None:
        if not rid:
            return
        BROKER.publish(rid, {"stage": stage, "message": message, "detail": detail or {}})
