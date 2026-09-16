"""Chat endpoint. Ties brain + memory + tools together.

Tool loop:
  1. Classify intent. If "command" (or the assistant emits a tool call anyway),
     pull the top-k relevant tools from the ToolRouter.
  2. Give the model a compact JSON tool-use contract. It may reply with a
     single tool_call JSON block; we parse, dispatch, feed the result back,
     and iterate up to MAX_TOOL_STEPS times.
  3. If the executor asks for confirmation, we stop the loop and return the
     ConfirmationRequest to the client, embedded in the assistant message
     metadata. The client approves via POST /api/tools/confirm/<id>.
"""
from __future__ import annotations

import json as json_module
import re
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request

from kira.brain.intent import IntentClassifier
from kira.brain.prompts import (
    KIRA_SYSTEM_PROMPT,
    MEMORY_EXTRACTION_PROMPT,
    render_system_prompt,
)
from kira.core.config import get_config
from kira.core.prompt_guard import sanitize_user_input, wrap_tool_output
from kira.memory.context import WorkingContext
from kira.memory.conversations import ConversationManager
from kira.memory.embeddings import EmbeddingEngine
from kira.memory.graph import KnowledgeGraph
from kira.memory.store import MemoryStore
from kira.core.types import (
    ChatRequest,
    ChatResponse,
    Entity,
    EntityType,
    KiraState,
    Memory,
    MemoryCategory,
    Message,
    Role,
)


router = APIRouter(tags=["chat"])

_contexts: dict[str, WorkingContext] = {}

MAX_TOOL_STEPS = 4
TOOL_INTENTS = {"command"}

_TOOL_INSTRUCTIONS = """You have access to the following tools. To use one,
respond with a single JSON object on its own line, in this exact shape:

  {{"tool_call": {{"name": "<qualified.tool.name>", "arguments": {{...}}}}}}

You will receive the tool's result in the next message and can then either
call another tool or reply with plain text as the final answer. Only emit a
tool_call when a tool is needed; otherwise reply in normal prose.

Tools:
{tool_list}
"""


def _tool_line(spec) -> str:
    schema_props = (spec.input_schema or {}).get("properties", {})
    params = ", ".join(schema_props.keys())
    return f"- {spec.qualified_name}({params}) — {spec.description}"


_TOOL_CALL_RE = re.compile(r"\{[\s\S]*?\"tool_call\"[\s\S]*\}")


