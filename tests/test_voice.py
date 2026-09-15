"""Tests for voice primitives that don't require real audio hardware."""
import math

from kira.voice.echo_detector import EchoDetector
from kira.voice.intent_judge import _STOP_RE
from kira.voice.stt import WhisperSTT


def test_echo_detector_flags_repeat():
    d = EchoDetector()
    d.note_spoken("The weather is clear today.")
    assert d.is_echo("The weather is clear today")


def test_echo_detector_ignores_unrelated():
    d = EchoDetector()
    d.note_spoken("The weather is clear today.")
    assert not d.is_echo("Open my calendar please")


def test_echo_detector_expires():
    d = EchoDetector()
    d._last_text = "hello world"
    d._last_at = 0.0  # long expired
    assert not d.is_echo("hello world")


def test_stop_regex_matches_common_forms():
    for utter in ["stop", "wait", "hold on", "KIRA stop",
                  "never mind", "nevermind", "shut up", "pause"]:
        assert _STOP_RE.match(utter), f"missed stop utterance {utter!r}"


def test_stop_regex_rejects_normal():
    assert not _STOP_RE.match("please continue")
    assert not _STOP_RE.match("what's the weather")


def test_hallucination_filter_rejects_low_confidence():
    # logprob = -2.0 -> confidence ~0.135; well below 0.4
    assert not WhisperSTT._looks_real("Thanks for watching.", -2.0, 0.1)


def test_hallucination_filter_rejects_high_no_speech():
    assert not WhisperSTT._looks_real("hello there", math.log(0.9), 0.8)


def test_hallucination_filter_accepts_real_speech():
    assert WhisperSTT._looks_real(
        "please read my calendar for tomorrow", math.log(0.85), 0.05
    )


def test_hallucination_filter_rejects_known_phantoms():
    assert not WhisperSTT._looks_real("Thanks for watching!", math.log(0.9), 0.05)
    assert not WhisperSTT._looks_real("you", math.log(0.9), 0.05)
