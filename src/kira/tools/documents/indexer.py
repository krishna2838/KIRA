"""Parse → chunk → embed → store, with hash-skip and progress events.

Runs on a bounded semaphore so a big directory index doesn't monopolize CPU
(especially for OCR). All embedding is async to overlap I/O.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

from kira.core.logger import get_logger

from kira.tools.documents.chunker import chunk_pages
from kira.tools.documents.parsers import (
    SUPPORTED_EXTENSIONS,
    parse_any,
)
from kira.tools.documents.progress import BROKER
from kira.tools.documents.store import DocumentStore


logger = get_logger("tools.documents.indexer")

DEFAULT_MAX_FILE_MB = 40
DEFAULT_PARALLELISM = 2


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
    except Exception:
        return ""
    return h.hexdigest()


class DocumentIndexer:
    def __init__(
        self,
        store: DocumentStore,
        embeddings,
        *,
        max_file_mb: int = DEFAULT_MAX_FILE_MB,
        parallelism: int = DEFAULT_PARALLELISM,
        chunk_tokens: int = 500,
        overlap_tokens: int = 50,
    ):
        self.store = store
        self.embeddings = embeddings
        self.max_file_bytes = max_file_mb * 1024 * 1024
        self.chunk_tokens = chunk_tokens
        self.overlap_tokens = overlap_tokens
        self._semaphore = asyncio.Semaphore(max(1, parallelism))
        self._indexing: set[str] = set()

    # -- public ------------------------------------------------------

    async def index_file(self, path: str, *, force: bool = False) -> dict:
        p = os.path.expanduser(path)
        if not os.path.isfile(p):
            return {"indexed": False, "error": "not a file"}
        if Path(p).suffix.lower() not in SUPPORTED_EXTENSIONS:
            return {"indexed": False, "error": "unsupported type"}
        try:
            size = os.path.getsize(p)
        except OSError as e:
            return {"indexed": False, "error": str(e)}
        if size > self.max_file_bytes:
            return {"indexed": False, "error": f"too large ({size} bytes)"}

        if p in self._indexing:
            return {"indexed": False, "error": "already indexing"}

        async with self._semaphore:
            self._indexing.add(p)
            try:
                return await self._do_index(p, force=force)
            finally:
                self._indexing.discard(p)

    async def index_directory(
        self,
        root: str,
        *,
        force: bool = False,
        exclude_dirs: tuple[str, ...] = (
            ".git", "node_modules", ".venv", "venv", "__pycache__",
            "dist", "build", ".mypy_cache", ".pytest_cache", ".Trash",
            ".Trashes", "Library", ".DS_Store",
        ),
    ) -> dict:
        root_p = Path(os.path.expanduser(root)).resolve()
        if not root_p.is_dir():
            return {"error": f"not a directory: {root_p}"}
        found: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root_p):
            dirnames[:] = [
                d for d in dirnames
                if d not in exclude_dirs and not d.startswith(".")
            ]
            for name in filenames:
                if name.startswith("."):
                    continue
                if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                found.append(str(Path(dirpath) / name))
        BROKER.publish({
            "stage": "start",
            "message": f"queued {len(found)} files under {root_p}",
            "detail": {"root": str(root_p), "count": len(found)},
        })
        indexed = 0
        skipped = 0
        errors = 0
        for i, path in enumerate(found, start=1):
            result = await self.index_file(path, force=force)
            if result.get("indexed"):
                indexed += 1
            elif result.get("skipped"):
                skipped += 1
            elif result.get("error"):
                errors += 1
            BROKER.publish({
                "stage": "progress",
                "message": f"{i}/{len(found)} {Path(path).name}",
                "detail": {
                    "path": path,
                    "indexed": indexed,
                    "skipped": skipped,
                    "errors": errors,
                    "total": len(found),
                },
            })
        BROKER.publish({
            "stage": "done",
            "message": f"indexed {indexed}, skipped {skipped}, errors {errors}",
            "detail": {"indexed": indexed, "skipped": skipped, "errors": errors},
        })
        return {"indexed": indexed, "skipped": skipped, "errors": errors, "total": len(found)}

    # -- internal ----------------------------------------------------

    async def _do_index(self, path: str, *, force: bool) -> dict:
        file_hash = await asyncio.to_thread(_hash_file, path)
        if not force:
            existing = await self.store.get_file_hash(path)
            if existing == file_hash:
                BROKER.publish({
                    "stage": "skip",
                    "message": f"unchanged: {Path(path).name}",
                    "detail": {"path": path},
                })
                return {"indexed": False, "skipped": True, "reason": "unchanged"}

        BROKER.publish({
            "stage": "parse",
            "message": f"parsing {Path(path).name}",
            "detail": {"path": path},
        })

        parsed = await parse_any(path)
        if "error" in parsed:
            return {"indexed": False, "error": parsed["error"]}

        chunks = chunk_pages(
            parsed.get("pages", []),
            chunk_tokens=self.chunk_tokens,
            overlap_tokens=self.overlap_tokens,
        )
        if not chunks:
            return {"indexed": False, "error": "no text extracted"}

        # Wipe stale chunks (file may have shrunk) then re-insert.
        await self.store.clear_file(path)

        file_name = Path(path).name
        for chunk in chunks:
            try:
                embedding = await self.embeddings.embed(chunk.content)
            except Exception as e:
                logger.debug(f"embed failed for {path} chunk {chunk.index}: {e}")
                embedding = None
            await self.store.upsert_chunk(
                file_path=path,
                file_name=file_name,
                chunk_index=chunk.index,
                content=chunk.content,
                page_number=chunk.page,
                embedding=embedding,
                file_hash=file_hash,
            )

        BROKER.publish({
            "stage": "indexed",
            "message": f"{file_name}: {len(chunks)} chunks",
            "detail": {"path": path, "chunks": len(chunks)},
        })
        return {"indexed": True, "chunks": len(chunks)}

    async def reindex(self, path: str) -> dict:
        return await self.index_file(path, force=True)
