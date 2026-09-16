"""Filesystem MCP server (in-process).

Scoped to the user's home directory. Any path that resolves outside $HOME is
rejected. Reads are auto-approved (L0). Writes/deletes go through permissions
as L2/L3.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from kira.tools.servers.base import InternalServer, InternalTool


HOME = Path.home().resolve()
MAX_READ_BYTES = 1_000_000
MAX_LIST_ENTRIES = 500
MAX_SEARCH_HITS = 100


def _safe(path: str) -> Path:
    p = (HOME / path if not os.path.isabs(path) else Path(path)).expanduser().resolve()
    try:
        p.relative_to(HOME)
    except ValueError as e:
        raise PermissionError(
            f"Path {p} is outside the sandboxed home directory."
        ) from e
    return p


async def read_file(args: dict) -> Any:
    path = _safe(args["path"])
    if not path.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    if path.stat().st_size > MAX_READ_BYTES:
        raise ValueError(
            f"File too large ({path.stat().st_size} bytes; cap {MAX_READ_BYTES})."
        )
    return {"path": str(path), "content": path.read_text(errors="replace")}


async def write_file(args: dict) -> Any:
    path = _safe(args["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    content = args.get("content", "")
    path.write_text(content)
    return {"path": str(path), "bytes_written": len(content.encode("utf-8"))}


async def list_directory(args: dict) -> Any:
    path = _safe(args.get("path", "."))
    if not path.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    entries = []
    for i, entry in enumerate(sorted(path.iterdir())):
        if i >= MAX_LIST_ENTRIES:
            break
        entries.append(
            {
                "name": entry.name,
                "path": str(entry),
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
            }
        )
    return {"path": str(path), "entries": entries}


async def search_files(args: dict) -> Any:
    root = _safe(args.get("path", "."))
    query = str(args["query"])
    mode = args.get("mode", "name")  # "name" | "content"
    max_hits = min(int(args.get("max_hits", 50)), MAX_SEARCH_HITS)

    hits: list[dict] = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden dirs
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in filenames:
            if len(hits) >= max_hits:
                break
            fpath = Path(dirpath) / fname
            if mode == "name":
                if pattern.search(fname):
                    hits.append({"path": str(fpath), "match": fname})
            elif mode == "content":
                try:
                    if fpath.stat().st_size > MAX_READ_BYTES:
                        continue
                    text = fpath.read_text(errors="ignore")
                except Exception:
                    continue
                m = pattern.search(text)
                if m:
                    start = max(0, m.start() - 40)
                    end = min(len(text), m.end() + 40)
                    hits.append(
                        {"path": str(fpath), "snippet": text[start:end]}
                    )
    return {"query": query, "mode": mode, "hits": hits}


async def delete_file(args: dict) -> Any:
    path = _safe(args["path"])
    if path.is_dir():
        raise IsADirectoryError(f"Refusing to delete directory: {path}")
    if not path.exists():
        return {"path": str(path), "deleted": False}
    path.unlink()
    return {"path": str(path), "deleted": True}


SERVER = InternalServer(
    name="filesystem",
    description="Read, write, list, and search files under the user's home directory.",
    tools=[
        InternalTool(
            name="read_file",
            description="Read the contents of a text file (path relative to $HOME).",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=read_file,
        ),
        InternalTool(
            name="write_file",
            description="Write text to a file, creating parent directories if needed.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            handler=write_file,
        ),
        InternalTool(
            name="list_files",
            description="List the entries of a directory.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            handler=list_directory,
        ),
        InternalTool(
            name="search_files",
            description=(
                "Search files under a directory by name or content. "
                "mode='name' or 'content'."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "query": {"type": "string"},
                    "mode": {"type": "string", "enum": ["name", "content"]},
                    "max_hits": {"type": "integer"},
                },
                "required": ["query"],
            },
            handler=search_files,
        ),
        InternalTool(
            name="delete_file",
            description="Delete a file (never a directory).",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=delete_file,
        ),
    ],
)
