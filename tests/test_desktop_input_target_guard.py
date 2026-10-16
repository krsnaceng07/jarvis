"""Input must stop when the task's target window loses focus."""

from unittest.mock import MagicMock, call, patch

import pytest

from src.desktop_automation.applications.generic import GenericDesktopAdapter
from src.desktop_automation.interaction.keyboard_controller import KeyboardController
from src.desktop_automation.state.active_desktop_context import ActiveDesktopContext


def test_typing_stops_between_characters_on_focus_loss():
    with (
        patch("src.desktop_automation.interaction.keyboard_controller.pyautogui") as keyboard,
        patch(
            "src.desktop_automation.interaction.keyboard_controller.WindowManager.get_foreground_window",
            side_effect=[42, 42, 99],
        ),
    ):
        assert not KeyboardController.type_text("abcd", expected_hwnd=42)
        assert keyboard.write.call_args_list == [
            call("a", interval=0.01, _pause=False),
            call("b", interval=0.01, _pause=False),
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["type", "hotkey", "press_key", "click", "drag", "scroll"])
async def test_generic_input_rejects_replacement_window(action):
    adapter = GenericDesktopAdapter()
    adapter.window_manager = MagicMock()
    adapter.window_manager.get_foreground_window.return_value = 99
    with patch("src.desktop_automation.interaction.keyboard_controller.pyautogui") as keyboard:
        result = await adapter.execute_action(
            action, {"text": "private"}, ActiveDesktopContext(active_hwnd=42)
        )
        assert not result.ok
        assert not result.verified
        assert "Re-observe" in result.error
        keyboard.write.assert_not_called()


@pytest.mark.asyncio
async def test_partial_typing_is_not_reported_complete():
    adapter = GenericDesktopAdapter()
    adapter.window_manager = MagicMock()
    adapter.window_manager.get_foreground_window.return_value = 42
    with patch.object(KeyboardController, "type_text", return_value=False):
        result = await adapter.execute_action(
            "type", {"text": "abcd"}, ActiveDesktopContext(active_hwnd=42)
        )
    assert not result.ok
    assert not result.verified
    assert "some text may already" in result.error
