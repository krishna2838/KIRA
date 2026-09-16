"""Fact-check on demand.

User: "Are you sure?" → the frontend POSTs to /api/factcheck with the
previous assistant message. We re-run a deep-ish research pass and let the
smart model compare its findings to the original claim.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter(tags=["factcheck"])


class FactCheckRequest(BaseModel):
    claim: str
    original_reply: str | None = None


_PROMPT = """You are fact-checking a previous answer.

Claim to verify:
{claim}

Sources you just gathered:
{sources}

If the claim is fully supported: reply "Confirmed by …" naming the source.
If partially supported: give the corrected version and note what was off.
If unsupported: reply "I couldn't find support for this. …"

Cite sources inline as [n] matching the source order below.
Be direct — no filler."""


@router.post("/factcheck")
async def factcheck(body: FactCheckRequest, req: Request):
    from kira.tools.servers import research_server
    from kira.brain.verifier import SourceRef, Verifier
    from kira.core.types import ModelTier

    if research_server._pipeline is None:
        raise HTTPException(status_code=503, detail="Research pipeline unavailable.")

    payload = await research_server._pipeline.quick(body.claim)

    src_block = "\n".join(
        f"[{i + 1}] {s.title} — {s.url}\n{s.snippet}"
        for i, s in enumerate(payload.sources)
    )

    router_ = req.app.state.router
    verdict = await router_.generate(
        ModelTier.SMART,
        [{"role": "user", "content": _PROMPT.format(claim=body.claim, sources=src_block)}],
    )

    verifier = Verifier()
    refs = [
        SourceRef(id=i + 1, url=s.url, title=s.title, snippet=s.snippet)
        for i, s in enumerate(payload.sources)
    ]
    report = verifier.verify(verdict, refs)

    return {
        "verdict": report.text,
        "used_source_ids": report.used_source_ids,
        "sources": [s.model_dump() for s in payload.sources],
        "images": [i.model_dump() for i in payload.images[:6]],
    }
