"""Redis-backed cache for hot memory searches.

Keyed by SHA-256(query + limit + category). Values are serialized Memory
JSON with a short TTL — memory contents change rarely, but we want quick
invalidation.
"""
from __future__ import annotations

import hashlib
import json


DEFAULT_TTL_SEC = 60


class MemoryCache:
    def __init__(self, redis_client=None, ttl_sec: int = DEFAULT_TTL_SEC):
        self.redis = redis_client
        self.ttl_sec = ttl_sec

    def _key(self, query: str, limit: int, category: str | None) -> str:
        h = hashlib.sha256(f"{query}|{limit}|{category or ''}".encode("utf-8")).hexdigest()[:20]
        return f"kira:memcache:{h}"

    async def get(self, query: str, limit: int, category: str | None = None) -> list | None:
        if self.redis is None:
            return None
        try:
            raw = await self.redis.get(self._key(query, limit, category))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            return None

    async def put(self, query: str, limit: int, category: str | None,
                  memories: list) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.set(
                self._key(query, limit, category),
                json.dumps(memories, default=str),
                ex=self.ttl_sec,
            )
        except Exception:
            pass
