"""Shared types for the voice subsystem."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VoiceState(str, Enum):
    IDLE = "idle"          # Listening for wake word
    LISTENING = "listening"  # Wake word tripped, capturing utterance
    THINKING = "thinking"   # STT + brain in flight
    SPEAKING = "speaking"   # TTS playback
    ERROR = "error"


@dataclass
class Transcription:
    text: str
    avg_logprob: float
    no_speech_prob: float
    duration_sec: float


SAMPLE_RATE = 16000       # every model in the pipeline wants 16k mono
FRAME_MS = 20             # 320 samples @ 16k
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
