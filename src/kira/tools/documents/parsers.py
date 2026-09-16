"""Document parsers.

Each parser returns a list of `Page` records: `[{page: int, text: str}]`.
Non-paginated formats emit a single page (page=1). Missing dependencies do
NOT crash — the parser returns an error dict so the indexer can skip and
move on.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {
    # Text-oriented
    ".md", ".markdown", ".txt", ".rst",
    # Code
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb",
    ".c", ".h", ".cpp", ".hpp", ".swift", ".sh", ".yaml", ".yml", ".json",
    ".toml", ".sql", ".html", ".css", ".ini",
    # Rich formats
    ".pdf", ".docx",
    # Images
    ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp",
}

TEXT_EXTS = {".md", ".markdown", ".txt", ".rst"}
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
             ".rb", ".c", ".h", ".cpp", ".hpp", ".swift", ".sh", ".yaml",
             ".yml", ".json", ".toml", ".sql", ".html", ".css", ".ini"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"}


@dataclass
class Page:
    page: int
    text: str


def detect_kind(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in TEXT_EXTS:
        return "markdown"
    if ext in CODE_EXTS:
        return "code"
    return "unknown"


# ---- PDF ----------------------------------------------------------------


async def parse_pdf(path: str, ocr: bool = True) -> dict:
    """Extract text from a PDF. If a page has no extractable text and
    `ocr=True`, fall back to OCR via PaddleOCR."""
    def _do():
        try:
            import fitz  # type: ignore  # PyMuPDF
        except Exception as e:
            return {"error": f"PyMuPDF missing (pip install PyMuPDF): {e}"}
        pages: list[Page] = []
        try:
            doc = fitz.open(path)
        except Exception as e:
            return {"error": f"open failed: {e}"}
        try:
            for i, page in enumerate(doc, start=1):
                text = page.get_text("text") or ""
                if not text.strip() and ocr:
                    # Rasterize the page and OCR
                    try:
                        pix = page.get_pixmap(dpi=200)
                        png = pix.tobytes("png")
                        text = _ocr_bytes(png) or ""
                    except Exception:
                        text = ""
                pages.append(Page(page=i, text=text.strip()))
        finally:
            doc.close()
        return {
            "path": path,
            "kind": "pdf",
            "pages": [{"page": p.page, "text": p.text} for p in pages],
        }
    return await asyncio.to_thread(_do)


# ---- DOCX ---------------------------------------------------------------


async def parse_docx(path: str) -> dict:
    def _do():
        try:
            import docx  # type: ignore
        except Exception as e:
            return {"error": f"python-docx missing: {e}"}
        try:
            d = docx.Document(path)
        except Exception as e:
            return {"error": f"open failed: {e}"}
        paragraphs = [p.text for p in d.paragraphs if p.text.strip()]
        for t in d.tables:
            for row in t.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    paragraphs.append(" | ".join(cells))
        text = "\n".join(paragraphs)
        return {
            "path": path,
            "kind": "docx",
            "pages": [{"page": 1, "text": text}],
        }
    return await asyncio.to_thread(_do)


# ---- Image (OCR) --------------------------------------------------------


def _ocr_bytes(image_bytes: bytes) -> str | None:
    try:
        from paddleocr import PaddleOCR  # type: ignore
        import io
        from PIL import Image  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return None
    # PaddleOCR is expensive to instantiate — cache one.
    global _paddle
    try:
        _paddle  # type: ignore[name-defined]
    except NameError:
        _paddle = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)  # type: ignore
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    result = _paddle.ocr(np.array(img), cls=True)  # type: ignore
    if not result:
        return None
    lines: list[str] = []
    for group in result:
        if not group:
            continue
        for item in group:
            if isinstance(item, list) and len(item) >= 2 and isinstance(item[1], (list, tuple)):
                text = item[1][0]
                if text:
                    lines.append(str(text))
    return "\n".join(lines) or None


async def parse_image(path: str) -> dict:
    def _do():
        try:
            with open(path, "rb") as f:
                png = f.read()
        except Exception as e:
            return {"error": f"open failed: {e}"}
        text = _ocr_bytes(png)
        if text is None:
            return {"error": "PaddleOCR not available or produced no text"}
        return {
            "path": path,
            "kind": "image",
            "pages": [{"page": 1, "text": text}],
        }
    return await asyncio.to_thread(_do)


# ---- Markdown / plain text ---------------------------------------------


async def parse_markdown(path: str) -> dict:
    def _do():
        try:
            text = Path(path).read_text(errors="replace")
        except Exception as e:
            return {"error": f"read failed: {e}"}
        return {
            "path": path,
            "kind": "markdown",
            "pages": [{"page": 1, "text": text}],
        }
    return await asyncio.to_thread(_do)


# ---- Code ---------------------------------------------------------------


async def parse_code(path: str) -> dict:
    def _do():
        try:
            text = Path(path).read_text(errors="replace")
        except Exception as e:
            return {"error": f"read failed: {e}"}
        return {
            "path": path,
            "kind": "code",
            "language": Path(path).suffix.lstrip("."),
            "pages": [{"page": 1, "text": text}],
        }
    return await asyncio.to_thread(_do)


# ---- Dispatcher ---------------------------------------------------------


async def parse_any(path: str, ocr: bool = True) -> dict:
    if not os.path.exists(path):
        return {"error": f"not found: {path}"}
    kind = detect_kind(path)
    if kind == "pdf":
        return await parse_pdf(path, ocr=ocr)
    if kind == "docx":
        return await parse_docx(path)
    if kind == "image":
        return await parse_image(path)
    if kind == "markdown":
        return await parse_markdown(path)
    if kind == "code":
        return await parse_code(path)
    return {"error": f"unsupported file type: {Path(path).suffix or '(none)'}"}
