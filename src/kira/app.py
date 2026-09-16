"""KIRA macOS menu-bar app — the PRIMARY interface.

Architecture:

  main thread            ──►  Cocoa (rumps) event loop, menu bar UI
    │
    ├─ background asyncio ──► uvicorn (Ollama-facing FastAPI on :8750)
    │                          → so the browser / phone / other tools all
    │                            keep working
    │
    └─ background asyncio ──► VoicePipeline
                                openWakeWord → Silero VAD → faster-whisper
                                → memory-aware reply via httpx → Piper TTS

The rumps title is a colored dot that reflects the voice pipeline's state:
  ⚫ idle · 🔵 listening · 🟡 thinking · 🟢 speaking · 🔴 error

Menu:
  • Listening… / Muted
  • Mute / Unmute
  • Open Web UI       (http://localhost:5173)
  • Open on Phone     (shows the LAN URL)
  • Quit

Cmd+Shift+K globally toggles the wake-word gate on/off (pynput; needs
Accessibility permission — falls back silently when it isn't granted).
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from typing import Optional


STATE_ICONS = {
    "idle": "⚫",
    "listening": "🔵",
    "thinking": "🟡",
    "speaking": "🟢",
    "searching": "🔵",
    "executing": "🟡",
    "error": "🔴",
    "success": "🟢",
}


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.4)
    try:
        return s.connect_ex((host, port)) == 0
    except Exception:
        return False
    finally:
        s.close()


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class _BackgroundLoop:
    """One asyncio event loop pinned to a daemon thread. All async work
    (server + voice pipeline) runs here so the rumps main thread stays
    free for Cocoa."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._t = threading.Thread(target=self._run, name="kira-async", daemon=True)
        self._t.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)


