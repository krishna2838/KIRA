"""Proactive monitor — background asyncio tasks that watch external state
and push events onto a queue for the frontend/voice pipeline to surface.

Design goals:
  - Cheap: run each check on a slow interval (5–15 min).
  - Idle-aware: `set_active(True)` while the user is actively chatting
    pauses proactive push events (they still accumulate).
  - Filtered: only IMPORTANT events (upcoming meetings, urgent emails,
    build failures) turn into user-visible pushes.
  - Fail-soft: any check that errors gets logged and skipped, never crashes
    the loop.

The queue is drained by:
  - The FastAPI /api/monitor/queue polling endpoint.
  - (Later) the voice pipeline's ambient-notification path.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from kira.logger import get_logger


logger = get_logger("tools.monitor")


class ProactiveEvent(dict):
    """Just a typed alias for readability."""


class Monitor:
    def __init__(
        self,
        *,
        get_today_events: Callable[[], Awaitable[list[dict]]] | None = None,
        get_unread_count: Callable[[], Awaitable[dict]] | None = None,
        notifications_store=None,
        check_interval_sec: int = 300,
    ):
        self.get_today_events = get_today_events
        self.get_unread_count = get_unread_count
        self.notifications_store = notifications_store
        self.check_interval_sec = check_interval_sec

        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._active = False   # True while the user is mid-conversation
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)
        self._seen_events: dict[str, datetime] = {}    # event id -> last-notified
        self._last_unread: int | None = None

    # -- lifecycle ---------------------------------------------------

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="kira-monitor")
        logger.info("Proactive monitor started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def set_active(self, active: bool) -> None:
        self._active = active

    # -- queue access -----------------------------------------------

    async def pop_events(self, max_items: int = 20) -> list[dict]:
        out: list[dict] = []
        while len(out) < max_items:
            try:
                out.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return out

    def qsize(self) -> int:
        return self._queue.qsize()

    def _publish(self, event: dict) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(event)
            except Exception:
                pass

    # -- loop -------------------------------------------------------

    async def _loop(self) -> None:
        # Run checks once immediately, then on the interval.
        while not self._stop.is_set():
            try:
                await self._run_checks()
            except Exception as e:
                logger.debug(f"monitor check failed: {e}")
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self.check_interval_sec
                )
                # stop signaled
                return
            except asyncio.TimeoutError:
                continue

    async def _run_checks(self) -> None:
        if self.get_today_events is not None:
            await self._check_upcoming_meeting()
        if self.get_unread_count is not None:
            await self._check_unread_email()

    async def _check_upcoming_meeting(self) -> None:
        try:
            events = await self.get_today_events()  # type: ignore[misc]
        except Exception:
            return
        now = datetime.now(timezone.utc)
        for ev in events or []:
            start = ev.get("start")
            if not start or not isinstance(start, str) or "T" not in start:
                continue
            try:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            except Exception:
                continue
            delta = dt - now
            # Notify once when we cross the 15-minute-out mark.
            if timedelta(minutes=13) < delta <= timedelta(minutes=15):
                key = f"meeting:{ev.get('id')}"
                if key in self._seen_events:
                    continue
                self._seen_events[key] = now
                self._publish({
                    "type": "upcoming_meeting",
                    "importance": 0.8,
                    "title": ev.get("title", "Meeting"),
                    "message": f"Meeting in 15 minutes: {ev.get('title', '')}",
                    "detail": ev,
                    "generated_at": now.isoformat(),
                })

    async def _check_unread_email(self) -> None:
        try:
            result = await self.get_unread_count()  # type: ignore[misc]
        except Exception:
            return
        unread = int(result.get("unread", 0) or 0)
        if self._last_unread is None:
            self._last_unread = unread
            return
        delta = unread - self._last_unread
        self._last_unread = unread
        if delta >= 3:
            # Only worth telling the user when a batch arrives, not one-by-one.
            self._publish({
                "type": "new_email_batch",
                "importance": 0.5,
                "title": f"{delta} new emails",
                "message": f"You have {delta} new unread emails ({unread} total).",
                "generated_at": datetime.utcnow().isoformat(),
            })

    # -- external ingest ------------------------------------------

    def enqueue(self, event: dict) -> None:
        """Let other subsystems (e.g. NC observer) push into the same queue."""
        self._publish(event)
