"""Long-term memory store with semantic search."""
from __future__ import annotations

from uuid import UUID

from kira.core.redaction import redact
from kira.core.types import Memory, MemoryCategory

from kira.memory.graph import _vec


class MemoryStore:
    def __init__(self, db, embeddings):
        self.db = db
        self.embeddings = embeddings

    async def store(self, memory: Memory) -> Memory:
        clean_content = redact(memory.content)
        embedding = await self.embeddings.embed(clean_content)
        await self.db.execute(
            """INSERT INTO memories (id, content, category, importance, embedding,
                                     source_type, source_id, entity_id)
               VALUES ($1, $2, $3, $4, $5::vector, $6, $7, $8)""",
            memory.id, clean_content, memory.category.value, memory.importance,
            _vec(embedding), memory.source_type, memory.source_id, memory.entity_id,
        )
        memory.content = clean_content
        return memory

    async def search(
        self,
        query: str,
        limit: int = 10,
        category: str | None = None,
        min_importance: float = 0.0,
    ) -> list[Memory]:
        embedding = await self.embeddings.embed(query)

        base_query = """
            SELECT id, content, category, importance, source_type, source_id,
                   entity_id, created_at,
                   embedding <=> $1::vector AS distance
            FROM memories
            WHERE importance >= $2
        """
        args: list = [_vec(embedding), min_importance]

        if category:
            base_query += f" AND category = ${len(args) + 1}"
            args.append(category)

        base_query += f" ORDER BY distance ASC LIMIT ${len(args) + 1}"
        args.append(limit)

        rows = await self.db.fetch(base_query, *args)

        for row in rows:
            await self.db.execute(
                "UPDATE memories SET accessed_at = NOW(), access_count = access_count + 1 WHERE id = $1",
                row["id"],
            )

        out: list[Memory] = []
        for row in rows:
            d = dict(row)
            d.pop("distance", None)
            d["category"] = MemoryCategory(d["category"])
            out.append(Memory(**d))
        return out

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[Memory]:
        rows = await self.db.fetch(
            """SELECT id, content, category, importance, source_type, source_id,
                      entity_id, created_at
               FROM memories ORDER BY created_at DESC LIMIT $1 OFFSET $2""",
            limit, offset,
        )
        out: list[Memory] = []
        for row in rows:
            d = dict(row)
            d["category"] = MemoryCategory(d["category"])
            out.append(Memory(**d))
        return out

    async def delete(self, memory_id: UUID) -> bool:
        result = await self.db.execute("DELETE FROM memories WHERE id = $1", memory_id)
        return result == "DELETE 1"
