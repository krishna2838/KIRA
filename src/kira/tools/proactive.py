"""Proactive intelligence engine.

Sits *above* the Phase 6 Monitor. The Monitor produces raw events (upcoming
meetings, unread-email deltas, etc.); ProactiveEngine adds:

  - event *sources* that don't fit the Monitor's polling model (build
    monitor via scheduled tasks, deadline watch via life OS)
  - a **relevance scorer**: urgency × relevance × actionability, thresholded
    at `min_score` (config)
  - an **intervention classifier**: NOTIFY / SUGGEST / ACT / SILENT
  - **smart timing**: never push during active conversation; batch similar
    events; hold low-priority items until the next user message.

Scored events land in a queue the frontend/StatusBar drains via
`/api/proactive/queue`. Batches of duplicates coalesce into one card
("3 new build failures").
"""
from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable


class Intervention(str, Enum):
    NOTIFY = "notify"     # tell the user
    SUGGEST = "suggest"   # offer help
    ACT = "act"           # take action WITH permission
    SILENT = "silent"     # log only


@dataclass
class ProactiveEvent:
    kind: str                        # "upcoming_meeting", "build_failure", …
    title: str
    message: str
    urgency: float = 0.5             # 0..1
    relevance: float = 0.5           # 0..1
    actionability: float = 0.5       # 0..1
    detail: dict = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    dedupe_key: str = ""             # events sharing this key coalesce
    intervention: Intervention = Intervention.NOTIFY
    score: float = 0.0

    def compute_score(self) -> float:
        self.score = float(self.urgency) * float(self.relevance) * float(self.actionability)
        return self.score


DEFAULT_MIN_SCORE = 0.6


AsyncGenerate = Callable[[str], Awaitable[str]]


_RELEVANCE_PROMPT = """Score the following event for a busy user right now.
Reply with a single JSON object:

  {{"urgency": 0.0-1.0, "relevance": 0.0-1.0, "actionability": 0.0-1.0,
    "intervention": "notify"|"suggest"|"act"|"silent"}}

Event kind: {kind}
Title: {title}
Message: {message}
Detail: {detail}

Guidance:
- urgency: how time-sensitive is it? Meetings in 15min = 0.9. Weekly report = 0.2.
- relevance: does it need the user's attention (vs. background noise)? Direct
  message to them = 0.9. Batch newsletter = 0.1.
- actionability: can the user actually do something about it right now? 0.9
  if there's a clear next action, 0.2 if it's just context.
- intervention: notify (just tell them), suggest (offer help), act (take
  action *with permission*), silent (log only).

JSON only.
"""


