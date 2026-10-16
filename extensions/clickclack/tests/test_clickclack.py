"""Unit tests for ClickClack extension."""

from __future__ import annotations

import pytest

from extensions.clickclack.src.terminal import format_terminal_progress, parse_terminal_command
from extensions.clickclack.plugin import clickclack_plugin


def test_format_terminal_progress() -> None:
    bar = format_terminal_progress(step=5, total=10, status="Building package")
    assert "50%" in bar
    assert "Building package" in bar


def test_parse_terminal_command() -> None:
    cmd = parse_terminal_command("/help agent")
    assert cmd["is_command"] is True
    assert cmd["command"] == "help"
    assert cmd["args"] == "agent"

    plain = parse_terminal_command("Hello there")
    assert plain["is_command"] is False
    assert plain["args"] == "Hello there"


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    res = await clickclack_plugin.send("term_session_1", "Running command...")
    assert res.is_ok
    data = res.unwrap()
    assert data["session_id"] == "term_session_1"
    assert data["dispatched"] is True
