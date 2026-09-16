"""Tests for document pipeline pieces that don't need external libs."""
from kira.core.permissions import PermissionEngine
from kira.tools.documents.chunker import chunk_pages
from kira.tools.documents.parsers import detect_kind
from kira.core.types import RiskLevel


# ---- chunker -----------------------------------------------------------


def test_chunker_chunks_a_single_page():
    long = "x" * 8000
    chunks = chunk_pages([{"page": 1, "text": long}],
                         chunk_tokens=500, overlap_tokens=50,
                         chars_per_token=4)
    # 8000 / (500*4 - 50*4) = 8000 / 1800 ≈ 5 chunks
    assert 4 <= len(chunks) <= 6
    assert all(c.page == 1 for c in chunks)
    assert all(c.content.strip() for c in chunks)


def test_chunker_never_spans_pages():
    pages = [
        {"page": 1, "text": "alpha " * 200},
        {"page": 2, "text": "beta " * 200},
    ]
    chunks = chunk_pages(pages, chunk_tokens=200, overlap_tokens=20,
                         chars_per_token=4)
    page1 = [c for c in chunks if c.page == 1]
    page2 = [c for c in chunks if c.page == 2]
    assert page1 and page2
    assert all("beta" not in c.content for c in page1)
    assert all("alpha" not in c.content for c in page2)


def test_chunker_skips_empty_pages():
    chunks = chunk_pages(
        [{"page": 1, "text": ""}, {"page": 2, "text": "hello world"}],
    )
    assert len(chunks) == 1
    assert chunks[0].page == 2


# ---- parsers -----------------------------------------------------------


def test_detect_kind_pdf():
    assert detect_kind("/tmp/x.PDF") == "pdf"
    assert detect_kind("/tmp/x.docx") == "docx"
    assert detect_kind("/tmp/x.png") == "image"
    assert detect_kind("/tmp/x.md") == "markdown"
    assert detect_kind("/tmp/x.py") == "code"
    assert detect_kind("/tmp/x.dat") == "unknown"


# ---- permissions -------------------------------------------------------


def test_document_reads_are_read_level():
    e = PermissionEngine()
    for name in (
        "documents.parse_pdf", "documents.parse_docx", "documents.parse_image",
        "documents.parse_markdown", "documents.parse_code", "documents.parse_any",
        "documents.search_documents", "documents.search_in_file",
        "documents.summarize_document", "documents.ask_document",
        "documents.list_indexed",
    ):
        assert e.classify_risk(name) == RiskLevel.READ, f"{name} should be READ"


def test_document_indexing_is_personal():
    e = PermissionEngine()
    for name in ("documents.index_file", "documents.index_directory",
                 "documents.reindex"):
        assert e.classify_risk(name) == RiskLevel.PERSONAL
