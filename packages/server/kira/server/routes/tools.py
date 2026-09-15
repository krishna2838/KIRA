"""Tools API — list registered tools, and approve/deny pending confirmations."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter(tags=["tools"])


class ConfirmationDecision(BaseModel):
    approved: bool


class ExecRequest(BaseModel):
    tool: str
    arguments: dict = {}


@router.get("/tools")
async def list_tools(req: Request):
    registry = req.app.state.tool_registry
    if registry is None:
        return {"servers": [], "tools": []}
    tools = [
        {
            "server": s.server,
            "name": s.name,
            "qualified_name": s.qualified_name,
            "description": s.description,
            "input_schema": s.input_schema,
        }
        for s in registry.all_tools()
    ]
    return {"servers": registry.servers(), "tools": tools}


@router.get("/tools/pending")
async def list_pending(req: Request):
    executor = req.app.state.tool_executor
    if executor is None:
        return {"pending": []}
    return {
        "pending": [
            c.model_dump(mode="json") for c in executor.all_pending()
        ]
    }


@router.post("/tools/exec")
async def exec_tool(body: ExecRequest, req: Request):
    """Directly execute one tool (permission-gated).

    Used by widgets like the SystemStatus panel that need to read specific
    read-only tools without going through the chat loop.
    """
    executor = req.app.state.tool_executor
    if executor is None:
        raise HTTPException(status_code=503, detail="Tools subsystem unavailable")
    from kira.tools.types import ToolCall

    outcome = await executor.execute(
        ToolCall(tool=body.tool, arguments=body.arguments)
    )
    if outcome.status == "ok" and outcome.result is not None:
        return {"status": "ok", "result": outcome.result.content}
    if outcome.status == "needs_confirmation" and outcome.confirmation is not None:
        return {
            "status": "needs_confirmation",
            "confirmation": outcome.confirmation.model_dump(mode="json"),
        }
    return {"status": outcome.status, "message": outcome.message}


@router.post("/tools/confirm/{confirmation_id}")
async def confirm(confirmation_id: str, body: ConfirmationDecision, req: Request):
    executor = req.app.state.tool_executor
    if executor is None:
        raise HTTPException(status_code=503, detail="Tools subsystem unavailable")
    try:
        cid = UUID(confirmation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad confirmation id")
    outcome = await executor.resolve_confirmation(cid, body.approved)
    return outcome.model_dump(mode="json")
