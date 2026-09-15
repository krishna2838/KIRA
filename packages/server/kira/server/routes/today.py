"""Personal-OS aggregate endpoints backed by life_os_server + notifications."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter(tags=["today"])


class DeadlineIn(BaseModel):
    name: str
    date: str  # ISO 8601
    notes: str = ""


@router.get("/today")
async def today(_: Request):
    from kira.tools.servers.life_os_server import _get_today_brief
    return await _get_today_brief({})


@router.get("/today/focus")
async def focus(_: Request):
    from kira.tools.servers.life_os_server import _get_focus_suggestion
    return await _get_focus_suggestion({})


@router.get("/today/morning")
async def morning(_: Request):
    from kira.tools.servers.life_os_server import _morning_brief
    return await _morning_brief({})


@router.get("/today/week")
async def week(_: Request):
    from kira.tools.servers.life_os_server import _get_weekly_overview
    return await _get_weekly_overview({})


@router.get("/deadlines")
async def deadlines(req: Request, days: int = 14):
    store = req.app.state.deadlines
    if store is None:
        return {"deadlines": []}
    return {"deadlines": await store.upcoming(days=days)}


@router.post("/deadlines")
async def add_deadline(body: DeadlineIn, req: Request):
    store = req.app.state.deadlines
    if store is None:
        raise HTTPException(status_code=503, detail="deadlines store unavailable")
    from datetime import datetime
    try:
        due = datetime.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be ISO 8601")
    return await store.add(body.name, due, body.notes)


@router.post("/deadlines/{deadline_id}/complete")
async def complete_deadline(deadline_id: str, req: Request):
    store = req.app.state.deadlines
    if store is None:
        raise HTTPException(status_code=503, detail="deadlines store unavailable")
    return await store.complete(deadline_id)
