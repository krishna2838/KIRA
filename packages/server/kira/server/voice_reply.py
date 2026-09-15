"""Bridge between the voice pipeline and the chat brain.

The voice pipeline calls `reply(user_text)` and expects a single assistant
string back. We reuse the memory + brain infrastructure but skip the
tool-loop for the first cut so latency stays low. (Adding tools to the
voice path is a Phase 4 concern.)
"""
from __future__ import annotations

from fastapi import FastAPI

from kira.brain.prompts import KIRA_SYSTEM_PROMPT
from kira.config import get_config
from kira.memory.context import WorkingContext
from kira.memory.conversations import ConversationManager
from kira.memory.embeddings import EmbeddingEngine
from kira.memory.graph import KnowledgeGraph
from kira.memory.store import MemoryStore
from kira.types import Message, Role


# Persistent working context for the voice session — one across all turns.
_voice_ctx = WorkingContext()
_voice_conv_id = None


def make_voice_reply(app: FastAPI):
    async def voice_reply(user_text: str) -> str:
        global _voice_conv_id

        db = app.state.db
        ollama = app.state.ollama
        model_router = app.state.router
        config = get_config()

        embeddings = EmbeddingEngine(ollama, config.models.embeddings.model)
        memory_store = MemoryStore(db, embeddings)
        knowledge_graph = KnowledgeGraph(db, embeddings)
        conversations = ConversationManager(
            db, ollama, config.models.fast.model,
            summarize_threshold=config.memory.auto_summarize_threshold,
        )

        if _voice_conv_id is None:
            _voice_conv_id = await conversations.create_conversation()

        await conversations.add_message(
            _voice_conv_id,
            Message(role=Role.USER, content=user_text, conversation_id=_voice_conv_id),
        )

        # Retrieve relevant memories
        memories = await memory_store.search(user_text, limit=4)
        memories_text = (
            "\n".join(f"- {m.content}" for m in memories) or "No relevant memories."
        )
        graph_context = await knowledge_graph.build_context_for(user_text)

        base_prompt = KIRA_SYSTEM_PROMPT.format(
            personal_context=graph_context or "No personal context loaded yet.",
            memories=memories_text,
            working_context=_voice_ctx.to_string(),
        )
        voice_addendum = (
            "\n\nVOICE MODE:\n"
            "You are speaking out loud. Reply in 1–2 short sentences by default. "
            "No lists, no code fences, no URLs. If greeted by name only, "
            "answer briefly, e.g. 'Yes?' or 'What's up?'. Prefer contractions "
            "and a conversational register."
        )
        system_prompt = base_prompt + voice_addendum

        recent = await conversations.get_recent_context(_voice_conv_id, max_messages=8)
        llm_messages = [{"role": "system", "content": system_prompt}, *recent]

        # Route based on complexity; voice defaults to smart tier for
        # nuance but simple utterances still fast-path.
        tier = await model_router.route(user_text, {"intent": "conversation"})
        reply_text = await model_router.generate(tier, llm_messages)
        reply_text = reply_text.strip()

        await conversations.add_message(
            _voice_conv_id,
            Message(
                role=Role.ASSISTANT,
                content=reply_text,
                conversation_id=_voice_conv_id,
                metadata={"model_tier": tier.value, "mode": "voice"},
            ),
        )
        return reply_text

    return voice_reply
