"""The investigate-and-fix workflow.

Not a single LLM call — a small, transparent state machine:

  1. read the project structure at `repo_path`
  2. search for terms the user's request implies (via a fast-model keyword
     extraction step) — surface candidate files
  3. read the top candidate files
  4. ask the smart model to diagnose and PROPOSE a patch (find/replace pairs)
  5. produce a unified diff preview
  6. return the plan — the CALLER (chat route / user) approves and then
     calls `apply(plan)` to run the edits and (optionally) tests.

We intentionally never auto-commit, auto-push, or auto-apply edits without
explicit user approval. `investigate_and_fix` returns a proposal; `apply`
does the writes.
"""
from __future__ import annotations

import json
import re
from typing import Awaitable, Callable

from kira.tools.coding.analyze import (
    read_file_with_lines,
    read_project_structure,
    search_code,
)
from kira.tools.coding.build import run_command as run_build_command
from kira.tools.coding.edit import edit_file, preview_edit


AsyncGenerate = Callable[[str], Awaitable[str]]


KEYWORDS_PROMPT = """Extract 3-5 code-search keywords that would help locate
the file(s) relevant to this request. Return a JSON array of strings.

Request: {request}
"""


DIAGNOSE_PROMPT = """You are debugging code. The user's request:
{request}

Relevant source snippets (with file:line):
{snippets}

Diagnose the likely bug and propose exact, minimal edits. Return JSON:

{{
  "diagnosis": "short explanation of the bug",
  "edits": [
    {{"path": "<abs-path>", "old_text": "<exact snippet>", "new_text": "<replacement>"}}
  ],
  "test_command": "<optional command to run after applying>"
}}

Rules:
- `old_text` MUST be an exact substring of the file it references and appear
  exactly once. Include enough surrounding context to make it unique.
- If you don't have enough context to be sure, return an empty edits array
  and describe what else to inspect in `diagnosis`.
- Do NOT invent files. Only edit files listed in the snippets.
"""


def _parse_json(text: str) -> dict:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


async def _keywords(request: str, fast_generate: AsyncGenerate | None) -> list[str]:
    if fast_generate is None:
        # Rough tokenization fallback
        return [w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]+", request) if len(w) > 3][:5]
    try:
        raw = await fast_generate(KEYWORDS_PROMPT.format(request=request))
    except Exception:
        return []
    m = re.search(r"\[[\s\S]*\]", raw)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
        return [str(x) for x in arr if str(x).strip()][:5]
    except Exception:
        return []


async def investigate_and_fix(
    request: str,
    repo_path: str,
    *,
    fast_generate: AsyncGenerate | None,
    smart_generate: AsyncGenerate | None,
    max_files: int = 3,
) -> dict:
    """Return a proposal dict:
      { steps: [event...], diagnosis, edits, test_command, repo_path }
    """
    steps: list[dict] = []

    # 1. Project structure
    tree = await read_project_structure(repo_path, max_depth=4)
    steps.append({"stage": "read_tree", "root": tree.get("root")})

    # 2. Keyword extraction + search
    keywords = await _keywords(request, fast_generate)
    steps.append({"stage": "keywords", "keywords": keywords})

    candidate_paths: dict[str, int] = {}
    for kw in keywords or [request]:
        r = await search_code(repo_path, kw, max_hits=20)
        for hit in r.get("hits", []):
            candidate_paths[hit["path"]] = candidate_paths.get(hit["path"], 0) + 1
        steps.append({
            "stage": "search",
            "query": kw,
            "hits": len(r.get("hits", [])),
        })

    ranked = sorted(candidate_paths.items(), key=lambda kv: kv[1], reverse=True)
    top = [p for p, _ in ranked[:max_files]]

    # 3. Read candidate files
    snippets: list[str] = []
    for path in top:
        r = await read_file_with_lines(path)
        if "content" in r:
            snippets.append(f"# {r['path']} (lines {r['start_line']}-{r['end_line']})\n{r['content']}")
        steps.append({"stage": "read", "path": path})

    if not snippets or smart_generate is None:
        return {
            "repo_path": repo_path,
            "steps": steps,
            "diagnosis": (
                "Not enough context or no smart model available to propose a fix."
                if smart_generate else
                "No smart model configured for diagnosis."
            ),
            "edits": [],
            "test_command": None,
        }

    # 4. Diagnose + propose edits
    raw = await smart_generate(
        DIAGNOSE_PROMPT.format(
            request=request,
            snippets="\n\n".join(snippets)[:24000],
        )
    )
    parsed = _parse_json(raw)
    diagnosis = parsed.get("diagnosis", "").strip() or "(model returned no diagnosis)"
    edits = parsed.get("edits") or []
    test_command = parsed.get("test_command")

    steps.append({"stage": "diagnose", "diagnosis_summary": diagnosis[:200]})

    # 5. Dry-run previews so the caller can show a diff
    previews: list[dict] = []
    for e in edits:
        if not isinstance(e, dict):
            continue
        p = e.get("path")
        old = e.get("old_text")
        new = e.get("new_text")
        if not (p and old is not None and new is not None):
            continue
        preview = await preview_edit(p, old, new)
        previews.append({
            "path": p,
            "old_text": old,
            "new_text": new,
            "diff": preview.get("diff"),
            "preview_error": preview.get("error"),
        })
    steps.append({"stage": "preview", "count": len(previews)})

    return {
        "repo_path": repo_path,
        "steps": steps,
        "diagnosis": diagnosis,
        "edits": previews,
        "test_command": test_command,
    }


async def apply_proposal(
    proposal: dict,
    *,
    run_tests: bool = True,
) -> dict:
    """Apply an investigate_and_fix proposal. Runs test_command afterwards
    when `run_tests=True` and one was suggested.
    """
    applied: list[dict] = []
    for e in proposal.get("edits", []):
        result = await edit_file(e["path"], e["old_text"], e["new_text"])
        applied.append({
            "path": e["path"],
            "applied": result.get("applied", False),
            "error": result.get("error"),
            "diff": result.get("diff"),
        })
    test_result = None
    tc = proposal.get("test_command")
    if run_tests and tc:
        test_result = await run_build_command(proposal["repo_path"], tc)
    return {"applied": applied, "test": test_result}
