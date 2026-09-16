"""Keep the fast model warm and preload smart on the first user request.

Ollama unloads models after a couple of minutes of inactivity. On a
16GB M4 we can't keep both hot forever, so:

  - Ping the fast model at boot and every N minutes.
  - Preload the smart model on demand — the first time the router routes
    SMART, we fire a background one-token generate to page the weights in.
"""
from __future__ import annotations

import asyncio

from kira.core.logger import get_logger


logger = get_logger("brain.preload")


class ModelPreloader:
    def __init__(self, ollama, fast_model: str, smart_model: str,
                 keep_warm_sec: int = 240):
        self.ollama = ollama
        self.fast = fast_model
        self.smart = smart_model
        self.keep_warm_sec = keep_warm_sec
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._smart_loaded = False
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        # Warm the fast model in the BACKGROUND — loading a multi-GB model
        # can take 20s+, and we must not block server startup on it. The
        # periodic keep-warm loop does the first ping itself.
        self._task = asyncio.create_task(self._loop(), name="kira-preloader")

    async def _loop(self) -> None:
        # Immediate first ping, then keep warm on an interval.
        await self._ping(self.fast)
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.keep_warm_sec)
                return
            except asyncio.TimeoutError:
                await self._ping(self.fast)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (Exception, asyncio.CancelledError):
                pass
            self._task = None

    async def ensure_smart(self) -> None:
        """Fire-and-forget: warm the smart model without blocking a request."""
        async with self._lock:
            if self._smart_loaded:
                return
            self._smart_loaded = True
        asyncio.create_task(self._ping(self.smart))

    async def _ping(self, model: str) -> None:
        try:
            # Zero-work generate — just enough to page the weights in.
            await self.ollama.generate(
                model=model, prompt=" ", options={"num_predict": 1},
            )
        except Exception as e:
            logger.debug(f"preload ping {model} failed: {e}")
