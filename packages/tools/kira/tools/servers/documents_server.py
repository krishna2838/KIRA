"""Documents MCP server — parsing, indexing, semantic search, and RAG QA.

Configured by bootstrap with a DocumentStore, a DocumentIndexer, and an
optional summarize/QA generator. Every tool degrades gracefully when the
dep it needs is missing.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from kira.tools.documents import parsers
from kira.tools.documents.indexer import DocumentIndexer
from kira.tools.documents.store import DocumentStore
from kira.tools.servers.base import InternalServer, InternalTool


_store: DocumentStore | None = None
_indexer: DocumentIndexer | None = None
_generate: Callable[[str], Awaitable[str]] | None = None


def configure(store: DocumentStore | None,
              indexer: DocumentIndexer | None,
              generate: Callable[[str], Awaitable[str]] | None) -> None:
    global _store, _indexer, _generate
    _store = store
    _indexer = indexer
    _generate = generate


def _need_store() -> dict:
    return {"error": "documents store not initialized"}


# ---- Parsing tools ------------------------------------------------------


async def _parse_pdf(args: dict) -> Any:
    return await parsers.parse_pdf(args["path"], ocr=bool(args.get("ocr", True)))


async def _parse_docx(args: dict) -> Any:
    return await parsers.parse_docx(args["path"])


async def _parse_image(args: dict) -> Any:
    return await parsers.parse_image(args["path"])


async def _parse_markdown(args: dict) -> Any:
    return await parsers.parse_markdown(args["path"])


async def _parse_code(args: dict) -> Any:
    return await parsers.parse_code(args["path"])


async def _parse_any(args: dict) -> Any:
    return await parsers.parse_any(args["path"], ocr=bool(args.get("ocr", True)))


# ---- Indexing tools -----------------------------------------------------


async def _index_file(args: dict) -> Any:
    if _indexer is None:
        return _need_store()
    return await _indexer.index_file(args["path"], force=bool(args.get("force", False)))


async def _index_directory(args: dict) -> Any:
    if _indexer is None:
        return _need_store()
    return await _indexer.index_directory(args["path"], force=bool(args.get("force", False)))


async def _reindex(args: dict) -> Any:
    if _indexer is None:
        return _need_store()
    return await _indexer.reindex(args["path"])


async def _list_indexed(args: dict) -> Any:
    if _store is None:
        return _need_store()
    return {"files": await _store.indexed_files(int(args.get("limit", 200)))}


# ---- Search / RAG tools -------------------------------------------------


async def _search_documents(args: dict) -> Any:
    if _store is None:
        return _need_store()
    hits = await _store.search(args["query"], limit=int(args.get("limit", 8)))
    return {"query": args["query"], "hits": hits}


async def _search_in_file(args: dict) -> Any:
    if _store is None:
        return _need_store()
    hits = await _store.search(
        args["query"], limit=int(args.get("limit", 8)), file_path=args["path"]
    )
    return {"query": args["query"], "path": args["path"], "hits": hits}


SUMMARY_PROMPT = """Summarize this document in 5–8 short bullets. Prioritize
what's actionable or non-obvious. If it's a technical document, note the
core claims and any specific numbers. No filler.

Document:
{content}
"""


async def _summarize_document(args: dict) -> Any:
    if _store is None:
        return _need_store()
    if _generate is None:
        return {"error": "no LLM configured for summarization"}
    chunks = await _store.chunks_for(args["path"])
    if not chunks:
        return {"error": "file not indexed — index it first"}
    joined = "\n\n".join(c["content"] for c in chunks)[:20000]
    try:
        summary = await _generate(SUMMARY_PROMPT.format(content=joined))
    except Exception as e:
        return {"error": f"summarize failed: {e}"}
    return {
        "path": args["path"],
        "summary": summary.strip(),
        "chunks": len(chunks),
    }


ASK_PROMPT = """Answer the user's question using ONLY the excerpts below. If
the excerpts don't contain the answer, say you don't know based on this
document. Cite excerpts inline as [n] matching their numbers.

Question: {question}

