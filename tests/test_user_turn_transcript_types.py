"""Smoke test for the type-only module src/sessions/user_turn_transcript_types.py.

The TS source is a type-only file (no runtime behavior). The
Python port keeps the same shape so the recorder helpers
have stable TypedDict targets. This test asserts the public
aliases and membership sets are importable and shaped as
expected.
"""
from __future__ import annotations

import pytest

from src.sessions.user_turn_transcript_types import (
    PersistedUserTurnMessage,
    UserTurnInput,
    UserTurnTranscriptRecorder,
    UserTurnTranscriptUpdateMode,
    VALID_USER_TURN_TRANSCRIPT_UPDATE_MODES,
)


def test_update_mode_membership_set_is_closed() -> None:
    assert VALID_USER_TURN_TRANSCRIPT_UPDATE_MODES == frozenset({"inline", "none"})


def test_persisted_user_turn_message_can_be_constructed() -> None:
    msg: PersistedUserTurnMessage = {"role": "user", "text": "hi"}
    assert msg["role"] == "user"
    assert msg["text"] == "hi"


def test_user_turn_input_accepts_full_shape() -> None:
    payload: UserTurnInput = {
        "text": "hello",
        "media": [{"path": "/tmp/a.png", "contentType": "image/png"}],
        "timestamp": 1_700_000_000_000,
        "idempotencyKey": "abc",
        "senderIsOwner": True,
        "transport": {"channel": "discord", "conversationRef": "channel:abc"},
    }
    assert payload["transport"]["channel"] == "discord"


def test_recorder_alias_is_importable() -> None:
    # Type-only assertion: the alias resolves and supports
    # the documented field set. No runtime method call.
    rec: UserTurnTranscriptRecorder = {"hasPersisted": lambda: True}
    assert rec["hasPersisted"]() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
