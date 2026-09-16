"""Scheduler API — CRUD over `scheduled_tasks` + manual run."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter(tags=["scheduler"])


class ScheduleRequest(BaseModel):
    name: str
    cron: str
    tool_chain: list[dict]
    permissions_required: int = 0
    enabled: bool = True


class RunOnceRequest(BaseModel):
    name: str
    tool_chain: list[dict]
    delay_seconds: int = 0
    permissions_required: int = 0


class EnableRequest(BaseModel):
    enabled: bool


@router.get("/scheduler/tasks")
async def list_tasks(req: Request):
    scheduler = req.app.state.scheduler
    if scheduler is None:
        return {"tasks": []}
    return {"tasks": await scheduler.list_scheduled()}


@router.post("/scheduler/tasks")
async def create_task(body: ScheduleRequest, req: Request):
    scheduler = req.app.state.scheduler
    if scheduler is None:
        raise HTTPException(status_code=503, detail="scheduler unavailable")
    return await scheduler.schedule_task(
        name=body.name,
        cron=body.cron,
        tool_chain=body.tool_chain,
        permissions_required=body.permissions_required,
        enabled=body.enabled,
    )


@router.delete("/scheduler/tasks/{name}")
async def delete_task(name: str, req: Request):
    scheduler = req.app.state.scheduler
    if scheduler is None:
        raise HTTPException(status_code=503, detail="scheduler unavailable")
    await scheduler.cancel_task(name)
    return {"deleted": name}


@router.post("/scheduler/tasks/{name}/enabled")
async def set_task_enabled(name: str, body: EnableRequest, req: Request):
    scheduler = req.app.state.scheduler
    if scheduler is None:
        raise HTTPException(status_code=503, detail="scheduler unavailable")
    await scheduler.set_enabled(name, body.enabled)
    return {"name": name, "enabled": body.enabled}


@router.post("/scheduler/tasks/{name}/run")
async def run_task_now(name: str, req: Request):
    scheduler = req.app.state.scheduler
    if scheduler is None:
        raise HTTPException(status_code=503, detail="scheduler unavailable")
    return await scheduler.run_now(name)


@router.post("/scheduler/run_once")
async def run_once(body: RunOnceRequest, req: Request):
    scheduler = req.app.state.scheduler
    if scheduler is None:
        raise HTTPException(status_code=503, detail="scheduler unavailable")
    return await scheduler.run_once(
        name=body.name,
        tool_chain=body.tool_chain,
        delay_seconds=body.delay_seconds,
        permissions_required=body.permissions_required,
    )