def _extract_tool_call(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    match = _TOOL_CALL_RE.search(text)
    if not match:
        return None
    try:
        obj = json_module.loads(match.group(0))
    except json_module.JSONDecodeError:
        return None
    call = obj.get("tool_call") if isinstance(obj, dict) else None
    if not isinstance(call, dict):
        return None
    if "name" not in call:
        return None
    call.setdefault("arguments", {})
    return call


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request):
    start = time.time()

    db = req.app.state.db
    # Degraded mode: no database → no memory/persistence. Answer plainly so
    # the UI still works instead of returning a 500.
    if db is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Database unavailable — KIRA is in degraded mode. Start Postgres (docker compose up -d) and retry.",
        )

    ollama = req.app.state.ollama
    model_router = req.app.state.router
    tool_router = req.app.state.tool_router
    tool_executor = req.app.state.tool_executor
    config = get_config()

    embeddings = EmbeddingEngine(ollama, config.models.embeddings.model)
    memory_store = MemoryStore(db, embeddings)
    knowledge_graph = KnowledgeGraph(db, embeddings)
    conversations = ConversationManager(
        db, ollama, config.models.fast.model,
        summarize_threshold=config.memory.auto_summarize_threshold,
    )
    intent_classifier = IntentClassifier(ollama, config.models.fast.model)

    # Sanitize inbound content (control chars, hard length cap).
    request.message = sanitize_user_input(request.message)

    conv_id = request.conversation_id
    if not conv_id:
        conv_id = await conversations.create_conversation()

    session_key = str(conv_id)
    ctx = _contexts.setdefault(session_key, WorkingContext())
    ctx.current_conversation_id = conv_id

    user_msg = Message(role=Role.USER, content=request.message, conversation_id=conv_id)
    await conversations.add_message(conv_id, user_msg)

    # Let the proactive layer know the user is engaged. The monitor pauses
    # pushing events; the engine holds any non-critical batches.
    monitor = getattr(req.app.state, "monitor", None)
    if monitor is not None:
        monitor.set_active(True)
    engine = getattr(req.app.state, "proactive_engine", None)
    if engine is not None:
        engine.set_active(True)

    intent = await intent_classifier.classify(request.message)

    # ---- Research short-circuit ----
    research_mode = _resolve_research_mode(request.message, request.research_mode)
    if research_mode != "off":
        return await _run_research_turn(
            request=request,
            conv_id=conv_id,
            mode=research_mode,
            conversations=conversations,
            memory_store=memory_store,
            intent=intent,
            start=start,
        )

    tier = await model_router.route(
        request.message,
        {"intent": intent, "has_context": bool(ctx.current_topic)},
    )
    preloader = getattr(req.app.state, "preloader", None)
    if preloader is not None and tier.value in ("smart", "cloud"):
        # Non-blocking — pages the smart model in for the next turn if
        # this turn happens to fall back to cloud.
        await preloader.ensure_smart()

    memories = await memory_store.search(request.message, limit=5)

    # Fold in document chunks only when the query is actually about the
    # user's files/notes, or it's an informational ask. Greetings and small
    # talk must NOT drag in random indexed code — and even then we keep only
    # strongly-relevant chunks so a weak match can't pollute the answer.
    doc_hits: list[dict] = []
    doc_store = getattr(req.app.state, "document_store", None)
    should_pull_docs = doc_store is not None and (
        _looks_docish(request.message)
        or intent in ("question", "memory_query")
    )
    if should_pull_docs:
        try:
            raw_hits = await doc_store.search(request.message, limit=5)
            doc_hits = [h for h in raw_hits if h.get("score", 0.0) >= 0.6]
        except Exception:
            doc_hits = []

    memories_text = "\n".join(f"- {m.content}" for m in memories)
    if doc_hits:
        cite_lines = [
            f"[doc {i + 1}] {h['file_name']}"
            + (f" p.{h['page_number']}" if h.get("page_number") else "")
            + f": {h['content'][:600]}"
            for i, h in enumerate(doc_hits)
        ]
        memories_text = (
            (memories_text + "\n\n" if memories_text else "")
            + wrap_tool_output(
                "documents.excerpts",
                "Excerpts from your documents (cite as [doc N]):\n" + "\n".join(cite_lines),
            )
        )
    if not memories_text:
        memories_text = "No relevant memories."
    graph_context = await knowledge_graph.build_context_for(request.message)

    system_prompt = render_system_prompt(
        personal_context=graph_context or "No personal context loaded yet.",
        memories=memories_text,
        working_context=ctx.to_string(),
        voice_mode=False,
        personality=config.personality.model_dump() if getattr(config, "personality", None) else None,
    )

    # Only expose tools when intent looks like a command (or when the router
    # is available and the user's message clearly asks for external state).
    relevant_tools: list = []
    if tool_router is not None and (intent in TOOL_INTENTS or _looks_toolish(request.message)):
        try:
            hits = await tool_router.relevant_tools(request.message)
            relevant_tools = [spec for spec, _score in hits]
        except Exception:
            relevant_tools = []

    if relevant_tools:
        tool_block = _TOOL_INSTRUCTIONS.format(
            tool_list="\n".join(_tool_line(s) for s in relevant_tools)
        )
        system_prompt = f"{system_prompt}\n\n{tool_block}"

    recent_messages = await conversations.get_recent_context(conv_id, max_messages=10)
    llm_messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        *recent_messages,
    ]

    tool_events: list[dict] = []
    confirmation_payload: dict | None = None
    response_text = ""
    for step in range(MAX_TOOL_STEPS):
        response_text = await model_router.generate(tier, llm_messages)
        call = _extract_tool_call(response_text) if relevant_tools else None
        if call is None:
            break

        qname = call["name"]
        args = call.get("arguments") or {}
        tool_events.append({"step": step, "phase": "start", "tool": qname, "arguments": args})

        outcome = await tool_executor.execute(
            _ToolCallShim(qname, args)
        )

        if outcome.status == "needs_confirmation" and outcome.confirmation is not None:
            confirmation_payload = outcome.confirmation.model_dump(mode="json")
            response_text = (
                f"I need permission to run `{qname}`. Approve to continue."
            )
            tool_events.append(
                {"step": step, "phase": "await_confirmation", "tool": qname}
            )
            break

        if outcome.status in ("denied", "rate_limited", "error"):
            tool_events.append(
                {"step": step, "phase": outcome.status, "tool": qname,
                 "message": outcome.message}
            )
            llm_messages.append({"role": "assistant", "content": response_text})
            llm_messages.append(
                {"role": "user",
                 "content": f"Tool `{qname}` failed: {outcome.message}. "
                            f"Try a different approach or answer without it."}
            )
            continue

        # ok
        result_content = outcome.result.content if outcome.result else None
        event: dict = {
            "step": step, "phase": "ok", "tool": qname,
            "latency_ms": outcome.result.latency_ms if outcome.result else 0,
        }
        # Surface small structured hints so the frontend can render inline
        # screenshots / app lists / file lists without another round trip.
        if isinstance(result_content, dict):
            if result_content.get("image_base64") and result_content.get("mime"):
                event["screenshot"] = {
                    "base64": result_content["image_base64"],
                    "mime": result_content.get("mime", "image/png"),
                }
            if isinstance(result_content.get("apps"), list):
                names = [a.get("name") for a in result_content["apps"] if isinstance(a, dict) and a.get("name")]
                if names:
                    event["apps"] = names[:40]
            if isinstance(result_content.get("results"), list) and (
                qname.endswith(".search_files") or qname == "filesystem.search_files"
            ):
                event["files"] = [
                    r for r in result_content["results"] if isinstance(r, str)
                ][:20]
            # Coding: a returned unified diff can be shown inline.
            if isinstance(result_content.get("diff"), str) and result_content.get("diff"):
                event["diff"] = {
                    "path": result_content.get("path") or "",
                    "diff": result_content["diff"],
                }
            # A source-file read → offer to render as a highlighted CodeBlock.
            if (
                qname in ("code.read_source_file", "filesystem.read_file")
                and isinstance(result_content.get("content"), str)
            ):
                event["code"] = {
                    "path": result_content.get("path") or "",
                    "language": result_content.get("language") or "",
                    "content": result_content["content"][:12000],
                }
            # investigate_and_fix → a whole proposal (diagnosis + edits[])
            if qname == "code.investigate_and_fix" and isinstance(result_content.get("edits"), list):
                event["proposal"] = {
                    "repo_path": result_content.get("repo_path"),
                    "diagnosis": result_content.get("diagnosis"),
                    "edits": result_content.get("edits"),
                    "test_command": result_content.get("test_command"),
                }
        tool_events.append(event)
        llm_messages.append({"role": "assistant", "content": response_text})
        llm_messages.append(
            {"role": "user",
             "content": (
                 wrap_tool_output(qname, result_content)
                 + "\n\nGive the final answer to the user based on the data above."
             )}
        )
    else:
        # loop exhausted without a plain-text finish — force a wrap-up.
        llm_messages.append(
            {"role": "user",
             "content": "Please summarize the results for the user in plain text now."}
        )
        response_text = await model_router.generate(tier, llm_messages)

    # Confidence pass — only meaningful when the answer actually leaned on
    # retrieved sources (memories or documents). Grading a greeting or plain
    # conversational reply against empty/irrelevant sources just produces a
    # bogus low score, so we skip it entirely in that case.
    confidence_info = None
    has_sources = bool(memories) or bool(doc_hits)
    grade_confidence = has_sources and intent in ("question", "memory_query", "command")
    if grade_confidence:
        try:
            from kira.brain.confidence import disclaimer_for, score as score_confidence

            async def _fast_gen(p: str) -> str:
                return await ollama.generate(
                    model=config.models.fast.model, prompt=p,
                    options={"temperature": 0.0},
                )
            confidence_info = await score_confidence(
                response_text, memories_text, _fast_gen
            )
            disclaimer = disclaimer_for(int(confidence_info["confidence"]))
            if disclaimer:
                response_text = f"{disclaimer}\n\n{response_text}"
        except Exception:
            confidence_info = None

    # Source tags: which pools contributed to this answer.
    source_tags: list[str] = []
    if memories:
        source_tags.append("MEMORY")
    if doc_hits:
        source_tags.append("DOCUMENT")
    if tool_events:
        source_tags.append("TOOL")
    if not source_tags:
        source_tags.append("INFERRED")

    assistant_metadata: dict = {
        "model_tier": tier.value, "intent": intent,
        "source_tags": source_tags,
    }
    if confidence_info is not None:
        assistant_metadata["confidence"] = confidence_info
    if tool_events:
        assistant_metadata["tool_events"] = tool_events
    if confirmation_payload:
        assistant_metadata["confirmation"] = confirmation_payload
    if doc_hits:
        assistant_metadata["document_citations"] = doc_hits

    assistant_msg = Message(
        role=Role.ASSISTANT,
        content=response_text,
        conversation_id=conv_id,
        metadata=assistant_metadata,
    )
    await conversations.add_message(conv_id, assistant_msg)

    try:
        await _extract_and_store_memories(
            request.message, response_text, conv_id,
            ollama, config, memory_store, knowledge_graph,
        )
    except Exception:
        pass

    latency_ms = int((time.time() - start) * 1000)
    return ChatResponse(
        message=assistant_msg,
        conversation_id=conv_id,
        state=KiraState.IDLE,
        memories_used=[m.id for m in memories],
        model_used=tier.value,
        latency_ms=latency_ms,
    )


