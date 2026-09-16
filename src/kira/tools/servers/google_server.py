"""Google Workspace MCP server.

Wraps Gmail + Calendar + Tasks + Drive helpers as tools. Every tool checks
`auth.is_authenticated()` up front and returns a helpful error otherwise —
this lets the LLM tell the user "connect your Google account first" rather
than crashing.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from kira.tools.google_ws import calendar as gcal
from kira.tools.google_ws import drive as gdrive
from kira.tools.google_ws import gmail as gmail
from kira.tools.google_ws import tasks as gtasks
from kira.tools.google_ws.auth import (
    forget_token,
    has_credentials_file,
    is_authenticated,
)
from kira.tools.servers.base import InternalServer, InternalTool


# Bound by the bootstrap so summarize_inbox can call the LLM.
_summarize_fn: Callable[[str], Awaitable[str]] | None = None


def configure(summarize_fn: Callable[[str], Awaitable[str]] | None) -> None:
    global _summarize_fn
    _summarize_fn = summarize_fn


def _unauth(msg: str) -> dict:
    return {
        "error": msg,
        "hint": "Call /api/auth/google to connect an account.",
    }


async def _auth_status(args: dict) -> Any:
    return {
        "authenticated": is_authenticated(),
        "credentials_file_present": has_credentials_file(),
    }


async def _sign_out(args: dict) -> Any:
    forget_token()
    return {"signed_out": True}


# ---- Gmail tools ---------------------------------------------------------


async def _list_emails(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    rows = await gmail.list_emails(
        query=args.get("query", ""),
        max_results=int(args.get("max_results", 10)),
    )
    return {"emails": rows}


async def _read_email(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return await gmail.read_email(args["id"])


async def _send_email(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return await gmail.send_email(args["to"], args["subject"], args["body"])


async def _draft_email(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return await gmail.draft_email(args["to"], args["subject"], args["body"])


async def _get_unread_count(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return await gmail.get_unread_count()


async def _summarize_inbox(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    if _summarize_fn is None:
        return {"error": "No summarizer configured yet."}
    return await gmail.summarize_inbox(_summarize_fn)


# ---- Calendar tools ------------------------------------------------------


async def _get_today_events(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return {"events": await gcal.get_today_events()}


async def _get_week_events(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return {"events": await gcal.get_week_events()}


async def _get_upcoming(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return {"events": await gcal.get_upcoming(int(args.get("count", 3)))}


async def _create_event(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return await gcal.create_event(
        args["title"], args["start"], args["end"],
        description=args.get("description", ""),
    )


async def _find_free_time(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return await gcal.find_free_time(
        args["date"],
        day_start_hour=int(args.get("day_start_hour", 9)),
        day_end_hour=int(args.get("day_end_hour", 21)),
        slot_minutes=int(args.get("slot_minutes", 30)),
    )


# ---- Tasks tools ---------------------------------------------------------


async def _list_tasks(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return {"tasks": await gtasks.list_tasks(only_open=bool(args.get("only_open", True)))}


async def _create_task(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return await gtasks.create_task(args["title"], due_date=args.get("due_date"))


async def _complete_task(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return await gtasks.complete_task(args["id"])


# ---- Drive tools ---------------------------------------------------------


async def _drive_search(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return {"files": await gdrive.search_files(args["query"],
                                                max_results=int(args.get("max_results", 20)))}


async def _drive_read(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return await gdrive.read_file(args["id"])


async def _drive_recent(args: dict) -> Any:
    if not is_authenticated():
        return _unauth("Not signed in to Google.")
    return {"files": await gdrive.list_recent(int(args.get("limit", 20)))}


# ---- server definition ---------------------------------------------------


SERVER = InternalServer(
    name="google",
    description="Google Workspace: Gmail, Calendar, Tasks, Drive.",
    tools=[
        InternalTool(name="auth_status", description="Report whether the user has connected a Google account.",
                     input_schema={"type": "object", "properties": {}}, handler=_auth_status),
        InternalTool(name="sign_out", description="Forget the stored Google token.",
                     input_schema={"type": "object", "properties": {}}, handler=_sign_out),

        # Gmail
        InternalTool(name="list_emails",
                     description="Search Gmail. Use Gmail query syntax (e.g. 'is:unread', 'from:...').",
                     input_schema={"type": "object",
                                   "properties": {"query": {"type": "string"},
                                                  "max_results": {"type": "integer", "default": 10}}},
                     handler=_list_emails),
        InternalTool(name="read_email", description="Fetch the full body of an email by id.",
                     input_schema={"type": "object",
                                   "properties": {"id": {"type": "string"}}, "required": ["id"]},
                     handler=_read_email),
        InternalTool(name="send_email",
                     description="Send an email. ALWAYS requires user confirmation (L3).",
                     input_schema={"type": "object",
                                   "properties": {"to": {"type": "string"},
                                                  "subject": {"type": "string"},
                                                  "body": {"type": "string"}},
                                   "required": ["to", "subject", "body"]},
                     handler=_send_email),
        InternalTool(name="draft_email", description="Create a draft email (L2).",
                     input_schema={"type": "object",
                                   "properties": {"to": {"type": "string"},
                                                  "subject": {"type": "string"},
                                                  "body": {"type": "string"}},
                                   "required": ["to", "subject", "body"]},
                     handler=_draft_email),
        InternalTool(name="get_unread_count", description="Number of unread INBOX messages.",
                     input_schema={"type": "object", "properties": {}},
                     handler=_get_unread_count),
        InternalTool(name="summarize_inbox",
                     description="LLM-summarize unread emails from the last 2 days.",
                     input_schema={"type": "object", "properties": {}},
                     handler=_summarize_inbox),

        # Calendar
        InternalTool(name="get_today_events", description="Today's calendar events.",
                     input_schema={"type": "object", "properties": {}},
                     handler=_get_today_events),
        InternalTool(name="get_week_events", description="This week's calendar events.",
                     input_schema={"type": "object", "properties": {}},
                     handler=_get_week_events),
        InternalTool(name="get_upcoming", description="Next N calendar events.",
                     input_schema={"type": "object",
                                   "properties": {"count": {"type": "integer", "default": 3}}},
                     handler=_get_upcoming),
        InternalTool(name="create_event",
                     description="Create a calendar event (L2). Times must be RFC3339.",
                     input_schema={"type": "object",
                                   "properties": {"title": {"type": "string"},
                                                  "start": {"type": "string"},
                                                  "end": {"type": "string"},
                                                  "description": {"type": "string"}},
                                   "required": ["title", "start", "end"]},
                     handler=_create_event),
        InternalTool(name="find_free_time",
                     description="Find free slots on a given YYYY-MM-DD date.",
                     input_schema={"type": "object",
                                   "properties": {"date": {"type": "string"},
                                                  "slot_minutes": {"type": "integer", "default": 30}},
                                   "required": ["date"]},
                     handler=_find_free_time),

        # Tasks
        InternalTool(name="list_tasks", description="List Google Tasks (default: open).",
                     input_schema={"type": "object",
                                   "properties": {"only_open": {"type": "boolean", "default": True}}},
                     handler=_list_tasks),
        InternalTool(name="create_task", description="Create a Google Task (L1).",
                     input_schema={"type": "object",
                                   "properties": {"title": {"type": "string"},
                                                  "due_date": {"type": "string"}},
                                   "required": ["title"]},
                     handler=_create_task),
        InternalTool(name="complete_task", description="Mark a task done (L1).",
                     input_schema={"type": "object",
                                   "properties": {"id": {"type": "string"}}, "required": ["id"]},
                     handler=_complete_task),

        # Drive
        InternalTool(name="drive_search", description="Search files in Google Drive.",
                     input_schema={"type": "object",
                                   "properties": {"query": {"type": "string"},
                                                  "max_results": {"type": "integer", "default": 20}},
                                   "required": ["query"]},
                     handler=_drive_search),
        InternalTool(name="drive_read", description="Read a Drive file's text content.",
                     input_schema={"type": "object",
                                   "properties": {"id": {"type": "string"}}, "required": ["id"]},
                     handler=_drive_read),
        InternalTool(name="drive_recent", description="Recently modified Drive files.",
                     input_schema={"type": "object",
                                   "properties": {"limit": {"type": "integer", "default": 20}}},
                     handler=_drive_recent),
    ],
)
