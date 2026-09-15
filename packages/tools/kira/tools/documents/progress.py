"""Simple pub/sub for indexing progress (mirrors research/progress.py)."""
from __future__ import annotations

import asyncio


class IndexBroker:
    def __init__(self):
        self._subs: list[asyncio.Queue] = []
        self._history: list[dict] = []
        self._max_history = 200

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        for evt in self._history[-40:]:
            q.put_nowait(evt)
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subs.remove(q)
        except ValueError:
            pass

    def publish(self, event: dict) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            del self._history[0 : len(self._history) - self._max_history]
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass


BROKER = IndexBroker()
