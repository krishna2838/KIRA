"""Terminal MCP server (in-process).

Runs a single shell command via /bin/sh, captures stdout/stderr/exit code,
timeouts at 30s. Any command that hits the DANGEROUS_PATTERNS list is flagged
as CRITICAL (L4) so the executor always demands confirmation — this is
enforced by run_command reporting `risk_override` metadata that the caller
can honor. The permission engine treats `terminal.run_command` as L2 by
default; the risk_override field bumps it to L4 when needed.
"""
from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from kira.tools.servers.base import InternalServer, InternalTool


DEFAULT_TIMEOUT_SEC = 30
MAX_OUTPUT_BYTES = 200_000

DANGEROUS_PATTERNS = [
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\bsudo\b", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+.*of=/dev/", re.IGNORECASE),
    re.compile(r":\s*\(\s*\)\s*\{", re.IGNORECASE),  # fork bomb
    re.compile(r">\s*/dev/sd[a-z]", re.IGNORECASE),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\breboot\b", re.IGNORECASE),
]


def classify_command(cmd: str) -> str:
    """Return "critical" or "normal"."""
    for pat in DANGEROUS_PATTERNS:
        if pat.search(cmd):
            return "critical"
    return "normal"


async def run_command(args: dict) -> Any:
    cmd = str(args["command"])
    cwd = args.get("cwd") or os.path.expanduser("~")
    timeout = float(args.get("timeout_sec", DEFAULT_TIMEOUT_SEC))

    danger = classify_command(cmd)

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except Exception as e:
        raise RuntimeError(f"failed to start shell: {e}") from e

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return {
            "command": cmd,
            "cwd": cwd,
            "timed_out": True,
            "timeout_sec": timeout,
            "risk": danger,
        }

    def _truncate(b: bytes) -> str:
        s = b.decode("utf-8", errors="replace")
        if len(s) > MAX_OUTPUT_BYTES:
            return s[:MAX_OUTPUT_BYTES] + "\n…[truncated]"
        return s

    return {
        "command": cmd,
        "cwd": cwd,
        "exit_code": proc.returncode,
        "stdout": _truncate(stdout_b),
        "stderr": _truncate(stderr_b),
        "risk": danger,
    }


SERVER = InternalServer(
    name="terminal",
    description="Execute shell commands and capture their output.",
    tools=[
        InternalTool(
            name="run_command",
            description=(
                "Run a shell command. Captures stdout, stderr, exit code. "
                "Timeout defaults to 30 seconds. Dangerous commands "
                "(rm -rf, sudo, shutdown, etc.) require explicit user confirmation."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeout_sec": {"type": "number"},
                },
                "required": ["command"],
            },
            handler=run_command,
        ),
    ],
)
