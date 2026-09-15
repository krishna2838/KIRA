"""Audit history endpoints.

Every permission decision, tool call, memory write, and scheduled-task run
already lands in `audit_log`. This route lets the frontend search + export
it.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


router = APIRouter(tags=["audit"])


@router.get("/audit")
async def list_audit(
    req: Request,
    q: str | None = None,
    tool: str | None = None,
    since_hours: int = 24,
    limit: int = 100,
):
    db = req.app.state.db
    sql = """
        SELECT id, action, tool_name, risk_level, input_summary, output_summary,
               approved, approved_by, error, latency_ms, created_at
        FROM audit_log
        WHERE created_at > NOW() - ($1 || ' hours')::interval
    """
    args: list = [str(int(since_hours))]
    if tool:
        sql += f" AND tool_name ILIKE ${len(args) + 1}"
        args.append(tool)
    if q:
        sql += (
            f" AND (COALESCE(input_summary, '') ILIKE ${len(args) + 1}"
            f"   OR COALESCE(output_summary, '') ILIKE ${len(args) + 1}"
            f"   OR COALESCE(error, '') ILIKE ${len(args) + 1})"
        )
        args.append(f"%{q}%")
    sql += f" ORDER BY created_at DESC LIMIT ${len(args) + 1}"
    args.append(int(limit))
    rows = await db.fetch(sql, *args)
    return {
        "entries": [
            {
                "id": str(r["id"]),
                "action": r["action"],
                "tool_name": r["tool_name"],
                "risk_level": r["risk_level"],
                "input_summary": r["input_summary"],
                "output_summary": r["output_summary"],
                "approved": r["approved"],
                "approved_by": r["approved_by"],
                "error": r["error"],
                "latency_ms": r["latency_ms"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    }


@router.get("/audit/export")
async def export_audit(req: Request, since_hours: int = 168):
    """JSON dump of the last N hours of audit entries (default: one week)."""
    r = await list_audit(req, since_hours=since_hours, limit=10_000)
    return JSONResponse(r, headers={
        "Content-Disposition": "attachment; filename=kira-audit.json",
    })
