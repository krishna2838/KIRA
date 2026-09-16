"""Voice API — status, settings, WebSocket stream."""
from __future__ import annotations

import asyncio
import base64
import json

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel


router = APIRouter(tags=["voice"])


class VoiceSettings(BaseModel):
    wake_word_enabled: bool | None = None


@router.get("/voice/status")
async def status(req: Request):
    pipeline = req.app.state.voice_pipeline
    if pipeline is None:
        return {"available": False, "reason": "voice pipeline not initialized"}
    return {"available": True, **pipeline.snapshot()}


@router.get("/voice/devices")
async def devices():
    from kira.voice.audio import list_devices
    return list_devices()


@router.post("/voice/settings")
async def update_settings(body: VoiceSettings, req: Request):
    pipeline = req.app.state.voice_pipeline
    if pipeline is None:
        return {"ok": False, "reason": "voice unavailable"}
    if body.wake_word_enabled is not None:
        pipeline.set_wake_word_enabled(body.wake_word_enabled)
    return {"ok": True, **pipeline.snapshot()}


@router.post("/voice/start")
async def start(req: Request):
    pipeline = req.app.state.voice_pipeline
    if pipeline is None:
        return {"ok": False, "reason": "voice unavailable"}
    await pipeline.start()
    return {"ok": True, **pipeline.snapshot()}


@router.post("/voice/stop")
async def stop(req: Request):
    pipeline = req.app.state.voice_pipeline
    if pipeline is None:
        return {"ok": False, "reason": "voice unavailable"}
    await pipeline.stop()
    return {"ok": True, **pipeline.snapshot()}


@router.websocket("/voice/stream")
async def voice_stream(ws: WebSocket):
    """Streaming channel between browser and server.

    Server → client messages (JSON):
      { "type": "state",       "state": "listening" }
      { "type": "transcript",  "text": "..." }
      { "type": "response",    "text": "..." }
      { "type": "audio",       "data": "<base64 pcm16>" }  # optional

    Client → server messages (JSON):
      { "type": "audio",       "data": "<base64 pcm16>", "sample_rate": 16000 }
      { "type": "text",        "text": "..." }             # push-to-talk transcript
      { "type": "stop" }                                   # interrupt TTS
    """
    await ws.accept()
    app = ws.app
    pipeline = app.state.voice_pipeline

    if pipeline is None:
        await ws.send_json({"type": "error", "reason": "voice pipeline unavailable"})
        await ws.close()
        return

    loop = asyncio.get_running_loop()

    def _forward(snapshot: dict) -> None:
        # Called from the pipeline's thread — hop back to the event loop.
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send_json({"type": "state", **snapshot}), loop
            )
        except Exception:
            pass

    pipeline.add_listener(_forward)

    try:
        # Push initial state
        await ws.send_json({"type": "state", **pipeline.snapshot()})
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            mtype = msg.get("type")
            if mtype == "stop":
                pipeline.tts.interrupt()
            elif mtype == "text":
                text = str(msg.get("text", "")).strip()
                if text:
                    # Manual push-to-talk: run through _handle_utterance-style
                    # path via the reply function directly.
                    reply = await pipeline.reply(text)
                    await ws.send_json({"type": "response", "text": reply})
            elif mtype == "audio":
                # Reserved for future client-captured audio streaming.
                _ = base64.b64decode(msg.get("data", ""))
                # Not fed into the pipeline here — server-side mic is the
                # authoritative capture path in Phase 3. Client audio will
                # land here in a later phase.
            else:
                continue
    except WebSocketDisconnect:
        pass
    finally:
        pipeline.remove_listener(_forward)
