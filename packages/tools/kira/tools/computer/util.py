"""Shared helpers for the computer control tools."""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Sequence


def is_macos() -> bool:
    return sys.platform == "darwin"


async def run(cmd: Sequence[str], input_text: str | None = None,
              timeout: float = 15.0) -> tuple[int, str, str]:
    """Run a subprocess, return (rc, stdout, stderr) — never raises."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if input_text is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        return 127, "", f"launch failed: {e}"
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(
                input_text.encode("utf-8") if input_text is not None else None
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", "timed out"
    return (
        proc.returncode or 0,
        (stdout or b"").decode("utf-8", errors="replace"),
        (stderr or b"").decode("utf-8", errors="replace"),
    )


async def osascript(script: str, timeout: float = 15.0) -> tuple[int, str, str]:
    """Run AppleScript. Falls back to `not on macOS` on other platforms."""
    if not is_macos():
        return 1, "", "osascript unavailable (not macOS)"
    return await run(["osascript", "-e", script], timeout=timeout)


def expand_path(path: str) -> str:
    return os.path.expanduser(os.path.expandvars(path))
