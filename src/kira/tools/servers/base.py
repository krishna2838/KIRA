"""Base contract for in-process MCP-style servers.

Each built-in server module exports a module-level `SERVER` object that
conforms to InternalServer. The registry consumes these directly (no
subprocess / stdio) so latency stays flat and memory doesn't balloon.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


ToolHandler = Callable[[dict], Awaitable[Any]]


@dataclass
class InternalTool:
    name: str
    description: str
    input_schema: dict
    handler: ToolHandler


@dataclass
class InternalServer:
    name: str
    description: str
    tools: list[InternalTool] = field(default_factory=list)

    def get_tool(self, name: str) -> InternalTool | None:
        return next((t for t in self.tools if t.name == name), None)
