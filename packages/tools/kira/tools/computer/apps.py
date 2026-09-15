"""App control via AppleScript / `open` / `osascript`."""
from __future__ import annotations

from kira.tools.computer.util import osascript, run


async def list_running_apps() -> list[dict]:
    rc, out, _ = await osascript(
        'tell application "System Events" to get name of (every process whose background only is false)'
    )
    if rc != 0:
        return []
    names = [n.strip() for n in out.strip().split(",") if n.strip()]
    return [{"name": n} for n in names]


async def open_app(name: str) -> dict:
    rc, out, err = await run(["open", "-a", name])
    if rc == 0:
        return {"opened": name}
    return {"opened": None, "error": err.strip() or f"exit {rc}"}


async def close_app(name: str) -> dict:
    rc, _, err = await osascript(f'tell application "{name}" to quit')
    if rc == 0:
        return {"closed": name}
    return {"closed": None, "error": err.strip() or f"exit {rc}"}


async def switch_to_app(name: str) -> dict:
    rc, _, err = await osascript(f'tell application "{name}" to activate')
    if rc == 0:
        return {"activated": name}
    return {"activated": None, "error": err.strip() or f"exit {rc}"}


async def window_titles(app: str) -> list[str]:
    """List window titles of a given app."""
    rc, out, _ = await osascript(
        f'tell application "System Events" to tell process "{app}" '
        f'to get name of every window'
    )
    if rc != 0:
        return []
    return [w.strip() for w in out.strip().split(",") if w.strip()]
