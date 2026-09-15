"""Voice pipeline orchestrator.

    Microphone → WakeWord → VAD → STT → EchoFilter → IntentJudge → Brain → TTS → Speaker

Barge-in behavior:
    - If the user starts speaking while `state == SPEAKING`, VAD picks it up.
      We immediately `tts.interrupt()`, drop the current playback, and route
      the new utterance through the pipeline as usual.
    - If the transcription is classified as a stop command by the intent
      judge, we skip the brain entirely and just return to IDLE.

State is exposed via `snapshot()` for the /api/voice/status endpoint and
broadcast to subscribers (WebSocket) via `on_state_change`.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Awaitable, Callable, Optional

from kira.logger import get_logger

from kira.voice.audio import Microphone
from kira.voice.echo_detector import EchoDetector
from kira.voice.intent_judge import VoiceIntentJudge
from kira.voice.stt import WhisperSTT
from kira.voice.tts import PiperTTS
from kira.voice.types import VoiceState
from kira.voice.vad import SileroVAD
from kira.voice.wake_word import WakeWordDetector


logger = get_logger("voice.pipeline")


StateListener = Callable[[dict], None]
ReplyFn = Callable[[str], Awaitable[str]]  # (user_text) -> assistant_text


class VoicePipeline:
    def __init__(
        self,
        *,
        reply: ReplyFn,
        intent_judge: VoiceIntentJudge,
        mic: Microphone | None = None,
        wake: WakeWordDetector | None = None,
        vad: SileroVAD | None = None,
        stt: WhisperSTT | None = None,
        tts: PiperTTS | None = None,
        echo: EchoDetector | None = None,
        wake_word_enabled: bool = True,
    ):
        self.reply = reply
        self.judge = intent_judge
        self.mic = mic or Microphone()
        self.wake = wake or WakeWordDetector()
        self.vad = vad or SileroVAD()
        self.stt = stt or WhisperSTT()
        self.tts = tts or PiperTTS()
        self.echo = echo or EchoDetector()
        self.wake_word_enabled = wake_word_enabled

        self._state = VoiceState.IDLE
        self._state_lock = threading.Lock()
        self._listeners: list[StateListener] = []
        self._active = False
        self._task: Optional[asyncio.Task] = None
        self._last_transcript = ""
        self._last_assistant_text = ""

    # -- lifecycle -----------------------------------------------------

    async def start(self) -> None:
        if self._active:
            return
        self._active = True
        # Best-effort model warm-up. Missing deps are OK — we still support
        # push-to-talk manual capture from the client without models.
        self.wake.load()
        self.vad.load()
        self.stt.load()
        self.tts.load()
        self.mic.start()
        self._set_state(VoiceState.IDLE)
        self._task = asyncio.create_task(self._loop())
        logger.info("Voice pipeline started")

    async def stop(self) -> None:
        self._active = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        self.tts.stop()
        self.mic.stop()
        self._set_state(VoiceState.IDLE)

    def add_listener(self, cb: StateListener) -> None:
        self._listeners.append(cb)

    def remove_listener(self, cb: StateListener) -> None:
        try:
            self._listeners.remove(cb)
        except ValueError:
            pass

    # -- state ---------------------------------------------------------

    def snapshot(self) -> dict:
        return {
            "state": self._state.value,
            "active": self._active,
            "wake_word_enabled": self.wake_word_enabled,
            "last_transcript": self._last_transcript,
        }

    def set_wake_word_enabled(self, enabled: bool) -> None:
        self.wake_word_enabled = enabled

    def _set_state(self, state: VoiceState) -> None:
        with self._state_lock:
            if state == self._state:
                return
            self._state = state
        snap = self.snapshot()
        for cb in list(self._listeners):
            try:
                cb(snap)
            except Exception as e:
                logger.debug(f"listener error: {e}")

    # -- main loop -----------------------------------------------------

    async def _loop(self) -> None:
        capture_active = not self.wake_word_enabled

        while self._active:
            frame = await self.mic.read(timeout=1.0)
            if frame is None:
                continue

            # Wake word gate
            if not capture_active and self.wake_word_enabled:
                triggered = self.wake.process(frame)
                if triggered:
                    logger.info(f"wake word: {triggered}")
                    self.vad.reset()
                    capture_active = True
                    self._set_state(VoiceState.LISTENING)
                continue

            # Speech capture
            vad_out = self.vad.process(frame)

            # Barge-in: user talking during TTS.
            if self._state == VoiceState.SPEAKING and vad_out["speech"]:
                logger.info("barge-in detected — stopping TTS")
                self.tts.interrupt()
                self._set_state(VoiceState.LISTENING)

            if not vad_out["end"]:
                if vad_out["speech"] and self._state != VoiceState.LISTENING:
                    self._set_state(VoiceState.LISTENING)
                continue

            audio = vad_out["captured"]
            if audio is None:
                continue

            # If wake-word gated, close the capture and go back to idle after
            # this turn. Push-to-talk / always-on mode stays open.
            reopen_after = not self.wake_word_enabled
            capture_active = reopen_after

            await self._handle_utterance(audio)
            if not reopen_after:
                self._set_state(VoiceState.IDLE)

    async def _handle_utterance(self, audio) -> None:
        self._set_state(VoiceState.THINKING)
        transcription = await asyncio.to_thread(self.stt.transcribe, audio)
        if transcription is None:
            self._set_state(VoiceState.IDLE)
            return
        text = transcription.text.strip()
        if not text:
            self._set_state(VoiceState.IDLE)
            return

        self._last_transcript = text

        # Echo filter — don't answer our own voice.
        if self.echo.is_echo(text):
            logger.info(f"echo dropped: {text!r}")
            self._set_state(VoiceState.IDLE)
            return

        # Stop-word detection (mid-conversation).
        if await self.judge.is_stop_command(text):
            logger.info(f"stop command: {text!r}")
            self.tts.interrupt()
            self._set_state(VoiceState.IDLE)
            return

        # Room-noise filter when there's no wake word gate.
        if not self.wake_word_enabled:
            directed = await self.judge.is_directed_at_kira(text)
            if not directed:
                logger.debug(f"undirected noise: {text!r}")
                self._set_state(VoiceState.IDLE)
                return

        try:
            reply_text = await self.reply(text)
        except Exception as e:
            logger.warning(f"reply failed: {e}")
            self._set_state(VoiceState.ERROR)
            return

        self._last_assistant_text = reply_text
        self.echo.note_spoken(reply_text)

        # Mute the mic input into wake/vad while KIRA speaks so we don't
        # feed our own audio back into the pipeline. (Barge-in still works
        # via VAD because we un-mute right after.)
        self._set_state(VoiceState.SPEAKING)
        self.mic.set_muted(True)
        try:
            await asyncio.to_thread(self.tts.speak, reply_text)
        finally:
            self.mic.set_muted(False)
        self._set_state(VoiceState.IDLE)
