"""Post-response confidence check.

Runs on the fast model. Given the assistant draft + the sources KIRA used,
returns a 0..10 confidence integer and a one-line rationale. Anything below
`min_confidence` should be flagged with a disclaimer.
"""
from __future__ import annotations

import re
from typing import Awaitable, Callable


AsyncGenerate = Callable[[str], Awaitable[str]]

_PROMPT = """You are grading whether an assistant's reply is well-supported by
the sources it was given. Reply with a single JSON object:

  {{"confidence": 0-10, "reason": "…one line…"}}

Rules:
- 10 = every factual claim is directly supported.
- 5  = the claims are plausible but partially unsupported.
- 0  = the reply invents facts the sources don't back up.

Assistant reply:
{reply}

Sources the assistant saw:
{sources}

JSON only.
"""


async def score(reply: str, sources_block: str, generate: AsyncGenerate) -> dict:
    try:
        raw = await generate(_PROMPT.format(
            reply=reply[:4000], sources=sources_block[:6000],
        ))
    except Exception:
        return {"confidence": 5, "reason": "confidence grader unavailable"}
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {"confidence": 5, "reason": "grader returned no JSON"}
    try:
        import json
        obj = json.loads(m.group(0))
        conf = int(obj.get("confidence", 5))
        conf = max(0, min(10, conf))
        return {"confidence": conf, "reason": str(obj.get("reason", ""))[:200]}
    except Exception:
        return {"confidence": 5, "reason": "grader returned malformed JSON"}


def disclaimer_for(confidence: int) -> str | None:
    if confidence >= 6:
        return None
    if confidence >= 3:
        return "(Low confidence — worth double-checking.)"
    return "(I'm not sure about this. Want me to look it up?)"
