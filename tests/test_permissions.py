from kira.permissions import PermissionEngine
from kira.types import RiskLevel


def test_read_tools_are_read_level():
    engine = PermissionEngine()
    assert engine.classify_risk("search") == RiskLevel.READ
    assert engine.classify_risk("read_file") == RiskLevel.READ


def test_execute_tools():
    engine = PermissionEngine()
    assert engine.classify_risk("run_script") == RiskLevel.EXECUTE


def test_external_tools():
    engine = PermissionEngine()
    assert engine.classify_risk("send_email") == RiskLevel.EXTERNAL


def test_critical_tools():
    engine = PermissionEngine()
    assert engine.classify_risk("payment") == RiskLevel.CRITICAL


def test_auto_approve_boundary():
    engine = PermissionEngine(auto_approve_level=1)
    assert engine.needs_confirmation(RiskLevel.READ) is False
    assert engine.needs_confirmation(RiskLevel.PERSONAL) is False
    assert engine.needs_confirmation(RiskLevel.EXECUTE) is True
    assert engine.needs_confirmation(RiskLevel.CRITICAL) is True


def test_unknown_tool_defaults_to_execute():
    engine = PermissionEngine()
    assert engine.classify_risk("whatever_new_tool") == RiskLevel.EXECUTE
