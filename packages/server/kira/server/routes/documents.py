"""Documents API — list, index (file/directory), search, and a progress WS."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel


router = APIRouter(tags=["documents"])


class IndexRequest(BaseModel):
    path: str
    force: bool = False


class SearchRequest(BaseModel):
    query: str
    limit: int = 8
    path: str | None = None


@router.get("/documents")
async def list_documents(req: Request, limit: int = 200):
    store = req.app.state.document_store
    if store is None:
        return {"files": []}
    return {"files": await store.indexed_files(limit=limit)}


@router.post("/documents/index_file")
async def index_file(body: IndexRequest, req: Request):
    indexer = req.app.state.document_indexer
    if indexer is None:
        raise HTTPException(status_code=503, detail="documents subsystem unavailable")
    # Fire and forget for large files — the WS carries progress.
    asyncio.create_task(indexer.index_file(body.path, force=body.force))
    return {"queued": True, "path": body.path}


@router.post("/documents/index_directory")
async def index_directory(body: IndexRequest, req: Request):
    indexer = req.app.state.document_indexer
    if indexer is None:
        raise HTTPException(status_code=503, detail="documents subsystem unavailable")
    asyncio.create_task(indexer.index_directory(body.path, force=body.force))
    return {"queued": True, "path": body.path}


@router.post("/documents/reindex")
async def reindex(body: IndexRequest, req: Request):
    indexer = req.app.state.document_indexer
    if indexer is None:
        raise HTTPException(status_code=503, detail="documents subsystem unavailable")
    return await indexer.reindex(body.path)


@router.post("/documents/search")
async def search_documents(body: SearchRequest, req: Request):
    store = req.app.state.document_store
    if store is None:
        return {"hits": []}
    return {"hits": await store.search(body.query, limit=body.limit, file_path=body.path)}


@router.websocket("/documents/progress")
async def documents_progress(ws: WebSocket):
    from kira.tools.documents.progress import BROKER

    await ws.accept()
    q = await BROKER.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=60.0)
            except asyncio.TimeoutError:
                await ws.send_json({"stage": "heartbeat"})
                continue
            await ws.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        BROKER.unsubscribe(q)
