"""Unit tests for Tlon extension."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from extensions.tlon.src.format import format_urbit_chat_post
from extensions.tlon.src.client import UrbitClient
from extensions.tlon.plugin import tlon_plugin


def test_format_urbit_chat_post() -> None:
    post = format_urbit_chat_post(author="~zod", text="Hello galaxy")
    assert post["post"]["author"] == "~zod"
    assert post["post"]["contents"][0]["inline"] == ["Hello galaxy"]


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    with patch.object(UrbitClient, "post_chat", return_value={"ok": True}):
        res = await tlon_plugin.send("chat/~zod/general", "Hello galaxy")
        assert res.is_ok
        assert res.unwrap()["ok"] is True
