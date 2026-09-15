"""Web search MCP server (in-process) — DuckDuckGo, no API key required."""
from __future__ import annotations

import asyncio
from typing import Any

from kira.tools.servers.base import InternalServer, InternalTool


def _ddgs():
    # Lazy import so the tools package still imports without duckduckgo-search.
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "duckduckgo-search is required for web search "
            f"(pip install duckduckgo-search): {e}"
        ) from e
    return DDGS()


def _text_search_sync(query: str, max_results: int) -> list[dict]:
    with _ddgs() as ddgs:
        results = ddgs.text(query, max_results=max_results) or []
    return [
        {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")}
        for r in results
    ]


def _news_search_sync(query: str, max_results: int) -> list[dict]:
    with _ddgs() as ddgs:
        results = ddgs.news(query, max_results=max_results) or []
    return [
        {
            "title": r.get("title"),
            "url": r.get("url") or r.get("href"),
            "snippet": r.get("body"),
            "source": r.get("source"),
            "date": r.get("date"),
        }
        for r in results
    ]


def _image_search_sync(query: str, max_results: int) -> list[dict]:
    with _ddgs() as ddgs:
        results = ddgs.images(query, max_results=max_results) or []
    return [
        {
            "title": r.get("title"),
            "image": r.get("image"),
            "thumbnail": r.get("thumbnail"),
            "source": r.get("source"),
            "url": r.get("url"),
        }
        for r in results
    ]


async def web_search(args: dict) -> Any:
    query = str(args["query"])
    max_results = min(int(args.get("max_results", 5)), 20)
    results = await asyncio.to_thread(_text_search_sync, query, max_results)
    return {"query": query, "results": results}


async def news_search(args: dict) -> Any:
    query = str(args["query"])
    max_results = min(int(args.get("max_results", 5)), 20)
    results = await asyncio.to_thread(_news_search_sync, query, max_results)
    return {"query": query, "results": results}


async def image_search(args: dict) -> Any:
    query = str(args["query"])
    max_results = min(int(args.get("max_results", 5)), 20)
    results = await asyncio.to_thread(_image_search_sync, query, max_results)
    return {"query": query, "results": results}


SERVER = InternalServer(
    name="web",
    description="Search the web via DuckDuckGo (text, news, images).",
    tools=[
        InternalTool(
            name="web_search",
            description=(
                "Search the web for a query. Returns a list of results with "
                "title, url, and snippet. Use for general information lookups."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            handler=web_search,
        ),
        InternalTool(
            name="news_search",
            description="Search recent news articles for a query.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            handler=news_search,
        ),
        InternalTool(
            name="image_search",
            description="Search for images matching a query.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            handler=image_search,
        ),
    ],
)
