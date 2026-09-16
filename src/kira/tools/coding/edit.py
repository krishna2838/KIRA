"""Code editing operations. Every mutation returns a unified diff so the
frontend can show a preview before the user approves.

`edit_file` uses find-and-replace with a uniqueness guard: if `old_text`
does not occur exactly once we refuse to apply. This mirrors how modern
coding agents like Claude Code stay safe.

`create_file` refuses to overwrite an existing file unless `overwrite=true`.
"""
from __future__ import annotations

import asyncio
import difflib
import os
from pathlib import Path


def _unified(old: str, new: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
        )
    )


async def edit_file(path: str, old_text: str, new_text: str,
                    replace_all: bool = False) -> dict:
    p = Path(os.path.expanduser(path)).resolve()

    def _do():
        if not p.is_file():
            return {"applied": False, "error": f"not a file: {p}"}
        original = p.read_text()
        if old_text not in original:
            return {"applied": False, "error": "old_text not found"}
        count = original.count(old_text)
        if count > 1 and not replace_all:
            return {
                "applied": False,
                "error": f"old_text occurs {count} times; pass replace_all=true "
                         "or provide more surrounding context to make it unique",
            }
        updated = original.replace(old_text, new_text, -1 if replace_all else 1)
        diff_text = _unified(original, updated, str(p))
        p.write_text(updated)
        return {
            "applied": True,
            "path": str(p),
            "diff": diff_text,
            "occurrences": count if replace_all else 1,
        }

    return await asyncio.to_thread(_do)


async def create_file(path: str, content: str, overwrite: bool = False) -> dict:
    p = Path(os.path.expanduser(path)).resolve()

    def _do():
        if p.exists() and not overwrite:
            return {"created": False, "error": "file exists (pass overwrite=true to replace)"}
        p.parent.mkdir(parents=True, exist_ok=True)
        prior = p.read_text() if p.exists() else ""
        p.write_text(content)
        diff_text = _unified(prior, content, str(p))
        return {"created": True, "path": str(p), "diff": diff_text, "bytes": len(content.encode("utf-8"))}

    return await asyncio.to_thread(_do)


async def preview_edit(path: str, old_text: str, new_text: str) -> dict:
    """Compute the diff WITHOUT applying — used by planner/agent for dry-runs."""
    p = Path(os.path.expanduser(path)).resolve()

    def _do():
        if not p.is_file():
            return {"error": f"not a file: {p}"}
        original = p.read_text()
        if old_text not in original:
            return {"error": "old_text not found"}
        updated = original.replace(old_text, new_text, 1)
        return {"path": str(p), "diff": _unified(original, updated, str(p))}

    return await asyncio.to_thread(_do)
