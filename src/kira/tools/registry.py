"""Tool registry.

Tracks every MCP server (internal + external) and its tools, plus a
pre-computed embedding per tool. The embedding cache is written to Redis so
that a restart doesn't force us to re-embed every tool description; falls
back to an in-memory dict if Redis is unavailable.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from kira.core.logger import get_logger

from kira.tools.mcp_client import MCPClient
from kira.tools.servers.base import InternalServer
from kira.tools.types import ToolSpec, ToolTransport


logger = get_logger("tools.registry")

_EMBED_CACHE_PREFIX = "kira:tool_embed:"


class ToolRegistry:
    def __init__(self, embeddings, redis_client=None):
        self.embeddings = embeddings
        self.redis = redis_client
        self._internal: dict[str, InternalServer] = {}
        self._external: dict[str, MCPClient] = {}
        # qualified_name -> ToolSpec
        self._tools: dict[str, ToolSpec] = {}
        # qualified_name -> list[float]
        self._embeddings: dict[str, list[float]] = {}
        # server_name -> transport label ("internal" / "stdio" / "sse")
        self._server_transport: dict[str, str] = {}
        self._server_status: dict[str, str] = {}
        self._lock = asyncio.Lock()

    # -- registration ---------------------------------------------------

    def register_internal(self, server: InternalServer) -> None:
        self._internal[server.name] = server
        self._server_transport[server.name] = ToolTransport.INTERNAL.value
        self._server_status[server.name] = "ready"
        for t in server.tools:
            spec = ToolSpec(
                server=server.name,
                name=t.name,
                qualified_name=f"{server.name}.{t.name}",
                description=t.description,
                input_schema=t.input_schema,
            )
            self._tools[spec.qualified_name] = spec

    async def register_external(self, client: MCPClient) -> None:
        self._external[client.server_name] = client
        self._server_transport[client.server_name] = client.transport.value
        try:
            await client.connect()
            self._server_status[client.server_name] = "ready"
            specs = await client.list_tools()
            for s in specs:
                self._tools[s.qualified_name] = s
        except Exception as e:
            self._server_status[client.server_name] = f"error: {e}"
            logger.warning(f"External MCP {client.server_name} failed: {e}")

    # -- lookup ---------------------------------------------------------

    def get(self, qualified_name: str) -> ToolSpec | None:
        return self._tools.get(qualified_name)

    def all_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def servers(self) -> list[dict]:
        out: list[dict] = []
        for name in {**self._server_transport}.keys():
            tool_count = sum(1 for s in self._tools.values() if s.server == name)
            out.append(
                {
                    "name": name,
                    "transport": self._server_transport.get(name, "unknown"),
                    "status": self._server_status.get(name, "unknown"),
                    "tool_count": tool_count,
                }
            )
        return out

    def embedding_for(self, qualified_name: str) -> list[float] | None:
        return self._embeddings.get(qualified_name)

    # -- embedding pass ------------------------------------------------

    async def build_embeddings(self) -> None:
        """Compute (or fetch cached) embeddings for every registered tool."""
        async with self._lock:
            for qname, spec in self._tools.items():
                if qname in self._embeddings:
                    continue
                cached = await self._get_cached_embedding(qname, spec.description)
                if cached is not None:
                    self._embeddings[qname] = cached
                    continue
                text = f"{spec.name}: {spec.description}"
                try:
                    vec = await self.embeddings.embed(text)
                except Exception as e:
                    logger.warning(f"embed failed for {qname}: {e}")
                    continue
                self._embeddings[qname] = vec
                await self._set_cached_embedding(qname, spec.description, vec)

    async def _get_cached_embedding(
        self, qname: str, description: str
    ) -> list[float] | None:
        if self.redis is None:
            return None
        try:
            raw = await self.redis.get(_EMBED_CACHE_PREFIX + qname)
        except Exception:
            return None
        if not raw:
            return None
        try:
            blob = json.loads(raw)
            if blob.get("desc") != description:
                return None
            return blob["vec"]
        except Exception:
            return None

    async def _set_cached_embedding(
        self, qname: str, description: str, vec: list[float]
    ) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.set(
                _EMBED_CACHE_PREFIX + qname,
                json.dumps({"desc": description, "vec": vec}),
            )
        except Exception as e:
            logger.debug(f"redis set failed for {qname}: {e}")

    # -- dispatch ------------------------------------------------------

    async def dispatch(self, qualified_name: str, arguments: dict) -> Any:
        spec = self._tools.get(qualified_name)
        if spec is None:
            raise KeyError(f"Unknown tool: {qualified_name}")

        # Internal path
        server = self._internal.get(spec.server)
        if server is not None:
            tool = server.get_tool(spec.name)
            if tool is None:
                raise KeyError(f"Internal server {spec.server} lost tool {spec.name}")
            return await tool.handler(arguments)

        # External path
        client = self._external.get(spec.server)
        if client is None:
            raise RuntimeError(f"No client for server {spec.server}")
        return await client.call_tool(spec.name, arguments)

    async def close(self) -> None:
        for client in self._external.values():
            try:
                await client.close()
            except Exception:
                pass
        # Give internal servers a chance to release long-lived resources
        # (Playwright browsers, etc.).
        for name in self._internal:
            try:
                import importlib
                module_path = {
                    "browser": "kira.tools.servers.browser_server",
                }.get(name)
                if not module_path:
                    continue
                module = importlib.import_module(module_path)
                shutdown = getattr(module, "shutdown", None)
                if shutdown is not None:
                    await shutdown()
            except Exception:
                pass
