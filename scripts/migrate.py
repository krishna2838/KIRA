"""Database migrations. Idempotent — safe to run multiple times."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Self-bootstrap: ensure the src-layout `kira` package is importable even
# when this script is run directly (`python scripts/migrate.py`) without
# PYTHONPATH set or the editable-install .pth being honored.
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding vector(768),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_embedding ON entities USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE IF NOT EXISTS relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    target_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    type VARCHAR(100) NOT NULL,
    weight FLOAT DEFAULT 1.0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    valid_until TIMESTAMPTZ,
    UNIQUE(source_id, target_id, type)
);
CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_id);

CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    importance FLOAT DEFAULT 0.5,
    embedding vector(768),
    source_type VARCHAR(50) NOT NULL,
    source_id UUID,
    entity_id UUID REFERENCES entities(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    accessed_at TIMESTAMPTZ DEFAULT NOW(),
    access_count INT DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255),
    summary TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    message_count INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action VARCHAR(100) NOT NULL,
    tool_name VARCHAR(100),
    risk_level INT NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    approved BOOLEAN,
    approved_by VARCHAR(50),
    error TEXT,
    latency_ms INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at DESC);

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_name VARCHAR(100),
    title TEXT,
    body TEXT,
    sender VARCHAR(255),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    read BOOLEAN DEFAULT FALSE,
    importance FLOAT DEFAULT 0.5,
    embedding vector(768)
);
CREATE INDEX IF NOT EXISTS idx_notifications_timestamp ON notifications(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_app ON notifications(app_name);
CREATE INDEX IF NOT EXISTS idx_notifications_sender ON notifications(sender);
CREATE INDEX IF NOT EXISTS idx_notifications_embedding
    ON notifications USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE IF NOT EXISTS deadlines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    due TIMESTAMPTZ NOT NULL,
    notes TEXT,
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_deadlines_due ON deadlines(due);

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path TEXT NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    page_number INT,
    embedding vector(768),
    file_hash VARCHAR(64),
    indexed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(file_path, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_chunks_file ON document_chunks(file_path);
CREATE INDEX IF NOT EXISTS idx_chunks_hash ON document_chunks(file_hash);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    cron_expression VARCHAR(100),
    tool_chain JSONB NOT NULL,
    permissions_required INT DEFAULT 0,
    enabled BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMPTZ,
    last_result TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tasks_enabled ON scheduled_tasks(enabled);
"""


async def run_migrations(db) -> None:
    async with db.pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)


async def _main() -> None:
    from kira.memory.db import get_db
    db = await get_db()
    await run_migrations(db)
    print("Migrations complete.")
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(_main())
