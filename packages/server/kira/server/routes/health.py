"""Health check endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter(tags=["health"])


@router.get("/health")
async def health(req: Request):
    ollama_ok = await req.app.state.ollama.health()
    db_ok = req.app.state.db.pool is not None
    cloud_available = req.app.state.gemini is not None

    body: dict = {
        "status": "ok" if (ollama_ok and db_ok) else "degraded",
        "ollama": "connected" if ollama_ok else "disconnected",
        "database": "connected" if db_ok else "disconnected",
        "cloud": "available" if cloud_available else "unavailable",
        "version": "0.1.0",
    }
    if not cloud_available:
        body["note"] = (
            "Cloud models are unavailable — no GEMINI_API_KEY set. "
            "KIRA is running fully locally on Ollama."
        )
    return body


@router.get("/health/detailed")
async def detailed(req: Request):
    """Roll-up of every optional subsystem — for a Settings health panel."""
    s = req.app.state
    ollama_ok = await s.ollama.health()
    db_ok = s.db.pool is not None

    def _mark(cond: bool, present_msg: str, absent_msg: str = "not configured"):
        return {"ok": bool(cond), "detail": present_msg if cond else absent_msg}

    tool_registry_ok = getattr(s, "tool_registry", None) is not None
    servers = []
    if tool_registry_ok:
        try:
            servers = s.tool_registry.servers()
        except Exception:
            servers = []

    voice = getattr(s, "voice_pipeline", None)
    voice_snap = voice.snapshot() if voice is not None else None

    doc_files = 0
    if getattr(s, "document_store", None) is not None:
        try:
            doc_files = len(await s.document_store.indexed_files(limit=1000))
        except Exception:
            doc_files = 0

    tasks_count = 0
    if getattr(s, "scheduler", None) is not None:
        try:
            tasks_count = len(await s.scheduler.list_scheduled())
        except Exception:
            tasks_count = 0

    return {
        "status": "ok" if (ollama_ok and db_ok) else "degraded",
        "version": "0.1.0",
        "core": {
            "ollama": _mark(ollama_ok, "connected", "disconnected"),
            "database": _mark(db_ok, "connected", "disconnected"),
            "cloud": _mark(s.gemini is not None, "available", "no API key"),
        },
        "tools": {
            "servers": servers,
            "total": len(servers),
        },
        "voice": voice_snap or {"available": False},
        "documents": {
            "indexed": doc_files,
            "watcher": _mark(getattr(s, "doc_watcher", None) is not None,
                             "watching filesystem"),
        },
        "scheduler": {
            "tasks": tasks_count,
            "engine": _mark(getattr(s, "proactive_engine", None) is not None,
                            "proactive engine online"),
        },
        "monitor": _mark(getattr(s, "monitor", None) is not None,
                         "monitor loop online"),
        "notifications": _mark(getattr(s, "notifications_store", None) is not None,
                                "notifications store online"),
    }
