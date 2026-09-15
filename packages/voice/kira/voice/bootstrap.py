"""Voice bootstrap — build a VoicePipeline from a Config + brain reply fn."""
from __future__ import annotations

from typing import Awaitable, Callable

from kira.logger import get_logger

from kira.voice.audio import Microphone
from kira.voice.echo_detector import EchoDetector
from kira.voice.intent_judge import VoiceIntentJudge
from kira.voice.pipeline import VoicePipeline
from kira.voice.stt import WhisperSTT
from kira.voice.tts import PiperTTS
from kira.voice.vad import SileroVAD
from kira.voice.wake_word import WakeWordDetector


logger = get_logger("voice.bootstrap")


def build_pipeline(
    config,
    ollama_client,
    reply: Callable[[str], Awaitable[str]],
) -> VoicePipeline | None:
    if not config.voice.enabled:
        logger.info("Voice disabled in config")
        return None

    try:
        mic = Microphone(device=config.voice.input_device)
        from kira.voice.audio import Speaker
        speaker = Speaker(device=config.voice.output_device)
        wake = WakeWordDetector(
            models=config.voice.wake_word_models,
            threshold=config.voice.wake_word_threshold,
        )
        vad = SileroVAD()
        stt = WhisperSTT(
            model_size=config.voice.whisper_model,
            device=config.voice.whisper_device,
            compute_type=config.voice.whisper_compute_type,
        )
        tts = PiperTTS(
            voice_path=config.voice.piper_voice_path or None,
            speaker=speaker,
        )
        echo = EchoDetector()
        judge = VoiceIntentJudge(ollama_client, config.models.fast.model)

        return VoicePipeline(
            reply=reply,
            intent_judge=judge,
            mic=mic,
            wake=wake,
            vad=vad,
            stt=stt,
            tts=tts,
            echo=echo,
            wake_word_enabled=config.voice.wake_word_enabled,
        )
    except Exception as e:
        logger.warning(f"Voice pipeline build failed: {e}")
        return None
