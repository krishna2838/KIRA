"""Screenshot + vision-based screen analysis.

`take_screenshot` shells out to `screencapture -x -t png -` to grab the
current screen without a shutter sound. Result is base64 PNG.

`analyze_screenshot` sends a screenshot to a caller-supplied vision generate
callable (`async (image_bytes, prompt) -> str`). The computer_server binds
this to Gemini when the cloud tier is available; otherwise the tool returns
{"available": False, ...}.
"""
from __future__ import annotations

import base64
from typing import Awaitable, Callable

from kira.tools.computer.util import is_macos, run


VisionCall = Callable[[bytes, str], Awaitable[str]]

_vision_fn: VisionCall | None = None


def configure_vision(fn: VisionCall | None) -> None:
    global _vision_fn
    _vision_fn = fn


async def take_screenshot() -> dict:
    if not is_macos():
        return {"available": False, "reason": "not macOS"}
    # -x = silent, -t = format, - = stdout
    rc, _, err = await run(["screencapture", "-x", "-t", "png", "/tmp/kira_screen.png"],
                           timeout=5.0)
    if rc != 0:
        return {"available": False, "reason": err.strip() or f"exit {rc}"}
    try:
        with open("/tmp/kira_screen.png", "rb") as f:
            png = f.read()
    except Exception as e:
        return {"available": False, "reason": str(e)}
    return {
        "available": True,
        "image_base64": base64.b64encode(png).decode("ascii"),
        "mime": "image/png",
        "bytes": len(png),
    }


async def analyze_screenshot(question: str) -> dict:
    if _vision_fn is None:
        return {
            "available": False,
            "reason": (
                "no vision model configured — set GEMINI_API_KEY or provide "
                "a local vision-capable Ollama model."
            ),
        }
    shot = await take_screenshot()
    if not shot.get("available"):
        return shot
    png = base64.b64decode(shot["image_base64"])
    try:
        answer = await _vision_fn(png, question)
    except Exception as e:
        return {"available": False, "reason": f"vision call failed: {e}"}
    return {
        "available": True,
        "answer": answer,
        "image_base64": shot["image_base64"],
        "mime": "image/png",
    }
