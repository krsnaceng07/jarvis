"""Unit tests for IRC extension."""

from __future__ import annotations

import pytest

from extensions.irc.src.protocol import parse_irc_line, format_irc_line, strip_irc_formatting
from extensions.irc.plugin import irc_plugin


def test_parse_irc_line() -> None:
    # 1. PING message
    msg1 = parse_irc_line("PING :server.example.com")
    assert msg1 is not None
    assert msg1.command == "PING"
    assert msg1.trailing == "server.example.com"

    # 2. PRIVMSG message
    msg2 = parse_irc_line(":alice!user@host PRIVMSG #general :Hello everyone!")
    assert msg2 is not None
    assert msg2.prefix == "alice!user@host"
    assert msg2.nick == "alice"
    assert msg2.command == "PRIVMSG"
    assert msg2.params == ["#general"]
    assert msg2.trailing == "Hello everyone!"


def test_format_irc_line() -> None:
    line = format_irc_line("PRIVMSG", "#general", trailing="Welcome!")
    assert line == "PRIVMSG #general :Welcome!\r\n"


def test_strip_irc_formatting() -> None:
    raw = "\x02Bold\x02 \x0304Red\x03 and \x1fUnderline\x1f"
    assert strip_irc_formatting(raw) == "Bold Red and Underline"


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    res = await irc_plugin.send("#channel", "\x02Hello\x02")
    assert res.is_ok
    data = res.unwrap()
    assert data["target"] == "#channel"
    assert data["text"] == "Hello"
    assert data["sent"] is True
