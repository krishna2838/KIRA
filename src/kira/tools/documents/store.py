"""Persistence for document chunks."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _vec(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


class DocumentStore:
    def __init__(self, db, embeddings):
        self.db = db
        self.embeddings = embeddings

    async def upsert_chunk(
        self,
        *,
        file_path: str,
        file_name: str,
        chunk_index: int,
        content: str,
        page_number: int | None,
        embedding: list[float] | None,
        file_hash: str,
    ) -> None:
        await self.db.execute(
            """INSERT INTO document_chunks
               (file_path, file_name, chunk_index, content, page_number, embedding, file_hash)
               VALUES ($1, $2, $3, $4, $5, $6::vector, $7)
               ON CONFLICT (file_path, chunk_index) DO UPDATE SET
                 content = EXCLUDED.content,
                 page_number = EXCLUDED.page_number,
                 embedding = EXCLUDED.embedding,
                 file_hash = EXCLUDED.file_hash,
                 indexed_at = NOW()""",
            file_path, file_name, chunk_index, content, page_number,
            _vec(embedding) if embedding else None, file_hash,
        )

    async def clear_file(self, file_path: str) -> int:
        result = await self.db.execute(
            "DELETE FROM document_chunks WHERE file_path = $1", file_path
        )
        try:
            return int(str(result).split()[-1])
        except Exception:
            return 0

    async def get_file_hash(self, file_path: str) -> str | None:
        return await self.db.fetchval(
            "SELECT file_hash FROM document_chunks WHERE file_path = $1 LIMIT 1",
            file_path,
        )

    async def indexed_files(self, limit: int = 200) -> list[dict]:
        rows = await self.db.fetch(
            """SELECT file_path, file_name, MAX(indexed_at) AS indexed_at,
                      COUNT(*) AS chunks
               FROM document_chunks
               GROUP BY file_path, file_name
               ORDER BY indexed_at DESC
               LIMIT $1""",
            limit,
        )
        return [
            {
                "file_path": r["file_path"],
                "file_name": r["file_name"],
                "indexed_at": r["indexed_at"].isoformat() if r["indexed_at"] else None,
                "chunks": r["chunks"],
            }
            for r in rows
        ]

    async def search(
        self, query: str, limit: int = 8, file_path: str | None = None
    ) -> list[dict]:
        try:
            emb = await self.embeddings.embed(query)
        except Exception:
            return []
        sql = """
            SELECT id, file_path, file_name, chunk_index, page_number,
                   content, indexed_at,
                   embedding <=> $1::vector AS distance
            FROM document_chunks
            WHERE embedding IS NOT NULL
        """
        args: list[Any] = [_vec(emb)]
        if file_path:
            sql += f" AND file_path = ${len(args) + 1}"
            args.append(file_path)
        sql += f" ORDER BY distance ASC LIMIT ${len(args) + 1}"
        args.append(limit)
        rows = await self.db.fetch(sql, *args)
        return [
            {
                "id": str(r["id"]),
                "file_path": r["file_path"],
                "file_name": r["file_name"],
                "chunk_index": r["chunk_index"],
                "page_number": r["page_number"],
                "content": r["content"],
                "score": 1.0 - float(r["distance"]),
                "indexed_at": r["indexed_at"].isoformat() if r["indexed_at"] else None,
            }
            for r in rows
        ]

    async def chunks_for(self, file_path: str) -> list[dict]:
        rows = await self.db.fetch(
            """SELECT chunk_index, page_number, content
               FROM document_chunks
               WHERE file_path = $1
               ORDER BY chunk_index""",
            file_path,
        )
        return [
            {"chunk_index": r["chunk_index"],
             "page_number": r["page_number"],
             "content": r["content"]}
            for r in rows
        ]
