"""Text-to-speech via Piper.

Piper synthesizes 22.05 kHz mono PCM per sentence. We stream sentence-by-
sentence so playback starts before the whole response is generated. The
Speaker respects `interrupt()` — any word-mid interruption halts playback
at the next PCM chunk boundary (a few tens of milliseconds).
"""
from __future__ import annotations

import io
import re
import wave

from kira.core.logger import get_logger

from kira.voice.audio import Speaker


logger = get_logger("voice.tts")


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def _sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT.split(text.strip())
    return [p for p in parts if p]


class PiperTTS:
    def __init__(self, voice_path: str | None = None, speaker: Speaker | None = None):
        # voice_path points at a .onnx file (with .onnx.json alongside).
        # A default English voice like en_US-lessac-medium is a good pick.
        import os
        self.voice_path = os.path.expanduser(voice_path) if voice_path else None
        self.speaker = speaker or Speaker(sample_rate=22050)
        self._voice = None
        self._interrupted = False

    def load(self) -> bool:
        if self._voice is not None:
            return True
        try:
            from piper.voice import PiperVoice  # type: ignore

            if not self.voice_path:
                raise RuntimeError(
                    "Piper voice path not configured (config.voice.piper_voice_path)"
                )
            self._voice = PiperVoice.load(self.voice_path)
            # Match sample rate to the voice
            if hasattr(self._voice, "config") and getattr(
                self._voice.config, "sample_rate", None
            ):
                self.speaker.sample_rate = int(self._voice.config.sample_rate)
            logger.info(f"Piper voice loaded: {self.voice_path}")
            return True
        except Exception as e:
            logger.info(f"TTS disabled ({e})")
            self._voice = None
            return False

    def interrupt(self) -> None:
        self._interrupted = True
        self.speaker.interrupt()

    def _new_utterance(self) -> None:
        self._interrupted = False
        self.speaker.clear_interrupt()

    def speak(self, text: str) -> bool:
        """Blocking: play `text` end-to-end. Returns True if finished, False
        if interrupted."""
        if self._voice is None or not text.strip():
            return False
        self._new_utterance()
        self.speaker.start()

        try:
            import numpy as np  # type: ignore
        except Exception:
            return False

        for sentence in _sentences(text):
            if self._interrupted:
                return False
            # Piper writes WAV frames into a buffer. We decode and stream.
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                self._voice.synthesize(sentence, w)  # type: ignore[union-attr]
            buf.seek(0)
            with wave.open(buf, "rb") as r:
                rate = r.getframerate()
                if rate != self.speaker.sample_rate:
                    self.speaker.stop()
                    self.speaker.sample_rate = rate
                    self.speaker.start()
                frames = r.readframes(r.getnframes())
            pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            # Chunked write so interrupt can fire in <=~40ms
            chunk = self.speaker.sample_rate // 25
            for i in range(0, len(pcm), chunk):
                if self._interrupted:
                    return False
                ok = self.speaker.write(pcm[i : i + chunk])
                if not ok:
                    return False
        return True

    def stop(self) -> None:
        self.interrupt()
        self.speaker.stop()
