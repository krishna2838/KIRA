"""Tool executor.

Every tool call funnels through here. Responsibilities:
  1. Deny outright if the tool has a `deny` override.
  2. Enforce per-tool rate limiting.
  3. Classify risk level via PermissionEngine.
  4. Auto-execute when the risk is within `auto_approve_level`; otherwise
     stash a pending confirmation and return a ConfirmationRequest.
  5. Record every attempt (approved, denied, rate-limited, error) to the
     `audit_log` table.
"""
from __future__ import annotations

import json
import time
from uuid import UUID, uuid4

from kira.logger import get_logger
from kira.permissions import PermissionEngine

from kira.tools.registry import ToolRegistry
from kira.tools.types import (
    ConfirmationRequest,
    ExecutionOutcome,
    ToolCall,
    ToolResult,
)


logger = get_logger("tools.executor")


class ToolExecutor:
    def __init__(
        self, registry: ToolRegistry, permissions: PermissionEngine, db=None
    ):
        self.registry = registry
        self.permissions = permissions
        self.db = db
        # Pending confirmations, keyed by their id.
        self._pending: dict[UUID, ConfirmationRequest] = {}

    # -- primary entry -------------------------------------------------

    async def execute(self, call: ToolCall) -> ExecutionOutcome:
        spec = self.registry.get(call.tool)
        if spec is None:
            await self._audit("tool_call", call.tool, 0, call.arguments, None,
                              approved=False, approved_by="auto",
                              error=f"unknown tool {call.tool}", latency_ms=0)
            return ExecutionOutcome(
                status="error", message=f"Unknown tool: {call.tool}"
            )

        decision, risk = self.permissions.decide(call.tool)

        if decision == "deny":
            await self._audit(
                "tool_call", call.tool, risk.value, call.arguments, None,
                approved=False, approved_by="policy",
                error="denied by policy", latency_ms=0,
            )
            return ExecutionOutcome(
                status="denied",
                message=f"Tool {call.tool} is denied by policy.",
            )

        if not self.permissions.check_and_record_rate(call.tool):
            await self._audit(
                "tool_call", call.tool, risk.value, call.arguments, None,
                approved=False, approved_by="rate_limit",
                error="rate limited", latency_ms=0,
            )
            return ExecutionOutcome(
                status="rate_limited",
                message=f"Rate limit exceeded for {call.tool}.",
            )

        if decision == "confirm":
            confirmation = ConfirmationRequest(
                tool=call.tool,
                arguments=call.arguments,
                risk_level=risk.value,
                description=(spec.description or call.tool),
            )
            self._pending[confirmation.id] = confirmation
            await self._audit(
                "tool_call_pending", call.tool, risk.value,
                call.arguments, None,
                approved=None, approved_by=None,
                error=None, latency_ms=0,
            )
            return ExecutionOutcome(
                status="needs_confirmation", confirmation=confirmation
            )

        # decision == "allow"
        return await self._run_and_audit(call, risk.value, approved_by="auto")

    async def resolve_confirmation(
        self, confirmation_id: UUID, approved: bool
    ) -> ExecutionOutcome:
        """User approved or denied a pending confirmation."""
        pending = self._pending.pop(confirmation_id, None)
        if pending is None:
            return ExecutionOutcome(
                status="error", message="Unknown or expired confirmation."
            )
        if not approved:
            await self._audit(
                "tool_call", pending.tool, pending.risk_level,
                pending.arguments, None,
                approved=False, approved_by="user",
                error="user denied", latency_ms=0,
            )
            return ExecutionOutcome(
                status="denied", message="User denied the action."
            )
        return await self._run_and_audit(
            ToolCall(tool=pending.tool, arguments=pending.arguments),
            pending.risk_level,
            approved_by="user",
        )

    def get_pending(self, confirmation_id: UUID) -> ConfirmationRequest | None:
        return self._pending.get(confirmation_id)

    def all_pending(self) -> list[ConfirmationRequest]:
        return list(self._pending.values())

    # -- run + audit ---------------------------------------------------

    async def _run_and_audit(
        self, call: ToolCall, risk_value: int, *, approved_by: str
    ) -> ExecutionOutcome:
        start = time.time()
        try:
            content = await self.registry.dispatch(call.tool, call.arguments)
            latency_ms = int((time.time() - start) * 1000)
            result = ToolResult(
                call_id=call.id,
                tool=call.tool,
                ok=True,
                content=content,
                latency_ms=latency_ms,
            )
            await self._audit(
                "tool_call", call.tool, risk_value,
                call.arguments, content,
                approved=True, approved_by=approved_by,
                error=None, latency_ms=latency_ms,
            )
            return ExecutionOutcome(status="ok", result=result)
        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            logger.warning(f"tool {call.tool} failed: {e}")
            await self._audit(
                "tool_call", call.tool, risk_value,
                call.arguments, None,
                approved=True, approved_by=approved_by,
                error=str(e), latency_ms=latency_ms,
            )
            return ExecutionOutcome(
                status="error",
                result=ToolResult(
                    call_id=call.id, tool=call.tool, ok=False,
                    error=str(e), latency_ms=latency_ms,
                ),
                message=str(e),
            )

    async def _audit(
        self,
        action: str,
        tool_name: str,
        risk_level: int,
        inp,
        out,
        *,
        approved: bool | None,
        approved_by: str | None,
        error: str | None,
        latency_ms: int,
    ) -> None:
        if self.db is None:
            return
        try:
            input_summary = _summarize(inp)
            output_summary = _summarize(out)
            await self.db.execute(
                """INSERT INTO audit_log
                   (action, tool_name, risk_level, input_summary, output_summary,
                    approved, approved_by, error, latency_ms)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                action, tool_name, risk_level,
                input_summary, output_summary,
                approved, approved_by, error, latency_ms,
            )
        except Exception as e:
            logger.debug(f"audit write failed: {e}")


def _summarize(v) -> str | None:
    if v is None:
        return None
    try:
        s = json.dumps(v, default=str)
    except Exception:
        s = str(v)
    if len(s) > 2000:
        s = s[:2000] + "…"
    return s