class ProactiveEngine:
    """Orchestrates the proactive event stream.

    Consumers:
      - `push(event)` from any source (monitor, scheduler-on-result, watchers)
      - Optionally `set_summarize_fn(fn)` for LLM-based scoring
      - `pop_events(max_items)` to drain

    We enforce three rules:
      1. NEVER push while `active` (user is chatting) unless urgency > 0.9.
      2. Batch: events with the same `dedupe_key` within a batch window
         collapse into one card ("3 items — see details").
      3. Only surface `score >= min_score` events. Anything below is stored
         as SILENT (still visible in a lower-priority feed).
    """

    def __init__(
        self,
        *,
        min_score: float = DEFAULT_MIN_SCORE,
        batch_window_sec: int = 30,
        max_queue: int = 200,
    ):
        self.min_score = min_score
        self.batch_window_sec = batch_window_sec
        self._queue: list[ProactiveEvent] = []
        self._silent: list[ProactiveEvent] = []
        self._max_queue = max_queue
        self._active = False
        self._lock = asyncio.Lock()
        self._score_fn: AsyncGenerate | None = None
        self._batch_open: dict[str, list[ProactiveEvent]] = defaultdict(list)
        self._batch_deadline: dict[str, float] = {}

    # -- config ------------------------------------------------------

    def set_active(self, active: bool) -> None:
        self._active = active

    def set_scorer(self, generate: AsyncGenerate | None) -> None:
        self._score_fn = generate

    # -- inbound -----------------------------------------------------

    async def push(self, event: ProactiveEvent) -> None:
        # 1. Ask the LLM for a nuanced score when we have one, otherwise use
        #    whatever the source pre-populated.
        if self._score_fn is not None:
            scored = await self._llm_rescore(event)
            if scored is not None:
                event.urgency, event.relevance, event.actionability, event.intervention = scored
        event.compute_score()

        # 2. Route by threshold.
        if event.score < self.min_score and event.intervention != Intervention.ACT:
            self._silent.append(event)
            if len(self._silent) > self._max_queue:
                self._silent.pop(0)
            return

        # 3. Timing rule: hold non-critical events while the user is active.
        # Anything with urgency > 0.9 punches through.
        if self._active and event.urgency <= 0.9:
            await self._enqueue(event)
            return

        # 4. Batch coalescing.
        if event.dedupe_key:
            await self._batch(event)
        else:
            await self._enqueue(event)

    async def _llm_rescore(self, event: ProactiveEvent):
        assert self._score_fn is not None
        try:
            raw = await self._score_fn(_RELEVANCE_PROMPT.format(
                kind=event.kind,
                title=event.title,
                message=event.message[:400],
                detail=str(event.detail)[:400],
            ))
        except Exception:
            return None
        try:
            import json
            obj = json.loads(_first_json(raw))
            urgency = float(obj.get("urgency", event.urgency))
            relevance = float(obj.get("relevance", event.relevance))
            actionability = float(obj.get("actionability", event.actionability))
            intervention = Intervention(str(obj.get("intervention", event.intervention.value)))
            return (urgency, relevance, actionability, intervention)
        except Exception:
            return None

    async def _batch(self, event: ProactiveEvent) -> None:
        async with self._lock:
            bucket = self._batch_open[event.dedupe_key]
            bucket.append(event)
            deadline = time.monotonic() + self.batch_window_sec
            self._batch_deadline[event.dedupe_key] = deadline
            # First event in a bucket schedules the flush.
            if len(bucket) == 1:
                asyncio.create_task(self._flush_after(event.dedupe_key))

    async def _flush_after(self, key: str) -> None:
        await asyncio.sleep(self.batch_window_sec + 0.1)
        async with self._lock:
            bucket = self._batch_open.pop(key, [])
            self._batch_deadline.pop(key, None)
        if not bucket:
            return
        if len(bucket) == 1:
            await self._enqueue(bucket[0])
            return
        # Coalesce
        first = bucket[0]
        coalesced = ProactiveEvent(
            kind=first.kind,
            title=f"{len(bucket)}× {first.title}",
            message=f"{len(bucket)} similar events. Latest: {bucket[-1].message}",
            urgency=max(e.urgency for e in bucket),
            relevance=max(e.relevance for e in bucket),
            actionability=max(e.actionability for e in bucket),
            detail={"batch": [e.__dict__ for e in bucket]},
            dedupe_key=key,
            intervention=first.intervention,
        )
        coalesced.compute_score()
        await self._enqueue(coalesced)

    async def _enqueue(self, event: ProactiveEvent) -> None:
        async with self._lock:
            self._queue.append(event)
            if len(self._queue) > self._max_queue:
                self._queue.pop(0)

    # -- outbound ---------------------------------------------------

    async def pop_events(self, max_items: int = 20) -> list[dict]:
        async with self._lock:
            take = self._queue[:max_items]
            del self._queue[:max_items]
        return [_shape(e) for e in take]

    async def peek(self, limit: int = 50) -> list[dict]:
        async with self._lock:
            return [_shape(e) for e in self._queue[:limit]]

    async def silent_log(self, limit: int = 50) -> list[dict]:
        return [_shape(e) for e in self._silent[-limit:]]

    def qsize(self) -> int:
        return len(self._queue)


def _shape(e: ProactiveEvent) -> dict:
    return {
        "kind": e.kind,
        "title": e.title,
        "message": e.message,
        "urgency": e.urgency,
        "relevance": e.relevance,
        "actionability": e.actionability,
        "score": e.score,
        "intervention": e.intervention.value,
        "detail": e.detail,
        "generated_at": e.generated_at,
        "dedupe_key": e.dedupe_key,
    }


def _first_json(text: str) -> str:
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0) if m else "{}"


# ---- adapters --------------------------------------------------


def from_monitor_event(evt: dict) -> ProactiveEvent:
    """Wrap a Phase 6 Monitor event as a ProactiveEvent with priors."""
    kind = evt.get("type", "generic")
    urgency, relevance, actionability = _priors_for_kind(kind)
    return ProactiveEvent(
        kind=kind,
        title=evt.get("title", kind),
        message=evt.get("message", ""),
        urgency=urgency,
        relevance=relevance,
        actionability=actionability,
        detail=evt.get("detail") or {},
        dedupe_key=kind,
        intervention=_intervention_for_kind(kind),
    )


def _priors_for_kind(kind: str) -> tuple[float, float, float]:
    return {
        "upcoming_meeting": (0.9, 0.9, 0.8),
        "new_email_batch":  (0.4, 0.6, 0.5),
        "build_failure":    (0.8, 0.9, 0.9),
        "build_success":    (0.2, 0.5, 0.2),
        "deadline_soon":    (0.85, 0.9, 0.7),
        "issue_review":     (0.5, 0.7, 0.6),
    }.get(kind, (0.5, 0.5, 0.5))


def _intervention_for_kind(kind: str) -> Intervention:
    return {
        "upcoming_meeting": Intervention.NOTIFY,
        "new_email_batch":  Intervention.NOTIFY,
        "build_failure":    Intervention.SUGGEST,
        "build_success":    Intervention.SILENT,
        "deadline_soon":    Intervention.SUGGEST,
        "issue_review":     Intervention.NOTIFY,
    }.get(kind, Intervention.NOTIFY)
