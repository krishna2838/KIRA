"""File ops: open, reveal, move/copy, trash, Spotlight search."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from kira.tools.computer.util import expand_path, is_macos, osascript, run


async def open_file(path: str) -> dict:
    p = expand_path(path)
    rc, _, err = await run(["open", p])
    if rc == 0:
        return {"opened": p}
    return {"opened": None, "error": err.strip() or f"exit {rc}"}


async def reveal_in_finder(path: str) -> dict:
    p = expand_path(path)
    rc, _, err = await run(["open", "-R", p])
    if rc == 0:
        return {"revealed": p}
    return {"revealed": None, "error": err.strip() or f"exit {rc}"}


async def move_file(src: str, dst: str) -> dict:
    src_p = expand_path(src)
    dst_p = expand_path(dst)
    try:
        shutil.move(src_p, dst_p)
    except Exception as e:
        return {"moved": False, "error": str(e)}
    return {"moved": True, "src": src_p, "dst": dst_p}


async def copy_file(src: str, dst: str) -> dict:
    src_p = expand_path(src)
    dst_p = expand_path(dst)
    try:
        if os.path.isdir(src_p):
            shutil.copytree(src_p, dst_p)
        else:
            shutil.copy2(src_p, dst_p)
    except Exception as e:
        return {"copied": False, "error": str(e)}
    return {"copied": True, "src": src_p, "dst": dst_p}


async def trash_file(path: str) -> dict:
    """Move to macOS Trash via Finder (recoverable)."""
    p = expand_path(path)
    if not os.path.exists(p):
        return {"trashed": False, "error": "does not exist"}
    if not is_macos():
        # Fallback: unlink (not recoverable). Callers should escalate risk.
        try:
            os.remove(p)
            return {"trashed": True, "path": p, "recoverable": False}
        except Exception as e:
            return {"trashed": False, "error": str(e)}
    rc, _, err = await osascript(
        f'tell application "Finder" to delete POSIX file "{p}"'
    )
    if rc == 0:
        return {"trashed": True, "path": p, "recoverable": True}
    return {"trashed": False, "error": err.strip() or f"exit {rc}"}


async def permanent_delete(path: str) -> dict:
    """Really-delete. Callers must gate this at L4."""
    p = expand_path(path)
    try:
        if os.path.isdir(p):
            shutil.rmtree(p)
        else:
            os.remove(p)
    except FileNotFoundError:
        return {"deleted": False, "error": "not found"}
    except Exception as e:
        return {"deleted": False, "error": str(e)}
    return {"deleted": True, "path": p}


async def search_files(query: str, directory: str | None = None,
                       max_results: int = 20) -> dict:
    """Use mdfind (Spotlight CLI) on macOS."""
    if not is_macos():
        # Portable fallback: recursive glob over `directory`
        root = Path(expand_path(directory or "~"))
        hits: list[str] = []
        try:
            for p in root.rglob(f"*{query}*"):
                hits.append(str(p))
                if len(hits) >= max_results:
                    break
        except Exception:
            pass
        return {"query": query, "results": hits}

    cmd = ["mdfind"]
    if directory:
        cmd.extend(["-onlyin", expand_path(directory)])
    cmd.append(query)
    rc, out, _ = await run(cmd, timeout=10.0)
    if rc != 0:
        return {"query": query, "results": []}
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return {"query": query, "results": lines[:max_results]}
