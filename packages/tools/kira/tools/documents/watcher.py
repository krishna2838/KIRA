"""watchdog-based directory monitor with debounce.

Emits path changes onto an asyncio.Queue; a consumer coroutine reads batches
and calls `indexer.index_file(path, force=True)`. We coalesce rapid events
per path (a single "save" from most editors bursts several fs events).
"""
from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

from kira.logger import get_logger

from kira.tools.documents.parsers import SUPPORTED_EXTENSIONS


logger = get_logger("tools.documents.watcher")

DEBOUNCE_SEC = 1.5


class DocumentWatcher:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self._observer = None
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._stopped = False

    def start(self, paths: list[str]) -> bool:
        try:
            from watchdog.events import FileSystemEventHandler  # type: ignore
            from watchdog.observers import Observer  # type: ignore
        except Exception as e:
            logger.info(f"watchdog missing: {e}")
            return False

        outer = self

        class _Handler(FileSystemEventHandler):
            def _emit(self, path: str):
                if outer._stopped:
                    return
                p = Path(path)
                if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    return
                if p.name.startswith("."):
                    return
                with outer._lock:
                    outer._pending[str(p)] = time.monotonic()

            def on_modified(self, event):
                if not event.is_directory:
                    self._emit(event.src_path)

            def on_created(self, event):
                if not event.is_directory:
                    self._emit(event.src_path)

            def on_moved(self, event):
                if not event.is_directory:
                    self._emit(event.dest_path)

        obs = Observer()
        handler = _Handler()
        for p in paths:
            root = Path(p).expanduser()
            if root.is_dir():
                obs.schedule(handler, str(root), recursive=True)
        obs.start()
        self._observer = obs

        # Debounce loop: every 0.5s promote paths with age > DEBOUNCE_SEC.
        threading.Thread(target=self._debounce_loop, daemon=True).start()
        return True

    def _debounce_loop(self) -> None:
        while not self._stopped:
            time.sleep(0.5)
            now = time.monotonic()
            ready: list[str] = []
            with self._lock:
                for path, ts in list(self._pending.items()):
                    if now - ts >= DEBOUNCE_SEC:
                        ready.append(path)
                        self._pending.pop(path, None)
            for path in ready:
                try:
                    asyncio.run_coroutine_threadsafe(self.queue.put(path), self.loop)
                except Exception:
                    pass

    def stop(self) -> None:
        self._stopped = True
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:
                pass
        self._observer = None


async def drain_into_indexer(
    watcher: DocumentWatcher, indexer, *, stop_event: asyncio.Event
) -> None:
    while not stop_event.is_set():
        try:
            path = await asyncio.wait_for(watcher.queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        try:
            await indexer.reindex(path)
        except Exception as e:
            logger.debug(f"watch reindex failed for {path}: {e}")
