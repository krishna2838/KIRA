"""MCP client wrapping the official `mcp` Python SDK.

Supports two transports:
  - stdio: spawn an MCP server subprocess and speak over its stdin/stdout
  - sse:   connect to a remote MCP server over Server-Sent Events

Built-in servers (packages/tools/kira/tools/servers/*) DO NOT use this — they
run in-process. This client is for external MCP servers only.

The SDK's exact API surface has shifted between minor versions; we shell all
of the version-fragile calls through small helpers so a version bump only
needs edits here.
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any

from kira.logger import get_logger

from kira.tools.types import ToolSpec, ToolTransport


logger = get_logger("tools.mcp_client")


class MCPClient:
    """A single connection to one MCP server."""

    def __init__(
        self,
        server_name: str,
        transport: ToolTransport,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
    ):
        if transport == ToolTransport.STDIO and not command:
            raise ValueError("stdio transport requires `command`")
        if transport == ToolTransport.SSE and not url:
            raise ValueError("sse transport requires `url`")
        self.server_name = server_name
        self.transport = transport
        self.command = command
        self.args = args or []
        self.env = env
        self.url = url

        self._stack: AsyncExitStack | None = None
        self._session: Any = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._session is not None:
            return

        # Import lazily so the tools package still imports if `mcp` is missing.
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except Exception as e:
            raise RuntimeError(
                "The `mcp` package is required for external MCP servers "
                f"(pip install mcp): {e}"
            ) from e

        self._stack = AsyncExitStack()

        if self.transport == ToolTransport.STDIO:
            params = StdioServerParameters(
                command=self.command,  # type: ignore[arg-type]
                args=self.args,
                env=self.env,
            )
            read, write = await self._stack.enter_async_context(stdio_client(params))
        else:
            from mcp.client.sse import sse_client  # type: ignore

            read, write = await self._stack.enter_async_context(sse_client(self.url))  # type: ignore[arg-type]

        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session
        logger.info(f"MCP connected: {self.server_name} ({self.transport.value})")

    async def close(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception as e:
                logger.warning(f"MCP close error for {self.server_name}: {e}")
        self._stack = None
        self._session = None

    async def list_tools(self) -> list[ToolSpec]:
        async with self._lock:
            if self._session is None:
                await self.connect()
            resp = await self._session.list_tools()  # type: ignore[union-attr]

        raw_tools = getattr(resp, "tools", resp) or []
        specs: list[ToolSpec] = []
        for t in raw_tools:
            name = getattr(t, "name", None) or t.get("name")  # type: ignore[union-attr]
            desc = (
                getattr(t, "description", None)
                or (t.get("description") if isinstance(t, dict) else None)
                or ""
            )
            schema = (
                getattr(t, "inputSchema", None)
                or getattr(t, "input_schema", None)
                or (t.get("inputSchema") if isinstance(t, dict) else None)
                or {}
            )
            if not name:
                continue
            specs.append(
                ToolSpec(
                    server=self.server_name,
                    name=name,
                    qualified_name=f"{self.server_name}.{name}",
                    description=desc,
                    input_schema=schema,
                )
            )
        return specs

    async def call_tool(self, name: str, arguments: dict) -> Any:
        async with self._lock:
            if self._session is None:
                await self.connect()
            resp = await self._session.call_tool(name, arguments)  # type: ignore[union-attr]

        content = getattr(resp, "content", resp)
        # Normalize to something JSON-serializable
        if isinstance(content, list):
            parts: list[Any] = []
            for c in content:
                text = getattr(c, "text", None)
                if text is not None:
                    parts.append(text)
                else:
                    parts.append(getattr(c, "model_dump", lambda: c)())
            if len(parts) == 1:
                return parts[0]
            return parts
        return content
