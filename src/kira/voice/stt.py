"""Speech-to-text using faster-whisper (`small.en` on Apple Silicon).

Hallucination filter — we drop transcriptions that look like phantom output
from silence/noise:

  - avg_logprob < LOGPROB_MIN            (confidence too low)
  - no_speech_prob > NO_SPEECH_MAX       (whisper itself says nothing was said)
  - text matches a known "Thanks for watching!"-style phantom list

This is exactly the class of bug that has plagued isair/jarvis and other
Whisper-based assistants.
"""
from __future__ import annotations

import re

from kira.core.logger import get_logger

from kira.voice.types import SAMPLE_RATE, Transcription


logger = get_logger("voice.stt")

LOGPROB_MIN = 0.4        # spec: reject when confidence below 0.4
NO_SPEECH_MAX = 0.6      # spec: reject when no_speech_probability > 0.6
MIN_CHARS = 2

# Known Whisper phantom transcriptions — stored already normalized (no
# trailing punctuation) so they match after _STRIP runs on inbound text.
_HALLUCINATION_TEXTS = {
    "thank you",
    "thanks for watching",
    "thank you for watching",
    "you",
    "please subscribe",
    "like and subscribe",
    "bye",
    "yeah",
    "",
}
_STRIP = re.compile(r"[\s\.\?!,;:]+$")


class WhisperSTT:
    def __init__(
        self,
        model_size: str = "small.en",
        device: str = "auto",
        compute_type: str = "int8",
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def load(self) -> bool:
        if self._model is not None:
            return True
        try:
            from faster_whisper import WhisperModel  # type: ignore

            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info(f"faster-whisper ready ({self.model_size})")
            return True
        except Exception as e:
            logger.info(f"STT disabled ({e})")
            self._model = None
            return False

    def transcribe(self, audio_float32) -> Transcription | None:
        if self._model is None:
            return None
        try:
            import numpy as np  # type: ignore
        except Exception:
            return None

        arr = np.asarray(audio_float32, dtype=np.float32).reshape(-1)
        if arr.size < SAMPLE_RATE // 4:
            # < 250ms — not worth running whisper on
            return None

        try:
            segments, info = self._model.transcribe(  # type: ignore[union-attr]
                arr,
                language="en",
                vad_filter=False,   # we already ran Silero VAD upstream
                beam_size=1,
                no_speech_threshold=0.6,
                condition_on_previous_text=False,
            )
            seg_list = list(segments)
        except Exception as e:
            logger.warning(f"whisper transcribe failed: {e}")
            return None

        if not seg_list:
            return None

        text = "".join(s.text for s in seg_list).strip()
        avg_logprob = sum(s.avg_logprob for s in seg_list) / len(seg_list)
        no_speech_prob = max(s.no_speech_prob for s in seg_list)
        duration = arr.size / float(SAMPLE_RATE)

        if not self._looks_real(text, avg_logprob, no_speech_prob):
            logger.debug(
                f"discarded transcription {text!r} "
                f"(logprob={avg_logprob:.2f}, no_speech={no_speech_prob:.2f})"
            )
            return None

        return Transcription(
            text=text,
            avg_logprob=avg_logprob,
            no_speech_prob=no_speech_prob,
            duration_sec=duration,
        )

    # -- hallucination filter -------------------------------------------

    @staticmethod
    def _looks_real(text: str, logprob: float, no_speech_prob: float) -> bool:
        if len(text) < MIN_CHARS:
            return False
        # avg_logprob comes back negative from Whisper; the spec's "below 0.4"
        # is the "confidence" reading, i.e. exp(logprob).
        import math
        confidence = math.exp(logprob) if logprob < 0 else logprob
        if confidence < LOGPROB_MIN:
            return False
        if no_speech_prob > NO_SPEECH_MAX:
            return False
        normalized = _STRIP.sub("", text.strip().lower())
        if normalized in _HALLUCINATION_TEXTS:
            return False
        return True
