"""Fast-model intent judge for voice.

Two questions:
  1. Is this transcription a *directed* utterance to KIRA (vs. background
     conversation the mic caught)? — used when there is no wake word gate.
  2. Is this a "stop / wait / never mind" style interruption? — used mid-TTS.

A tiny model like gemma4:e2b answers both in <300ms and reliably enough for
the pipeline. We fall back to plain-word matching if the model isn't
reachable.
"""
from __future__ import annotations

import re


STOP_WORDS = {
    "stop", "wait", "hold on", "hold on kira", "never mind", "nevermind",
    "shut up", "quiet", "silence", "pause", "cancel", "abort",
}

_STOP_RE = re.compile(
    r"^(kira,?\s+)?(stop|wait|hold on|never mind|nevermind|shut up|quiet|pause|cancel|abort)\b",
    re.IGNORECASE,
)


class VoiceIntentJudge:
    def __init__(self, ollama_client, model: str):
        self.ollama = ollama_client
        self.model = model

    async def is_stop_command(self, text: str) -> bool:
        clean = text.strip().lower()
        if not clean:
            return False
        if _STOP_RE.match(clean):
            return True
        if clean in STOP_WORDS:
            return True

        prompt = (
            "You are a strict classifier. The user is mid-conversation with a "
            "voice assistant named KIRA that is currently speaking. Does this "
            "utterance mean STOP the assistant? Answer only 'yes' or 'no'.\n\n"
            f"Utterance: {text}"
        )
        try:
            resp = await self.ollama.generate(
                model=self.model, prompt=prompt,
                options={"temperature": 0.0},
            )
        except Exception:
            return False
        return resp.strip().lower().startswith("y")

    async def is_directed_at_kira(self, text: str) -> bool:
        clean = text.strip().lower()
        if not clean:
            return False
        if "kira" in clean:
            return True

        prompt = (
            "The following was overheard in a room. Is the speaker addressing "
            "the personal AI assistant KIRA directly (a command, question, or "
            "request), or is it background conversation between other people? "
            "Reply only 'kira' or 'other'.\n\n"
            f"Utterance: {text}"
        )
        try:
            resp = await self.ollama.generate(
                model=self.model, prompt=prompt,
                options={"temperature": 0.0},
            )
        except Exception:
            return True  # default to answering when the model isn't reachable
        return resp.strip().lower().startswith("k")
