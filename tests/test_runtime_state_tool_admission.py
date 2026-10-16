from src.agents.task.runtime_state import RuntimeStateManager


def test_stale_tool_call_is_rejected_before_execution():
    state = RuntimeStateManager()
    state.begin_user_turn("turn-new", "open browser")

    admitted, payload = state.admit_tool_call(
        turn_id="turn-old",
        tool_call_id="call-1",
        tool_name="browser",
        arguments={"action": "open", "url": "about:blank"},
    )

    assert admitted is False
    assert payload["status"] == "context_invalid"
    assert payload["error_type"] == "stale_action"
    assert payload["command_accepted"] is False
    assert payload["effect_verified"] is False


def test_cancelled_task_rejects_late_tool_call():
    state = RuntimeStateManager()
    state.begin_user_turn("turn-1", "type hello")
    state.cancel_active_task("user_closed_target")

    admitted, payload = state.admit_tool_call(
        turn_id="turn-1",
        tool_call_id="call-2",
        tool_name="desktop",
        arguments={"action": "type", "text": "hello"},
    )

    assert admitted is False
    assert payload["status"] == "cancelled"
    assert payload["error_type"] == "task_cancelled"


def test_admitted_tool_call_records_owner_and_pending_action():
    state = RuntimeStateManager()
    state.begin_user_turn("turn-1", "open browser", session_id="desktop:hud")

    admitted, payload = state.admit_tool_call(
        turn_id="turn-1",
        tool_call_id="call-3",
        tool_name="browser",
        arguments={"action": "open", "url": "about:blank"},
    )

    assert admitted is True
    assert payload == {}
    assert state.state.tool_call_id == "call-3"
    assert state.state.action_owner == "desktop:hud"
    assert state.state.pending_action == {
        "tool": "browser",
        "arguments": {"action": "open", "url": "about:blank"},
    }
