"""Read-only code analysis: tree, read, grep, error explain, code explain."""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Awaitable, Callable


IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".next", ".turbo", ".idea",
    ".vscode", "target", ".DS_Store",
}
MAX_TREE_ENTRIES = 400
MAX_READ_BYTES = 400_000
MAX_GREP_HITS = 200
MAX_LINE_CHARS = 400


def _in_ignore(name: str) -> bool:
    return name in IGNORE_DIRS or name.startswith(".") and name not in {".env.example", ".gitignore"}


async def read_project_structure(path: str, max_depth: int = 4) -> dict:
    root = Path(os.path.expanduser(path)).resolve()
    if not root.is_dir():
        return {"error": f"not a directory: {root}"}

    def _do():
        lines: list[str] = []

        def walk(p: Path, depth: int):
            if len(lines) >= MAX_TREE_ENTRIES or depth > max_depth:
                return
            try:
                entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            except Exception:
                return
            for entry in entries:
                if entry.name in IGNORE_DIRS or entry.name.startswith("."):
                    if entry.name not in {".env.example", ".gitignore"}:
                        continue
                indent = "  " * depth
                if entry.is_dir():
                    lines.append(f"{indent}{entry.name}/")
                    walk(entry, depth + 1)
                else:
                    lines.append(f"{indent}{entry.name}")
                if len(lines) >= MAX_TREE_ENTRIES:
                    lines.append(f"{indent}… (truncated)")
                    return

        walk(root, 0)
        return "\n".join(lines)

    tree = await asyncio.to_thread(_do)
    return {"root": str(root), "tree": tree}


async def read_file_with_lines(path: str, start_line: int | None = None,
                               end_line: int | None = None) -> dict:
    p = Path(os.path.expanduser(path)).resolve()
    if not p.is_file():
        return {"error": f"not a file: {p}"}
    if p.stat().st_size > MAX_READ_BYTES:
        return {"error": f"file too large ({p.stat().st_size} bytes)"}
    text = p.read_text(errors="replace")
    lines = text.splitlines()
    s = max(1, start_line or 1)
    e = min(len(lines), end_line or len(lines))
    numbered = "\n".join(
        f"{i + 1:>5}  {ln[:MAX_LINE_CHARS]}"
        for i, ln in enumerate(lines[s - 1 : e], start=s - 1)
    )
    return {
        "path": str(p),
        "start_line": s,
        "end_line": e,
        "total_lines": len(lines),
        "content": numbered,
        "language": _guess_language(p),
    }


def _guess_language(p: Path) -> str:
    ext = p.suffix.lower()
    return {
        ".py": "python", ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "tsx", ".rs": "rust", ".go": "go",
        ".java": "java", ".rb": "ruby", ".sh": "bash", ".zsh": "bash",
        ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".md": "markdown",
        ".html": "html", ".css": "css", ".sql": "sql", ".toml": "toml",
        ".c": "c", ".cpp": "cpp", ".h": "c", ".swift": "swift",
    }.get(ext, "")


def _rg_available() -> bool:
    return shutil.which("rg") is not None


async def search_code(path: str, query: str, max_hits: int = 100,
                      include_glob: str | None = None) -> dict:
    root = Path(os.path.expanduser(path)).resolve()
    if not root.exists():
        return {"error": f"not found: {root}"}

    max_hits = min(int(max_hits), MAX_GREP_HITS)

    if _rg_available():
        cmd = ["rg", "--hidden", "--no-messages", "--line-number", "--column",
               "--no-heading", "--color=never", "--max-count", "10", query, str(root)]
        for d in IGNORE_DIRS:
            cmd += ["--glob", f"!{d}/**"]
        if include_glob:
            cmd += ["--glob", include_glob]

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        hits: list[dict] = []
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            if len(hits) >= max_hits:
                break
            # <path>:<line>:<col>:<content>
            parts = line.split(":", 3)
            if len(parts) < 4:
                continue
            hits.append({
                "path": parts[0],
                "line": int(parts[1]) if parts[1].isdigit() else 0,
                "col": int(parts[2]) if parts[2].isdigit() else 0,
                "snippet": parts[3][:MAX_LINE_CHARS],
            })
        return {"engine": "ripgrep", "query": query, "hits": hits}

    # Python fallback
    def _walk():
        results: list[dict] = []
        q = query
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
            for name in filenames:
                if len(results) >= max_hits:
                    return results
                p = Path(dirpath) / name
                try:
                    if p.stat().st_size > MAX_READ_BYTES:
                        continue
                    with p.open("r", errors="ignore") as f:
                        for lineno, line in enumerate(f, start=1):
                            if q in line:
                                results.append({
                                    "path": str(p),
                                    "line": lineno,
                                    "col": line.find(q) + 1,
                                    "snippet": line.rstrip()[:MAX_LINE_CHARS],
                                })
                                if len(results) >= max_hits:
                                    return results
                except Exception:
                    continue
        return results
    hits = await asyncio.to_thread(_walk)
    return {"engine": "python", "query": query, "hits": hits}


# ---- LLM-driven analysis (analyze_error / explain_code) ------------------


AsyncGenerate = Callable[[str], Awaitable[str]]


ERROR_PROMPT = """You are a senior engineer helping diagnose an error message.

Error:
{error}

Return:
1. What's likely broken (2-3 lines)
2. Two concrete fixes (bulleted)
3. What to inspect first (file/function/log)

Keep it short and specific."""


EXPLAIN_PROMPT = """Explain what this code does in 4-6 concise lines. Call out:
- The core responsibility
- Any non-obvious behavior
- Anything that looks buggy or brittle

Code:
```
{code}
```
"""


async def analyze_error(error_text: str, generate: AsyncGenerate | None) -> dict:
    if generate is None:
        return {"analysis": "(no LLM configured for analysis)"}
    try:
        text = await generate(ERROR_PROMPT.format(error=error_text[:4000]))
    except Exception as e:
        return {"analysis": f"analysis failed: {e}"}
    return {"analysis": text.strip()}


async def explain_code(path: str, start_line: int | None, end_line: int | None,
                       generate: AsyncGenerate | None) -> dict:
    read = await read_file_with_lines(path, start_line, end_line)
    if "error" in read:
        return read
    if generate is None:
        return {"explanation": "(no LLM configured for analysis)",
                "excerpt": read["content"]}
    try:
        text = await generate(EXPLAIN_PROMPT.format(code=read["content"][:8000]))
    except Exception as e:
        return {"explanation": f"analysis failed: {e}", "excerpt": read["content"]}
    return {
        "path": read["path"],
        "start_line": read["start_line"],
        "end_line": read["end_line"],
        "explanation": text.strip(),
    }
