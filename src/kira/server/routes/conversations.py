"""Conversation list + open."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request


router = APIRouter(tags=["conversations"])


@router.get("/conversations")
async def list_conversations(req: Request, q: str | None = None, limit: int = 100):
    db = req.app.state.db
    sql = """
        SELECT id, title, summary, started_at, ended_at, message_count
        FROM conversations
    """
    args: list = []
    if q:
        sql += " WHERE (title ILIKE $1 OR summary ILIKE $1)"
        args.append(f"%{q}%")
    sql += f" ORDER BY started_at DESC LIMIT ${len(args) + 1}"
    args.append(int(limit))
    rows = await db.fetch(sql, *args)
    return {
        "conversations": [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "summary": r["summary"],
                "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                "message_count": r["message_count"],
            }
            for r in rows
        ]
    }


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str, req: Request, limit: int = 200):
    db = req.app.state.db
    try:
        cid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad id")
    rows = await db.fetch(
        """SELECT id, role, content, metadata, created_at
           FROM messages
           WHERE conversation_id = $1
           ORDER BY created_at ASC
           LIMIT $2""",
        cid, limit,
    )
    return {
        "messages": [
            {
                "id": str(r["id"]),
                "role": r["role"],
                "content": r["content"],
                "metadata": r["metadata"] if isinstance(r["metadata"], dict) else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    }
