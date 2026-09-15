"""Memory API endpoints."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Request

from kira.memory.embeddings import EmbeddingEngine
from kira.memory.store import MemoryStore


router = APIRouter(tags=["memory"])


def _store(req: Request) -> MemoryStore:
    embeddings = EmbeddingEngine(req.app.state.ollama)
    return MemoryStore(req.app.state.db, embeddings)


@router.get("/memory/search")
async def search_memories(q: str, limit: int = 10, req: Request = None):  # type: ignore[assignment]
    store = _store(req)
    memories = await store.search(q, limit=limit)
    return {"memories": [m.model_dump(mode="json") for m in memories]}


@router.get("/memory/all")
async def get_all_memories(limit: int = 50, offset: int = 0, req: Request = None):  # type: ignore[assignment]
    store = _store(req)
    memories = await store.get_all(limit=limit, offset=offset)
    return {"memories": [m.model_dump(mode="json") for m in memories]}


@router.get("/memory/graph")
async def get_graph(req: Request):
    db = req.app.state.db
    entities = await db.fetch(
        "SELECT id, type, name, metadata FROM entities ORDER BY updated_at DESC LIMIT 100"
    )
    relationships = await db.fetch(
        "SELECT id, source_id, target_id, type, weight FROM relationships "
        "WHERE valid_until IS NULL LIMIT 500"
    )
    def _row(r):
        d = dict(r)
        for k, v in list(d.items()):
            if hasattr(v, "hex"):
                d[k] = str(v)
            if isinstance(v, str) and k == "metadata":
                try:
                    d[k] = json.loads(v)
                except Exception:
                    pass
        return d
    return {
        "entities": [_row(e) for e in entities],
        "relationships": [_row(r) for r in relationships],
    }


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str, req: Request):
    store = _store(req)
    deleted = await store.delete(UUID(memory_id))
    return {"deleted": deleted}
