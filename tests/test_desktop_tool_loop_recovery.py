"""Tests for desktop tool loop recovery, task fulfillment directives, and execution recording parity."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from apps.desktop.src.jarvis_desktop.tool_pipeline import execute_desktop_action
from src.agents.decision.tool_selection import ToolSelector, ToolLoopInterventionError


@pytest.mark.asyncio
async def test_whatsapp_send_fulfillment_directive():
    """Verify that execute_desktop_action returns an explicit terminal fulfillment directive."""
    mock_res = MagicMock(ok=True, output_text="Message sent to krishna kushwaha", error=None)

    with patch("src.desktop_automation.DesktopRuntime.get_instance") as mock_get_rt:
        mock_rt = MagicMock()
        mock_rt.execute_action = AsyncMock(return_value=mock_res)
        mock_get_rt.return_value = mock_rt

        result = await execute_desktop_action({
            "action": "whatsapp_send",
            "recipient": "krishna kushwaha",
            "message": "hello",
        })

        assert "SUCCESS: WhatsApp message sent to 'krishna kushwaha'" in result
        assert "TASK FULFILLED" in result
        assert "DO NOT invoke 'desktop' or 'open_path' again" in result
        assert "Confirm to the user via voice" in result


def test_tool_selector_streak_pruning_and_reset():
    """Verify ToolSelector prunes streak on intervention and reset() clears state."""
    selector = ToolSelector(max_identical_calls=2)

    args = {"action": "whatsapp_send", "recipient": "krishna"}
    # Call 1: ok
    selector.check_loop_intervention("desktop", args)
    # Call 2: ok
    selector.check_loop_intervention("desktop", args)

    # Call 3: raises ToolLoopInterventionError
    with pytest.raises(ToolLoopInterventionError) as exc_info:
        selector.check_loop_intervention("desktop", args)

    assert "Tool loop detected" in str(exc_info.value)
    # Streak should be pruned so replanning doesn't inherit permanent poison
    assert len(selector._call_history) == 0

    # Reset clears any remaining history
    selector.check_loop_intervention("desktop", {"action": "other"})
    assert len(selector._call_history) == 1
    selector.reset()
    assert len(selector._call_history) == 0


@pytest.mark.asyncio
async def test_desktop_tool_loop_intervention_response_handling():
    """Verify that JarvisLive._execute_tool halts without setting error=True on loop intervention."""
    from apps.desktop.src.jarvis_desktop.app import JarvisLive

    mock_ui = MagicMock()
    mock_ui.muted = False
    jarvis = JarvisLive(mock_ui)

    # Force decision engine preflight to raise ToolLoopInterventionError
    fc = MagicMock()
    fc.id = "call-123"
    fc.name = "desktop"
    fc.args = {"action": "whatsapp_send", "recipient": "krishna"}

    with patch.object(
        jarvis._decision_engine,
        "preflight_tool_execution",
        side_effect=ToolLoopInterventionError("Repetitive call detected"),
    ):
        resp = await jarvis._execute_tool(fc)

        assert resp.id == "call-123"
        assert resp.name == "desktop"
        assert isinstance(resp.response, dict)
        # MUST NOT have error: True so Gemini Live does not enter an automatic retry loop
        assert "error" not in resp.response or resp.response["error"] is False
        assert resp.response.get("silent") is False
        assert "LOOP INTERVENTION ACTIVE: Stop calling tools immediately" in resp.response["result"]


@pytest.mark.asyncio
async def test_desktop_tool_records_outcome_and_task_execution():
    """Verify that desktop tool calls register with tool loop guard and task manager."""
    from apps.desktop.src.jarvis_desktop.app import JarvisLive

    mock_ui = MagicMock()
    mock_ui.muted = False
    jarvis = JarvisLive(mock_ui)

    fc = MagicMock()
    fc.id = "call-456"
    fc.name = "desktop"
    fc.args = {"action": "whatsapp_send", "recipient": "krishna", "message": "hi"}

    with patch(
        "apps.desktop.src.jarvis_desktop.tool_pipeline.execute_desktop_action",
        new_callable=AsyncMock,
        return_value="SUCCESS: WhatsApp message sent to 'krishna'. [TASK FULFILLED]",
    ), patch.object(jarvis._tool_loop_guard, "record_outcome") as mock_record_loop, \
       patch.object(jarvis._task_manager, "record_execution") as mock_record_task:

        mock_rec = MagicMock()
        mock_rec.to_dict.return_value = {"id": "rec-1"}
        mock_record_task.return_value = mock_rec

        resp = await jarvis._execute_tool(fc)

        assert resp.id == "call-456"
        assert "SUCCESS: WhatsApp message sent to 'krishna'" in resp.response["result"]

        # Loop guard outcome recorded
        mock_record_loop.assert_called_once()
        name_arg = mock_record_loop.call_args[0][0]
        assert name_arg == "desktop"

        # Task manager record_execution recorded
        mock_record_task.assert_called_once()
        task_kwargs = mock_record_task.call_args[1]
        assert task_kwargs["tool_name"] == "desktop"
        assert task_kwargs["status"] == "success"
        assert task_kwargs["verification"].verified is True


@pytest.mark.asyncio
async def test_desktop_action_generic_with_recipient_and_message_auto_repaired_to_whatsapp_send():
    """Verify that action='generic' with recipient and message auto-repairs to whatsapp_send."""
    mock_res = MagicMock(ok=True, output_text="Message sent to krishna kushwaha", error=None)

    with patch("src.desktop_automation.DesktopRuntime.get_instance") as mock_get_rt:
        mock_rt = MagicMock()
        mock_rt.execute_action = AsyncMock(return_value=mock_res)
        mock_get_rt.return_value = mock_rt

        # Pass action='generic', which Gemini passed in the user log
        result = await execute_desktop_action({
            "action": "generic",
            "recipient": "krishna kushwaha",
            "message": "hello",
            "agentId": "main",
        })

        assert "SUCCESS: WhatsApp message sent to 'krishna kushwaha'" in result
        mock_rt.execute_action.assert_called_once()
        call_app, call_act, call_args = mock_rt.execute_action.call_args[0]
        assert call_app == "whatsapp"
        assert call_act == "send"


def test_speech_guard_repairs_desktop_generic_to_whatsapp_send():
    """Verify SpeechGroundingGuard repairs desktop action='generic' to 'whatsapp_send'."""
    from src.talk.speech_guard import SpeechGroundingGuard

    guard = SpeechGroundingGuard()
    res = guard.validate_voice_tool_call(
        tool_name="desktop",
        tool_args={"action": "generic", "recipient": "krishna kushwaha", "message": "hello"},
        user_speech="send hello to krishna kushwaha on whatsapp",
    )

    assert res.is_allowed is True
    assert res.repaired_tool_name == "desktop"
    assert res.repaired_args["action"] == "whatsapp_send"
    assert res.repaired_args["recipient"] == "krishna kushwaha"

