"""Audio I/O — microphone capture and speaker playback.

Uses sounddevice (portaudio) for cross-platform capture on macOS/Linux/Win.
Both the input stream and the output stream are 16 kHz mono float32.

Frames are queued as raw `numpy.ndarray` chunks; the pipeline is responsible
for down/up-mixing to whatever a model wants.
"""
from __future__ import annotations

import asyncio
import queue
import threading
from typing import Callable, Optional

from kira.core.logger import get_logger

from kira.voice.types import FRAME_SAMPLES, SAMPLE_RATE


logger = get_logger("voice.audio")


def _lazy_sd():
    try:
        import sounddevice as sd  # type: ignore
        return sd
    except Exception as e:
        raise RuntimeError(
            "sounddevice (portaudio) is required for voice: "
            f"pip install sounddevice — original error: {e}"
        ) from e


def _lazy_np():
    try:
        import numpy as np  # type: ignore
        return np
    except Exception as e:
        raise RuntimeError("numpy is required for voice") from e


class Microphone:
    """Non-blocking mic capture. Frames are pushed to a queue every ~20ms.

    Use `read()` in the async pipeline (returns FRAME_SAMPLES floats) or
    subscribe with `on_frame` for a callback style.
    """

    def __init__(self, device: Optional[int | str] = None,
                 sample_rate: int = SAMPLE_RATE,
                 frame_samples: int = FRAME_SAMPLES):
        self.device = device
        self.sample_rate = sample_rate
        self.frame_samples = frame_samples
        self._queue: "queue.Queue" = queue.Queue(maxsize=200)
        self._stream = None
        self._on_frame: Optional[Callable[[object], None]] = None
        self._muted = False

    def start(self) -> None:
        if self._stream is not None:
            return
        sd = _lazy_sd()

        def _cb(indata, frames, time_info, status):  # noqa: ARG001
            if status:
                logger.debug(f"mic status: {status}")
            if self._muted:
                return
            # Copy — sounddevice reuses the buffer.
            chunk = indata.copy().reshape(-1)
            try:
                self._queue.put_nowait(chunk)
            except queue.Full:
                # Drop oldest to make room; this keeps us near-real-time.
                try:
                    self._queue.get_nowait()
                    self._queue.put_nowait(chunk)
                except queue.Empty:
                    pass
            if self._on_frame is not None:
                try:
                    self._on_frame(chunk)
                except Exception as e:
                    logger.debug(f"on_frame callback error: {e}")

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.frame_samples,
            device=self.device,
            channels=1,
            dtype="float32",
            callback=_cb,
        )
        self._stream.start()
        logger.info(
            f"Microphone started (device={self.device!r}, "
            f"rate={self.sample_rate}, frame={self.frame_samples})"
        )

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception as e:
            logger.warning(f"mic stop error: {e}")
        self._stream = None

    def set_muted(self, muted: bool) -> None:
        """Ignore incoming mic frames without tearing the stream down.

        Used while TTS is playing so we don't feed KIRA's own speech into
        the wake-word detector.
        """
        self._muted = muted

    def on_frame(self, cb: Callable[[object], None]) -> None:
        self._on_frame = cb

    async def read(self, timeout: float = 1.0):
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None, lambda: self._queue.get(timeout=timeout)
            )
        except queue.Empty:
            return None


class Speaker:
    """Streaming playback. `write(np.float32 mono @ 16k)` blocks briefly."""

    def __init__(self, device: Optional[int | str] = None,
                 sample_rate: int = SAMPLE_RATE):
        self.device = device
        self.sample_rate = sample_rate
        self._stream = None
        self._interrupt = threading.Event()

    def start(self) -> None:
        if self._stream is not None:
            return
        sd = _lazy_sd()
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            device=self.device,
            channels=1,
            dtype="float32",
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        self._stream = None

    def interrupt(self) -> None:
        """Signal any in-flight write loop to bail out ASAP."""
        self._interrupt.set()

    def clear_interrupt(self) -> None:
        self._interrupt.clear()

    def write(self, chunk) -> bool:
        """Return True if the chunk played fully; False if interrupted."""
        if self._stream is None:
            self.start()
        if self._interrupt.is_set():
            return False
        try:
            self._stream.write(chunk)  # type: ignore[union-attr]
        except Exception as e:
            logger.warning(f"speaker write failed: {e}")
            return False
        return not self._interrupt.is_set()


def list_devices() -> dict:
    """Enumerate available audio devices for the settings UI."""
    try:
        sd = _lazy_sd()
    except RuntimeError as e:
        return {"available": False, "reason": str(e), "input": [], "output": []}
    devices = sd.query_devices()
    return {
        "available": True,
        "input": [
            {"index": i, "name": d["name"], "channels": d["max_input_channels"]}
            for i, d in enumerate(devices) if d["max_input_channels"] > 0
        ],
        "output": [
            {"index": i, "name": d["name"], "channels": d["max_output_channels"]}
            for i, d in enumerate(devices) if d["max_output_channels"] > 0
        ],
        "default_input": sd.default.device[0] if sd.default.device else None,
        "default_output": sd.default.device[1] if sd.default.device else None,
    }
