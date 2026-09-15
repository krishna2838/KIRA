"""Google Tasks helpers."""
from __future__ import annotations

from typing import Any

from kira.tools.google_ws.services import run_google, tasks_service


DEFAULT_LIST = "@default"


async def list_tasks(only_open: bool = True) -> list[dict]:
    def _do():
        svc = tasks_service()
        resp = svc.tasks().list(
            tasklist=DEFAULT_LIST,
            showCompleted=not only_open,
            maxResults=50,
        ).execute()
        rows = resp.get("items", [])
        return [
            {
                "id": t["id"],
                "title": t.get("title", ""),
                "notes": t.get("notes", ""),
                "due": t.get("due"),
                "status": t.get("status", "needsAction"),
                "completed": t.get("completed"),
            }
            for t in rows
        ]
    return await run_google(_do)


async def create_task(title: str, due_date: str | None = None) -> dict:
    def _do():
        svc = tasks_service()
        body: dict = {"title": title}
        if due_date:
            # Google Tasks needs RFC-3339 timestamp; a date is enough.
            body["due"] = due_date + ("T00:00:00.000Z" if "T" not in due_date else "")
        t = svc.tasks().insert(tasklist=DEFAULT_LIST, body=body).execute()
        return {"created": True, "id": t.get("id"), "title": t.get("title")}
    return await run_google(_do)


async def complete_task(task_id: str) -> dict:
    def _do():
        svc = tasks_service()
        t = svc.tasks().get(tasklist=DEFAULT_LIST, task=task_id).execute()
        t["status"] = "completed"
        svc.tasks().update(tasklist=DEFAULT_LIST, task=task_id, body=t).execute()
        return {"completed": True, "id": task_id}
    return await run_google(_do)
