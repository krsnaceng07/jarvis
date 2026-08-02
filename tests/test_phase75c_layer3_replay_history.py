"""Phase 7.5c tests — replay-history."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.replay_history import (
    STREAM_ERROR_FALLBACK_TEXT,
    normalize_assistant_replay_content,
    sanitize_session_history,
    set_is_bare_delivery_mirror_duplicate_hook,
    set_is_reasoning_only_length_assistant_turn_hook,
    set_is_transcript_only_openclaw_assistant_message_hook,
    set_is_zero_usage_empty_stop_assistant_turn_hook,
    set_normalize_assistant_replay_block_content_hook,
    set_normalize_assistant_replay_text_content_hook,
    set_sanitize_session_history_hook,
    set_sanitize_user_replay_content_hook,
    set_validate_replay_turns_hook,
    validate_replay_turns,
)


def _install_default_hooks() -> None:
    set_sanitize_user_replay_content_hook(lambda m: m)
    set_is_transcript_only_openclaw_assistant_message_hook(lambda m: False)
    set_normalize_assistant_replay_text_content_hook(
        lambda m, t: None  # drop on default
    )
    set_normalize_assistant_replay_block_content_hook(lambda m, c: m)
    set_is_reasoning_only_length_assistant_turn_hook(lambda m: False)
    set_is_zero_usage_empty_stop_assistant_turn_hook(lambda m: False)
    set_is_bare_delivery_mirror_duplicate_hook(lambda prev, m: False)


# ============================================================================
# normalize_assistant_replay_content
# ============================================================================


class TestNormalizeAssistantReplayContent:
    def setup_method(self) -> None:
        _install_default_hooks()

    def test_empty(self) -> None:
        assert normalize_assistant_replay_content([]) == []

    def test_user_passes_through(self) -> None:
        msgs = [{"role": "user", "content": "hi"}]
        assert normalize_assistant_replay_content(msgs) == msgs

    def test_non_dict_passes_through(self) -> None:
        msgs: List[Any] = [None, "string", 42]
        # Touched is False (no user/assistant), so we get the
        # original list back.
        result = normalize_assistant_replay_content(msgs)
        # The implementation returns a new list (touched False
        # case returns a new list copy).
        assert list(result) == [None, "string", 42]

    def test_user_sanitize_touched(self) -> None:
        set_sanitize_user_replay_content_hook(
            lambda m: {**m, "sanitized": True} if isinstance(m, dict) else m
        )
        msgs = [{"role": "user", "content": "hi"}]
        result = normalize_assistant_replay_content(msgs)
        assert result[0].get("sanitized") is True

    def test_user_sanitize_returns_none_drops(self) -> None:
        set_sanitize_user_replay_content_hook(lambda _m: None)
        msgs = [{"role": "user", "content": "hi"}]
        result = normalize_assistant_replay_content(msgs)
        assert result == []

    def test_user_no_touch_returns_original_list(self) -> None:
        msgs = [{"role": "user", "content": "hi"}]
        result = normalize_assistant_replay_content(msgs)
        # touched=False path returns list(messages) -> new list
        # copy. The same dicts inside.
        assert result == msgs

    def test_transcript_only_assistant_dropped(self) -> None:
        set_is_transcript_only_openclaw_assistant_message_hook(
            lambda m: isinstance(m, dict) and m.get("id") == "transcript"
        )
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "id": "transcript", "content": []},
            {"role": "assistant", "id": "real", "content": []},
        ]
        result = normalize_assistant_replay_content(msgs)
        ids = [m.get("id") for m in result if isinstance(m, dict)]
        assert "transcript" not in ids
        assert "real" in ids

    def test_assistant_text_content_uses_normalizer(self) -> None:
        def normalizer(m: Any, _t: str) -> Optional[Dict[str, Any]]:
            if not isinstance(m, dict):
                return None
            return {**m, "normalized": True}

        set_normalize_assistant_replay_text_content_hook(normalizer)
        msgs = [{"role": "assistant", "content": "hi"}]
        result = normalize_assistant_replay_content(msgs)
        assert len(result) == 1
        assert result[0].get("normalized") is True

    def test_assistant_text_content_normalizer_returns_none_drops(self) -> None:
        msgs = [{"role": "assistant", "content": "hi"}]
        result = normalize_assistant_replay_content(msgs)
        assert result == []

    def test_assistant_object_content_wrapped(self) -> None:
        msgs = [
            {"role": "assistant", "content": {"type": "text", "text": "hi"}},
        ]
        result = normalize_assistant_replay_content(msgs)
        assert len(result) == 1
        assert isinstance(result[0]["content"], list)

    def test_assistant_null_content(self) -> None:
        msgs = [{"role": "assistant", "content": None}]
        result = normalize_assistant_replay_content(msgs)
        assert len(result) == 1
        assert result[0]["content"] == []

    def test_reasoning_only_dropped(self) -> None:
        set_is_reasoning_only_length_assistant_turn_hook(
            lambda m: isinstance(m, dict) and m.get("id") == "reasoning-only"
        )
        msgs = [
            {"role": "assistant", "id": "real", "content": [{"type": "text", "text": "ok"}]},
            {"role": "assistant", "id": "reasoning-only", "content": []},
        ]
        result = normalize_assistant_replay_content(msgs)
        ids = [m.get("id") for m in result if isinstance(m, dict)]
        assert "reasoning-only" not in ids
        assert "real" in ids

    def test_empty_error_stop_injected(self) -> None:
        msgs = [
            {"role": "assistant", "stopReason": "error", "content": []},
        ]
        result = normalize_assistant_replay_content(msgs)
        assert len(result) == 1
        assert result[0]["content"] == [
            {"type": "text", "text": STREAM_ERROR_FALLBACK_TEXT},
        ]

    def test_empty_zero_usage_stop_injected(self) -> None:
        set_is_zero_usage_empty_stop_assistant_turn_hook(
            lambda m: isinstance(m, dict) and m.get("id") == "zero"
        )
        msgs = [
            {"role": "assistant", "id": "zero", "content": []},
        ]
        result = normalize_assistant_replay_content(msgs)
        assert result[0]["content"] == [
            {"type": "text", "text": STREAM_ERROR_FALLBACK_TEXT},
        ]

    def test_empty_silent_reply_preserved(self) -> None:
        # An empty assistant turn with no error/zero-usage marker
        # should be preserved (silent reply semantics).
        msgs = [
            {"role": "assistant", "content": []},
        ]
        result = normalize_assistant_replay_content(msgs)
        assert len(result) == 1
        assert result[0]["content"] == []

    def test_bare_delivery_mirror_duplicate_dropped(self) -> None:
        # Set up a previous message that matches the bare-delivery
        # shape.
        def is_dup(prev_list: List[Any], message: Any) -> bool:
            if not prev_list:
                return False
            last = prev_list[-1]
            return (
                isinstance(last, dict)
                and isinstance(message, dict)
                and last.get("role") == "assistant"
                and message.get("role") == "assistant"
                and last.get("content") == message.get("content")
                and last.get("id") != message.get("id")
            )

        set_is_bare_delivery_mirror_duplicate_hook(is_dup)
        msgs = [
            {"role": "assistant", "id": "a1", "content": [{"type": "text", "text": "ok"}]},
            {"role": "assistant", "id": "a2", "content": [{"type": "text", "text": "ok"}]},
        ]
        result = normalize_assistant_replay_content(msgs)
        ids = [m.get("id") for m in result if isinstance(m, dict)]
        # The duplicate (a2) should be dropped.
        assert ids == ["a1"]

    def test_assistant_block_content_uses_normalizer(self) -> None:
        def normalizer(m: Any, _content: List[Any]) -> Optional[Dict[str, Any]]:
            if not isinstance(m, dict):
                return None
            return {**m, "content": [{"type": "text", "text": "normalized"}]}

        set_normalize_assistant_replay_block_content_hook(normalizer)
        msgs = [
            {"role": "assistant", "content": [{"type": "text", "text": "raw"}]},
        ]
        result = normalize_assistant_replay_content(msgs)
        assert result[0]["content"] == [
            {"type": "text", "text": "normalized"},
        ]


# ============================================================================
# sanitize_session_history
# ============================================================================


class TestSanitizeSessionHistory:
    def setup_method(self) -> None:
        set_sanitize_session_history_hook(
            lambda params: _async_return(params.get("messages") or [])
        )

    @pytest.mark.asyncio
    async def test_default(self) -> None:
        msgs = [{"role": "user", "content": "hi"}]
        result = await sanitize_session_history(messages=msgs)
        assert result == msgs

    @pytest.mark.asyncio
    async def test_custom(self) -> None:
        async def hook(params: Dict[str, Any]) -> List[Dict[str, Any]]:
            return [{"sanitized": True, "i": i} for i, _ in enumerate(params.get("messages") or [])]

        set_sanitize_session_history_hook(hook)
        msgs = [{"role": "user"}, {"role": "assistant"}]
        result = await sanitize_session_history(messages=msgs)
        assert result == [
            {"sanitized": True, "i": 0},
            {"sanitized": True, "i": 1},
        ]


# ============================================================================
# validate_replay_turns
# ============================================================================


class TestValidateReplayTurns:
    def setup_method(self) -> None:
        set_validate_replay_turns_hook(
            lambda params: _async_return(params.get("messages") or [])
        )

    @pytest.mark.asyncio
    async def test_default(self) -> None:
        msgs = [{"role": "user"}]
        result = await validate_replay_turns(messages=msgs)
        assert result == msgs

    @pytest.mark.asyncio
    async def test_custom(self) -> None:
        async def hook(params: Dict[str, Any]) -> List[Dict[str, Any]]:
            return [{"validated": True, "i": i} for i, _ in enumerate(params.get("messages") or [])]

        set_validate_replay_turns_hook(hook)
        msgs = [{"role": "user"}]
        result = await validate_replay_turns(messages=msgs)
        assert result == [{"validated": True, "i": 0}]


async def _async_return(value: Any) -> Any:
    return value
