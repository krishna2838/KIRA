"""Multi-step task planner.

A `Plan` is a small ordered list of `Step`s the LLM proposes for a goal.
Each Step names a tool (or free-form action), its arguments, and a short
rationale. The executor iterates the plan, running each step, retrying up
to `max_retries` on failure, and threading state through so a later step
can reference an earlier step's output.

The planner + executor are transport-agnostic — the caller wires them to
whatever dispatch fn they want (in KIRA, this is `ToolExecutor.execute`).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


AsyncGenerate = Callable[[str], Awaitable[str]]
AsyncDispatch = Callable[[str, dict], Awaitable[Any]]  # (tool_name, args) -> result


@dataclass
class Step:
    name: str
    tool: str
    arguments: dict = field(default_factory=dict)
    rationale: str = ""


@dataclass
class SubTask:
    """A richer plan node — for `decompose()`.

    A SubTask names the *desired outcome* and the tools it may use to reach
    it; downstream execution picks one Step per SubTask (typically the
    first satisfied by state resolution). SubTasks form a DAG via `depends_on`.
    """
    name: str
    description: str
    required_tools: list[str] = field(default_factory=list)
    expected_output: str = ""
    depends_on: list[str] = field(default_factory=list)
    step: Step | None = None  # concrete step assigned by decompose()


@dataclass
class StepResult:
    step: Step
    ok: bool
    output: Any = None
    error: str | None = None
    attempts: int = 1


@dataclass
class ExecutionRecord:
    goal: str
    plan: list[Step]
    results: list[StepResult]
    aborted: bool = False
    abort_reason: str | None = None


DECOMPOSE_PROMPT = """You are decomposing a complex goal into ordered sub-tasks.

Goal: {goal}

Available tools (name — description):
{tools}

Return a JSON array. Each item:

  {{
    "name": "short_snake_case_id",
    "description": "what this sub-task accomplishes",
    "required_tools": ["<tool_name>", ...],
    "expected_output": "what this step produces (single line)",
    "depends_on": ["<other_step_name>", ...],
    "tool": "<the single tool to actually call>",
    "arguments": {{...}}
  }}

Rules:
- Every `tool` and every entry of `required_tools` MUST come from the tool list above.
- `depends_on` names steps that must run first.
- For arguments that depend on a previous step's output, use
  {{"$ref": "<step_name>.<jsonpath>"}}.
- Reads before writes; verification (tests/checks) after writes.
- Keep the graph small — 3–8 nodes.
- If the goal can't be planned with these tools, return an empty array.

JSON only.
"""


PLAN_PROMPT = """You are planning a multi-step task for a coding assistant.

Goal: {goal}

Available tools (name — description):
{tools}

Break the goal into 3–8 discrete steps. Return a JSON array where each item
looks like:

  {{"name": "…", "tool": "<tool_name>", "arguments": {{…}}, "rationale": "…"}}

Rules:
- Every step's `tool` MUST come from the list above.
- Use `{{"$ref": "step_name.<jsonpath>"}}` for arguments that depend on a
  previous step's output.
- Keep steps small — one tool call each. Reads before writes. Tests after edits.
- If you can't plan the goal with these tools, return an empty array.

