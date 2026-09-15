"""Tests for computer-control primitives + permissions of new tools."""
import asyncio

from kira.permissions import PermissionEngine, ToolPermission
from kira.tools.computer.util import expand_path
from kira.types import RiskLevel


def test_expand_path_expands_tilde():
    p = expand_path("~/Desktop")
    assert not p.startswith("~")


def test_permission_maps_read_tools_to_read():
    e = PermissionEngine()
    for name in (
        "computer.get_battery", "computer.get_disk_space",
        "computer.get_wifi_network", "computer.ui_tree",
        "computer.take_screenshot", "computer.get_clipboard",
        "computer.system_status",
        "browser.open_url", "browser.get_page_content", "browser.screenshot_page",
    ):
        assert e.classify_risk(name) == RiskLevel.READ, f"{name} should be READ"


def test_permission_maps_personal_tools_to_personal():
    e = PermissionEngine()
    for name in (
        "computer.open_app", "computer.switch_to_app",
        "computer.set_volume", "computer.toggle_dark_mode",
        "computer.set_clipboard", "computer.open_file",
        "computer.reveal_in_finder", "computer.copy_file",
    ):
        assert e.classify_risk(name) == RiskLevel.PERSONAL, f"{name} should be PERSONAL"


def test_permission_maps_execute_tools_to_execute():
    e = PermissionEngine()
    for name in (
        "computer.close_app", "computer.move_file",
        "browser.click_element", "browser.fill_form",
    ):
        # Note the config file also overrides these to EXECUTE (2) — base class
        # already places them there.
        assert e.classify_risk(name) == RiskLevel.EXECUTE, f"{name} should be EXECUTE"


def test_override_bumps_delete_to_critical():
    e = PermissionEngine(
        tool_overrides={
            "computer.delete_file": ToolPermission(risk_override=RiskLevel.CRITICAL),
        }
    )
    assert e.classify_risk("computer.delete_file") == RiskLevel.CRITICAL


def test_apps_list_running_apps_gracefully_returns_when_unavailable():
    # On non-macOS runners osascript is unavailable — the function must not
    # raise; it should return an empty list.
    from kira.tools.computer import apps
    result = asyncio.run(apps.list_running_apps())
    assert isinstance(result, list)


def test_disk_space_returns_numbers():
    from kira.tools.computer import system
    result = asyncio.run(system.get_disk_space("/"))
    assert isinstance(result["total_gb"], (int, float))
    assert result["free_gb"] <= result["total_gb"]
