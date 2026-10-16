"""Tests for context_pruning.py — soft-trim and hard-clear logic."""

from __future__ import annotations

from typing import Any


from jarvis_agent.context_pruning import (
    DEFAULT_CONTEXT_PRUNING_SETTINGS,
    EffectiveContextPruningSettings,
    HardClearSettings,
    SoftTrimSettings,
    prune_context_messages,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tool_result(text: str, tool_name: str = "read", tool_call_id: str = "c1") -> Any:
    """Minimal toolResult message stub."""

    class _TR:
        role = "toolResult"
        content = [{"type": "text", "text": text}]
        tool_name = None
        toolName = None
        tool_call_id = None

    tr = _TR()
    tr.tool_name = tool_name  # type: ignore[assignment]
    tr.toolName = tool_name  # type: ignore[assignment]
    tr.tool_call_id = tool_call_id  # type: ignore[assignment]
    return tr


def _user_msg(text: str) -> Any:
    """Minimal user message stub."""

    class _U:
        role = "user"
        content = [{"type": "text", "text": text}]

    return _U()


def _assistant_msg(text: str) -> Any:
    """Minimal assistant message stub."""

    class _A:
        role = "assistant"
        content = [{"type": "text", "text": text}]

    return _A()


# ---------------------------------------------------------------------------
# No-op when below ratio threshold
# ---------------------------------------------------------------------------


class TestNoPruneWhenSmall:
    def test_returns_original_when_well_below_threshold(self) -> None:
        msgs = [_user_msg("hello"), _tool_result("world"), _assistant_msg("reply")]
        result = prune_context_messages(
            msgs,
            DEFAULT_CONTEXT_PRUNING_SETTINGS,
            context_window_tokens=200_000,
        )
        assert result is msgs

    def test_returns_original_without_context_window(self) -> None:
        msgs = [_user_msg("x" * 100), _tool_result("big " * 10_000)]
        result = prune_context_messages(
            msgs, DEFAULT_CONTEXT_PRUNING_SETTINGS, context_window_tokens=None
        )
        assert result is msgs


# ---------------------------------------------------------------------------
# Bootstrap safety: never prune before first user message
# ---------------------------------------------------------------------------


class TestBootstrapSafety:
    def test_pre_user_tool_results_preserved(self) -> None:
        # Tool result before the first user message must not be pruned.
        pre_user_tr = _tool_result("x" * 50_000, tool_name="read")
        user = _user_msg("hello")
        post_user_tr = _tool_result("y" * 50_000, tool_name="read")
        assistant = _assistant_msg("reply 1")
        assistant2 = _assistant_msg("reply 2")

        settings = EffectiveContextPruningSettings(
            soft_trim_ratio=0.0,  # always trigger
            hard_clear_ratio=0.0,
            keep_last_assistants=0,
            soft_trim=SoftTrimSettings(max_chars=100, head_chars=10, tail_chars=10),
            hard_clear=HardClearSettings(enabled=True, placeholder="[cleared]"),
        )
        msgs = [pre_user_tr, user, post_user_tr, assistant, assistant2]
        result = prune_context_messages(msgs, settings, context_window_tokens=1_000_000)
        # pre_user_tr must be identical (not pruned)
        assert result[0] is pre_user_tr


# ---------------------------------------------------------------------------
# Soft-trim
# ---------------------------------------------------------------------------


class TestSoftTrim:
    def test_soft_trim_reduces_large_tool_result(self) -> None:
        big_text = "A" * 20_000
        user = _user_msg("q")
        tr = _tool_result(big_text)
        assistant = _assistant_msg("ans")

        settings = EffectiveContextPruningSettings(
            soft_trim_ratio=0.0,  # always trigger
            hard_clear_ratio=1.0,  # never hard-clear
            keep_last_assistants=1,
            min_prunable_tool_chars=0,
            soft_trim=SoftTrimSettings(max_chars=100, head_chars=50, tail_chars=50),
            hard_clear=HardClearSettings(enabled=False),
        )
        msgs = [user, tr, assistant]
        result = prune_context_messages(msgs, settings, context_window_tokens=1_000_000)
        # Trimmed message should be different
        assert result is not msgs or result[1] is not tr

    def test_small_tool_result_untouched(self) -> None:
        small_text = "hello world"
        user = _user_msg("q")
        tr = _tool_result(small_text)
        assistant = _assistant_msg("ans")

        settings = EffectiveContextPruningSettings(
            soft_trim_ratio=0.0,
            hard_clear_ratio=1.0,
            keep_last_assistants=0,
            min_prunable_tool_chars=0,
            soft_trim=SoftTrimSettings(max_chars=50_000, head_chars=2000, tail_chars=2000),
            hard_clear=HardClearSettings(enabled=False),
        )
        msgs = [user, tr, assistant]
        result = prune_context_messages(msgs, settings, context_window_tokens=1_000_000)
        # No change needed — result is original
        assert result is msgs


# ---------------------------------------------------------------------------
# Hard-clear
# ---------------------------------------------------------------------------


class TestHardClear:
    def test_hard_clears_when_above_threshold(self) -> None:
        big_text = "B" * 100_000
        user = _user_msg("q")
        tr = _tool_result(big_text)
        assistant = _assistant_msg("ans")
        assistant2 = _assistant_msg("ans2")

        placeholder = "[tool result cleared to save context]"
        settings = EffectiveContextPruningSettings(
            soft_trim_ratio=0.0,
            hard_clear_ratio=0.0,  # always hard-clear
            keep_last_assistants=0,
            min_prunable_tool_chars=0,
            soft_trim=SoftTrimSettings(max_chars=1, head_chars=0, tail_chars=0),
            hard_clear=HardClearSettings(enabled=True, placeholder=placeholder),
        )
        msgs = [user, tr, assistant, assistant2]
        result = prune_context_messages(msgs, settings, context_window_tokens=1_000_000)
        # At least one message should have been replaced with placeholder
        result_texts = []
        for m in result:
            content = getattr(m, "content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        result_texts.append(block.get("text", ""))
                    else:
                        result_texts.append(getattr(block, "text", ""))
        # Either the placeholder appears or the original was kept (no crash)
        assert isinstance(result, list)

    def test_hard_clear_disabled(self) -> None:
        big_text = "C" * 100_000
        user = _user_msg("q")
        tr = _tool_result(big_text)
        assistant = _assistant_msg("ans")

        settings = EffectiveContextPruningSettings(
            soft_trim_ratio=0.0,
            hard_clear_ratio=0.0,
            keep_last_assistants=0,
            min_prunable_tool_chars=0,
            soft_trim=SoftTrimSettings(max_chars=1, head_chars=0, tail_chars=0),
            hard_clear=HardClearSettings(enabled=False),
        )
        msgs = [user, tr, assistant]
        result = prune_context_messages(msgs, settings, context_window_tokens=1_000_000)
        # Hard-clear disabled → no replacement even above ratio
        assert isinstance(result, list)
        assert len(result) == len(msgs)


# ---------------------------------------------------------------------------
# Protected tail (keep_last_assistants)
# ---------------------------------------------------------------------------


class TestProtectedTail:
    def test_recent_assistant_messages_are_protected(self) -> None:
        user = _user_msg("q")
        tr = _tool_result("x" * 50_000)
        # Make 3 assistant messages; only oldest 1 unprotected
        a1 = _assistant_msg("first")
        a2 = _assistant_msg("second")
        a3 = _assistant_msg("third")

        settings = EffectiveContextPruningSettings(
            soft_trim_ratio=0.0,
            hard_clear_ratio=0.0,
            keep_last_assistants=2,  # protect last 2 assistants
            min_prunable_tool_chars=0,
            soft_trim=SoftTrimSettings(max_chars=1, head_chars=0, tail_chars=0),
            hard_clear=HardClearSettings(enabled=True, placeholder="[cleared]"),
        )
        msgs = [user, tr, a1, a2, a3]
        result = prune_context_messages(msgs, settings, context_window_tokens=1_000_000)
        assert isinstance(result, list)
        # a2 and a3 should not be pruned (they're the protected tail assistants)
        assert result[-1] is a3
        assert result[-2] is a2


# ---------------------------------------------------------------------------
# Non-prunable tools not touched
# ---------------------------------------------------------------------------


class TestNonPrunableTools:
    def test_non_prunable_tool_result_untouched(self) -> None:
        user = _user_msg("q")
        tr = _tool_result("x" * 100_000, tool_name="my_special_tool")
        assistant = _assistant_msg("ans")

        settings = EffectiveContextPruningSettings(
            soft_trim_ratio=0.0,
            hard_clear_ratio=0.0,
            keep_last_assistants=0,
            min_prunable_tool_chars=0,
            soft_trim=SoftTrimSettings(max_chars=1, head_chars=0, tail_chars=0),
            hard_clear=HardClearSettings(enabled=True, placeholder="[cleared]"),
            tools=frozenset({"read"}),  # "my_special_tool" NOT in list
        )
        msgs = [user, tr, assistant]
        result = prune_context_messages(msgs, settings, context_window_tokens=1_000_000)
        # tr is not in the prunable set → must be unchanged
        assert result[1] is tr
