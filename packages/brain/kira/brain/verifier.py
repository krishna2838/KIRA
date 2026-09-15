"""Anti-hallucination layer.

Given an assistant draft answer and the sources/tool-results the model saw,
we split the answer into claim-sized sentences, classify each as KNOWN,
INFERRED, or UNKNOWN, hedge UNKNOWN claims, and append inline citations for
claims tied to a specific source.

A CLAIM is "known" when at least one supplied source snippet lexically
supports it (fraction of content words that appear in some source snippet
above KNOWN_OVERLAP). Otherwise, if it looks like an assertion of fact
(no hedging language already present), we mark it UNKNOWN and rewrite the
sentence with a soft hedge.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Confidence(str, Enum):
    KNOWN = "known"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


KNOWN_OVERLAP = 0.4
_HEDGE_RE = re.compile(
    r"\b(i think|i believe|maybe|might|could|possibly|likely|probably|"
    r"seems?|apparently|based on|reportedly|allegedly)\b",
    re.IGNORECASE,
)
_ASSERTION_HINTS = re.compile(
    r"\b(is|are|was|were|has|have|will|does|do|costs?|equals?|contains?)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-z0-9\-]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class SourceRef:
    id: int
    url: str = ""
    title: str = ""
    snippet: str = ""


@dataclass
class ClaimVerdict:
    sentence: str
    confidence: Confidence
    supporting_source_ids: list[int]
    rewritten: str


@dataclass
class VerificationReport:
    text: str                 # rewritten, hedged, cited
    claims: list[ClaimVerdict]
    used_source_ids: list[int]


def _content_words(text: str) -> set[str]:
    return {
        w.lower() for w in _WORD.findall(text)
        if len(w) > 3 and not w.isdigit()
    }


class Verifier:
    def __init__(self, router=None):
        self.router = router

    def classify_claim(
        self, sentence: str, sources: list[SourceRef]
    ) -> tuple[Confidence, list[int]]:
        words = _content_words(sentence)
        if not words:
            return Confidence.INFERRED, []

        support: list[tuple[int, float]] = []
        for src in sources:
            src_words = _content_words(f"{src.title} {src.snippet}")
            if not src_words:
                continue
            overlap = len(words & src_words) / len(words)
            if overlap >= KNOWN_OVERLAP:
                support.append((src.id, overlap))

        if support:
            support.sort(key=lambda p: p[1], reverse=True)
            return Confidence.KNOWN, [sid for sid, _ in support[:3]]

        if _HEDGE_RE.search(sentence):
            return Confidence.INFERRED, []

        if _ASSERTION_HINTS.search(sentence):
            return Confidence.UNKNOWN, []

        return Confidence.INFERRED, []

    def hedge(self, sentence: str) -> str:
        if _HEDGE_RE.search(sentence):
            return sentence
        lead, rest = sentence[:1], sentence[1:]
        return f"I think {lead.lower()}{rest}" if lead.isalpha() else f"I think {sentence}"

    def annotate(
        self, sentence: str, source_ids: list[int]
    ) -> str:
        if not source_ids:
            return sentence
        cites = "".join(f"[{i}]" for i in source_ids)
        if sentence.endswith((".", "!", "?")):
            return sentence[:-1] + " " + cites + sentence[-1]
        return sentence + " " + cites

    def verify(
        self, text: str, sources: list[SourceRef]
    ) -> VerificationReport:
        # Skip if the model already inlined [n] citations — respect them.
        if re.search(r"\[\d+\]", text):
            return VerificationReport(
                text=text, claims=[], used_source_ids=self._extract_cited(text)
            )

        pieces = _SENTENCE_SPLIT.split(text.strip())
        claims: list[ClaimVerdict] = []
        rewritten_parts: list[str] = []
        used: set[int] = set()

        for sentence in pieces:
            s = sentence.strip()
            if not s:
                continue
            conf, source_ids = self.classify_claim(s, sources)
            rewritten = s
            if conf == Confidence.UNKNOWN:
                rewritten = self.hedge(s)
            elif conf == Confidence.KNOWN and source_ids:
                rewritten = self.annotate(s, source_ids)
                used.update(source_ids)
            claims.append(
                ClaimVerdict(
                    sentence=s,
                    confidence=conf,
                    supporting_source_ids=source_ids,
                    rewritten=rewritten,
                )
            )
            rewritten_parts.append(rewritten)

        return VerificationReport(
            text=" ".join(rewritten_parts),
            claims=claims,
            used_source_ids=sorted(used),
        )

    @staticmethod
    def _extract_cited(text: str) -> list[int]:
        return sorted({int(m) for m in re.findall(r"\[(\d+)\]", text)})
