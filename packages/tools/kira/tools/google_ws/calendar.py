"""Google Calendar helpers."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from kira.tools.google_ws.services import calendar_service, run_google


LOCAL_TZ = datetime.now().astimezone().tzinfo


def _isoz(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _shape_event(ev: dict) -> dict:
    return {
        "id": ev.get("id"),
        "title": ev.get("summary", ""),
        "description": ev.get("description", ""),
        "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date"),
        "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
        "location": ev.get("location", ""),
        "hangout_link": ev.get("hangoutLink") or "",
        "attendees": [a.get("email") for a in ev.get("attendees") or [] if a.get("email")],
    }


async def _events_between(start: datetime, end: datetime, max_results: int = 25) -> list[dict]:
    def _do():
        svc = calendar_service()
        resp = svc.events().list(
            calendarId="primary",
            timeMin=_isoz(start),
            timeMax=_isoz(end),
            singleEvents=True,
            orderBy="startTime",
            maxResults=max_results,
        ).execute()
        return [_shape_event(e) for e in resp.get("items", [])]
    return await run_google(_do)


async def get_today_events() -> list[dict]:
    now = datetime.now(LOCAL_TZ)
    start = datetime.combine(now.date(), time.min, LOCAL_TZ)
    end = start + timedelta(days=1)
    return await _events_between(start, end)


async def get_week_events() -> list[dict]:
    now = datetime.now(LOCAL_TZ)
    start = datetime.combine(now.date(), time.min, LOCAL_TZ)
    end = start + timedelta(days=7)
    return await _events_between(start, end, max_results=50)


async def get_upcoming(count: int = 3) -> list[dict]:
    now = datetime.now(LOCAL_TZ)
    end = now + timedelta(days=14)
    events = await _events_between(now, end, max_results=count)
    return events[:count]


async def create_event(
    title: str, start: str, end: str, description: str = ""
) -> dict:
    def _do():
        svc = calendar_service()
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }
        ev = svc.events().insert(calendarId="primary", body=body).execute()
        return {"created": True, "id": ev.get("id"), "html_link": ev.get("htmlLink")}
    return await run_google(_do)


async def find_free_time(date: str, day_start_hour: int = 9,
                         day_end_hour: int = 21, slot_minutes: int = 30) -> dict:
    """Return free slots on `date` (YYYY-MM-DD). Simple gap-finder."""
    d = datetime.fromisoformat(date).replace(tzinfo=LOCAL_TZ)
    day_start = d.replace(hour=day_start_hour, minute=0, second=0, microsecond=0)
    day_end = d.replace(hour=day_end_hour, minute=0, second=0, microsecond=0)
    events = await _events_between(day_start, day_end, max_results=50)
    # Convert to (start, end) datetimes; skip all-day.
    busy: list[tuple[datetime, datetime]] = []
    for e in events:
        try:
            if "T" in (e["start"] or "") and "T" in (e["end"] or ""):
                busy.append(
                    (datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"]))
                )
        except Exception:
            continue
    busy.sort()

    slots: list[dict] = []
    cursor = day_start
    for bs, be in busy:
        if bs > cursor:
            duration = (bs - cursor).total_seconds() / 60
            if duration >= slot_minutes:
                slots.append({"start": cursor.isoformat(), "end": bs.isoformat()})
        if be > cursor:
            cursor = be
    if cursor < day_end:
        duration = (day_end - cursor).total_seconds() / 60
        if duration >= slot_minutes:
            slots.append({"start": cursor.isoformat(), "end": day_end.isoformat()})
    return {"date": date, "free_slots": slots}
