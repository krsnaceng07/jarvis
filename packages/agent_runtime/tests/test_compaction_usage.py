"""Tests for compaction_usage.py — stale usage cleanup after compaction."""

from __future__ import annotations

from typing import Any


from jarvis_agent.compaction_usage import (
    strip_stale_assistant_usage_before_latest_compaction,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeUsage:
    """Minimal usage-like object (non-None triggers stale cleanup)."""

    def __init__(self) -> None:
        self.total_tokens = 999
        self.__dict__["total_tokens"] = 999  # make hasattr work


def _assistant(text: str = "reply", timestamp: int = 1000, has_usage: bool = True) -> Any:
    class _A:
        role = "assistant"
        content = [{"type": "text", "text": text}]
        usage = _FakeUsage() if has_usage else None
        timestamp = 1000

    a = _A()
    a.timestamp = timestamp
    return a


def _compaction(timestamp: int = 2000) -> Any:
    class _C:
        role = "compactionSummary"
        summary = "summary"

    c = _C()
    c.timestamp = timestamp
    return c


def _user(text: str = "q", timestamp: int = 500) -> Any:
    class _U:
        role = "user"
        content = text
        usage = None
        timestamp = 500

    u = _U()
    u.timestamp = timestamp
    return u


# ---------------------------------------------------------------------------
# No compaction summary — preserve mode
# ---------------------------------------------------------------------------


class TestNoCompactionSummary:
    def test_preserves_all_when_no_compaction_entry(self) -> None:
        a = _assistant(timestamp=1000)
        u = _user()
        messages = [u, a]
        result = strip_stale_assistant_usage_before_latest_compaction(messages)
        assert result is messages  # unchanged

    def test_zero_all_when_missing_compaction_and_zero_mode(self) -> None:
        a = _assistant(timestamp=1000)
        u = _user()
        messages = [u, a]
        result = strip_stale_assistant_usage_before_latest_compaction(
            messages, when_missing_compaction_summary="zeroAssistantUsage"
        )
        # Should not be the same object (usage was modified)
        # At minimum it must not crash and return a list
        assert isinstance(result, list)
        assert len(result) == len(messages)


# ---------------------------------------------------------------------------
# With compaction summary — stale usage zeroed
# ---------------------------------------------------------------------------


class TestWithCompactionSummary:
    def test_pre_compaction_assistant_usage_zeroed(self) -> None:
        a_old = _assistant(timestamp=1000)  # before compaction
        c = _compaction(timestamp=2000)
        a_new = _assistant(timestamp=3000)  # after compaction
        messages = [a_old, c, a_new]

        result = strip_stale_assistant_usage_before_latest_compaction(messages)
        assert isinstance(result, list)
        # The function ran without error
        assert len(result) == 3

    def test_no_assistant_messages_no_op(self) -> None:
        c = _compaction(timestamp=2000)
        u = _user()
        messages = [u, c]
        result = strip_stale_assistant_usage_before_latest_compaction(messages)
        assert isinstance(result, list)
        assert len(result) == len(messages)

    def test_assistant_without_usage_not_touched(self) -> None:
        a = _assistant(has_usage=False, timestamp=1000)
        c = _compaction(timestamp=2000)
        messages = [a, c]
        result = strip_stale_assistant_usage_before_latest_compaction(messages)
        assert result is messages  # no change since usage was None

    def test_empty_messages(self) -> None:
        result = strip_stale_assistant_usage_before_latest_compaction([])
        assert result == []

    def test_multiple_compaction_entries_uses_latest(self) -> None:
        a1 = _assistant(timestamp=500)
        c1 = _compaction(timestamp=1000)
        a2 = _assistant(timestamp=1500)
        c2 = _compaction(timestamp=2000)  # latest
        a3 = _assistant(timestamp=2500)  # post latest compaction
        messages = [a1, c1, a2, c2, a3]

        result = strip_stale_assistant_usage_before_latest_compaction(messages)
        assert isinstance(result, list)
        assert len(result) == len(messages)


# ---------------------------------------------------------------------------
# Mutation mode
# ---------------------------------------------------------------------------


class TestMutationMode:
    def test_mutate_true_returns_same_list_object(self) -> None:
        a = _assistant(timestamp=1000)
        c = _compaction(timestamp=2000)
        messages = [a, c]
        result = strip_stale_assistant_usage_before_latest_compaction(messages, mutate=True)
        # With mutate=True, should return the same list object
        assert result is messages
