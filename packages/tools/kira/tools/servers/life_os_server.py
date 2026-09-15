"""Life OS — the personal context aggregator.

Composes calendar, unread mail, tasks, notifications, and deadlines into
one snapshot. Delegates to the other server modules; nothing here talks to
Google/DB directly, keeping this file thin.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable

from kira.tools.google_ws import calendar as gcal
from kira.tools.google_ws import gmail as gmail
from kira.tools.google_ws import tasks as gtasks
from kira.tools.google_ws.auth import is_authenticated
from kira.tools.life.deadlines import Deadlines
from kira.tools.notifications.store import NotificationStore
from kira.tools.servers.base import InternalServer, InternalTool


_notifications: NotificationStore | None = None
_deadlines: Deadlines | None = None
_summarize_fn: Callable[[str], Awaitable[str]] | None = None


def configure(
    notifications: NotificationStore | None,
    deadlines: Deadlines | None,
    summarize_fn,
) -> None:
    global _notifications, _deadlines, _summarize_fn
    _notifications = notifications
    _deadlines = deadlines
    _summarize_fn = summarize_fn


async def _google_slice() -> dict:
    if not is_authenticated():
        return {
            "connected": False,
            "hint": "Connect via /api/auth/google to pull calendar/email/tasks.",
        }
    events = tasks = []
    unread = None
    try:
        events = await gcal.get_today_events()
    except Exception as e:
        events = [{"error": str(e)}]
    try:
        tasks = await gtasks.list_tasks(only_open=True)
    except Exception as e:
        tasks = [{"error": str(e)}]
    try:
        unread = (await gmail.get_unread_count()).get("unread")
    except Exception:
        unread = None
    return {
        "connected": True,
        "today_events": events,
        "open_tasks": tasks,
        "unread_email": unread,
    }


# ---- tool handlers ------------------------------------------------------


async def _get_today_brief(args: dict) -> Any:
    google = await _google_slice()
    notifs = []
    unread_notifs = 0
    if _notifications is not None:
        try:
            notifs = await _notifications.recent(limit=6, since_hours=12)
            unread_notifs = await _notifications.unread_count()
        except Exception:
            notifs = []
    deadlines_ = []
    if _deadlines is not None:
        try:
            deadlines_ = await _deadlines.upcoming(days=14)
        except Exception:
            deadlines_ = []
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "google": google,
        "notifications": {
            "recent": notifs,
            "unread": unread_notifs,
        },
        "deadlines": deadlines_,
    }


async def _get_focus_suggestion(args: dict) -> Any:
    if _summarize_fn is None:
        return {"suggestion": "Set aside 25 minutes for your most important task."}
    brief = await _get_today_brief({})
    prompt = (
        "You are helping a busy CSE student decide what to focus on RIGHT NOW. "
        "Look at the schedule, tasks, and recent notifications. Recommend "
        "ONE thing to focus on in the next hour, in 1–2 sentences, and say "
        "why. Be direct. Data:\n\n"
        f"{brief}"
    )
    suggestion = await _summarize_fn(prompt)
    return {"suggestion": suggestion.strip()}


async def _get_weekly_overview(args: dict) -> Any:
    if not is_authenticated():
        return {"connected": False}
    try:
        events = await gcal.get_week_events()
    except Exception as e:
        events = [{"error": str(e)}]
    deadlines_ = []
    if _deadlines is not None:
        try:
            deadlines_ = await _deadlines.upcoming(days=7)
        except Exception:
            pass
    return {"events": events, "deadlines": deadlines_}


async def _track_deadline(args: dict) -> Any:
    if _deadlines is None:
        return {"error": "deadlines store not configured"}
    due = datetime.fromisoformat(args["date"])
    return await _deadlines.add(args["name"], due, args.get("notes", ""))


async def _list_deadlines(args: dict) -> Any:
    if _deadlines is None:
        return {"deadlines": []}
    return {"deadlines": await _deadlines.upcoming(int(args.get("days", 14)))}


async def _complete_deadline(args: dict) -> Any:
    if _deadlines is None:
        return {"completed": False, "error": "deadlines store not configured"}
    return await _deadlines.complete(args["id"])


async def _morning_brief(args: dict) -> Any:
    brief = await _get_today_brief({})
    if _summarize_fn is None:
        return {"brief": "Good morning — connect a Google account to see your schedule."}
    prompt = (
        "Write a concise morning brief (4–6 short bullets) for a CSE student. "
        "Use ONLY the data below. Highlight the first meeting, most important "
        "task, urgent notifications, upcoming deadlines. If Google isn't "
        "connected, say so briefly. No fluff.\n\n"
        f"{brief}"
    )
    text = await _summarize_fn(prompt)
    return {"brief": text.strip(), "data": brief}


SERVER = InternalServer(
    name="life",
    description="Personal context: today's schedule, tasks, notifications, deadlines, and morning brief.",
    tools=[
        InternalTool(name="get_today_brief",
                     description="Structured snapshot of today (calendar + tasks + unread + notifications).",
                     input_schema={"type": "object", "properties": {}},
                     handler=_get_today_brief),
        InternalTool(name="get_focus_suggestion",
                     description="LLM recommendation of what to focus on right now.",
                     input_schema={"type": "object", "properties": {}},
                     handler=_get_focus_suggestion),
        InternalTool(name="get_weekly_overview",
                     description="This week's calendar + deadlines.",
                     input_schema={"type": "object", "properties": {}},
                     handler=_get_weekly_overview),
        InternalTool(name="track_deadline",
                     description="Add a personal deadline (name + ISO date + optional notes).",
                     input_schema={"type": "object",
                                   "properties": {"name": {"type": "string"},
                                                  "date": {"type": "string"},
                                                  "notes": {"type": "string"}},
                                   "required": ["name", "date"]},
                     handler=_track_deadline),
        InternalTool(name="list_deadlines",
                     description="Upcoming deadlines within N days (default 14).",
                     input_schema={"type": "object",
                                   "properties": {"days": {"type": "integer", "default": 14}}},
                     handler=_list_deadlines),
        InternalTool(name="complete_deadline",
                     description="Mark a deadline as done.",
                     input_schema={"type": "object",
                                   "properties": {"id": {"type": "string"}}, "required": ["id"]},
                     handler=_complete_deadline),
        InternalTool(name="morning_brief",
                     description="Full morning brief, LLM-written, backed by the day's data.",
                     input_schema={"type": "object", "properties": {}},
                     handler=_morning_brief),
    ],
)