def _dump(v: Any) -> str:
    try:
        return json_module.dumps(v, indent=2, default=str)[:4000]
    except Exception:
        return str(v)[:4000]


_TOOL_HINTS = (
    "search", "google", "look up", "find file", "read file", "write file",
    "run", "execute", "shell", "command", "news", "weather", "browse",
)


def _looks_toolish(message: str) -> bool:
    m = message.lower()
    return any(hint in m for hint in _TOOL_HINTS)


_DOC_HINTS = (
    "my notes", "my document", "in the pdf", "in my pdf", "the doc",
    "my files", "in my files", "my downloads", "resume", "syllabus",
    "invoice", "receipt", "spec", "chapter", "page ",
)


def _looks_docish(message: str) -> bool:
    m = message.lower()
    return any(hint in m for hint in _DOC_HINTS)


class _ToolCallShim:
    """Minimal duck-type wrapper matching kira.tools.types.ToolCall."""
    def __init__(self, name: str, arguments: dict):
        from uuid import uuid4
        self.id = uuid4()
        self.tool = name
        self.arguments = arguments


# ---- Research helpers ---------------------------------------------------


_RESEARCH_QUICK_HINTS = ("look up", "search for", "find out")
_RESEARCH_DEEP_HINTS = ("deep research", "research the", "compare", "in depth")


