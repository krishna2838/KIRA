"""Research API — WebSocket progress stream + result fetch."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from kira.tools.research.progress import BROKER


router = APIRouter(tags=["research"])


@router.websocket("/research/stream/{research_id}")
async def research_stream(ws: WebSocket, research_id: str):
    await ws.accept()
    q = await BROKER.subscribe(research_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=90.0)
            except asyncio.TimeoutError:
                # Keep-alive: let the client know we're still here.
                await ws.send_json({"stage": "waiting", "message": "waiting for progress"})
                continue
            await ws.send_json(event)
            if event.get("stage") == "done":
                break
    except WebSocketDisconnect:
        pass
    finally:
        await BROKER.unsubscribe(research_id, q)
