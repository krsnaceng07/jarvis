"""Phase 5.13 — ``session-key.continuity.test.ts`` → Python.

OpenClaw parity: ports the 4 ``it`` blocks from
``src/routing/session-key.continuity.test.ts``.

Python adaptations:
- ``it.each([{...}, {...}])("$name", ({...}) => ...)`` becomes
  ``@pytest.mark.parametrize``.
- The ``expectUnknownChannelKeyCase`` helper becomes an inline
  assertion block in each parameterized case.
"""
from __future__ import annotations

import pytest

from src.routing.resolve_route import build_agent_session_key


_AGENT_ID = "main"
_CHANNEL = "quietchat"
_ACCOUNT_ID = "default"


def _build_channel_session_key(peer, dm_scope="main"):
    return build_agent_session_key(
        {
            "agentId": _AGENT_ID,
            "channel": _CHANNEL,
            "accountId": _ACCOUNT_ID,
            "dmScope": dm_scope,
            "peer": peer,
        }
    )


@pytest.mark.parametrize(
    ("dm_scope", "expected_dm_key"),
    [
        ("main", "agent:main:main"),
        ("per-peer", "agent:main:direct:user123"),
    ],
)
def test_keeps_dm_and_channel_session_keys_distinct(dm_scope, expected_dm_key):
    """DM and channel session keys must never collide (the openclaw#1234 family
    of regressions)."""
    dm_key = _build_channel_session_key(
        peer={"kind": "direct", "id": "user123"}, dm_scope=dm_scope
    )
    group_key = _build_channel_session_key(peer={"kind": "channel", "id": "channel456"})

    assert dm_key == expected_dm_key
    assert group_key == "agent:main:quietchat:channel:channel456"
    assert dm_key != group_key


@pytest.mark.parametrize("invalid_channel_id", ["", "   "])
def test_handles_invalid_channel_id_without_collisions(invalid_channel_id):
    """An empty / whitespace channel id falls back to ``unknown`` so the DM
    ``main`` key never collides with a missing-channel DM."""
    missing_id_key = _build_channel_session_key(
        peer={"kind": "channel", "id": invalid_channel_id}
    )
    assert "unknown" in missing_id_key
    assert missing_id_key != "agent:main:main"
