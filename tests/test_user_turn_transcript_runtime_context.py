"""Tests for src/sessions/user_turn_transcript_runtime_context.py.

Mirrors the public surface of OpenClaw's
``src/sessions/user-turn-transcript-runtime-context.ts`` (no
dedicated TS test file; the helpers are exercised through
``user-turn-transcript.test.ts``). These tests cover the
attach/take contract directly.
"""
from __future__ import annotations

import pytest

from src.sessions.user_turn_transcript_runtime_context import (
    RuntimeUserTurnTranscriptContext,
    UserTurnMessage,
    UserTurnTranscriptRecorder,
    attach_runtime_user_turn_transcript_context,
    attach_runtime_user_turn_transcript_recorder,
    take_runtime_user_turn_transcript_context,
    take_runtime_user_turn_transcript_recorder,
)


def _make_message() -> UserTurnMessage:
    return {"role": "user", "text": "hello"}


def _make_recorder() -> UserTurnTranscriptRecorder:
    return {"message": _make_message(), "resolveMessage": lambda: None}


class TestAttachAndTakeContext:
    def test_attach_then_take_returns_attached_context(self) -> None:
        msg = _make_message()
        ctx = RuntimeUserTurnTranscriptContext(
            message=msg, recorder=_make_recorder()
        )
        carrier = attach_runtime_user_turn_transcript_context(msg, ctx)
        # take removes the context.
        taken = take_runtime_user_turn_transcript_context(carrier)
        assert taken is ctx

    def test_take_returns_none_when_not_attached(self) -> None:
        msg = _make_message()
        assert take_runtime_user_turn_transcript_context(msg) is None

    def test_take_clears_the_attached_context(self) -> None:
        msg = _make_message()
        ctx = RuntimeUserTurnTranscriptContext(
            message=msg, recorder=_make_recorder()
        )
        carrier = attach_runtime_user_turn_transcript_context(msg, ctx)
        # First take returns the context.
        first = take_runtime_user_turn_transcript_context(carrier)
        assert first is ctx
        # Second take returns None (the context was cleared).
        second = take_runtime_user_turn_transcript_context(carrier)
        assert second is None

    def test_take_returns_carrier_message(self) -> None:
        msg = _make_message()
        ctx = RuntimeUserTurnTranscriptContext(
            message=msg, recorder=_make_recorder()
        )
        carrier = attach_runtime_user_turn_transcript_context(msg, ctx)
        # attach on a non-carrier returns a carrier; the
        # carrier's payload is the original message.
        assert take_runtime_user_turn_transcript_context(carrier) is not None

    def test_attach_does_not_mutate_original_message(self) -> None:
        msg = _make_message()
        original = dict(msg)
        ctx = RuntimeUserTurnTranscriptContext(
            message=msg, recorder=_make_recorder()
        )
        attach_runtime_user_turn_transcript_context(msg, ctx)
        # The original dict is unchanged (we attached to a
        # carrier, not to the message in place).
        assert msg == original

    def test_attach_is_idempotent_per_slot(self) -> None:
        msg = _make_message()
        ctx_a = RuntimeUserTurnTranscriptContext(
            message=msg, recorder=_make_recorder()
        )
        ctx_b = RuntimeUserTurnTranscriptContext(
            message=msg, recorder=_make_recorder()
        )
        carrier = attach_runtime_user_turn_transcript_context(msg, ctx_a)
        carrier = attach_runtime_user_turn_transcript_context(carrier, ctx_b)
        # The latest attach wins.
        assert take_runtime_user_turn_transcript_context(carrier) is ctx_b


class TestAttachAndTakeRecorder:
    def test_attach_then_take_returns_attached_recorder(self) -> None:
        msg = _make_message()
        recorder = _make_recorder()
        carrier = attach_runtime_user_turn_transcript_recorder(msg, recorder)
        # take removes the recorder.
        taken = take_runtime_user_turn_transcript_recorder(carrier)
        assert taken is recorder

    def test_take_returns_none_when_not_attached(self) -> None:
        msg = _make_message()
        assert take_runtime_user_turn_transcript_recorder(msg) is None

    def test_take_clears_the_attached_recorder(self) -> None:
        msg = _make_message()
        recorder = _make_recorder()
        carrier = attach_runtime_user_turn_transcript_recorder(msg, recorder)
        first = take_runtime_user_turn_transcript_recorder(carrier)
        assert first is recorder
        second = take_runtime_user_turn_transcript_recorder(carrier)
        assert second is None


class TestIndependentSlots:
    def test_context_and_recorder_are_independent(self) -> None:
        msg = _make_message()
        ctx = RuntimeUserTurnTranscriptContext(
            message=msg, recorder=_make_recorder()
        )
        recorder = _make_recorder()
        carrier = attach_runtime_user_turn_transcript_context(msg, ctx)
        carrier = attach_runtime_user_turn_transcript_recorder(carrier, recorder)
        # Each slot can be taken independently.
        assert take_runtime_user_turn_transcript_context(carrier) is ctx
        # Recorder is still attached after the context was taken.
        assert take_runtime_user_turn_transcript_recorder(carrier) is recorder


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
