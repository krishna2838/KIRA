"""Voice Activity Detection via Silero VAD.

Silero wants 512-sample chunks at 16 kHz mono. We buffer incoming mic frames,
run inference, and report a speech probability per chunk. The caller decides
when a stream of "no speech" chunks marks the end of an utterance.
"""
from __future__ import annotations

from kira.core.logger import get_logger


logger = get_logger("voice.vad")

CHUNK = 512
SPEECH_THRESHOLD = 0.5
END_OF_SPEECH_MS = 700   # trailing silence to close an utterance
MIN_UTTERANCE_MS = 300   # ignore blips shorter than this


class SileroVAD:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._model = None
        self._utils = None
        self._buffer: list[float] = []
        # State
        self._in_speech = False
        self._silence_ms = 0
        self._speech_ms = 0
        self._captured: list[float] = []

    def load(self) -> bool:
        if self._model is not None:
            return True
        try:
            import torch  # type: ignore

            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                onnx=False,
                trust_repo=True,
            )
            self._model = model
            self._utils = utils
            logger.info("Silero VAD ready")
            return True
        except Exception as e:
            logger.info(f"VAD disabled ({e})")
            self._model = None
            return False

    def reset(self) -> None:
        self._buffer = []
        self._in_speech = False
        self._silence_ms = 0
        self._speech_ms = 0
        self._captured = []

    def process(self, frame_float32) -> dict:
        """Feed a mono float32 frame. Returns a status dict:

        { 'speech': bool, 'end': bool, 'captured': np.ndarray | None }

        - 'speech' — current chunk contains speech
        - 'end'    — an utterance just completed; 'captured' has the audio
        """
        try:
            import numpy as np  # type: ignore
            import torch  # type: ignore
        except Exception:
            return {"speech": False, "end": False, "captured": None}

        if self._model is None:
            return {"speech": False, "end": False, "captured": None}

        arr = np.asarray(frame_float32, dtype=np.float32).reshape(-1)
        self._buffer.extend(arr.tolist())

        end_flag = False
        captured = None
        ms_per_chunk = 1000.0 * CHUNK / self.sample_rate

        while len(self._buffer) >= CHUNK:
            chunk = np.array(self._buffer[:CHUNK], dtype=np.float32)
            self._buffer = self._buffer[CHUNK:]
            with_grad = torch.from_numpy(chunk)
            try:
                prob = float(
                    self._model(with_grad, self.sample_rate).item()  # type: ignore[operator]
                )
            except Exception as e:
                logger.debug(f"vad predict: {e}")
                prob = 0.0

            is_speech = prob >= SPEECH_THRESHOLD
            if is_speech:
                self._in_speech = True
                self._silence_ms = 0
                self._speech_ms += ms_per_chunk
                self._captured.extend(chunk.tolist())
            else:
                if self._in_speech:
                    self._silence_ms += ms_per_chunk
                    self._captured.extend(chunk.tolist())
                    if (
                        self._silence_ms >= END_OF_SPEECH_MS
                        and self._speech_ms >= MIN_UTTERANCE_MS
                    ):
                        captured = np.array(self._captured, dtype=np.float32)
                        end_flag = True
                        self.reset()
                        break

        return {"speech": self._in_speech, "end": end_flag, "captured": captured}