class KiraApp:
    """Menu-bar orchestrator."""

    def __init__(self):
        # Import rumps lazily so importing this module on non-macOS doesn't
        # crash — for tests, imports, etc.
        try:
            import rumps  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "rumps is required for the menu-bar app (macOS only): " + str(e)
            ) from e

        self.rumps = rumps
        self.app = rumps.App("KIRA", title="⚫ KIRA", quit_button=None)
        self.status_item = rumps.MenuItem("Starting…")
        self.mute_item = rumps.MenuItem("Mute", callback=self._on_mute)
        self.web_item = rumps.MenuItem("Open Web UI", callback=self._on_web)
        self.phone_item = rumps.MenuItem("Open on Phone", callback=self._on_phone)
        self.reindex_item = rumps.MenuItem("Reindex Documents", callback=self._on_reindex)
        self.quit_item = rumps.MenuItem("Quit", callback=self._on_quit)
        self.app.menu = [
            self.status_item, None,
            self.mute_item, None,
            self.web_item, self.phone_item, None,
            self.reindex_item, None,
            self.quit_item,
        ]

        self.loop_bg = _BackgroundLoop()
        self.server_proc: Optional[subprocess.Popen] = None
        self.pipeline = None
        self.muted = False
        self._starting = True

        self._start_server()
        # Small delay so uvicorn is listening before the voice pipeline
        # tries to POST /api/chat.
        threading.Timer(2.0, self._start_voice).start()
        self._register_hotkey()

    # -- server ------------------------------------------------------

    def _start_server(self) -> None:
        # If a KIRA server is already listening on 8750 (another launch, a
        # dev.sh run, or a leftover), reuse it instead of spawning a second
        # uvicorn that would fail to bind.
        if _port_in_use(8750):
            self.server_proc = None
            self.status_item.title = "Using existing server on :8750"
            return

        env = os.environ.copy()
        # Ensure the child uvicorn can import `kira` even if the editable
        # .pth isn't honored — src/ is two levels up from this file.
        from pathlib import Path
        src = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        cmd = [
            sys.executable, "-m", "uvicorn",
            "kira.server.app:create_app", "--factory",
            "--host", "0.0.0.0", "--port", "8750",
        ]
        self.server_proc = subprocess.Popen(cmd, env=env)
        self.status_item.title = "Server booting…"

    # -- voice pipeline ----------------------------------------------

    def _start_voice(self) -> None:
        # The menu bar app MUST stay up even if voice can't initialize
        # (missing models, no audio device, import errors). Any failure
        # here degrades to text-only: the server + Web UI still work.
        try:
            self._start_voice_inner()
        except Exception as e:
            self.pipeline = None
            self._starting = False
            self.status_item.title = "Voice unavailable (text-only)"
            self.mute_item.set_callback(None)
            try:
                self.rumps.notification(
                    "KIRA", "Voice unavailable",
                    f"Running in text-only mode. Web UI still works. ({type(e).__name__})",
                )
            except Exception:
                pass

    def _start_voice_inner(self) -> None:
        from kira.brain.ollama_client import OllamaClient
        from kira.core.config import get_config
        from kira.voice.bootstrap import build_pipeline

        cfg = get_config()
        ollama = OllamaClient()

        # Reply function — POSTs to the just-started FastAPI so voice
        # answers ride on the same memory + tool + confidence stack the
        # web UI uses.
        import httpx
        client = httpx.AsyncClient(base_url="http://127.0.0.1:8750", timeout=90.0)

        async def reply(user_text: str) -> str:
            # Try up to a few times while uvicorn finishes booting.
            for attempt in range(6):
                try:
                    r = await client.post("/api/chat", json={"message": user_text})
                    r.raise_for_status()
                    data = r.json()
                    return data.get("message", {}).get("content", "")
                except Exception:
                    if attempt == 5:
                        return "The server isn't ready yet. Try again in a moment."
                    await asyncio.sleep(1.0)
            return ""

        pipeline = build_pipeline(cfg, ollama, reply)
        if pipeline is None:
            self.status_item.title = "Voice disabled — see config/voice"
            return
        self.pipeline = pipeline
        pipeline.add_listener(self._on_voice_state)

        fut = self.loop_bg.submit(pipeline.start())
        fut.add_done_callback(self._after_voice_start)

    def _after_voice_start(self, fut) -> None:
        self._starting = False
        exc = None
        try:
            exc = fut.exception()
        except Exception:
            pass
        if exc is not None:
            self.pipeline = None
            self.status_item.title = "Voice unavailable (text-only)"
        else:
            self.status_item.title = "Listening for 'Hey KIRA'"

    def _on_voice_state(self, snap: dict) -> None:
        state = str(snap.get("state") or "idle")
        icon = STATE_ICONS.get(state, "⚫")
        self.app.title = f"{icon} KIRA"
        if not self._starting:
            self.status_item.title = f"{state.title()}"

    # -- menu callbacks ---------------------------------------------

    def _on_mute(self, sender) -> None:
        self.muted = not self.muted
        sender.title = "Unmute" if self.muted else "Mute"
        if self.pipeline is not None:
            self.pipeline.mic.set_muted(self.muted)
        self.status_item.title = "Muted" if self.muted else "Listening for 'Hey KIRA'"

    def _on_web(self, _sender) -> None:
        webbrowser.open("http://localhost:5173")

    def _on_phone(self, _sender) -> None:
        ip = _local_ip()
        self.rumps.notification(
            "KIRA — Open on phone",
            f"On the same Wi-Fi:",
            f"http://{ip}:8750",
        )

    def _on_reindex(self, _sender) -> None:
        # Fire and forget — the server has an endpoint for this.
        import httpx
        try:
            httpx.post(
                "http://127.0.0.1:8750/api/documents/index_directory",
                json={"path": "~/Documents", "force": False},
                timeout=5.0,
            )
            self.rumps.notification("KIRA", "Documents", "Reindexing queued.")
        except Exception:
            pass

    def _on_quit(self, _sender) -> None:
        try:
            if self.pipeline is not None:
                fut = self.loop_bg.submit(self.pipeline.stop())
                try:
                    fut.result(timeout=3.0)
                except Exception:
                    pass
        finally:
            if self.server_proc is not None:
                try:
                    self.server_proc.terminate()
                    for _ in range(30):
                        if self.server_proc.poll() is not None:
                            break
                        time.sleep(0.1)
                    if self.server_proc.poll() is None:
                        self.server_proc.kill()
                except Exception:
                    pass
            self.rumps.quit_application()

    # -- global hotkey ----------------------------------------------

    def _register_hotkey(self) -> None:
        """Cmd+Shift+K toggles the wake-word gate (aka mute).

        Pynput needs macOS Accessibility permission — fails soft when it
        isn't granted; we ship without the shortcut and the menu still
        works.
        """
        try:
            from pynput import keyboard  # type: ignore
        except Exception:
            return

        def on_activate():
            self._on_mute(self.mute_item)

        hk = keyboard.GlobalHotKeys({"<cmd>+<shift>+k": on_activate})
        try:
            hk.start()
        except Exception:
            return

    # -- lifecycle --------------------------------------------------

    def run(self) -> None:
        try:
            self.app.run()
        finally:
            # If rumps exits without going through _on_quit (e.g. the user
            # kills the process), still tear the server down cleanly.
            if self.server_proc is not None and self.server_proc.poll() is None:
                self.server_proc.terminate()


def main() -> None:
    if sys.platform != "darwin":
        print("kira.app is macOS-only (rumps). Use `bash scripts/dev.sh` on other platforms.")
        sys.exit(1)
    KiraApp().run()


if __name__ == "__main__":
    main()