def _resolve_research_mode(message: str, override: str | None) -> str:
    if override in ("off", "quick", "deep"):
        return override
    lower = message.lower().strip()
    if any(h in lower for h in _RESEARCH_DEEP_HINTS):
        return "deep"
    if lower.startswith("research ") or lower.startswith("kira, research"):
        return "deep"
    if any(h in lower for h in _RESEARCH_QUICK_HINTS):
        return "quick"
    return "off"


async def _run_research_turn(
    *,
    request: ChatRequest,
    conv_id: UUID,
    mode: str,
    conversations: ConversationManager,
    memory_store: MemoryStore,
    intent: str,
    start: float,
) -> ChatResponse:
    from kira.brain.verifier import SourceRef, Verifier
    from kira.tools.research.progress import BROKER
    from kira.tools.servers import research_server

    research_id = request.research_id or f"r-{conv_id}-{int(time.time() * 1000)}"

    if research_server._pipeline is None:
        # Research not configured — fall back to a message.
        response_text = (
            "Research pipeline isn't configured on this server yet."
        )
        assistant_msg = Message(
            role=Role.ASSISTANT, content=response_text,
            conversation_id=conv_id,
            metadata={"intent": intent, "research_mode": mode},
        )
        await conversations.add_message(conv_id, assistant_msg)
        return ChatResponse(
            message=assistant_msg, conversation_id=conv_id,
            state=KiraState.IDLE, memories_used=[],
            model_used="research:unavailable",
            latency_ms=int((time.time() - start) * 1000),
        )

    if mode == "deep":
        payload = await research_server._pipeline.deep(
            request.message, research_id=research_id
        )
    else:
        payload = await research_server._pipeline.quick(
            request.message, research_id=research_id
        )

    # Verifier — cite/hedge the synthesized summary against the sources
    # we actually pulled in this run.
    verifier = Verifier()
    source_refs = [
        SourceRef(id=i + 1, url=s.url, title=s.title, snippet=s.snippet)
        for i, s in enumerate(payload.sources)
    ]
    report = verifier.verify(payload.summary, source_refs)
    payload.summary = report.text

    memories = await memory_store.search(request.message, limit=3)

    assistant_msg = Message(
        role=Role.ASSISTANT,
        content=payload.summary,
        conversation_id=conv_id,
        metadata={
            "intent": intent,
            "research_mode": mode,
            "research_id": research_id,
            "research": payload.model_dump(mode="json"),
            "verification": {
                "used_source_ids": report.used_source_ids,
                "claims": [
                    {"confidence": c.confidence.value, "sentence": c.sentence}
                    for c in report.claims
                ],
            },
        },
    )
    await conversations.add_message(conv_id, assistant_msg)

    # Cache pruning courtesy — research broker keeps history until we
    # explicitly clear it.
    BROKER.clear(research_id)

    latency_ms = int((time.time() - start) * 1000)
    return ChatResponse(
        message=assistant_msg,
        conversation_id=conv_id,
        state=KiraState.IDLE,
        memories_used=[m.id for m in memories],
        model_used=f"research:{mode}",
        latency_ms=latency_ms,
    )