JSON only.
"""


def _extract_json_array(text: str) -> list[dict]:
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
        return arr if isinstance(arr, list) else []
    except Exception:
        return []


def _resolve_refs(value: Any, state: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        if len(value) == 1 and "$ref" in value:
            ref = str(value["$ref"])
            parts = ref.split(".")
            step_name = parts[0]
            node = state.get(step_name)
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


class Planner:
    def __init__(self, generate: AsyncGenerate | None = None, router=None):
        # Prefer explicit `generate`; fall back to the router's smart tier.
        if generate is None and router is not None:
            from kira.types import ModelTier

            async def _from_router(prompt: str) -> str:
                return await router.generate(
                    ModelTier.SMART, [{"role": "user", "content": prompt}]
                )
            generate = _from_router
        self.generate = generate

    async def decompose(self, goal: str, tools: list[dict]) -> list[SubTask]:
        """Return a DAG of SubTasks. Each carries a concrete `step` to run.

        The returned list is already topologically ordered (parents first).
        Circular dependencies get broken by the topological sorter with a
        `depends_on` prune.
        """
        if self.generate is None or not tools:
            return []
        tool_lines = "\n".join(f"- {t['name']} — {t.get('description', '')}" for t in tools)
        try:
            raw = await self.generate(DECOMPOSE_PROMPT.format(goal=goal, tools=tool_lines))
        except Exception:
            return []

        rows = _extract_json_array(raw)
        subtasks: list[SubTask] = []
        for row in rows:
            if not isinstance(row, dict) or "tool" not in row or "name" not in row:
                continue
            step = Step(
                name=str(row["name"]),
                tool=str(row["tool"]),
                arguments=dict(row.get("arguments") or {}),
                rationale=str(row.get("description") or ""),
            )
            subtasks.append(SubTask(
                name=str(row["name"]),
                description=str(row.get("description") or ""),
                required_tools=[str(t) for t in (row.get("required_tools") or [])],
                expected_output=str(row.get("expected_output") or ""),
                depends_on=[str(d) for d in (row.get("depends_on") or [])],
                step=step,
            ))
        return topological_order(subtasks)

    async def plan(self, goal: str, tools: list[dict]) -> list[Step]:
        """Produce a Plan for `goal` given the callable tools.

        `tools` is a list of `{"name": ..., "description": ...}`.
        """
        if self.generate is None or not tools:
            return []
        tool_lines = "\n".join(f"- {t['name']} — {t.get('description', '')}" for t in tools)
        try:
            raw = await self.generate(PLAN_PROMPT.format(goal=goal, tools=tool_lines))
        except Exception:
            return []
        rows = _extract_json_array(raw)
        steps: list[Step] = []
        for row in rows:
            if not isinstance(row, dict) or "tool" not in row:
                continue
            steps.append(Step(
                name=str(row.get("name") or row.get("tool")),
                tool=str(row["tool"]),
                arguments=dict(row.get("arguments") or {}),
                rationale=str(row.get("rationale") or ""),
            ))
        return steps


def topological_order(subtasks: list[SubTask]) -> list[SubTask]:
    """Kahn's algorithm. Nodes whose depends_on reference unknown names have
    those unknown edges dropped (planner sometimes hallucinates names)."""
    by_name = {s.name: s for s in subtasks}
    # Prune unknown deps
    for s in subtasks:
        s.depends_on = [d for d in s.depends_on if d in by_name and d != s.name]

    remaining = {s.name: set(s.depends_on) for s in subtasks}
    ordered: list[SubTask] = []
    ready = [n for n, deps in remaining.items() if not deps]
    while ready:
        n = ready.pop(0)
        ordered.append(by_name[n])
        del remaining[n]
        for m, deps in remaining.items():
            if n in deps:
                deps.remove(n)
                if not deps:
                    ready.append(m)
    # Anything left is part of a cycle — append in original order to keep them.
    for name in list(remaining.keys()):
        ordered.append(by_name[name])
    return ordered


class PlanExecutor:
    def __init__(self, dispatch: AsyncDispatch, *, max_retries: int = 1):
        self.dispatch = dispatch
        self.max_retries = max_retries

    async def execute(self, goal: str, plan: list[Step],
                      *, abort_on_error: bool = True) -> ExecutionRecord:
        results: list[StepResult] = []
        state: dict[str, Any] = {}
        record = ExecutionRecord(goal=goal, plan=plan, results=results)

        for step in plan:
            args = _resolve_refs(step.arguments, state)
            attempt = 0
            last_error: str | None = None
            output: Any = None
            ok = False
            while attempt <= self.max_retries:
                attempt += 1
                try:
                    output = await self.dispatch(step.tool, args if isinstance(args, dict) else {})
                    ok = True
                    break
                except Exception as e:
                    last_error = str(e)
                    if attempt > self.max_retries:
                        break
            results.append(StepResult(step=step, ok=ok, output=output,
                                      error=last_error, attempts=attempt))
            if ok:
                state[step.name] = output
            elif abort_on_error:
                record.aborted = True
                record.abort_reason = f"{step.name} failed: {last_error}"
                break
        return record

    async def execute_graph(
        self,
        goal: str,
        subtasks: list[SubTask],
        *,
        skip_dependents_on_error: bool = True,
    ) -> ExecutionRecord:
        """Run a `decompose()` graph. Steps whose upstream dependency failed
        are skipped (and reported as such)."""
        ordered = topological_order(subtasks)
        plan = [s.step for s in ordered if s.step is not None]
        results: list[StepResult] = []
        state: dict[str, Any] = {}
        failed: set[str] = set()
        record = ExecutionRecord(goal=goal, plan=plan, results=results)

        by_name = {s.name: s for s in ordered}
        for sub in ordered:
            if sub.step is None:
                continue
            # Skip if any upstream failed.
            if skip_dependents_on_error and any(d in failed for d in sub.depends_on):
                results.append(StepResult(
                    step=sub.step, ok=False, output=None,
                    error=f"skipped — dependency failed", attempts=0,
                ))
                failed.add(sub.name)
                continue

            args = _resolve_refs(sub.step.arguments, state)
            attempt = 0
            last_error: str | None = None
            output: Any = None
            ok = False
            while attempt <= self.max_retries:
                attempt += 1
                try:
                    output = await self.dispatch(sub.step.tool,
                                                 args if isinstance(args, dict) else {})
                    ok = True
                    break
                except Exception as e:
                    last_error = str(e)
                    if attempt > self.max_retries:
                        break
            results.append(StepResult(
                step=sub.step, ok=ok, output=output,
                error=last_error, attempts=attempt,
            ))
            if ok:
                state[sub.name] = output
            else:
                failed.add(sub.name)
        if failed:
            record.aborted = False if not skip_dependents_on_error else False
            # Not "aborted" — we ran what we could. The caller inspects results.
        return record
