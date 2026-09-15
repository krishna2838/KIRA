"""Permission classification, per-tool overrides, and rate limiting."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from kira.types import RiskLevel


READ_TOOLS = {
    "search", "read_file", "list_files", "search_files",
    "web_search", "news_search", "image_search", "video_search",
    "wikipedia", "read_url", "research", "deep_research",
    "get_weather",
    # browser (read-only)
    "open_url", "get_page_content", "screenshot_page", "extract_data",
    # computer — introspection
    "list_running_apps", "window_titles", "get_battery", "get_disk_space",
    "get_wifi_network", "get_volume", "get_brightness", "system_status",
    "a11y_status", "ui_tree", "take_screenshot", "analyze_screenshot",
    "get_clipboard",
    # google — read
    "auth_status",
    "list_emails", "read_email", "get_unread_count", "summarize_inbox",
    "get_today_events", "get_week_events", "get_upcoming", "find_free_time",
    "list_tasks",
    "drive_search", "drive_read", "drive_recent",
    # notifications — read
    "list_recent", "unread_count", "search", "latest_from", "summarize_unread",
    "telegram_read", "discord_read",
    # life — read
    "get_today_brief", "get_focus_suggestion", "get_weekly_overview",
    "list_deadlines", "morning_brief",
    # code — read
    "git_status", "git_diff", "git_log", "git_branch_list",
    "github_status", "list_repos", "get_repo_issues", "get_pull_requests",
    "get_actions_status", "read_file_from_github",
    "read_project_structure", "read_source_file", "search_code",
    "analyze_error", "explain_code",
    "parse_build_errors",
    "investigate_and_fix",
    # documents — read/RAG
    "parse_pdf", "parse_docx", "parse_image", "parse_markdown",
    "parse_code", "parse_any",
    "search_documents", "search_in_file", "summarize_document",
    "ask_document", "list_indexed",
}
PERSONAL_TOOLS = {
    "read_calendar", "read_notes", "read_contacts",
    # low-friction side effects
    "open_app", "switch_to_app", "open_file", "reveal_in_finder",
    "copy_file",
    "set_volume", "toggle_dark_mode", "set_clipboard",
    # tasks
    "create_task", "complete_task",
    # life
    "track_deadline", "complete_deadline",
    # notifications
    "mark_read", "ingest",
    # google auth
    "sign_out",
    # code auth
    "github_set_token", "github_sign_out",
    # documents — writes are personal (embed to your local DB)
    "index_file", "index_directory", "reindex",
}
EXECUTE_TOOLS = {
    "run_script", "run_command", "modify_file", "write_file",
    "create_file", "delete_file",
    # browser (mutating)
    "click_element", "fill_form",
    # computer — mutating
    "close_app", "move_file",
    # google — draft is L2
    "draft_email", "create_event",
    # code — mutations
    "git_checkout", "git_commit",
    "create_issue",
    "edit_source_file", "create_source_file",
    "run_build", "run_tests",
    "apply_proposal",
}
EXTERNAL_TOOLS = {
    "send_email", "send_message", "post_content",
    "telegram_send",
    # code — publishing
    "git_push",
}
CRITICAL_TOOLS = {"payment", "account_change", "security_change"}


@dataclass
class ToolPermission:
    """User-configurable per-tool override.

    - allow: force-approve without confirmation, ignoring risk level
    - deny:  refuse the call outright
    - default: normal risk-based flow
    - rate_limit_per_min: cap calls per rolling 60s window (None = unlimited)
    - risk_override: force a specific risk level for classification
    """
    mode: str = "default"  # "default" | "allow" | "deny"
    rate_limit_per_min: int | None = None
    risk_override: RiskLevel | None = None


@dataclass
class _RateWindow:
    hits: deque[float] = field(default_factory=deque)


class PermissionEngine:
    def __init__(
        self,
        auto_approve_level: int = 1,
        tool_overrides: dict[str, ToolPermission] | None = None,
    ):
        self.auto_approve_level = auto_approve_level
        self.tool_overrides: dict[str, ToolPermission] = tool_overrides or {}
        self._rate: dict[str, _RateWindow] = {}

    # -- classification ---------------------------------------------------

    def _base_risk(self, tool_name: str) -> RiskLevel:
        short = tool_name.split(".")[-1]  # strip "server." prefix
        if short in READ_TOOLS or tool_name in READ_TOOLS:
            return RiskLevel.READ
        if short in PERSONAL_TOOLS or tool_name in PERSONAL_TOOLS:
            return RiskLevel.PERSONAL
        if short in EXECUTE_TOOLS or tool_name in EXECUTE_TOOLS:
            return RiskLevel.EXECUTE
        if short in EXTERNAL_TOOLS or tool_name in EXTERNAL_TOOLS:
            return RiskLevel.EXTERNAL
        if short in CRITICAL_TOOLS or tool_name in CRITICAL_TOOLS:
            return RiskLevel.CRITICAL
        return RiskLevel.EXECUTE

    def classify_risk(self, tool_name: str, action: str = "") -> RiskLevel:
        override = self.tool_overrides.get(tool_name)
        if override and override.risk_override is not None:
            return override.risk_override
        return self._base_risk(tool_name)

    def needs_confirmation(self, risk_level: RiskLevel) -> bool:
        return risk_level.value > self.auto_approve_level

    # -- per-tool overrides ---------------------------------------------

    def is_denied(self, tool_name: str) -> bool:
        override = self.tool_overrides.get(tool_name)
        return bool(override and override.mode == "deny")

    def is_force_allowed(self, tool_name: str) -> bool:
        override = self.tool_overrides.get(tool_name)
        return bool(override and override.mode == "allow")

    def set_override(self, tool_name: str, override: ToolPermission) -> None:
        self.tool_overrides[tool_name] = override

    # -- rate limiting --------------------------------------------------

    def _limit_for(self, tool_name: str) -> int | None:
        override = self.tool_overrides.get(tool_name)
        return override.rate_limit_per_min if override else None

    def check_and_record_rate(self, tool_name: str, now: float | None = None) -> bool:
        """Return True if allowed. If allowed, records the hit."""
        limit = self._limit_for(tool_name)
        if limit is None:
            return True
        now = now if now is not None else time.time()
        window = self._rate.setdefault(tool_name, _RateWindow())
        cutoff = now - 60.0
        while window.hits and window.hits[0] < cutoff:
            window.hits.popleft()
        if len(window.hits) >= limit:
            return False
        window.hits.append(now)
        return True

    # -- unified decision -----------------------------------------------

    def decide(self, tool_name: str) -> tuple[str, RiskLevel]:
        """Return (decision, risk). decision ∈ {"deny", "allow", "confirm"}."""
        risk = self.classify_risk(tool_name)
        if self.is_denied(tool_name):
            return "deny", risk
        if self.is_force_allowed(tool_name):
            return "allow", risk
        if self.needs_confirmation(risk):
            return "confirm", risk
        return "allow", risk


def load_tool_overrides(raw: dict | None) -> dict[str, ToolPermission]:
    """Parse the YAML `permissions.tool_overrides` map into ToolPermission."""
    out: dict[str, ToolPermission] = {}
    if not raw:
        return out
    for tool_name, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        risk_override_raw = spec.get("risk_override")
        risk_override: RiskLevel | None = None
        if isinstance(risk_override_raw, int):
            try:
                risk_override = RiskLevel(risk_override_raw)
            except ValueError:
                pass
        out[tool_name] = ToolPermission(
            mode=spec.get("mode", "default"),
            rate_limit_per_min=spec.get("rate_limit_per_min"),
            risk_override=risk_override,
        )
    return out
