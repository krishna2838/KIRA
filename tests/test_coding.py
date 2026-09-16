"""Tests for coding-agent primitives (offline-safe)."""
import asyncio
import os
import tempfile
from pathlib import Path

from kira.brain.planner import (
    PlanExecutor,
    Planner,
    Step,
    _extract_json_array,
    _resolve_refs,
)
from kira.core.permissions import PermissionEngine
from kira.tools.coding import analyze, build, edit
from kira.core.types import RiskLevel


# ---- edit --------------------------------------------------------------


def test_edit_file_replaces_and_returns_diff(tmp_path: Path):
    p = tmp_path / "f.py"
    p.write_text("def foo():\n    return 1\n")
    r = asyncio.run(edit.edit_file(str(p), "return 1", "return 42"))
    assert r["applied"] is True
    assert "return 42" in p.read_text()
    assert "-    return 1" in r["diff"]
    assert "+    return 42" in r["diff"]


def test_edit_file_refuses_ambiguous(tmp_path: Path):
    p = tmp_path / "f.py"
    p.write_text("x = 1\ny = 1\n")
    r = asyncio.run(edit.edit_file(str(p), "1", "2"))
    assert r["applied"] is False
    assert "occurs" in r["error"]


def test_create_file_refuses_overwrite_without_flag(tmp_path: Path):
    p = tmp_path / "new.txt"
    r1 = asyncio.run(edit.create_file(str(p), "hello"))
    assert r1["created"] is True
    r2 = asyncio.run(edit.create_file(str(p), "changed"))
    assert r2["created"] is False
    assert p.read_text() == "hello"


# ---- analyze -----------------------------------------------------------


def test_read_project_structure_skips_ignored(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("junk")
    r = asyncio.run(analyze.read_project_structure(str(tmp_path)))
    assert "src/" in r["tree"]
    assert "node_modules" not in r["tree"]


def test_read_file_with_lines_numbers_lines(tmp_path: Path):
    p = tmp_path / "f.py"
    p.write_text("a\nb\nc\n")
    r = asyncio.run(analyze.read_file_with_lines(str(p)))
    assert r["total_lines"] == 3
    assert r["language"] == "python"
    assert "    1  a" in r["content"]


def test_search_code_python_fallback(tmp_path: Path):
    p = tmp_path / "app.py"
    p.write_text("def login(user):\n    return True\n")
    r = asyncio.run(analyze.search_code(str(tmp_path), "login"))
    assert any("login" in hit["snippet"] for hit in r["hits"])


# ---- build parse -------------------------------------------------------


def test_parse_build_errors_pep8_style():
    out = "src/foo.py:12:5: error: undefined name 'bar'\n"
    hits = build.parse_build_errors(out)
    assert hits and hits[0]["file"] == "src/foo.py"
    assert hits[0]["line"] == 12
    assert hits[0]["level"] == "error"


def test_parse_build_errors_python_traceback():
    out = 'Traceback:\n  File "/tmp/x.py", line 3, in <module>\n    bar()\n'
    hits = build.parse_build_errors(out)
    assert hits and hits[0]["file"] == "/tmp/x.py"


# ---- permissions -------------------------------------------------------


def test_permission_reads_are_read():
    e = PermissionEngine()
    for name in (
        "code.git_status", "code.git_diff", "code.git_log", "code.git_branch_list",
        "code.list_repos", "code.get_repo_issues", "code.get_actions_status",
        "code.read_project_structure", "code.read_source_file", "code.search_code",
        "code.investigate_and_fix",
    ):
        assert e.classify_risk(name) == RiskLevel.READ, f"{name} should be READ"


def test_permission_mutations_are_execute():
    e = PermissionEngine()
    for name in (
        "code.git_checkout", "code.git_commit",
        "code.edit_source_file", "code.create_source_file",
        "code.run_build", "code.run_tests",
        "code.create_issue",
        "code.apply_proposal",
    ):
        assert e.classify_risk(name) == RiskLevel.EXECUTE, f"{name} should be EXECUTE"


def test_permission_push_is_external():
    e = PermissionEngine()
    assert e.classify_risk("code.git_push") == RiskLevel.EXTERNAL


# ---- planner -----------------------------------------------------------


def test_extract_json_array_recovers_from_fenced_output():
    text = "Sure — here you go:\n```json\n[{\"tool\": \"a\", \"arguments\": {}}]\n```"
    arr = _extract_json_array(text)
    assert arr == [{"tool": "a", "arguments": {}}]


def test_resolve_refs_pulls_from_state():
    state = {"first": {"count": 5}}
    args = {"n": {"$ref": "first.count"}}
    assert _resolve_refs(args, state) == {"n": 5}


def test_plan_executor_runs_steps_in_order_and_threads_state():
    calls: list[tuple[str, dict]] = []

    async def dispatch(tool: str, args: dict):
        calls.append((tool, args))
        if tool == "produce":
            return {"value": 7}
        if tool == "consume":
            return {"received": args["v"]}
        raise ValueError(f"unknown tool {tool}")

    plan = [
        Step(name="a", tool="produce"),
        Step(name="b", tool="consume", arguments={"v": {"$ref": "a.value"}}),
    ]

    executor = PlanExecutor(dispatch)
    record = asyncio.run(executor.execute("goal", plan))
    assert not record.aborted
    assert [c[0] for c in calls] == ["produce", "consume"]
    assert calls[1][1]["v"] == 7
    assert record.results[-1].output == {"received": 7}


def test_plan_executor_retries_and_aborts_on_persistent_failure():
    calls: list[str] = []

    async def dispatch(tool: str, args: dict):
        calls.append(tool)
        raise RuntimeError("nope")

    executor = PlanExecutor(dispatch, max_retries=1)
    plan = [Step(name="only", tool="fail")]
    record = asyncio.run(executor.execute("goal", plan))
    assert record.aborted
    assert record.results[0].attempts == 2  # 1 initial + 1 retry
    assert "fail" in record.abort_reason
