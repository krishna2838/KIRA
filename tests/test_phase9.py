"""Tests for Phase 9 primitives (offline-safe)."""
import asyncio

from kira.brain.planner import (
    PlanExecutor,
    Planner,
    Step,
    SubTask,
    topological_order,
)
from kira.tools.proactive import (
    Intervention,
    ProactiveEngine,
    ProactiveEvent,
    from_monitor_event,
)


# ---- topological order --------------------------------------------------


def test_topological_order_respects_deps():
    subs = [
        SubTask(name="c", description="", depends_on=["b"]),
        SubTask(name="b", description="", depends_on=["a"]),
        SubTask(name="a", description="", depends_on=[]),
    ]
    ordered = topological_order(subs)
    assert [s.name for s in ordered] == ["a", "b", "c"]


def test_topological_prunes_unknown_deps():
    subs = [
        SubTask(name="a", description="", depends_on=["missing"]),
    ]
    ordered = topological_order(subs)
    assert [s.name for s in ordered] == ["a"]
    assert subs[0].depends_on == []


def test_topological_handles_cycle_gracefully():
    subs = [
        SubTask(name="a", depends_on=["b"], description=""),
        SubTask(name="b", depends_on=["a"], description=""),
    ]
    ordered = topological_order(subs)
    # Both survive, ordering falls back to insertion order.
    assert {s.name for s in ordered} == {"a", "b"}


# ---- graph execution ---------------------------------------------------


def test_execute_graph_skips_dependents_when_upstream_fails():
    calls: list[str] = []

    async def dispatch(tool: str, args: dict):
        calls.append(tool)
        if tool == "fail":
            raise RuntimeError("boom")
        return {"ok": True}

    subs = [
        SubTask(name="root", step=Step(name="root", tool="fail"),
                description="", depends_on=[]),
        SubTask(name="child", step=Step(name="child", tool="ok"),
                description="", depends_on=["root"]),
        SubTask(name="sibling", step=Step(name="sibling", tool="ok"),
                description="", depends_on=[]),
    ]
    executor = PlanExecutor(dispatch, max_retries=0)
    rec = asyncio.run(executor.execute_graph("goal", subs))
    ok = {r.step.name: r.ok for r in rec.results}
    assert ok["root"] is False
    assert ok["child"] is False    # skipped
    assert ok["sibling"] is True   # independent branch survives
    # child should never dispatch; only "fail" + "ok" (sibling) called.
    assert "fail" in calls
    assert calls.count("ok") == 1


# ---- proactive scoring + queueing --------------------------------------


def test_proactive_score_below_threshold_is_silenced():
    engine = ProactiveEngine(min_score=0.5, batch_window_sec=0)
    evt = ProactiveEvent(
        kind="new_email_batch", title="1 new", message="one",
        urgency=0.2, relevance=0.2, actionability=0.2,
        intervention=Intervention.NOTIFY,
    )
    asyncio.run(engine.push(evt))
    q = asyncio.run(engine.pop_events())
    silent = asyncio.run(engine.silent_log())
    assert q == []
    assert len(silent) == 1


def test_proactive_score_above_threshold_surfaces():
    engine = ProactiveEngine(min_score=0.5, batch_window_sec=0)
    evt = ProactiveEvent(
        kind="build_failure", title="build red", message="ci failed",
        urgency=0.9, relevance=0.9, actionability=0.9,
    )
    asyncio.run(engine.push(evt))
    q = asyncio.run(engine.pop_events())
    assert len(q) == 1
    assert q[0]["kind"] == "build_failure"
    assert q[0]["score"] > 0.5


def test_proactive_holds_low_urgency_while_active():
    engine = ProactiveEngine(min_score=0.1, batch_window_sec=0)
    engine.set_active(True)
    evt = ProactiveEvent(
        kind="new_email_batch", title="3 new", message="…",
        urgency=0.4, relevance=0.9, actionability=0.9,
    )
    asyncio.run(engine.push(evt))
    # Held in the queue, but the test peek+pop still yields it — the "hold"
    # rule affects whether we push during chat; drainable via pop_events.
    q = asyncio.run(engine.pop_events())
    assert len(q) == 1


def test_proactive_from_monitor_maps_priors():
    evt = from_monitor_event({
        "type": "upcoming_meeting",
        "title": "Standup",
        "message": "in 15 min",
        "detail": {},
    })
    assert evt.kind == "upcoming_meeting"
    assert evt.urgency >= 0.8
    assert evt.intervention == Intervention.NOTIFY


def test_proactive_from_monitor_build_defaults_to_suggest():
    evt = from_monitor_event({
        "type": "build_failure",
        "title": "build red",
        "message": "…",
    })
    assert evt.intervention == Intervention.SUGGEST
