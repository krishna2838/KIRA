"""Scheduled tasks.

A scheduled task is:
  - a `name` (unique)
  - either a cron expression (recurring) or a delay (one-shot)
  - a `tool_chain` — a list of {tool, arguments} calls to execute in order,
    each argument dict optionally uses {"$ref": "<prev_step_name>.<path>"}
    the same way the Planner does.

APScheduler drives the timing; every fired job runs through `_run_chain`,
which iterates the tool_chain and dispatches each step through the caller-
supplied `dispatch(tool, args)` (in KIRA, the ToolExecutor). Every scheduled
run persists `last_run` + a compact `last_result` string.
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable


AsyncDispatch = Callable[[str, dict], Awaitable[Any]]


_REF_RE = re.compile(r"^\$ref:")


def _resolve_refs(value: Any, state: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        if len(value) == 1 and "$ref" in value:
            ref = str(value["$ref"])
            parts = ref.split(".")
            node: Any = state.get(parts[0])
            for key in parts[1:]:
                if isinstance(node, dict):
                    node = node.get(key)
                elif isinstance(node, list) and key.isdigit():
                    idx = int(key)
                    node = node[idx] if 0 <= idx < len(node) else None
                else:
                    node = None
            return node
        return {k: _resolve_refs(v, state) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(v, state) for v in value]
    return value


class TaskScheduler:
    def __init__(self, db, dispatch: AsyncDispatch, *, on_result=None):
        """
        `dispatch(tool_name, args)` is the async callable that runs one
        tool call (typically `ToolExecutor.execute` re-shaped to return a
        payload / raise on failure).

        `on_result(name, chain_outcome)` is an optional callback so a
        proactive engine can inspect scheduled-task output and decide
        whether to surface it.
        """
        self.db = db
        self.dispatch = dispatch
        self.on_result = on_result
        self._scheduler = None
        self._enabled = False

    # -- lifecycle ---------------------------------------------------

    def _new_scheduler(self):
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
            return AsyncIOScheduler()
        except Exception as e:
            raise RuntimeError(
                "APScheduler is required (pip install APScheduler): " + str(e)
            ) from e

    async def start(self) -> bool:
        if self._enabled:
            return True
        try:
            self._scheduler = self._new_scheduler()
            self._scheduler.start()
        except Exception:
            self._scheduler = None
            return False
        self._enabled = True
        # Restore persisted tasks
        try:
            rows = await self.db.fetch(
                "SELECT name, cron_expression, tool_chain, enabled FROM scheduled_tasks"
            )
            for row in rows:
                if not row["enabled"] or not row["cron_expression"]:
                    continue
                self._add_cron_job(row["name"], row["cron_expression"])
        except Exception:
            pass
        return True

    async def stop(self) -> None:
        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception:
                pass
        self._scheduler = None
        self._enabled = False

    # -- CRUD --------------------------------------------------------

    async def schedule_task(
        self,
        name: str,
        cron: str,
        tool_chain: list[dict],
        permissions_required: int = 0,
        enabled: bool = True,
    ) -> dict:
        await self.db.execute(
            """INSERT INTO scheduled_tasks
               (name, cron_expression, tool_chain, permissions_required, enabled)
               VALUES ($1, $2, $3::jsonb, $4, $5)
               ON CONFLICT (name) DO UPDATE SET
                 cron_expression = EXCLUDED.cron_expression,
                 tool_chain = EXCLUDED.tool_chain,
                 permissions_required = EXCLUDED.permissions_required,
                 enabled = EXCLUDED.enabled""",
            name, cron, json.dumps(tool_chain), int(permissions_required), enabled,
        )
        if self._scheduler is not None and enabled:
            self._remove_job(name)
            self._add_cron_job(name, cron)
        return {"name": name, "cron": cron, "enabled": enabled}

    async def run_once(
        self,
        name: str,
        tool_chain: list[dict],
        delay_seconds: int = 0,
        permissions_required: int = 0,
    ) -> dict:
        """Fire a one-shot task after `delay_seconds`. Not persisted."""
        if self._scheduler is None:
            # Fall back to running it inline.
            asyncio.create_task(self._run_chain(name, tool_chain))
            return {"name": name, "scheduled": False, "ran_inline": True}
        try:
            from apscheduler.triggers.date import DateTrigger  # type: ignore
        except Exception as e:
            return {"name": name, "error": str(e)}
        when = datetime.now(timezone.utc) + timedelta(seconds=int(delay_seconds))
        self._scheduler.add_job(
            self._run_chain,
            trigger=DateTrigger(run_date=when),
            args=[name, tool_chain],
            id=f"once-{name}-{uuid.uuid4().hex[:8]}",
        )
        return {"name": name, "scheduled": True, "when": when.isoformat()}

    async def list_scheduled(self) -> list[dict]:
        rows = await self.db.fetch(
            """SELECT name, cron_expression, tool_chain, permissions_required,
                      enabled, last_run, last_result, created_at
               FROM scheduled_tasks
               ORDER BY name"""
        )
        return [
            {
                "name": r["name"],
                "cron": r["cron_expression"],
                "tool_chain": r["tool_chain"] if isinstance(r["tool_chain"], list)
                               else json.loads(r["tool_chain"]) if r["tool_chain"] else [],
                "permissions_required": r["permissions_required"],
                "enabled": r["enabled"],
                "last_run": r["last_run"].isoformat() if r["last_run"] else None,
                "last_result": r["last_result"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

    async def cancel_task(self, name: str) -> bool:
        await self.db.execute("DELETE FROM scheduled_tasks WHERE name = $1", name)
        self._remove_job(name)
        return True

    async def set_enabled(self, name: str, enabled: bool) -> bool:
        await self.db.execute(
            "UPDATE scheduled_tasks SET enabled = $2 WHERE name = $1",
            name, enabled,
        )
        self._remove_job(name)
        if enabled:
            row = await self.db.fetchrow(
                "SELECT cron_expression FROM scheduled_tasks WHERE name = $1", name
            )
            if row and row["cron_expression"]:
                self._add_cron_job(name, row["cron_expression"])
        return True

    async def run_now(self, name: str) -> dict:
        """Manually trigger a task by name (used from the frontend)."""
        row = await self.db.fetchrow(
            "SELECT tool_chain FROM scheduled_tasks WHERE name = $1", name
        )
        if row is None:
            return {"error": f"unknown task: {name}"}
        chain = row["tool_chain"] if isinstance(row["tool_chain"], list) else json.loads(row["tool_chain"])
        return await self._run_chain(name, chain)

    # -- APScheduler wiring -----------------------------------------

    def _add_cron_job(self, name: str, cron: str) -> None:
        try:
            from apscheduler.triggers.cron import CronTrigger  # type: ignore

            trigger = CronTrigger.from_crontab(cron)
        except Exception:
            return
        # Fetch the chain lazily on fire so DB edits pick up immediately.
        async def _fire():
            row = await self.db.fetchrow(
                "SELECT tool_chain, enabled FROM scheduled_tasks WHERE name = $1", name
            )
            if not row or not row["enabled"]:
                return
            chain = row["tool_chain"] if isinstance(row["tool_chain"], list) else json.loads(row["tool_chain"])
            await self._run_chain(name, chain)

        if self._scheduler is None:
            return
        self._scheduler.add_job(_fire, trigger=trigger, id=f"cron-{name}", replace_existing=True)

    def _remove_job(self, name: str) -> None:
        if self._scheduler is None:
            return
        try:
            self._scheduler.remove_job(f"cron-{name}")
        except Exception:
            pass

    # -- chain execution --------------------------------------------

    async def _run_chain(self, name: str, tool_chain: list[dict]) -> dict:
        state: dict[str, Any] = {}
        outputs: list[dict] = []
        aborted = False
        summary_parts: list[str] = []
        for i, step in enumerate(tool_chain or []):
            step_name = str(step.get("name") or f"step_{i}")
            tool = str(step.get("tool") or "")
            if not tool:
                continue
            raw_args = step.get("arguments") or {}
            args = _resolve_refs(raw_args, state)
            try:
                out = await self.dispatch(tool, args if isinstance(args, dict) else {})
                state[step_name] = out
                outputs.append({"step": step_name, "tool": tool, "ok": True})
                summary_parts.append(f"{step_name}:ok")
            except Exception as e:
                outputs.append({"step": step_name, "tool": tool, "ok": False, "error": str(e)})
                summary_parts.append(f"{step_name}:{str(e)[:60]}")
                aborted = True
                break

        last_result = "; ".join(summary_parts)[:2000]
        try:
            await self.db.execute(
                "UPDATE scheduled_tasks SET last_run = NOW(), last_result = $2 WHERE name = $1",
                name, last_result,
            )
        except Exception:
            pass

        outcome = {"name": name, "outputs": outputs, "aborted": aborted, "state": state}
        if self.on_result is not None:
            try:
                await self.on_result(outcome)
            except Exception:
                pass
        return outcome


# ---- seed defaults ------------------------------------------------


DEFAULT_TASKS = [
    {
        "name": "morning_brief",
        "cron": "0 8 * * 1-5",   # 8:00 weekdays
        "tool_chain": [
            {"name": "brief", "tool": "life.morning_brief", "arguments": {}},
        ],
        "permissions_required": 0,
    },
    {
        "name": "build_monitor",
        "cron": "*/30 * * * *",  # every 30 min
        "tool_chain": [
            # Users can wire specific repos via the frontend; the default
            # tool_chain is a no-op sentinel. When empty, the runner does nothing.
        ],
        "permissions_required": 0,
    },
    {
        "name": "deadline_watch",
        "cron": "0 9 * * *",     # daily 9:00
        "tool_chain": [
            {"name": "deadlines", "tool": "life.list_deadlines",
             "arguments": {"days": 3}},
        ],
        "permissions_required": 0,
    },
]


async def seed_defaults(scheduler: TaskScheduler) -> None:
    for spec in DEFAULT_TASKS:
        try:
            existing = await scheduler.db.fetchval(
                "SELECT 1 FROM scheduled_tasks WHERE name = $1", spec["name"]
            )
            if existing:
                continue
            await scheduler.schedule_task(
                name=spec["name"],
                cron=spec["cron"],
                tool_chain=spec["tool_chain"],
                permissions_required=spec["permissions_required"],
                enabled=True,
            )
        except Exception:
            continue
