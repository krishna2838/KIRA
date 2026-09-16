"""GitHub REST via PyGithub, with the PAT stored in the macOS Keychain."""
from __future__ import annotations

import asyncio


KEYRING_SERVICE = "KIRA/github"
KEYRING_USER = "pat"


def _keyring():
    try:
        import keyring  # type: ignore
        return keyring
    except Exception as e:
        raise RuntimeError(
            "keyring is required for GitHub PAT storage: " + str(e)
        ) from e


def get_pat() -> str | None:
    try:
        return _keyring().get_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        return None


def set_pat(token: str) -> None:
    _keyring().set_password(KEYRING_SERVICE, KEYRING_USER, token.strip())


def forget_pat() -> None:
    try:
        _keyring().delete_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        pass


def has_pat() -> bool:
    return bool(get_pat())


def _client():
    try:
        from github import Github, Auth  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "PyGithub is required (pip install PyGithub): " + str(e)
        ) from e
    pat = get_pat()
    if not pat:
        raise RuntimeError("No GitHub PAT stored. POST /api/auth/github with a token.")
    return Github(auth=Auth.Token(pat), per_page=30)


async def list_repos(limit: int = 30) -> list[dict]:
    def _do():
        gh = _client()
        user = gh.get_user()
        out = []
        for i, r in enumerate(user.get_repos(sort="pushed", direction="desc")):
            if i >= limit:
                break
            out.append({
                "name": r.full_name,
                "private": r.private,
                "url": r.html_url,
                "default_branch": r.default_branch,
                "description": r.description or "",
                "pushed_at": r.pushed_at.isoformat() if r.pushed_at else None,
            })
        return out
    return await asyncio.to_thread(_do)


async def get_repo_issues(repo: str, state: str = "open", limit: int = 20) -> list[dict]:
    def _do():
        gh = _client()
        r = gh.get_repo(repo)
        out = []
        for i, issue in enumerate(r.get_issues(state=state)):
            if i >= limit or issue.pull_request:
                if issue.pull_request:
                    continue
                if i >= limit:
                    break
            out.append({
                "number": issue.number,
                "title": issue.title,
                "url": issue.html_url,
                "state": issue.state,
                "labels": [l.name for l in issue.labels],
                "created_at": issue.created_at.isoformat() if issue.created_at else None,
                "author": issue.user.login if issue.user else "",
            })
        return out
    return await asyncio.to_thread(_do)


async def create_issue(repo: str, title: str, body: str = "") -> dict:
    def _do():
        gh = _client()
        r = gh.get_repo(repo)
        issue = r.create_issue(title=title, body=body)
        return {"created": True, "number": issue.number, "url": issue.html_url}
    return await asyncio.to_thread(_do)


async def get_pull_requests(repo: str, state: str = "open", limit: int = 20) -> list[dict]:
    def _do():
        gh = _client()
        r = gh.get_repo(repo)
        out = []
        for i, pr in enumerate(r.get_pulls(state=state, sort="updated", direction="desc")):
            if i >= limit:
                break
            out.append({
                "number": pr.number,
                "title": pr.title,
                "url": pr.html_url,
                "state": pr.state,
                "draft": pr.draft,
                "user": pr.user.login if pr.user else "",
                "head": pr.head.ref if pr.head else "",
                "base": pr.base.ref if pr.base else "",
                "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
            })
        return out
    return await asyncio.to_thread(_do)


async def get_actions_status(repo: str, limit: int = 10) -> dict:
    """Return the status of recent workflow runs on the default branch."""
    def _do():
        gh = _client()
        r = gh.get_repo(repo)
        runs = r.get_workflow_runs(branch=r.default_branch)
        out = []
        for i, run in enumerate(runs):
            if i >= limit:
                break
            out.append({
                "id": run.id,
                "name": run.name,
                "status": run.status,
                "conclusion": run.conclusion,
                "url": run.html_url,
                "head_sha": run.head_sha[:12] if run.head_sha else "",
                "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            })
        summary = {"passing": 0, "failing": 0, "in_progress": 0}
        for run in out:
            if run["status"] == "completed":
                if run["conclusion"] == "success":
                    summary["passing"] += 1
                elif run["conclusion"] in ("failure", "cancelled", "timed_out"):
                    summary["failing"] += 1
            else:
                summary["in_progress"] += 1
        return {"repo": repo, "runs": out, "summary": summary}
    return await asyncio.to_thread(_do)


async def read_file_from_github(repo: str, path: str, ref: str | None = None) -> dict:
    def _do():
        gh = _client()
        r = gh.get_repo(repo)
        content = r.get_contents(path, ref=ref) if ref else r.get_contents(path)
        # Non-file (directory) returns a list.
        if isinstance(content, list):
            return {
                "path": path,
                "is_directory": True,
                "entries": [{"name": c.name, "path": c.path, "type": c.type} for c in content],
            }
        try:
            text = content.decoded_content.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return {
            "path": content.path,
            "size": content.size,
            "sha": content.sha,
            "url": content.html_url,
            "content": text[:60000],
        }
    return await asyncio.to_thread(_do)