async def _extract_and_store_memories(
    user_message: str,
    assistant_response: str,
    conv_id: UUID,
    ollama,
    config,
    memory_store: MemoryStore,
    knowledge_graph: KnowledgeGraph,
) -> None:
    exchange = f"User: {user_message}\nAssistant: {assistant_response}"
    try:
        result = await ollama.generate(
            model=config.models.fast.model,
            prompt=MEMORY_EXTRACTION_PROMPT.format(conversation=exchange),
            options={"temperature": 0.1},
        )
    except Exception:
        return

    clean = result.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]

    try:
        facts = json_module.loads(clean)
    except json_module.JSONDecodeError:
        return
    if not isinstance(facts, list):
        return

    for fact in facts:
        if not isinstance(fact, dict) or not fact.get("content"):
            continue
        try:
            category = MemoryCategory(fact.get("category", "observation"))
        except ValueError:
            category = MemoryCategory.OBSERVATION

        memory = Memory(
            content=fact["content"],
            category=category,
            importance=float(fact.get("importance", 0.5)),
            source_type="conversation",
            source_id=conv_id,
        )
        await memory_store.store(memory)

        for entity_name in fact.get("entities", []) or []:
            if not isinstance(entity_name, str):
                continue
            existing = await knowledge_graph.get_entity(entity_name)
            if not existing:
                await knowledge_graph.add_entity(
                    Entity(type=EntityType.TOPIC, name=entity_name)
                )
