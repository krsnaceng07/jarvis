"""Unit tests for ZaloUser extension."""

from __future__ import annotations

import pytest

from extensions.zalouser.src.session import ZaloUserSession
from extensions.zalouser.src.client import ZaloUserClient
from extensions.zalouser.plugin import zalouser_plugin


def test_zalo_user_session() -> None:
    s_empty = ZaloUserSession()
    assert s_empty.is_authenticated() is False

    s_valid = ZaloUserSession(imei="imei123", cookie="c123", user_id="u456", logged_in=True)
    assert s_valid.is_authenticated() is True


def test_zalo_user_client() -> None:
    s_valid = ZaloUserSession(imei="imei123", cookie="c123", logged_in=True)
    client = ZaloUserClient(s_valid)
    res = client.send_direct_message("friend_1", "Hello friend")
    assert res["status"] == 0
    assert res["data"]["to"] == "friend_1"
    assert res["data"]["text"] == "Hello friend"

    react = client.add_reaction("msg_123", "❤️")
    assert react["status"] == 0
    assert react["emoji"] == "❤️"


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    res = await zalouser_plugin.send("friend_1", "Hello")
    assert res.is_ok
    data = res.unwrap()
    assert data["status"] == 0
