"""Coding MCP server — git, GitHub, analysis, edits, build, and the
investigate-and-fix workflow.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from kira.tools.coding import analyze, build, edit, git_ops, github_api, workflow
from kira.tools.servers.base import InternalServer, InternalTool


_fast_generate: Callable[[str], Awaitable[str]] | None = None
_smart_generate: Callable[[str], Awaitable[str]] | None = None


def configure(fast_generate, smart_generate) -> None:
    global _fast_generate, _smart_generate
    _fast_generate = fast_generate
    _smart_generate = smart_generate


# ---- git ----------------------------------------------------------------


async def _git_status(args: dict) -> Any:      return await git_ops.status(args["repo_path"])
async def _git_diff(args: dict) -> Any:        return await git_ops.diff(args["repo_path"], bool(args.get("staged", False)))
async def _git_log(args: dict) -> Any:         return await git_ops.log(args["repo_path"], int(args.get("n", 10)))
async def _git_branch_list(args: dict) -> Any: return await git_ops.branch_list(args["repo_path"])
async def _git_checkout(args: dict) -> Any:    return await git_ops.checkout(args["repo_path"], args["branch"])
async def _git_commit(args: dict) -> Any:      return await git_ops.commit(args["repo_path"], args["message"])
async def _git_push(args: dict) -> Any:
    return await git_ops.push(
        args["repo_path"],
        remote=args.get("remote", "origin"),
        branch=args.get("branch"),
    )


# ---- GitHub -------------------------------------------------------------


async def _github_status(args: dict) -> Any:
    return {"authenticated": github_api.has_pat()}


async def _github_set_token(args: dict) -> Any:
    github_api.set_pat(args["token"])
    return {"stored": True}


async def _github_sign_out(args: dict) -> Any:
    github_api.forget_pat()
    return {"signed_out": True}


async def _github_list_repos(args: dict) -> Any:
    return {"repos": await github_api.list_repos(int(args.get("limit", 30)))}


async def _github_repo_issues(args: dict) -> Any:
    return {"issues": await github_api.get_repo_issues(
        args["repo"], state=args.get("state", "open"),
        limit=int(args.get("limit", 20)),
    )}


async def _github_create_issue(args: dict) -> Any:
    return await github_api.create_issue(
        args["repo"], args["title"], args.get("body", "")
    )


async def _github_pull_requests(args: dict) -> Any:
    return {"prs": await github_api.get_pull_requests(
        args["repo"], state=args.get("state", "open"),
        limit=int(args.get("limit", 20)),
    )}


async def _github_actions_status(args: dict) -> Any:
    return await github_api.get_actions_status(args["repo"], int(args.get("limit", 10)))


async def _github_read_file(args: dict) -> Any:
    return await github_api.read_file_from_github(
        args["repo"], args["path"], ref=args.get("ref")
    )


# ---- analyze ------------------------------------------------------------


async def _read_project_structure(args: dict) -> Any:
    return await analyze.read_project_structure(
        args["path"], max_depth=int(args.get("max_depth", 4))
    )


async def _read_file(args: dict) -> Any:
    return await analyze.read_file_with_lines(
        args["path"],
        start_line=args.get("start_line"),
        end_line=args.get("end_line"),
    )


async def _search_code(args: dict) -> Any:
    return await analyze.search_code(
        args["path"], args["query"],
        max_hits=int(args.get("max_hits", 100)),
        include_glob=args.get("include_glob"),
    )


async def _analyze_error(args: dict) -> Any:
    return await analyze.analyze_error(args["error_text"], _smart_generate)


async def _explain_code(args: dict) -> Any:
    return await analyze.explain_code(
        args["path"], args.get("start_line"), args.get("end_line"),
        _smart_generate,
    )


# ---- edit ---------------------------------------------------------------


async def _edit_file(args: dict) -> Any:
    return await edit.edit_file(
        args["path"], args["old_text"], args["new_text"],
        replace_all=bool(args.get("replace_all", False)),
    )


async def _create_file(args: dict) -> Any:
    return await edit.create_file(
        args["path"], args["content"],
        overwrite=bool(args.get("overwrite", False)),
    )


# ---- build / test -------------------------------------------------------


async def _run_build(args: dict) -> Any:
    return await build.run_command(
        args["path"], args["command"],
        timeout_sec=float(args.get("timeout_sec", 300)),
    )


async def _run_tests(args: dict) -> Any:
    return await build.run_command(
        args["path"], args["command"],
        timeout_sec=float(args.get("timeout_sec", 600)),
    )


async def _parse_build_errors(args: dict) -> Any:
    return await build.explain_build_output(args["output"], _smart_generate)


# ---- workflow -----------------------------------------------------------


async def _investigate_and_fix(args: dict) -> Any:
    return await workflow.investigate_and_fix(
        args["request"], args["repo_path"],
        fast_generate=_fast_generate,
        smart_generate=_smart_generate,
        max_files=int(args.get("max_files", 3)),
    )


async def _apply_proposal(args: dict) -> Any:
    return await workflow.apply_proposal(
        args["proposal"], run_tests=bool(args.get("run_tests", True))
    )


# ---- server -------------------------------------------------------------


SERVER = InternalServer(
    name="code",
    description=(
        "Git + GitHub + code reading, editing, and testing. Includes an "
        "investigate-and-fix workflow that produces a diff proposal you can "
        "approve before it's applied."
    ),
    tools=[
        # git
        InternalTool(name="git_status",
                     description="Git status of a repo (branch, changes, staged, untracked).",
                     input_schema={"type": "object",
                                   "properties": {"repo_path": {"type": "string"}},
                                   "required": ["repo_path"]},
                     handler=_git_status),
        InternalTool(name="git_diff", description="Show the current diff (unstaged by default).",
                     input_schema={"type": "object",
                                   "properties": {"repo_path": {"type": "string"},
                                                  "staged": {"type": "boolean", "default": False}},
                                   "required": ["repo_path"]},
                     handler=_git_diff),
        InternalTool(name="git_log", description="Recent commits.",
                     input_schema={"type": "object",
                                   "properties": {"repo_path": {"type": "string"},
                                                  "n": {"type": "integer", "default": 10}},
                                   "required": ["repo_path"]},
                     handler=_git_log),
        InternalTool(name="git_branch_list", description="List branches (local + remote).",
                     input_schema={"type": "object",
                                   "properties": {"repo_path": {"type": "string"}},
                                   "required": ["repo_path"]},
                     handler=_git_branch_list),
        InternalTool(name="git_checkout", description="Switch to a branch (L2).",
                     input_schema={"type": "object",
                                   "properties": {"repo_path": {"type": "string"},
                                                  "branch": {"type": "string"}},
                                   "required": ["repo_path", "branch"]},
                     handler=_git_checkout),
        InternalTool(name="git_commit", description="Commit staged changes (L2).",
                     input_schema={"type": "object",
                                   "properties": {"repo_path": {"type": "string"},
                                                  "message": {"type": "string"}},
                                   "required": ["repo_path", "message"]},
                     handler=_git_commit),
        InternalTool(name="git_push", description="Push to a remote (L3 — always confirm).",
                     input_schema={"type": "object",
                                   "properties": {"repo_path": {"type": "string"},
                                                  "remote": {"type": "string", "default": "origin"},
                                                  "branch": {"type": "string"}},
                                   "required": ["repo_path"]},
                     handler=_git_push),

        # github
        InternalTool(name="github_status",
                     description="Whether a GitHub PAT is stored in the Keychain.",
                     input_schema={"type": "object", "properties": {}}, handler=_github_status),
        InternalTool(name="github_set_token",
                     description="Store a GitHub personal access token in the Keychain.",
                     input_schema={"type": "object",
                                   "properties": {"token": {"type": "string"}},
                                   "required": ["token"]},
                     handler=_github_set_token),
        InternalTool(name="github_sign_out",
                     description="Forget the stored GitHub PAT.",
                     input_schema={"type": "object", "properties": {}},
                     handler=_github_sign_out),
        InternalTool(name="list_repos", description="User's GitHub repositories.",
                     input_schema={"type": "object",
                                   "properties": {"limit": {"type": "integer", "default": 30}}},
                     handler=_github_list_repos),
        InternalTool(name="get_repo_issues", description="Open issues in a repo (owner/name).",
                     input_schema={"type": "object",
                                   "properties": {"repo": {"type": "string"},
                                                  "state": {"type": "string", "default": "open"},
                                                  "limit": {"type": "integer", "default": 20}},
                                   "required": ["repo"]},
                     handler=_github_repo_issues),
        InternalTool(name="create_issue", description="Create a GitHub issue (L2).",
                     input_schema={"type": "object",
                                   "properties": {"repo": {"type": "string"},
                                                  "title": {"type": "string"},
                                                  "body": {"type": "string"}},
                                   "required": ["repo", "title"]},
                     handler=_github_create_issue),
        InternalTool(name="get_pull_requests", description="Open PRs in a repo.",
                     input_schema={"type": "object",
                                   "properties": {"repo": {"type": "string"},
                                                  "state": {"type": "string", "default": "open"},
                                                  "limit": {"type": "integer", "default": 20}},
                                   "required": ["repo"]},
                     handler=_github_pull_requests),
        InternalTool(name="get_actions_status",
                     description="Recent GitHub Actions workflow runs and a pass/fail summary.",
                     input_schema={"type": "object",
                                   "properties": {"repo": {"type": "string"},
                                                  "limit": {"type": "integer", "default": 10}},
                                   "required": ["repo"]},
                     handler=_github_actions_status),
        InternalTool(name="read_file_from_github",
                     description="Read a file from a GitHub repo (at optional ref).",
                     input_schema={"type": "object",
                                   "properties": {"repo": {"type": "string"},
                                                  "path": {"type": "string"},
                                                  "ref": {"type": "string"}},
                                   "required": ["repo", "path"]},
                     handler=_github_read_file),

        # analyze
        InternalTool(name="read_project_structure",
                     description="Tree view of a project (skipping .git/node_modules/etc).",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "max_depth": {"type": "integer", "default": 4}},
                                   "required": ["path"]},
                     handler=_read_project_structure),
        InternalTool(name="read_source_file",
                     description="Read a source file with 1-indexed line numbers.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "start_line": {"type": "integer"},
                                                  "end_line": {"type": "integer"}},
                                   "required": ["path"]},
                     handler=_read_file),
        InternalTool(name="search_code",
                     description="Search codebase (ripgrep if available, Python fallback).",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "query": {"type": "string"},
                                                  "max_hits": {"type": "integer", "default": 100},
                                                  "include_glob": {"type": "string"}},
                                   "required": ["path", "query"]},
                     handler=_search_code),
        InternalTool(name="analyze_error",
                     description="LLM-analyze an error message + suggest fixes.",
                     input_schema={"type": "object",
                                   "properties": {"error_text": {"type": "string"}},
                                   "required": ["error_text"]},
                     handler=_analyze_error),
        InternalTool(name="explain_code",
                     description="LLM-explain a code slice.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "start_line": {"type": "integer"},
                                                  "end_line": {"type": "integer"}},
                                   "required": ["path"]},
                     handler=_explain_code),

        # edit
        InternalTool(name="edit_source_file",
                     description=(
                         "Find/replace an exact substring of a file (L2). The "
                         "match must occur exactly once unless replace_all is true. "
                         "Returns the unified diff."
                     ),
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "old_text": {"type": "string"},
                                                  "new_text": {"type": "string"},
                                                  "replace_all": {"type": "boolean", "default": False}},
                                   "required": ["path", "old_text", "new_text"]},
                     handler=_edit_file),
        InternalTool(name="create_source_file",
                     description="Create a new source file (L2). Refuses to overwrite unless overwrite=true.",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "content": {"type": "string"},
                                                  "overwrite": {"type": "boolean", "default": False}},
                                   "required": ["path", "content"]},
                     handler=_create_file),

        # build / test
        InternalTool(name="run_build",
                     description="Run a build command in a repo (L2).",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "command": {"type": "string"},
                                                  "timeout_sec": {"type": "number", "default": 300}},
                                   "required": ["path", "command"]},
                     handler=_run_build),
        InternalTool(name="run_tests",
                     description="Run a test suite in a repo (L2).",
                     input_schema={"type": "object",
                                   "properties": {"path": {"type": "string"},
                                                  "command": {"type": "string"},
                                                  "timeout_sec": {"type": "number", "default": 600}},
                                   "required": ["path", "command"]},
                     handler=_run_tests),
        InternalTool(name="parse_build_errors",
                     description="Extract structured errors from build/test output and explain them.",
                     input_schema={"type": "object",
                                   "properties": {"output": {"type": "string"}},
                                   "required": ["output"]},
                     handler=_parse_build_errors),

        # workflow
        InternalTool(name="investigate_and_fix",
                     description=(
                         "Multi-step: read tree → search → read files → diagnose "
                         "→ propose exact edits with a diff preview. Does NOT apply."
                     ),
                     input_schema={"type": "object",
                                   "properties": {"request": {"type": "string"},
                                                  "repo_path": {"type": "string"},
                                                  "max_files": {"type": "integer", "default": 3}},
                                   "required": ["request", "repo_path"]},
                     handler=_investigate_and_fix),
        InternalTool(name="apply_proposal",
                     description=(
                         "Apply an investigate_and_fix proposal (L2). Runs its "
                         "suggested test_command after edits when run_tests=true."
                     ),
                     input_schema={"type": "object",
                                   "properties": {"proposal": {"type": "object"},
                                                  "run_tests": {"type": "boolean", "default": True}},
                                   "required": ["proposal"]},
                     handler=_apply_proposal),
    ],
)
