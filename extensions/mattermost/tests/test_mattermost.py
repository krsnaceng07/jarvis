"""Unit tests for Mattermost extension."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from extensions.mattermost.src.format import format_mattermost_post, build_interactive_attachment
from extensions.mattermost.src.slash import parse_slash_command, format_slash_response
from extensions.mattermost.src.client import MattermostClient
from extensions.mattermost.plugin import mattermost_plugin


def test_format_mattermost_post() -> None:
    post = format_mattermost_post("Hello world", channel_id="chn123", root_id="root456")
    assert post["channel_id"] == "chn123"
    assert post["message"] == "Hello world"
    assert post["root_id"] == "root456"


def test_build_interactive_attachment() -> None:
    att = build_interactive_attachment(
        title="Deploy Approval",
        text="Approve deployment to production?",
        actions=[
            {
                "id": "act1",
                "name": "Approve",
                "url": "https://api.example.com/approve",
                "action": "yes",
            }
        ],
    )
    assert att["title"] == "Deploy Approval"
    assert len(att["actions"]) == 1
    assert att["actions"][0]["name"] == "Approve"


def test_slash_handling() -> None:
    form = {
        "command": "/jarvis",
        "text": "status check",
        "user_name": "developer",
        "channel_id": "c1",
    }
    cmd = parse_slash_command(form)
    assert cmd["command"] == "/jarvis"
    assert cmd["text"] == "status check"
    assert cmd["user_name"] == "developer"

    resp = format_slash_response("Status OK", response_type="in_channel")
    assert resp["text"] == "Status OK"
    assert resp["response_type"] == "in_channel"


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    with patch.object(
        MattermostClient, "create_post", return_value={"id": "post123", "message": "Hi"}
    ):
        res = await mattermost_plugin.send("c1", "Hi")
        assert res.is_ok
        assert res.unwrap()["id"] == "post123"
