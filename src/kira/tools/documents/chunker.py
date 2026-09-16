"""Sliding-window chunker with token approximation.

We don't have a tokenizer per-model wired here (that would tie us to a
specific model family). Instead we use a stable heuristic: ~4 characters
per token. Callers can override via `chars_per_token`.

Each chunk keeps its source `page` and its position in the file so the UI
can jump to it.
"""
from __future__ import annotations

from dataclasses import dataclass


DEFAULT_CHUNK_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 50
CHARS_PER_TOKEN = 4  # heuristic


@dataclass
class Chunk:
    index: int
    page: int | None
    content: str


def _sliding(text: str, chunk_chars: int, overlap_chars: int) -> list[str]:
    if not text:
        return []
    if chunk_chars <= 0:
        return [text]
    step = max(1, chunk_chars - overlap_chars)
    pieces: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        pieces.append(text[i : i + chunk_chars])
        if i + chunk_chars >= n:
            break
        i += step
    return pieces


def chunk_pages(
    pages: list[dict],
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    chars_per_token: int = CHARS_PER_TOKEN,
) -> list[Chunk]:
    """Chunk a parsed document's pages.

    Chunks never span pages — that keeps the `page` attribution honest.
    Short pages become one chunk each.
    """
    chunk_chars = chunk_tokens * chars_per_token
    overlap_chars = overlap_tokens * chars_per_token
    out: list[Chunk] = []
    idx = 0
    for entry in pages:
        page_num = entry.get("page")
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        for piece in _sliding(text, chunk_chars, overlap_chars):
            trimmed = piece.strip()
            if not trimmed:
                continue
            out.append(Chunk(index=idx, page=page_num, content=trimmed))
            idx += 1
    return out
