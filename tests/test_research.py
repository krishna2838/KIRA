"""Tests for the research layer (offline-safe)."""
from kira.brain.verifier import Confidence, SourceRef, Verifier

from kira.tools.research.sources import classify_reliability


# ---- reliability ---------------------------------------------------------


def test_wikipedia_is_high_trust():
    assert classify_reliability("https://en.wikipedia.org/wiki/M4_(microarchitecture)") == "high"


def test_bbc_is_high_trust():
    assert classify_reliability("https://www.bbc.com/news/world-asia") == "high"


def test_medium_blog_marked_low():
    assert classify_reliability("https://medium.com/@random/post-123") == "low"


def test_unknown_is_medium():
    assert classify_reliability("https://example.com/thing") == "medium"


# ---- verifier ------------------------------------------------------------


def test_verifier_marks_supported_claim_known_and_cites():
    verifier = Verifier()
    sources = [
        SourceRef(
            id=1,
            url="https://apple.com",
            title="M4 chip overview",
            snippet=(
                "The Apple M4 uses second-generation 3-nanometer technology and "
                "has an improved neural engine capable of 38 trillion operations."
            ),
        )
    ]
    report = verifier.verify(
        "The Apple M4 uses 3-nanometer technology and includes a faster neural engine.",
        sources,
    )
    assert report.claims and report.claims[0].confidence == Confidence.KNOWN
    assert "[1]" in report.text
    assert 1 in report.used_source_ids


def test_verifier_hedges_unsupported_claim():
    verifier = Verifier()
    sources = [
        SourceRef(id=1, url="https://x", title="Weather", snippet="It rained a lot.")
    ]
    report = verifier.verify(
        "The Apollo mission cost twelve billion dollars.",
        sources,
    )
    # An assertion about a topic our sources don't cover — must be hedged.
    verdict = report.claims[0]
    assert verdict.confidence == Confidence.UNKNOWN
    assert report.text.lower().startswith("i think")


def test_verifier_preserves_hedged_language():
    verifier = Verifier()
    report = verifier.verify("I think this might be true.", [])
    assert report.claims[0].confidence == Confidence.INFERRED


def test_verifier_respects_pre_existing_citations():
    verifier = Verifier()
    text = "The M4 uses 3nm process [1]."
    report = verifier.verify(text, [SourceRef(id=1)])
    assert report.text == text
    assert 1 in report.used_source_ids
