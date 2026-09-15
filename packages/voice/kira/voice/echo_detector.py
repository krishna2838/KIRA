"""Echo filter — reject transcriptions of KIRA's own voice.

We compare an inbound STT string against the text KIRA most recently spoke.
Similarity is a normalized Levenshtein ratio via difflib. Anything above
`ECHO_THRESHOLD` is treated as feedback and dropped.

Cleared automatically after `MEMORY_SEC` seconds so a legitimate later
utterance that happens to quote KIRA's line still passes.
"""
from __future__ import annotations

import re
import time
from difflib import SequenceMatcher


ECHO_THRESHOLD = 0.8
MEMORY_SEC = 15.0
_WORD = re.compile(r"\w+")


def _normalize(text: str) -> str:
    return " ".join(_WORD.findall(text.lower()))


class EchoDetector:
    def __init__(self):
        self._last_text: str | None = None
        self._last_at: float = 0.0

    def note_spoken(self, text: str) -> None:
        n = _normalize(text)
        if n:
            self._last_text = n
            self._last_at = time.monotonic()

    def similarity(self, heard: str) -> float:
        if not self._last_text:
            return 0.0
        if time.monotonic() - self._last_at > MEMORY_SEC:
            return 0.0
        return SequenceMatcher(None, _normalize(heard), self._last_text).ratio()

    def is_echo(self, heard: str, threshold: float = ECHO_THRESHOLD) -> bool:
        return self.similarity(heard) >= threshold
