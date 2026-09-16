"""Database connection pool."""
from __future__ import annotations

import asyncpg

from kira.core.config import get_config
from kira.core.logger import get_logger


logger = get_logger("memory.db")


class Database:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        config = get_config()
        self.pool = await asyncpg.create_pool(
            host=config.database.postgres.host,
            port=config.database.postgres.port,
            database=config.database.postgres.database,
            user=config.database.postgres.user,
            password=config.database.postgres.password,
            min_size=2,
            max_size=10,
        )
        logger.info("Connected to PostgreSQL")

    async def disconnect(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:  # type: ignore[union-attr]
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        async with self.pool.acquire() as conn:  # type: ignore[union-attr]
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self.pool.acquire() as conn:  # type: ignore[union-attr]
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        async with self.pool.acquire() as conn:  # type: ignore[union-attr]
            return await conn.fetchval(query, *args)


_db = Database()


async def get_db() -> Database:
    if _db.pool is None:
        await _db.connect()
    return _db
