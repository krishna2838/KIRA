"""Tests for memory helpers that don't need a live database."""
from kira.memory.context import WorkingContext
from kira.core.types import KiraState


def test_working_context_default_state():
    ctx = WorkingContext()
    assert ctx.state == KiraState.IDLE
    assert ctx.to_string().startswith("No prior context")


def test_working_context_tracks_entities():
    ctx = WorkingContext()
    for name in ["React", "KIRA", "PostgreSQL"]:
        ctx.add_entity(name)
    ctx.add_entity("React")  # dedupe
    assert ctx.recent_entities == ["React", "KIRA", "PostgreSQL"]


def test_working_context_caps_entities():
    ctx = WorkingContext()
    for i in range(30):
        ctx.add_entity(f"e{i}")
    assert len(ctx.recent_entities) == 20


def test_working_context_summary_includes_topic():
    ctx = WorkingContext()
    ctx.update_topic("Phase 1 build")
    ctx.add_fact("Uses gemma3:8b as smart tier")
    s = ctx.to_string()
    assert "Phase 1 build" in s
    assert "gemma3:8b" in s
