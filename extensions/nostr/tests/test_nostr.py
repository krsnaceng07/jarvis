"""Unit tests for Nostr extension."""

from __future__ import annotations

import json
import pytest

from extensions.nostr.src.keys import is_valid_hex_key, normalize_nostr_pubkey
from extensions.nostr.src.events import create_text_note, create_direct_message
from extensions.nostr.src.relays import format_publish_event_message, format_subscription_request
from extensions.nostr.plugin import nostr_plugin


def test_nostr_keys() -> None:
    valid_hex = "a" * 64
    assert is_valid_hex_key(valid_hex) is True
    assert is_valid_hex_key("short_key") is False
    assert normalize_nostr_pubkey("  NPub1XYZ  ") == "npub1xyz"


def test_nostr_event_id_computation() -> None:
    ev = create_text_note(pubkey="1" * 64, content="Hello Nostr")
    assert ev.kind == 1
    assert len(ev.id) == 64
    # Re-computing ID produces exact same hash
    assert ev.compute_id() == ev.id

    dm = create_direct_message(sender_pubkey="1" * 64, recipient_pubkey="2" * 64, content="Secret")
    assert dm.kind == 4
    assert dm.tags == [["p", "2" * 64]]
    assert len(dm.id) == 64


def test_nostr_relay_messages() -> None:
    ev = create_text_note(pubkey="1" * 64, content="Test")
    msg = format_publish_event_message(ev)
    parsed = json.loads(msg)
    assert parsed[0] == "EVENT"
    assert parsed[1]["id"] == ev.id

    req = format_subscription_request("sub1", [{"kinds": [1], "limit": 10}])
    parsed_req = json.loads(req)
    assert parsed_req[0] == "REQ"
    assert parsed_req[1] == "sub1"
    assert parsed_req[2]["limit"] == 10


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    res = await nostr_plugin.send("npub1qqqq", "Decentralized greetings")
    assert res.is_ok
    data = res.unwrap()
    assert data["kind"] == 4
    assert data["published"] is True
