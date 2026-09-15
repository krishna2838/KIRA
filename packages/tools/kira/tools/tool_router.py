"""Embedding-based tool relevance filter.

Given a user message, we don't ship every registered tool description to the
LLM (that inflates context and makes routing noisier). We embed the message,
compare against pre-computed tool embeddings via cosine similarity, and hand
back only the top-k candidates.
"""
from __future__ import annotations

import math

from kira.tools.registry import ToolRegistry
from kira.tools.types import ToolSpec


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom == 0.0:
        return 0.0
    return dot / denom


class ToolRouter:
    def __init__(self, registry: ToolRegistry, embeddings, top_k: int = 6):
        self.registry = registry
        self.embeddings = embeddings
        self.top_k = top_k

    async def relevant_tools(
        self, message: str, top_k: int | None = None, min_score: float = 0.15
    ) -> list[tuple[ToolSpec, float]]:
        tools = self.registry.all_tools()
        if not tools:
            return []

        k = top_k or self.top_k
        try:
            query_vec = await self.embeddings.embed(message)
        except Exception:
            # Fall back to lexical scoring when embeddings are unavailable.
            return self._lexical_fallback(message, tools, k)

        scored: list[tuple[ToolSpec, float]] = []
        for spec in tools:
            vec = self.registry.embedding_for(spec.qualified_name)
            if vec is None:
                continue
            score = _cosine(query_vec, vec)
            if score >= min_score:
                scored.append((spec, score))

        scored.sort(key=lambda p: p[1], reverse=True)
        return scored[:k]

    def _lexical_fallback(
        self, message: str, tools: list[ToolSpec], k: int
    ) -> list[tuple[ToolSpec, float]]:
        words = {w.lower() for w in message.split() if len(w) > 2}
        scored: list[tuple[ToolSpec, float]] = []
        for spec in tools:
            hay = f"{spec.name} {spec.description}".lower()
            hits = sum(1 for w in words if w in hay)
            if hits:
                scored.append((spec, float(hits)))
        scored.sort(key=lambda p: p[1], reverse=True)
        return scored[:k]
