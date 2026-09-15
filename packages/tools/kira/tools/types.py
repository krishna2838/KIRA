"""Shared types for the tools subsystem."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ToolTransport(str, Enum):
    INTERNAL = "internal"   # In-process Python provider
    STDIO = "stdio"         # MCP stdio subprocess
    SSE = "sse"             # MCP over SSE


class ToolSpec(BaseModel):
    """A tool available from some MCP server."""
    server: str
    name: str
    qualified_name: str  # "<server>.<name>"
    description: str
    input_schema: dict = Field(default_factory=dict)


class ToolCall(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tool: str  # qualified_name
    arguments: dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    call_id: UUID
    tool: str
    ok: bool
    content: Any = None
    error: str | None = None
    latency_ms: int = 0


class ConfirmationRequest(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tool: str
    arguments: dict = Field(default_factory=dict)
    risk_level: int
    description: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExecutionOutcome(BaseModel):
    """Wraps either a completed ToolResult or a pending ConfirmationRequest."""
    status: Literal["ok", "needs_confirmation", "denied", "rate_limited", "error"]
    result: Optional[ToolResult] = None
    confirmation: Optional[ConfirmationRequest] = None
    message: str | None = None
