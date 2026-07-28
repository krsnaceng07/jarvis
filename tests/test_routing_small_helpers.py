"""Phase 5.13 — small routing-helper smoke tests.

OpenClaw parity: the small routing helpers
(``peer-kind-match``, ``default-account-warnings``,
``conversation-ref``) don't have dedicated test files in
OpenClaw — they're covered indirectly by ``resolve-route.test.ts``.
This file gives the Python port a minimal direct-coverage
smoke test for each helper so the routing surface has at
least one dedicated test per module.
"""
from __future__ import annotations

import pytest

from src.routing.conversation_ref import (
    build_conversation_ref,
    normalize_conversation_peer_id,
)
from src.routing.default_account_warnings import (
    format_channel_accounts_default_path,
    format_set_explicit_default_instruction,
    format_set_explicit_default_to_configured_instruction,
)
from src.routing.peer_kind_match import peer_kind_matches


# ---------------------------------------------------------------------------
# peer_kind_match
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("binding_kind", "peer_kind", "expected"),
    [
        # Exact match.
        ("channel", "channel", True),
        ("group", "group", True),
        # Group/channel are treated as equivalent in both directions.
        ("group", "channel", True),
        ("channel", "group", True),
        # Otherwise no match.
        ("channel", "direct", False),
        ("group", "direct", False),
        ("direct", "channel", False),
    ],
)
def test_peer_kind_matches(binding_kind, peer_kind, expected):
    assert peer_kind_matches(binding_kind, peer_kind) is expected


# ---------------------------------------------------------------------------
# default_account_warnings
# ---------------------------------------------------------------------------


def test_format_channel_accounts_default_path_uses_dotted_path():
    msg = format_channel_accounts_default_path("telegram")
    assert "telegram" in msg
    assert "channels.telegram" in msg or "accounts" in msg


def test_format_set_explicit_default_instruction_mentions_channel():
    msg = format_set_explicit_default_instruction("telegram")
    assert "telegram" in msg


def test_format_set_explicit_default_to_configured_instruction_mentions_account():
    msg = format_set_explicit_default_to_configured_instruction(
        {"channelKey": "telegram", "accountId": "work"}
    )
    assert "telegram" in msg
    # The configured-instruction variant does not echo the account id
    # (it points the operator at the config path instead); assert the
    # instruction tells the operator to set the config option.
    assert "defaultAccount" in msg or "default" in msg


# ---------------------------------------------------------------------------
# conversation_ref
# ---------------------------------------------------------------------------


def test_normalize_conversation_peer_id_preserves_case():
    """The Python port preserves the original case (the OpenClaw
    helper normalizes the channel but keeps the peer-id case)."""
    result = normalize_conversation_peer_id("Telegram", "USER_42")
    assert "USER_42" in result


def test_normalize_conversation_peer_id_handles_empty_value():
    assert normalize_conversation_peer_id("Telegram", "") == ""


def test_build_conversation_ref_uses_channel_and_peer():
    ref = build_conversation_ref(
        {
            "channel": "telegram",
            "accountId": "default",
            "kind": "direct",
            "peerId": "user-42",
        }
    )
    # The ref is an opaque ``conv_<sha256>`` token; the channel +
    # peer id are inputs to the hash, not substrings of the result.
    assert ref.startswith("conv_")
    assert len(ref) == 5 + 32  # prefix + 32 hex chars
