"""Token-streaming chat over WebSocket.

Design: pretty much the POST /api/chat pipeline, but the final response is
generated with Ollama's `stream=true` so we can push tokens to the client
as they arrive. Tool loops, research short-circuit, and confidence pass
are intentionally simpler here — this WS is optimized for the quick
conversational path.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from kira.brain.prompts import KIRA_SYSTEM_PROMPT
from kira.config import get_config
from kira.memory.conversations import ConversationManager
from kira.memory.embeddings import EmbeddingEngine
from kira.memory.graph import KnowledgeGraph
from kira.memory.store import MemoryStore
from kira.prompt_guard import sanitize_user_input
from kira.types import Message, Role


router = APIRouter(tags=["chat"])


@router.websocket("/chat/stream")
async def chat_stream(ws: WebSocket):
    await ws.accept()
    app = ws.app
    config = get_config()

    try:
        while True:
            raw = await ws.receive_text()
            try:
                req = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "error": "bad JSON"})
                continue

            user_text = sanitize_user_input(str(req.get("message", "")))
            if not user_text:
                await ws.send_json({"type": "error", "error": "empty message"})
                continue

            db = app.state.db
            ollama = app.state.ollama
            router_ = app.state.router

            embeddings = EmbeddingEngine(ollama, config.models.embeddings.model)
            memory_store = MemoryStore(db, embeddings)
            knowledge_graph = KnowledgeGraph(db, embeddings)
            conversations = ConversationManager(
                db, ollama, config.models.fast.model,
                summarize_threshold=config.memory.auto_summarize_threshold,
            )

            conv_id = req.get("conversation_id")
            if conv_id is None:
                from uuid import UUID
                conv_id = await conversations.create_conversation()
            else:
                from uuid import UUID
                conv_id = UUID(str(conv_id))

            await conversations.add_message(
                conv_id,
                Message(role=Role.USER, content=user_text, conversation_id=conv_id),
            )
            await ws.send_json({"type": "conversation", "conversation_id": str(conv_id)})

            memories = await memory_store.search(user_text, limit=5)
            memories_text = "\n".join(f"- {m.content}" for m in memories) or "No relevant memories."
            graph_context = await knowledge_graph.build_context_for(user_text) or "No personal context loaded yet."

            system_prompt = KIRA_SYSTEM_PROMPT.format(
                personal_context=graph_context,
                memories=memories_text,
                working_context="Streaming session.",
            )
            recent = await conversations.get_recent_context(conv_id, max_messages=8)
            llm_messages = [{"role": "system", "content": system_prompt}, *recent]

            await ws.send_json({"type": "state", "state": "thinking"})

            # Route to a tier, then stream from ollama for FAST/SMART. Cloud
            # tier falls back to a single-shot response (no incremental push).
            from kira.types import ModelTier
            tier = await router_.route(user_text, {"intent": "conversation"})
            full: list[str] = []

            if tier in (ModelTier.FAST, ModelTier.SMART):
                model_name = (
                    config.models.fast.model if tier == ModelTier.FAST
                    else config.models.smart.model
                )
                try:
                    async with ollama.client.stream(
                        "POST", "/api/chat",
                        json={"model": model_name, "messages": llm_messages, "stream": True},
                    ) as resp:
                        async for line in resp.aiter_lines():
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line)
                            except Exception:
                                continue
                            piece = ((chunk.get("message") or {}).get("content")) or ""
                            if piece:
                                full.append(piece)
                                await ws.send_json({"type": "delta", "text": piece})
                            if chunk.get("done"):
                                break
                except Exception as e:
                    await ws.send_json({"type": "error", "error": f"stream failed: {e}"})
                    continue
            else:
                # Cloud path — single shot.
                text = await router_.generate(tier, llm_messages)
                full.append(text)
                await ws.send_json({"type": "delta", "text": text})

            final_text = "".join(full).strip()

            await conversations.add_message(
                conv_id,
                Message(role=Role.ASSISTANT, content=final_text, conversation_id=conv_id,
                        metadata={"model_tier": tier.value, "streamed": True}),
            )
            await ws.send_json({
                "type": "done",
                "content": final_text,
                "model": tier.value,
                "conversation_id": str(conv_id),
            })
    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "error": str(e)})
        except Exception:
            pass
