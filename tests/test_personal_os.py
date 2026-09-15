"""Tests for personal-OS pieces that don't need external APIs."""
import asyncio
from datetime import datetime, timedelta, timezone

from kira.permissions import PermissionEngine
from kira.tools.monitor import Monitor
from kira.types import RiskLevel


def test_permission_maps_google_reads_to_read():
    e = PermissionEngine()
    for name in (
        "google.list_emails", "google.read_email", "google.get_unread_count",
        "google.summarize_inbox",
        "google.get_today_events", "google.get_week_events",
        "google.get_upcoming", "google.find_free_time",
        "google.list_tasks",
        "google.drive_search", "google.drive_read", "google.drive_recent",
        "life.get_today_brief", "life.morning_brief",
        "notifications.list_recent", "notifications.search",
    ):
        assert e.classify_risk(name) == RiskLevel.READ, f"{name} should be READ"


def test_permission_maps_google_send_to_external():
    e = PermissionEngine()
    assert e.classify_risk("google.send_email") == RiskLevel.EXTERNAL
    assert e.classify_risk("notifications.telegram_send") == RiskLevel.EXTERNAL


def test_permission_maps_google_drafts_and_events_to_execute():
    e = PermissionEngine()
    assert e.classify_risk("google.draft_email") == RiskLevel.EXECUTE
    assert e.classify_risk("google.create_event") == RiskLevel.EXECUTE


def test_permission_task_and_deadline_ops_personal():
    e = PermissionEngine()
    for name in (
        "google.create_task", "google.complete_task",
        "life.track_deadline", "life.complete_deadline",
        "notifications.mark_read",
    ):
        assert e.classify_risk(name) == RiskLevel.PERSONAL, f"{name} should be PERSONAL"


def test_monitor_publishes_upcoming_meeting_once():
    async def _events():
        now = datetime.now(timezone.utc)
        return [{
            "id": "m1",
            "title": "Standup",
            "start": (now + timedelta(minutes=14)).isoformat(),
            "end": (now + timedelta(minutes=44)).isoformat(),
        }]

    async def _unread():
        return {"unread": 0}

    async def _run():
        m = Monitor(
            get_today_events=_events,
            get_unread_count=_unread,
            check_interval_sec=999,
        )
        await m._check_upcoming_meeting()
        # Second call should dedupe.
        await m._check_upcoming_meeting()
        events = await m.pop_events()
        return events

    events = asyncio.run(_run())
    types = [e["type"] for e in events]
    assert types == ["upcoming_meeting"]


def test_monitor_publishes_email_batch_on_delta():
    async def _events():
        return []

    counter = {"n": 0}

    async def _unread():
        counter["n"] += 1
        return {"unread": counter["n"] * 5}

    async def _run():
        m = Monitor(get_today_events=_events, get_unread_count=_unread,
                    check_interval_sec=999)
        await m._check_unread_email()   # baseline (last_unread = 5)
        await m._check_unread_email()   # delta = 5 → publish
        return await m.pop_events()

    events = asyncio.run(_run())
    assert any(e["type"] == "new_email_batch" for e in events)
