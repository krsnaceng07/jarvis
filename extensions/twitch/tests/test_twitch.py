"""Unit tests for Twitch extension."""

from __future__ import annotations

import pytest

from extensions.twitch.src.tags import parse_twitch_tags, extract_twitch_user_info
from extensions.twitch.src.client import TwitchChatClient
from extensions.twitch.plugin import twitch_plugin


def test_parse_twitch_tags() -> None:
    raw_tags = "@badge-info=;badges=broadcaster/1,subscriber/0;color=#00FF7F;display-name=StreamerName;mod=0;subscriber=1;user-id=12345"
    tags = parse_twitch_tags(raw_tags)
    assert tags["display-name"] == "StreamerName"
    assert tags["color"] == "#00FF7F"
    assert tags["user-id"] == "12345"

    info = extract_twitch_user_info(tags)
    assert info["display_name"] == "StreamerName"
    assert info["subscriber"] is True
    assert info["mod"] is False
    assert "broadcaster/1" in info["badges"]


def test_parse_incoming_privmsg() -> None:
    client = TwitchChatClient(oauth_token="oauth:xyz123")
    raw_line = "@display-name=Viewer1;mod=1 :viewer1!viewer1@viewer1.tmi.twitch.tv PRIVMSG #mychannel :!ask jarvis help"
    parsed = client.parse_incoming_privmsg(raw_line)
    assert parsed is not None
    assert parsed["channel"] == "mychannel"
    assert parsed["text"] == "!ask jarvis help"
    assert parsed["user"]["display_name"] == "Viewer1"
    assert parsed["user"]["mod"] is True


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    res = await twitch_plugin.send("#streamer", "PogChamp")
    assert res.is_ok
    data = res.unwrap()
    assert data["channel"] == "streamer"
    assert data["message"] == "PogChamp"
    assert data["sent"] is True
