"""Unit tests for EnableGate (COMP-BR-03) — mirrors TC-009, TC-010, TC-012
in docs/testing/QA-testcases.csv.

TC-011 (disable mid-EXECUTING does not cancel the in-flight trajectory) is
NOT unit-testable here: EnableGate only gates whether BridgeNode sends a NEW
goal (see bridge_node.py `_on_detections`), it has no notion of "currently
executing". That guarantee is structural (BridgeNode never calls any cancel
API), not something this class enforces — TC-011 needs an integration test
on the simulator once fanuc_moveit_config mock hardware is exercised
end-to-end.
"""

from bridge_node.enable_gate import EnableGate


def test_tc012_default_enabled_on_start():
    gate = EnableGate()
    assert gate.is_enabled() is True


def test_can_start_disabled():
    gate = EnableGate(enabled_on_start=False)
    assert gate.is_enabled() is False


def test_tc009_disable_blocks():
    gate = EnableGate(enabled_on_start=True)
    gate.set_enabled(False)
    assert gate.is_enabled() is False


def test_tc010_enable_resumes():
    gate = EnableGate(enabled_on_start=False)
    gate.set_enabled(True)
    assert gate.is_enabled() is True
