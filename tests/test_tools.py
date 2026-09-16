"""Tests for the tools subsystem (offline-safe)."""
import asyncio

import pytest

from kira.core.permissions import PermissionEngine, ToolPermission
from kira.core.types import RiskLevel

from kira.tools.executor import ToolExecutor
from kira.tools.registry import ToolRegistry
from kira.tools.tool_router import ToolRouter, _cosine
from kira.tools.servers.base import InternalServer, InternalTool
from kira.tools.servers.terminal_server import classify_command
from kira.tools.types import ToolCall


# ---- fakes --------------------------------------------------------------


class FakeEmbeddings:
    """Deterministic hash-based embeddings, small dimension."""

    async def embed(self, text: str) -> list[float]:
        vec = [0.0] * 8
        for i, ch in enumerate(text.lower().encode("utf-8")):
            vec[i % 8] += (ch % 13) / 13.0
        # Normalize
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]


def _sample_server() -> InternalServer:
    async def echo(args: dict):
        return {"echo": args}

    return InternalServer(
        name="s",
        description="sample",
        tools=[
            InternalTool(
                name="echo",
                description="Echo back the input arguments verbatim.",
                input_schema={"type": "object"},
                handler=echo,
            ),
            InternalTool(
                name="add",
                description="Add two numbers together and return the sum.",
                input_schema={"type": "object"},
                handler=lambda args: asyncio.sleep(0, result={"sum": args["a"] + args["b"]}),
            ),
        ],
    )


# ---- cosine --------------------------------------------------------------


def test_cosine_identical_is_one():
    assert abs(_cosine([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9


def test_cosine_orthogonal_is_zero():
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


# ---- registry ------------------------------------------------------------


def test_registry_lists_internal_tools():
    reg = ToolRegistry(embeddings=FakeEmbeddings())
    reg.register_internal(_sample_server())
    tools = reg.all_tools()
    assert {t.qualified_name for t in tools} == {"s.echo", "s.add"}
    assert reg.servers()[0]["transport"] == "internal"


def test_registry_dispatch_internal():
    reg = ToolRegistry(embeddings=FakeEmbeddings())
    reg.register_internal(_sample_server())
    out = asyncio.run(reg.dispatch("s.echo", {"hi": 1}))
    assert out == {"echo": {"hi": 1}}


# ---- tool router --------------------------------------------------------


def test_tool_router_returns_topk():
    reg = ToolRegistry(embeddings=FakeEmbeddings())
    reg.register_internal(_sample_server())
    asyncio.run(reg.build_embeddings())
    tr = ToolRouter(reg, FakeEmbeddings(), top_k=1)
    hits = asyncio.run(tr.relevant_tools("please echo my values back"))
    assert len(hits) == 1
    assert hits[0][0].qualified_name in {"s.echo", "s.add"}


# ---- permissions --------------------------------------------------------


def test_permission_override_deny_and_allow():
    engine = PermissionEngine(
        auto_approve_level=1,
        tool_overrides={
            "web.web_search": ToolPermission(mode="allow"),
            "terminal.run_command": ToolPermission(mode="deny"),
        },
    )
    dec, _ = engine.decide("web.web_search")
    assert dec == "allow"
    dec, _ = engine.decide("terminal.run_command")
    assert dec == "deny"


def test_rate_limit_blocks_after_quota():
    engine = PermissionEngine(
        tool_overrides={
            "web.web_search": ToolPermission(rate_limit_per_min=2),
        }
    )
    assert engine.check_and_record_rate("web.web_search", now=1000.0)
    assert engine.check_and_record_rate("web.web_search", now=1001.0)
    assert not engine.check_and_record_rate("web.web_search", now=1002.0)
    # After the window rolls, allowed again.
    assert engine.check_and_record_rate("web.web_search", now=1200.0)


def test_web_search_classifies_as_read():
    engine = PermissionEngine()
    assert engine.classify_risk("web.web_search") == RiskLevel.READ


def test_run_command_classifies_as_execute():
    engine = PermissionEngine()
    assert engine.classify_risk("terminal.run_command") == RiskLevel.EXECUTE


# ---- executor -----------------------------------------------------------


def test_executor_auto_approves_read_tool():
    reg = ToolRegistry(embeddings=FakeEmbeddings())
    reg.register_internal(
        InternalServer(
            name="web",
            description="web",
            tools=[
                InternalTool(
                    name="web_search",
                    description="Search the web",
                    input_schema={},
                    handler=lambda a: asyncio.sleep(0, result={"query": a["q"]}),
                )
            ],
        )
    )
    engine = PermissionEngine(auto_approve_level=1)
    executor = ToolExecutor(reg, engine)
    outcome = asyncio.run(executor.execute(ToolCall(tool="web.web_search", arguments={"q": "hi"})))
    assert outcome.status == "ok"
    assert outcome.result and outcome.result.ok


def test_executor_requires_confirmation_for_execute_tool():
    reg = ToolRegistry(embeddings=FakeEmbeddings())
    reg.register_internal(
        InternalServer(
            name="fs",
            description="fs",
            tools=[
                InternalTool(
                    name="write_file",
                    description="Write file",
                    input_schema={},
                    handler=lambda a: asyncio.sleep(0, result={"ok": True}),
                )
            ],
        )
    )
    engine = PermissionEngine(auto_approve_level=1)
    executor = ToolExecutor(reg, engine)
    outcome = asyncio.run(
        executor.execute(ToolCall(tool="fs.write_file", arguments={"path": "x", "content": "y"}))
    )
    assert outcome.status == "needs_confirmation"
    assert outcome.confirmation is not None

    # Resolve as approved
    approved = asyncio.run(
        executor.resolve_confirmation(outcome.confirmation.id, approved=True)
    )
    assert approved.status == "ok"


def test_executor_denies_tool_marked_deny():
    reg = ToolRegistry(embeddings=FakeEmbeddings())
    reg.register_internal(_sample_server())
    engine = PermissionEngine(
        tool_overrides={"s.echo": ToolPermission(mode="deny")}
    )
    executor = ToolExecutor(reg, engine)
    outcome = asyncio.run(
        executor.execute(ToolCall(tool="s.echo", arguments={}))
    )
    assert outcome.status == "denied"


# ---- terminal classifier ------------------------------------------------


def test_dangerous_commands_are_flagged():
    assert classify_command("rm -rf /") == "critical"
    assert classify_command("sudo apt update") == "critical"
    assert classify_command("shutdown now") == "critical"
    assert classify_command("ls -la") == "normal"
    assert classify_command("echo hi") == "normal"
