"""Research MCP server (in-process).

Exposes:
  - research.web_search       — enhanced DDG text search (SourceHit list)
  - research.news_search      — DDG news
  - research.image_search     — DDG images
  - research.video_search     — DDG videos
  - research.wikipedia        — Wikipedia summary
  - research.read_url         — fetch + trafilatura extract
  - research.research         — one-pass research (structured payload)
  - research.deep_research    — full multi-source pipeline

The `research` and `deep_research` tools need an LLM callable and (optionally)
a Redis client; those come in via a module-level "context" that the server
bootstrap sets before use.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from kira.tools.research.pipeline import ResearchPipeline
from kira.tools.research.sources import (
    ddg_images,
    ddg_news,
    ddg_text,
    ddg_videos,
    extract_url,
    wikipedia_summary,
)
from kira.tools.servers.base import InternalServer, InternalTool


# ---- runtime context injection ------------------------------------------

_pipeline: Optional[ResearchPipeline] = None


def configure(
    planner_generate: Callable[[str], Awaitable[str]],
    synth_generate: Callable[[str], Awaitable[str]],
    redis_client=None,
) -> None:
    """Called from the server bootstrap once brain + redis are ready."""
    global _pipeline
    _pipeline = ResearchPipeline(
        planner_generate=planner_generate,
        synth_generate=synth_generate,
        redis_client=redis_client,
    )


# ---- tool handlers -------------------------------------------------------


async def _tool_web_search(args: dict) -> Any:
    hits = await ddg_text(args["query"], max_results=int(args.get("max_results", 8)))
    return {"query": args["query"], "results": [h.model_dump() for h in hits]}


async def _tool_news_search(args: dict) -> Any:
    hits = await ddg_news(args["query"], max_results=int(args.get("max_results", 6)))
    return {"query": args["query"], "results": [h.model_dump() for h in hits]}


async def _tool_image_search(args: dict) -> Any:
    hits = await ddg_images(args["query"], max_results=int(args.get("max_results", 8)))
    return {"query": args["query"], "results": [h.model_dump() for h in hits]}


async def _tool_video_search(args: dict) -> Any:
    hits = await ddg_videos(args["query"], max_results=int(args.get("max_results", 6)))
    return {"query": args["query"], "results": [h.model_dump() for h in hits]}


async def _tool_wikipedia(args: dict) -> Any:
    hit = await wikipedia_summary(args["query"])
    return {"query": args["query"], "result": hit.model_dump() if hit else None}


async def _tool_read_url(args: dict) -> Any:
    page = await extract_url(args["url"])
    return page.model_dump() if page else {"url": args["url"], "extracted": False}


async def _tool_research(args: dict) -> Any:
    if _pipeline is None:
        return {"error": "research pipeline not configured"}
    resp = await _pipeline.quick(
        args["question"], research_id=args.get("research_id")
    )
    return resp.model_dump(mode="json")


async def _tool_deep_research(args: dict) -> Any:
    if _pipeline is None:
        return {"error": "research pipeline not configured"}
    resp = await _pipeline.deep(
        args["question"], research_id=args.get("research_id")
    )
    return resp.model_dump(mode="json")


# ---- server definition ---------------------------------------------------


SERVER = InternalServer(
    name="research",
    description=(
        "Search the web (text/news/images/videos), Wikipedia, and full-page "
        "content extraction. Includes a deep-research pipeline that plans "
        "sub-queries, reads sources, cross-verifies, and synthesizes cited answers."
    ),
    tools=[
        InternalTool(
            name="web_search",
            description="Search the web for a query. Returns structured hits.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
            handler=_tool_web_search,
        ),
        InternalTool(
            name="news_search",
            description="Search recent news for a query.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 6},
                },
                "required": ["query"],
            },
            handler=_tool_news_search,
        ),
        InternalTool(
            name="image_search",
            description="Search the web for images.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
            handler=_tool_image_search,
        ),
        InternalTool(
            name="video_search",
            description="Search the web for videos (YouTube, etc.).",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 6},
                },
                "required": ["query"],
            },
            handler=_tool_video_search,
        ),
        InternalTool(
            name="wikipedia",
            description="Fetch a Wikipedia summary for a term. Great for factual lookups.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=_tool_wikipedia,
        ),
        InternalTool(
            name="read_url",
            description=(
                "Fetch a webpage and extract its clean text + metadata "
                "(title, author, date, description, main body)."
            ),
            input_schema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
            handler=_tool_read_url,
        ),
        InternalTool(
            name="research",
            description=(
                "One-pass research on a question. Runs a search, reads top "
                "results, and returns a structured response with summary, "
                "images, videos, and cited sources."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "research_id": {"type": "string"},
                },
                "required": ["question"],
            },
            handler=_tool_research,
        ),
        InternalTool(
            name="deep_research",
            description=(
                "Deep research: plans 3–5 sub-queries, searches multiple "
                "sources in parallel, reads several pages, cross-verifies "
                "claims, and synthesizes a cited answer. Takes 30–60 seconds."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "research_id": {"type": "string"},
                },
                "required": ["question"],
            },
            handler=_tool_deep_research,
        ),
    ],
)
