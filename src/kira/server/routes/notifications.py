"""Notifications API: list, ingest, mark-read, and monitor queue drain."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter(tags=["notifications"])


class IngestRequest(BaseModel):
    app_name: str
    title: str = ""
    body: str = ""
    sender: str | None = None
    importance: float = 0.5


class MarkReadRequest(BaseModel):
    ids: list[str] | None = None


@router.get("/notifications")
async def list_notifications(req: Request, limit: int = 30, since_hours: int = 24):
    store = req.app.state.notifications_store
    if store is None:
        return {"notifications": [], "unread": 0}
    return {
        "notifications": await store.recent(limit=limit, since_hours=since_hours),
        "unread": await store.unread_count(),
    }


@router.post("/notifications/ingest")
async def ingest(body: IngestRequest, req: Request):
    """Public ingest endpoint — used by external adapters (e.g. a discord.py
    process running elsewhere) that want to push into KIRA's notification
    store."""
    store = req.app.state.notifications_store
    if store is None:
        raise HTTPException(status_code=503, detail="notifications store unavailable")
    return await store.ingest(
        app_name=body.app_name,
        title=body.title,
        body=body.body,
        sender=body.sender,
        importance=body.importance,
    )


@router.post("/notifications/mark_read")
async def mark_read(body: MarkReadRequest, req: Request):
    store = req.app.state.notifications_store
    if store is None:
        raise HTTPException(status_code=503, detail="notifications store unavailable")
    n = await store.mark_read(body.ids)
    return {"marked": n}


@router.get("/monitor/queue")
async def drain_monitor(req: Request):
    """Drain proactive events for the frontend.

    Two-stage: pop raw events from the Monitor, push each through the
    ProactiveEngine (which scores + batches + filters), then drain the
    engine.
    """
    monitor = req.app.state.monitor
    engine = req.app.state.proactive_engine
    if monitor is None:
        return {"events": []}

    raw = await monitor.pop_events(max_items=20)
    if engine is None:
        return {"events": raw}

    from kira.tools.proactive import from_monitor_event
    for evt in raw:
        try:
            await engine.push(from_monitor_event(evt))
        except Exception:
            pass
    return {"events": await engine.pop_events(max_items=20)}


@router.post("/monitor/active")
async def set_active(active: bool, req: Request):
    monitor = req.app.state.monitor
    if monitor is None:
        return {"ok": False}
    monitor.set_active(active)
    return {"ok": True, "active": active}
