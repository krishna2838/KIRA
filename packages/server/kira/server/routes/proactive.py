"""Proactive engine endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel


router = APIRouter(tags=["proactive"])


class PushEventRequest(BaseModel):
    kind: str
    title: str
    message: str
    urgency: float = 0.5
    relevance: float = 0.5
    actionability: float = 0.5
    detail: dict = {}
    dedupe_key: str = ""


@router.get("/proactive/queue")
async def drain(req: Request):
    engine = req.app.state.proactive_engine
    if engine is None:
        return {"events": []}
    return {"events": await engine.pop_events(max_items=20)}


@router.get("/proactive/peek")
async def peek(req: Request):
    engine = req.app.state.proactive_engine
    if engine is None:
        return {"events": []}
    return {"events": await engine.peek(limit=50)}


@router.get("/proactive/silent")
async def silent(req: Request):
    engine = req.app.state.proactive_engine
    if engine is None:
        return {"events": []}
    return {"events": await engine.silent_log(limit=50)}


@router.post("/proactive/push")
async def push_event(body: PushEventRequest, req: Request):
    """Public hook for external agents / adapters to push into the engine."""
    engine = req.app.state.proactive_engine
    if engine is None:
        return {"pushed": False}
    from kira.tools.proactive import ProactiveEvent
    await engine.push(ProactiveEvent(**body.model_dump()))
    return {"pushed": True}
