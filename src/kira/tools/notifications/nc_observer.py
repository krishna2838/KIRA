"""macOS Notification Center observer.

Registers a distributed-notification observer. Whenever an app posts an NS
user notification, the callback runs on the main NSRunLoop; we bounce the
payload into an asyncio queue that the consumer drains.

This requires the running process to have permission to observe user
notifications. On modern macOS versions Apple restricts what can be seen —
we fail soft and log an informational note when pyobjc isn't installed or
the observer can't attach.
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from typing import Optional

from kira.core.logger import get_logger


logger = get_logger("tools.notifications.nc")


class NCObserver:
    def __init__(self, event_loop: asyncio.AbstractEventLoop):
        self.loop = event_loop
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._available = False

    def available(self) -> bool:
        return self._available

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        try:
            import AppKit  # type: ignore  # noqa: F401
            import Foundation  # type: ignore  # noqa: F401
        except Exception as e:
            logger.info(f"NC observer disabled (pyobjc missing: {e})")
            self._available = False
            return
        self._available = True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="kira-nc-observer", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _emit(self, evt: dict) -> None:
        try:
            asyncio.run_coroutine_threadsafe(self.queue.put(evt), self.loop)
        except Exception as e:
            logger.debug(f"emit failed: {e}")

    def _run(self) -> None:
        import AppKit  # type: ignore
        import Foundation  # type: ignore

        center = Foundation.NSDistributedNotificationCenter.defaultCenter()

        class _Handler(Foundation.NSObject):
            outer = self

            def onNotification_(self_, notification):
                try:
                    name = str(notification.name() or "")
                    obj = str(notification.object() or "")
                    ui = dict(notification.userInfo() or {})
                    title = str(ui.get("title") or ui.get("NSTitle") or "")
                    body = str(ui.get("body") or ui.get("NSInformativeText") or "")
                    sender = str(ui.get("sender") or ui.get("NSSubtitle") or "") or None
                    self_.outer._emit({
                        "app_name": obj or "unknown",
                        "title": title or name,
                        "body": body,
                        "sender": sender,
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                except Exception as e:
                    logger.debug(f"nc callback error: {e}")

        try:
            handler = _Handler.alloc().init()
            # Broad observer: any notification with the standard name. Real
            # per-app notifications post distinct names; we observe them all
            # by using `None` and let the callback filter.
            center.addObserver_selector_name_object_(
                handler, b"onNotification:", None, None
            )
            # Pump the run loop until stopped.
            while not self._stop.is_set():
                Foundation.NSRunLoop.currentRunLoop().runUntilDate_(
                    Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.5)
                )
        except Exception as e:
            logger.info(f"NC observer failed: {e}")
            self._available = False


async def drain_into_store(observer: NCObserver, store, *, stop_event: asyncio.Event) -> None:
    """Long-running task: consume observer events and persist them."""
    while not stop_event.is_set():
        try:
            evt = await asyncio.wait_for(observer.queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        except Exception:
            continue
        try:
            await store.ingest(
                app_name=evt["app_name"],
                title=evt["title"],
                body=evt["body"],
                sender=evt.get("sender"),
            )
        except Exception as e:
            logger.debug(f"nc store ingest error: {e}")
