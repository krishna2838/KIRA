"""Notifications MCP server.

Read-only inspection of the captured-notifications table, semantic search,
sender filter, unread summarization, plus optional Telegram/Discord reads.
Sending is L3 and gated by the executor.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from kira.tools.notifications import discord_adapter, telegram_adapter
from kira.tools.notifications.store import NotificationStore
from kira.tools.servers.base import InternalServer, InternalTool


_store: NotificationStore | None = None
_summarize_fn: Callable[[str], Awaitable[str]] | None = None


def configure(store: NotificationStore | None, summarize_fn) -> None:
    global _store, _summarize_fn
    _store = store
    _summarize_fn = summarize_fn


def _need_store() -> dict:
    return {"error": "notifications store not initialized"}


# ---- tool handlers ------------------------------------------------------


async def _list_recent(args: dict) -> Any:
    if _store is None:
        return _need_store()
    limit = int(args.get("limit", 20))
    hours = int(args.get("since_hours", 24))
    return {"notifications": await _store.recent(limit=limit, since_hours=hours)}


async def _unread_count(args: dict) -> Any:
    if _store is None:
        return _need_store()
    return {"unread": await _store.unread_count()}


async def _mark_read(args: dict) -> Any:
    if _store is None:
        return _need_store()
    ids = args.get("ids")
    n = await _store.mark_read(ids)
    return {"marked": n}


async def _search(args: dict) -> Any:
    if _store is None:
        return _need_store()
    rows = await _store.search(
        args["query"],
        limit=int(args.get("limit", 15)),
        app=args.get("app"),
        sender=args.get("sender"),
    )
    return {"query": args["query"], "notifications": rows}


async def _latest_from(args: dict) -> Any:
    if _store is None:
        return _need_store()
    return {
        "sender": args["sender"],
        "notifications": await _store.latest_from(args["sender"], limit=int(args.get("limit", 5))),
    }


async def _summarize_unread(args: dict) -> Any:
    if _store is None:
        return _need_store()
    if _summarize_fn is None:
        return {"error": "no summarizer configured"}
    return await _store.summarize_unread(_summarize_fn)


async def _ingest(args: dict) -> Any:
    if _store is None:
        return _need_store()
    return await _store.ingest(
        app_name=args["app_name"],
        title=args.get("title", ""),
        body=args.get("body", ""),
        sender=args.get("sender"),
        importance=float(args.get("importance", 0.5)),
    )


# Telegram
async def _telegram_read(args: dict) -> Any:
    return await telegram_adapter.read_recent(
        int(args["chat_id"]), limit=int(args.get("limit", 20))
    )


async def _telegram_send(args: dict) -> Any:
    return await telegram_adapter.send_message(int(args["chat_id"]), args["text"])


# Discord
async def _discord_read(args: dict) -> Any:
    return await discord_adapter.read_channel(
        str(args["channel_id"]), limit=int(args.get("limit", 25))
    )


SERVER = InternalServer(
    name="notifications",
    description="Captured notifications + optional Telegram/Discord reads.",
    tools=[
        InternalTool(name="list_recent",
                     description="Recent captured notifications (default: last 24h).",
                     input_schema={"type": "object",
                                   "properties": {"limit": {"type": "integer", "default": 20},
                                                  "since_hours": {"type": "integer", "default": 24}}},
                     handler=_list_recent),
        InternalTool(name="unread_count",
                     description="How many captured notifications are unread.",
                     input_schema={"type": "object", "properties": {}},
                     handler=_unread_count),
        InternalTool(name="mark_read",
                     description="Mark notifications as read. Omit `ids` to mark ALL unread.",
                     input_schema={"type": "object",
                                   "properties": {"ids": {"type": "array", "items": {"type": "string"}}}},
                     handler=_mark_read),
        InternalTool(name="search",
                     description="Search captured notifications by text (semantic when embeddings available).",
                     input_schema={"type": "object",
                                   "properties": {"query": {"type": "string"},
                                                  "app": {"type": "string"},
                                                  "sender": {"type": "string"},
                                                  "limit": {"type": "integer", "default": 15}},
                                   "required": ["query"]},
                     handler=_search),
        InternalTool(name="latest_from",
                     description="Get the most recent notifications from a given sender.",
                     input_schema={"type": "object",
                                   "properties": {"sender": {"type": "string"},
                                                  "limit": {"type": "integer", "default": 5}},
                                   "required": ["sender"]},
                     handler=_latest_from),
        InternalTool(name="summarize_unread",
                     description="LLM-summarize unread notifications from the last 6h.",
                     input_schema={"type": "object", "properties": {}},
                     handler=_summarize_unread),
        InternalTool(name="ingest",
                     description="Ingest a notification (used by external adapters or the setup UI).",
                     input_schema={"type": "object",
                                   "properties": {
                                       "app_name": {"type": "string"},
                                       "title": {"type": "string"},
                                       "body": {"type": "string"},
                                       "sender": {"type": "string"},
                                       "importance": {"type": "number", "default": 0.5},
                                   },
                                   "required": ["app_name"]},
                     handler=_ingest),
        InternalTool(name="telegram_read",
                     description="Read recent Telegram messages from a chat (optional).",
                     input_schema={"type": "object",
                                   "properties": {"chat_id": {"type": "integer"},
                                                  "limit": {"type": "integer", "default": 20}},
                                   "required": ["chat_id"]},
                     handler=_telegram_read),
        InternalTool(name="telegram_send",
                     description="Send a Telegram message (L3 — always confirm).",
                     input_schema={"type": "object",
                                   "properties": {"chat_id": {"type": "integer"},
                                                  "text": {"type": "string"}},
                                   "required": ["chat_id", "text"]},
                     handler=_telegram_send),
        InternalTool(name="discord_read",
                     description="Read recent Discord messages from a channel (optional).",
                     input_schema={"type": "object",
                                   "properties": {"channel_id": {"type": "string"},
                                                  "limit": {"type": "integer", "default": 25}},
                                   "required": ["channel_id"]},
                     handler=_discord_read),
    ],
)
