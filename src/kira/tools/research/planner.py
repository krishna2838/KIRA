"""Query planner + synthesizer for deep research.

Both stages call the LLM through a caller-supplied `generate(prompt)` callable
so this module is decoupled from the concrete brain/router layer.
"""
from __future__ import annotations

import json
import re
from typing import Awaitable, Callable


PLANNER_PROMPT = """You are a query planner for a research assistant.
Break the user's question into 3–5 distinct, specific search-engine queries
that together would answer it well. Return a JSON array of strings, e.g.
["…", "…"]. Do not include explanations.

User question: {question}
"""


SYNTHESIS_PROMPT = """You are synthesizing a research answer for the user.

Rules:
- Answer only from the provided sources — if the sources don't say something, don't invent it.
- Prefer facts confirmed by multiple sources; note disagreements.
- Use inline citations [1], [2] matching the source order below.
- Be concise but specific — no filler.
- Structure the reply as short paragraphs or a compact bulleted list when comparing options.

User question:
{question}

Sources:
{sources}

Return only the answer text (with [n] citations). Do not repeat the source list.
"""


AsyncGenerate = Callable[[str], Awaitable[str]]


class QueryPlanner:
    def __init__(self, generate: AsyncGenerate):
        self.generate = generate

    async def plan(self, question: str) -> list[str]:
        try:
            raw = await self.generate(PLANNER_PROMPT.format(question=question))
        except Exception:
            return [question]

        # Try to pull a JSON array out of the reply.
        match = re.search(r"\[[\s\S]*\]", raw)
        if match:
            try:
                arr = json.loads(match.group(0))
                if isinstance(arr, list):
                    out = [str(x).strip() for x in arr if str(x).strip()]
                    if out:
                        return out[:5]
            except json.JSONDecodeError:
                pass

        # Fallback: split by newlines
        lines = [
            re.sub(r"^[-\d\.\)\s]+", "", ln).strip("\"' ")
            for ln in raw.splitlines()
            if ln.strip()
        ]
        return [ln for ln in lines if ln][:5] or [question]


class Synthesizer:
    def __init__(self, generate: AsyncGenerate):
        self.generate = generate

    async def synthesize(
        self, question: str, sources_block: str
    ) -> str:
        try:
            return (
                await self.generate(
                    SYNTHESIS_PROMPT.format(question=question, sources=sources_block)
                )
            ).strip()
        except Exception:
            return (
                "I couldn't finish the synthesis pass, but I gathered several "
                "sources — see the citations below."
            )
