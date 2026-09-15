"""Git operations via GitPython.

Falls back to raising a friendly RuntimeError if GitPython isn't installed,
so the coding server can still expose non-git tools.
"""
from __future__ import annotations

import asyncio
import os


def _git():
    try:
        import git  # type: ignore  # GitPython
        return git
    except Exception as e:
        raise RuntimeError(
            "GitPython is required for git tools (pip install GitPython): "
            + str(e)
        ) from e


def _open(repo_path: str):
    git = _git()
    return git.Repo(os.path.expanduser(repo_path), search_parent_directories=True)


async def status(repo_path: str) -> dict:
    def _do():
        repo = _open(repo_path)
        branch = repo.active_branch.name if not repo.head.is_detached else "(detached)"
        changed = [i.a_path for i in repo.index.diff(None)]
        staged = [i.a_path for i in repo.index.diff("HEAD")]
        untracked = list(repo.untracked_files)
        return {
            "repo": repo.working_tree_dir,
            "branch": branch,
            "detached": repo.head.is_detached,
            "changed": changed,
            "staged": staged,
            "untracked": untracked,
            "clean": not (changed or staged or untracked),
        }
    return await asyncio.to_thread(_do)


async def diff(repo_path: str, staged: bool = False) -> dict:
    def _do():
        repo = _open(repo_path)
        text = repo.git.diff("--cached") if staged else repo.git.diff()
        return {"repo": repo.working_tree_dir, "diff": text[:60000], "staged": staged}
    return await asyncio.to_thread(_do)


async def log(repo_path: str, n: int = 10) -> dict:
    def _do():
        repo = _open(repo_path)
        entries = []
        for c in repo.iter_commits(max_count=n):
            entries.append({
                "sha": c.hexsha[:12],
                "author": f"{c.author.name} <{c.author.email}>",
                "date": c.committed_datetime.isoformat(),
                "summary": c.summary,
            })
        return {"repo": repo.working_tree_dir, "commits": entries}
    return await asyncio.to_thread(_do)


async def branch_list(repo_path: str) -> dict:
    def _do():
        repo = _open(repo_path)
        current = repo.active_branch.name if not repo.head.is_detached else None
        branches = [h.name for h in repo.heads]
        remote = []
        try:
            remote = [r.name for r in repo.remote().refs]
        except Exception:
            pass
        return {"current": current, "local": branches, "remote": remote}
    return await asyncio.to_thread(_do)


async def checkout(repo_path: str, branch: str) -> dict:
    def _do():
        repo = _open(repo_path)
        repo.git.checkout(branch)
        return {"checked_out": branch, "current": repo.active_branch.name}
    return await asyncio.to_thread(_do)


async def commit(repo_path: str, message: str) -> dict:
    def _do():
        repo = _open(repo_path)
        if not repo.index.diff("HEAD"):
            return {"committed": False, "reason": "nothing staged"}
        c = repo.index.commit(message)
        return {"committed": True, "sha": c.hexsha[:12], "summary": c.summary}
    return await asyncio.to_thread(_do)


async def push(repo_path: str, remote: str = "origin", branch: str | None = None) -> dict:
    def _do():
        repo = _open(repo_path)
        target_branch = branch or (repo.active_branch.name if not repo.head.is_detached else None)
        if target_branch is None:
            return {"pushed": False, "reason": "detached HEAD"}
        info = repo.remote(remote).push(target_branch)
        # info is a PushInfoList; make it JSON-friendly.
        return {
            "pushed": True,
            "remote": remote,
            "branch": target_branch,
            "results": [str(i) for i in info],
        }
    return await asyncio.to_thread(_do)
