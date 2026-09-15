"""Conversation history + auto-summarization."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from kira.types import Message, Role


class ConversationManager:
    def __init__(self, db, ollama_client, model: str, summarize_threshold: int = 20):
        self.db = db
        self.ollama = ollama_client
        self.model = model
        self.summarize_threshold = summarize_threshold

    async def create_conversation(self) -> UUID:
        conv_id = uuid4()
        await self.db.execute("INSERT INTO conversations (id) VALUES ($1)", conv_id)
        return conv_id

    async def add_message(self, conversation_id: UUID, message: Message) -> Message:
        await self.db.execute(
            """INSERT INTO messages (id, conversation_id, role, content, metadata)
               VALUES ($1, $2, $3, $4, $5::jsonb)""",
            message.id, conversation_id, message.role.value,
            message.content, json.dumps(message.metadata),
        )
        await self.db.execute(
            "UPDATE conversations SET message_count = message_count + 1 WHERE id = $1",
            conversation_id,
        )

        count = await self.db.fetchval(
            "SELECT message_count FROM conversations WHERE id = $1", conversation_id
        )
        if count and count >= self.summarize_threshold and count % self.summarize_threshold == 0:
            try:
                await self._auto_summarize(conversation_id)
            except Exception:
                pass
        return message

    async def get_messages(self, conversation_id: UUID, limit: int = 50) -> list[Message]:
        rows = await self.db.fetch(
            """SELECT id, conversation_id, role, content, metadata, created_at
               FROM messages WHERE conversation_id = $1
               ORDER BY created_at ASC LIMIT $2""",
            conversation_id, limit,
        )
        out: list[Message] = []
        for row in rows:
            d = dict(row)
            d["role"] = Role(d["role"])
            if isinstance(d.get("metadata"), str):
                d["metadata"] = json.loads(d["metadata"])
            out.append(Message(**d))
        return out

    async def get_recent_context(self, conversation_id: UUID, max_messages: int = 10) -> list[dict]:
        messages = await self.get_messages(conversation_id, limit=max_messages)
        return [{"role": m.role.value, "content": m.content} for m in messages]

    async def _auto_summarize(self, conversation_id: UUID) -> None:
        messages = await self.get_messages(conversation_id, limit=100)
        conversation_text = "\n".join(f"{m.role.value}: {m.content}" for m in messages)

        from kira.brain.prompts import SUMMARIZATION_PROMPT
        summary = await self.ollama.generate(
            model=self.model,
            prompt=SUMMARIZATION_PROMPT.format(conversation=conversation_text),
            options={"temperature": 0.3},
        )
        await self.db.execute(
            "UPDATE conversations SET summary = $1 WHERE id = $2",
            summary.strip(), conversation_id,
        )
