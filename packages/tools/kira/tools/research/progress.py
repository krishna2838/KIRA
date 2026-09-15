"""In-process pub/sub for research progress events.

Chat route generates a research_id, subscribers (WebSocket clients) attach
an asyncio.Queue, and the pipeline `publish()`es events as work advances.
"""
from __future__ import annotations

import asyncio
from typing import Any


class ProgressBroker:
    def __init__(self):
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._history: dict[str, list[dict]] = {}
        self._lock = asyncio.Lock()
        self._max_history = 100

    async def subscribe(self, research_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._subs.setdefault(research_id, []).append(q)
            # Replay any history so late subscribers see prior events.
            for evt in self._history.get(research_id, []):
                q.put_nowait(evt)
        return q

    async def unsubscribe(self, research_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            lst = self._subs.get(research_id)
            if not lst:
                return
            try:
                lst.remove(q)
            except ValueError:
                pass
            if not lst:
                self._subs.pop(research_id, None)

    def publish(self, research_id: str, event: dict) -> None:
        # Sync-safe: subscribers pull via async get; queue.put_nowait works from any thread-safe caller.
        history = self._history.setdefault(research_id, [])
        history.append(event)
        if len(history) > self._max_history:
            del history[0 : len(history) - self._max_history]
        for q in self._subs.get(research_id, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop the oldest to keep pace
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass

    def finalize(self, research_id: str, result: Any) -> None:
        self.publish(
            research_id,
            {"stage": "done", "message": "complete", "detail": {"result": result}},
        )

    def clear(self, research_id: str) -> None:
        self._subs.pop(research_id, None)
        self._history.pop(research_id, None)


# Module-level singleton — good enough for a single-process server.
BROKER = ProgressBroker()
