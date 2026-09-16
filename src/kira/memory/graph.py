"""Knowledge graph: entities + relationships, backed by PostgreSQL + pgvector."""
from __future__ import annotations

import json
from uuid import UUID

from kira.core.types import Entity, EntityType, Relationship


def _vec(embedding: list[float]) -> str:
    """Serialize a vector for pgvector."""
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


class KnowledgeGraph:
    def __init__(self, db, embeddings):
        self.db = db
        self.embeddings = embeddings

    async def add_entity(self, entity: Entity) -> Entity:
        embedding = await self.embeddings.embed(f"{entity.type.value}: {entity.name}")
        await self.db.execute(
            """INSERT INTO entities (id, type, name, metadata, embedding)
               VALUES ($1, $2, $3, $4::jsonb, $5::vector)
               ON CONFLICT (id) DO UPDATE SET
                 name = EXCLUDED.name,
                 metadata = EXCLUDED.metadata,
                 embedding = EXCLUDED.embedding,
                 updated_at = NOW()""",
            entity.id,
            entity.type.value,
            entity.name,
            json.dumps(entity.metadata),
            _vec(embedding),
        )
        return entity

    async def add_relationship(self, rel: Relationship) -> Relationship:
        await self.db.execute(
            """INSERT INTO relationships (id, source_id, target_id, type, weight, metadata)
               VALUES ($1, $2, $3, $4, $5, $6::jsonb)
               ON CONFLICT (source_id, target_id, type) DO UPDATE SET
                 weight = EXCLUDED.weight,
                 metadata = EXCLUDED.metadata""",
            rel.id, rel.source_id, rel.target_id, rel.type, rel.weight,
            json.dumps(rel.metadata),
        )
        return rel

    async def get_entity(self, name: str) -> Entity | None:
        row = await self.db.fetchrow(
            "SELECT id, type, name, metadata, created_at FROM entities WHERE LOWER(name) = LOWER($1)",
            name,
        )
        if not row:
            return None
        d = dict(row)
        d["type"] = EntityType(d["type"])
        if isinstance(d.get("metadata"), str):
            d["metadata"] = json.loads(d["metadata"])
        return Entity(**d)

    async def get_related(self, entity_id: UUID, depth: int = 1) -> list[dict]:
        rows = await self.db.fetch(
            """SELECT e.id, e.type, e.name, r.type as rel_type, r.weight
               FROM relationships r
               JOIN entities e ON (e.id = r.target_id OR e.id = r.source_id)
               WHERE (r.source_id = $1 OR r.target_id = $1)
                 AND e.id != $1
                 AND r.valid_until IS NULL""",
            entity_id,
        )
        return [dict(r) for r in rows]

    async def search_entities(self, query: str, limit: int = 10) -> list[Entity]:
        embedding = await self.embeddings.embed(query)
        rows = await self.db.fetch(
            """SELECT id, type, name, metadata, created_at,
                      embedding <=> $1::vector AS distance
               FROM entities
               ORDER BY distance ASC
               LIMIT $2""",
            _vec(embedding), limit,
        )
        out: list[Entity] = []
        for row in rows:
            d = dict(row)
            d.pop("distance", None)
            d["type"] = EntityType(d["type"])
            if isinstance(d.get("metadata"), str):
                d["metadata"] = json.loads(d["metadata"])
            out.append(Entity(**d))
        return out

    async def build_context_for(self, query: str) -> str:
        try:
            entities = await self.search_entities(query, limit=5)
        except Exception:
            return ""
        if not entities:
            return ""
        parts: list[str] = []
        for entity in entities:
            related = await self.get_related(entity.id)
            relations_str = ", ".join(
                f"{r['rel_type']} {r['name']}" for r in related[:5]
            )
            if relations_str:
                parts.append(f"{entity.name} ({entity.type.value}): {relations_str}")
            else:
                parts.append(f"{entity.name} ({entity.type.value})")
        return "\n".join(parts)
