"""Build/test running + error extraction."""
from __future__ import annotations

import asyncio
import os
import re
from typing import Awaitable, Callable


DEFAULT_TIMEOUT_SEC = 300
MAX_OUTPUT_BYTES = 200_000


async def run_command(path: str, command: str,
                      timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> dict:
    cwd = os.path.expanduser(path)
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_sec
        )
    except asyncio.TimeoutError:
        proc.kill()
        return {"command": command, "cwd": cwd, "timed_out": True}

    def _decode(b: bytes) -> str:
        s = b.decode("utf-8", errors="replace")
        if len(s) > MAX_OUTPUT_BYTES:
            return s[:MAX_OUTPUT_BYTES] + "\n…[truncated]"
        return s

    return {
        "command": command,
        "cwd": cwd,
        "exit_code": proc.returncode,
        "stdout": _decode(stdout_b),
        "stderr": _decode(stderr_b),
    }


# ---- error parsing ------------------------------------------------------


# Generic patterns for common toolchains.
_PATTERNS = [
    # path:line:col: error/warning
    re.compile(r"^(?P<file>[^:\s]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<level>error|warning|note):\s*(?P<msg>.+)$",
               re.MULTILINE | re.IGNORECASE),
    # path:line:col - message
    re.compile(r"^(?P<file>[^:\s]+):(?P<line>\d+):(?P<col>\d+)\s*[-–]\s*(?P<msg>.+)$",
               re.MULTILINE),
    # Python traceback: File "x", line N
    re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)'),
    # Rust: --> path:line:col
    re.compile(r"-->\s*(?P<file>[^:\s]+):(?P<line>\d+):(?P<col>\d+)"),
]


def parse_build_errors(output: str) -> list[dict]:
    hits: list[dict] = []
    seen: set[tuple] = set()
    for pat in _PATTERNS:
        for m in pat.finditer(output):
            key = (m.group("file"), m.group("line"))
            if key in seen:
                continue
            seen.add(key)
            hits.append({
                "file": m.group("file"),
                "line": int(m.group("line")),
                "col": int(m.groupdict().get("col") or 0) if m.groupdict().get("col") else None,
                "level": (m.groupdict().get("level") or "error").lower(),
                "message": (m.groupdict().get("msg") or "").strip(),
            })
    return hits[:50]


EXPLAIN_BUILD_PROMPT = """These build/test errors just fired. Give me:
1. The root cause in 1-2 lines.
2. The fix in 1-2 concrete steps.
No filler.

Errors:
{errors}
"""


async def explain_build_output(output: str,
                               generate: Callable[[str], Awaitable[str]] | None) -> dict:
    errors = parse_build_errors(output)
    if not errors and not output.strip():
        return {"errors": [], "explanation": "No output."}
    text = None
    if generate is not None:
        try:
            # Feed the first ~2k chars of raw output plus parsed errors so the
            # LLM has both structure and context.
            payload = ""
            if errors:
                payload = "\n".join(
                    f"{e['file']}:{e['line']} — {e['message']}" for e in errors[:15]
                )
            payload += "\n\n---RAW OUTPUT (truncated)---\n" + output[:2000]
            text = (await generate(EXPLAIN_BUILD_PROMPT.format(errors=payload))).strip()
        except Exception as e:
            text = f"analysis failed: {e}"
    return {"errors": errors, "explanation": text}
