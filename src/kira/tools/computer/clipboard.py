"""Clipboard read/write via pbpaste / pbcopy."""
from __future__ import annotations

from kira.tools.computer.util import is_macos, run


async def get_clipboard() -> dict:
    if not is_macos():
        return {"available": False, "text": None}
    rc, out, _ = await run(["pbpaste"], timeout=3.0)
    if rc != 0:
        return {"available": False, "text": None}
    return {"available": True, "text": out}


async def set_clipboard(text: str) -> dict:
    if not is_macos():
        return {"set": False, "error": "not macOS"}
    rc, _, err = await run(["pbcopy"], input_text=text, timeout=3.0)
    if rc != 0:
        return {"set": False, "error": err.strip() or f"exit {rc}"}
    return {"set": True, "bytes": len(text.encode("utf-8"))}
