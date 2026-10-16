"""Tests for screen_tool — OpenClaw parity.

Validates:
- Invalid actions raise ValueError.
- Invalid dock raises ValueError.
- Session key resolution fallback to agent session key.
- Missing gateway_call raises RuntimeError.
- Correct RPC payload shape is dispatched to gateway_call.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock

from src.agents.sessions.tools.screen_tool import (
    create_screen_tool,
    create_screen_tool_definition,
    _command_for_action,
    _resolve_session_key,
    _read_dock,
    ACTIONS,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tool(gateway_call=None, session_key="test-session"):
    return create_screen_tool(
        {"gateway_call": gateway_call or AsyncMock(return_value={"ok": True}),
         "session_key": session_key}
    )


async def _run(tool, action, extra=None):
    params = {"action": action, **(extra or {})}
    return await tool["execute"]("tc-1", params, None, None)


# ---------------------------------------------------------------------------
# Schema (sync — no asyncio needed)
# ---------------------------------------------------------------------------

class TestDefinition:
    def test_name(self):
        d = create_screen_tool_definition()
        assert d["name"] == "screen"

    def test_all_actions_in_schema(self):
        d = create_screen_tool_definition()
        enum = d["inputSchema"]["properties"]["action"]["enum"]
        for a in ACTIONS:
            assert a in enum

    def test_dock_enum(self):
        d = create_screen_tool_definition()
        assert d["inputSchema"]["properties"]["dock"]["enum"] == ["bottom", "right"]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestValidation:
    async def test_no_gateway_call_raises(self):
        tool = create_screen_tool({"session_key": "s"})
        with pytest.raises(RuntimeError, match="gateway_call"):
            await _run(tool, "focus")

    async def test_invalid_action_raises(self):
        tool = make_tool()
        with pytest.raises(ValueError, match="Invalid or missing action"):
            await _run(tool, "fly_away")

    async def test_missing_action_raises(self):
        tool = make_tool()
        with pytest.raises(ValueError):
            await tool["execute"]("tc-1", {}, None, None)

    def test_invalid_dock_raises(self):
        with pytest.raises(ValueError, match="dock must be"):
            _read_dock({"dock": "left"})

    def test_valid_dock_bottom(self):
        assert _read_dock({"dock": "bottom"}) == "bottom"

    def test_valid_dock_right(self):
        assert _read_dock({"dock": "right"}) == "right"

    def test_dock_none_ok(self):
        assert _read_dock({}) is None


# ---------------------------------------------------------------------------
# Session key resolution (sync)
# ---------------------------------------------------------------------------

class TestSessionKey:
    def test_uses_param_session_key(self):
        result = _resolve_session_key({"sessionKey": "from-param"}, "from-agent")
        assert result == "from-param"

    def test_falls_back_to_agent_session_key(self):
        result = _resolve_session_key({}, "from-agent")
        assert result == "from-agent"

    def test_missing_raises(self):
        with pytest.raises(ValueError, match="sessionKey required"):
            _resolve_session_key({}, "")


# ---------------------------------------------------------------------------
# Command payload shapes (sync)
# ---------------------------------------------------------------------------

class TestCommandForAction:
    SK = "sess-1"

    def test_split_right(self):
        cmd = _command_for_action("split_right", {"sessionKey": self.SK}, "")
        assert cmd == {"kind": "split", "direction": "right", "sessionKey": self.SK}

    def test_split_down(self):
        cmd = _command_for_action("split_down", {"sessionKey": self.SK}, "")
        assert cmd == {"kind": "split", "direction": "down", "sessionKey": self.SK}

    def test_close_pane(self):
        cmd = _command_for_action("close_pane", {"sessionKey": self.SK}, "")
        assert cmd["kind"] == "close-pane"

    def test_focus(self):
        cmd = _command_for_action("focus", {"sessionKey": self.SK}, "")
        assert cmd["kind"] == "focus"

    def test_sidebar_show(self):
        cmd = _command_for_action("sidebar_show", {}, "")
        assert cmd == {"kind": "sidebar", "visible": True}

    def test_sidebar_hide(self):
        cmd = _command_for_action("sidebar_hide", {}, "")
        assert cmd == {"kind": "sidebar", "visible": False}

    def test_terminal_show_with_dock(self):
        cmd = _command_for_action("terminal_show", {"sessionKey": self.SK, "dock": "bottom"}, "")
        assert cmd["kind"] == "panel"
        assert cmd["panel"] == "terminal"
        assert cmd["open"] is True
        assert cmd["dock"] == "bottom"

    def test_terminal_hide_no_dock(self):
        cmd = _command_for_action("terminal_hide", {"sessionKey": self.SK}, "")
        assert cmd["open"] is False
        assert "dock" not in cmd

    def test_browser_show(self):
        cmd = _command_for_action("browser_show", {"sessionKey": self.SK, "dock": "right"}, "")
        assert cmd["panel"] == "browser"
        assert cmd["dock"] == "right"

    def test_browser_hide(self):
        cmd = _command_for_action("browser_hide", {"sessionKey": self.SK}, "")
        assert cmd["panel"] == "browser"
        assert cmd["open"] is False

    def test_unknown_action_raises(self):
        with pytest.raises(ValueError, match="Unknown action"):
            _command_for_action("warp_drive", {}, "")


# ---------------------------------------------------------------------------
# End-to-end gateway dispatch
# ---------------------------------------------------------------------------

class TestGatewayDispatch:
    async def test_dispatches_ui_command(self):
        gw = AsyncMock(return_value={"ok": True})
        tool = create_screen_tool({"gateway_call": gw, "session_key": "s"})

        await tool["execute"]("tc-2", {"action": "sidebar_show"}, None, None)

        gw.assert_awaited_once()
        call_args = gw.await_args
        assert call_args.args[0] == "ui.command"
        payload = call_args.args[1]
        assert "command" in payload
        assert payload["command"]["kind"] == "sidebar"
        assert payload["command"]["visible"] is True

    async def test_returns_gateway_response(self):
        gw = AsyncMock(return_value={"status": "ok"})
        tool = create_screen_tool({"gateway_call": gw, "session_key": "s"})

        result = await tool["execute"]("tc-3", {"action": "sidebar_hide"}, None, None)

        text = result["content"][0]["text"]
        data = json.loads(text)
        assert data["status"] == "ok"