Excerpts:
{excerpts}
"""


async def _ask_document(args: dict) -> Any:
    if _store is None:
        return _need_store()
    if _generate is None:
        return {"error": "no LLM configured"}
    hits = await _store.search(
        args["question"], limit=int(args.get("limit", 6)), file_path=args["path"]
    )
    if not hits:
        return {"answer": "This document doesn't seem to contain that information."}
    excerpts_text = "\n\n".join(
        f"[{i + 1}] (p.{h['page_number']}) {h['content']}"
        for i, h in enumerate(hits)
    )
    prompt = ASK_PROMPT.format(question=args["question"], excerpts=excerpts_text[:12000])
    try:
        answer = await _generate(prompt)
    except Exception as e:
        return {"error": f"ask failed: {e}"}
    return {
        "path": args["path"],
        "question": args["question"],
        "answer": answer.strip(),
        "sources": [
            {"index": i + 1, "page": h["page_number"], "score": h["score"],
             "content": h["content"]}
            for i, h in enumerate(hits)
        ],
    }


# ---- Server -------------------------------------------------------------


SERVER = InternalServer(
    name="documents",
    description=(
        "Parse, index, and search your personal documents (PDF, DOCX, "
        "Markdown, code, images with OCR). Supports RAG QA over specific files."
    ),
    tools=[
        # parsing
        InternalTool(name="parse_pdf",
                     description="Extract text from a PDF (OCR fallback for scanned pages).",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "ocr": {"type": "boolean", "default": True}},
                                   "required": ["path"]},
                     handler=_parse_pdf),
        InternalTool(name="parse_docx",
                     description="Extract text from a .docx file.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"}},
                                   "required": ["path"]},
                     handler=_parse_docx),
        InternalTool(name="parse_image",
                     description="OCR an image (PNG/JPG/etc.) using PaddleOCR.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"}},
                                   "required": ["path"]},
                     handler=_parse_image),
        InternalTool(name="parse_markdown",
                     description="Read a Markdown/plaintext file.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"}},
                                   "required": ["path"]},
                     handler=_parse_markdown),
        InternalTool(name="parse_code",
                     description="Read a source code file with language detection.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"}},
                                   "required": ["path"]},
                     handler=_parse_code),
        InternalTool(name="parse_any",
                     description="Auto-detect file type and parse.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "ocr": {"type": "boolean", "default": True}},
                                   "required": ["path"]},
                     handler=_parse_any),

        # indexing
        InternalTool(name="index_file",
                     description="Parse a file, chunk it, embed each chunk, store in pgvector.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "force": {"type": "boolean", "default": False}},
                                   "required": ["path"]},
                     handler=_index_file),
        InternalTool(name="index_directory",
                     description="Recursively index all supported files in a directory.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "force": {"type": "boolean", "default": False}},
                                   "required": ["path"]},
                     handler=_index_directory),
        InternalTool(name="reindex",
                     description="Re-parse and re-embed a file, replacing existing chunks.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"}},
                                   "required": ["path"]},
                     handler=_reindex),
        InternalTool(name="list_indexed",
                     description="List indexed files with chunk counts + last-indexed time.",
                     input_schema={"type": "object",
                                   "properties": {"limit": {"type": "integer", "default": 200}}},
                     handler=_list_indexed),

        # search + RAG
        InternalTool(name="search_documents",
                     description="Semantic search across all indexed documents.",
                     input_schema={"type": "object",
                                   "properties": {"query": {"type": "string"},
                                                  "limit": {"type": "integer", "default": 8}},
                                   "required": ["query"]},
                     handler=_search_documents),
        InternalTool(name="search_in_file",
                     description="Semantic search within a single indexed file.",
                     input_schema={"type": "object",
                                   "properties": {"query": {"type": "string"},
                                                  "path": {"type": "string"},
                                                  "limit": {"type": "integer", "default": 8}},
                                   "required": ["query", "path"]},
                     handler=_search_in_file),
        InternalTool(name="summarize_document",
                     description="LLM-summarize an indexed document.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"}},
                                   "required": ["path"]},
                     handler=_summarize_document),
        InternalTool(name="ask_document",
                     description="RAG QA over a specific indexed document. Returns a cited answer.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "question": {"type": "string"},
                                                  "limit": {"type": "integer", "default": 6}},
                                   "required": ["path", "question"]},
                     handler=_ask_document),
    ],
)
