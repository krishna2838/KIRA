"""Wake word detection via openWakeWord.

Runs in the same asyncio loop as the pipeline — the model is fast on CPU,
so keeping it in-process is fine. We chunk the incoming mic stream into the
80ms windows openWakeWord expects.

When the detector never loads (missing dependency, missing model file), the
detector transparently returns "never triggered", so voice can still work
via the manual push-to-talk path.
"""
from __future__ import annotations

from kira.logger import get_logger

from kira.voice.types import SAMPLE_RATE


logger = get_logger("voice.wake_word")


class WakeWordDetector:
    def __init__(
        self,
        models: list[str] | None = None,
        threshold: float = 0.5,
        cooldown_ms: int = 1500,
    ):
        # openWakeWord ships "hey_jarvis" and "alexa" by default; a custom
        # KIRA model can be dropped in as a .onnx path here.
        self.models = models or ["hey_jarvis"]
        self.threshold = threshold
        self.cooldown_ms = cooldown_ms
        self._model = None
        self._last_trigger_ms = 0.0
        self._buffer: list[float] = []
        # openWakeWord internal frame size, 16k mono int16.
        self._window_samples = 1280  # 80ms

    def load(self) -> bool:
        if self._model is not None:
            return True
        try:
            from openwakeword.model import Model  # type: ignore

            self._model = Model(wakeword_models=self.models)
            logger.info(f"Wake word ready: {self.models}")
            return True
        except Exception as e:
            logger.info(f"Wake word disabled ({e})")
            self._model = None
            return False

    def unload(self) -> None:
        self._model = None
        self._buffer = []

    def process(self, frame_float32) -> str | None:
        """Feed a mono float32 frame (any length). Return the model name that
        triggered above threshold, or None."""
        if self._model is None:
            return None
        import time

        # Convert float32 [-1,1] -> int16 for openWakeWord
        try:
            import numpy as np  # type: ignore
        except Exception:
            return None

        arr = np.asarray(frame_float32, dtype=np.float32)
        pcm16 = np.clip(arr * 32768.0, -32768, 32767).astype(np.int16)
        self._buffer.extend(pcm16.tolist())

        triggered: str | None = None
        while len(self._buffer) >= self._window_samples:
            window = np.array(
                self._buffer[: self._window_samples], dtype=np.int16
            )
            self._buffer = self._buffer[self._window_samples :]
            try:
                scores = self._model.predict(window)  # type: ignore[union-attr]
            except Exception as e:
                logger.debug(f"wake predict error: {e}")
                continue
            now_ms = time.monotonic() * 1000.0
            for name, score in (scores or {}).items():
                if (
                    score >= self.threshold
                    and (now_ms - self._last_trigger_ms) > self.cooldown_ms
                ):
                    self._last_trigger_ms = now_ms
                    triggered = name
        return triggered
