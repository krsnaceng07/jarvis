"""Phase 7.2a — embedded_agent_runner compaction helpers tests.

Verifies the public surface of
the 7.2a compaction helpers:

- :func:`classify_compaction_reason` +
  :func:`resolve_compaction_failure_reason` +
  :func:`format_unknown_compaction_reason_detail`
  (compact-reasons)
- :func:`resolve_compaction_timeout_ms` +
  :func:`compact_with_safety_timeout` +
  :func:`compact_context_engine_with_safety_timeout`
  (compaction-safety-timeout)
- :func:`build_compaction_harness_model_provider`
  (compaction-harness-model-provider)
- :func:`repair_rejected_thinking_replay_in_session_manager`
  (thinking-replay-repair)
- :func:`create_post_compaction_loop_guard` +
  :class:`PostCompactionLoopPersistedError`
  (post-compaction-loop-guard)
- :func:`dedupe_duplicate_user_messages_for_compaction` +
  :func:`collect_duplicate_user_message_entry_ids_for_compaction`
  (compaction-duplicate-user-messages)
- :func:`compact_embedded_agent_session_direct`
  (compact-runtime STUB)
"""
from __future__ import annotations

import asyncio
import pytest

from src.agents.embedded_agent_runner import (
    DEFAULT_DUPLICATE_USER_MESSAGE_WINDOW_MS,
    DEFERRED_CONTEXT_ENGINE_COMPACTION_REASON,
    EMBEDDED_COMPACTION_TIMEOUT_MS,
    MIN_DUPLICATE_USER_MESSAGE_CHARS,
    POST_COMPACTION_WINDOW_SIZE,
    PostCompactionLoopPersistedError,
    build_compaction_harness_model_provider,
    classify_compaction_reason,
    collect_duplicate_user_message_entry_ids_for_compaction,
    compact_context_engine_with_safety_timeout,
    compact_embedded_agent_session_direct,
    compact_with_safety_timeout,
    create_post_compaction_loop_guard,
    dedupe_duplicate_user_messages_for_compaction,
    format_unknown_compaction_reason_detail,
    repair_rejected_thinking_replay_in_session_manager,
    resolve_compaction_failure_reason,
    resolve_compaction_timeout_ms,
)


# ============================================================================
# compact-reasons
# ============================================================================


class TestResolveCompactionFailureReason:
    def test_passthrough(self) -> None:
        assert (
            resolve_compaction_failure_reason("some error")
            == "some error"
        )

    def test_generic_cancellation_replaced(self) -> None:
        result = resolve_compaction_failure_reason(
            "compaction cancelled",
            safeguard_cancel_reason="aborted by user",
        )
        assert result == "aborted by user"

    def test_generic_error_prefix_replaced(self) -> None:
        result = resolve_compaction_failure_reason(
            "Error: compaction cancelled",
            safeguard_cancel_reason="timeout",
        )
        assert result == "timeout"

    def test_non_generic_kept(self) -> None:
        # Specific reason — not
        # replaced even if safeguard
        # is set.
        result = resolve_compaction_failure_reason(
            "context overflow", safeguard_cancel_reason="abort"
        )
        assert result == "context overflow"


class TestClassifyCompactionReason:
    def test_empty(self) -> None:
        assert classify_compaction_reason(None) == "unknown"
        assert classify_compaction_reason("") == "unknown"

    def test_no_compactable(self) -> None:
        assert (
            classify_compaction_reason("Nothing to compact")
            == "no_compactable_entries"
        )
        assert (
            classify_compaction_reason(
                "no real conversation messages found"
            )
            == "no_compactable_entries"
        )

    def test_below_threshold(self) -> None:
        assert (
            classify_compaction_reason("Below threshold")
            == "below_threshold"
        )
        assert (
            classify_compaction_reason("Already under target")
            == "below_threshold"
        )

    def test_already_compacted(self) -> None:
        assert (
            classify_compaction_reason("Already compacted")
            == "already_compacted_recently"
        )

    def test_deferred(self) -> None:
        assert (
            classify_compaction_reason(
                "compaction deferred to background"
            )
            == "deferred_background"
        )

    def test_exceeds_target(self) -> None:
        assert (
            classify_compaction_reason(
                "live context still exceeds target"
            )
            == "live_context_still_exceeds_target"
        )

    def test_guard(self) -> None:
        assert (
            classify_compaction_reason("post-compaction guard")
            == "guard_blocked"
        )

    def test_summary(self) -> None:
        assert (
            classify_compaction_reason("summary failed")
            == "summary_failed"
        )

    def test_timeout(self) -> None:
        assert (
            classify_compaction_reason("compaction timed out")
            == "timeout"
        )
        assert classify_compaction_reason("timeout") == "timeout"

    def test_4xx(self) -> None:
        assert (
            classify_compaction_reason("provider returned 429")
            == "provider_error_4xx"
        )

    def test_5xx(self) -> None:
        assert (
            classify_compaction_reason("provider returned 503")
            == "provider_error_5xx"
        )

    def test_unknown(self) -> None:
        assert (
            classify_compaction_reason("weird thing happened")
            == "unknown"
        )


class TestFormatUnknownCompactionReasonDetail:
    def test_none(self) -> None:
        assert format_unknown_compaction_reason_detail(None) is None
        assert format_unknown_compaction_reason_detail("") is None

    def test_basic(self) -> None:
        result = format_unknown_compaction_reason_detail(
            "some error reason"
        )
        assert result is not None
        assert "some" in result
        assert "error" in result

    def test_special_chars_replaced(self) -> None:
        result = format_unknown_compaction_reason_detail(
            "error!@#$%^&*()"
        )
        assert result is not None
        # Allowed chars (per OpenClaw regex): letters, digits, ._:@/+~-
        # Special chars replaced with _
        assert "!" not in result
        assert "#" not in result
        assert "$" not in result
        # @ is allowed and preserved (matches OpenClaw compact-reasons.ts:83)
        assert "@" in result

    def test_truncation(self) -> None:
        long_reason = "a" * 500
        result = format_unknown_compaction_reason_detail(
            long_reason
        )
        assert result is not None
        assert len(result) <= 100


# ============================================================================
# compaction-safety-timeout
# ============================================================================


class TestResolveCompactionTimeoutMs:
    def test_default(self) -> None:
        assert (
            resolve_compaction_timeout_ms(None)
            == EMBEDDED_COMPACTION_TIMEOUT_MS
        )

    def test_from_config(self) -> None:
        cfg = {
            "agents": {
                "defaults": {
                    "compaction": {"timeoutSeconds": 60}
                }
            }
        }
        assert resolve_compaction_timeout_ms(cfg) == 60_000

    def test_from_config_float(self) -> None:
        cfg = {
            "agents": {
                "defaults": {
                    "compaction": {"timeoutSeconds": 1.5}
                }
            }
        }
        # floor to 1s
        assert resolve_compaction_timeout_ms(cfg) == 1000

    def test_from_config_invalid(self) -> None:
        cfg = {
            "agents": {
                "defaults": {
                    "compaction": {"timeoutSeconds": "bad"}
                }
            }
        }
        assert (
            resolve_compaction_timeout_ms(cfg)
            == EMBEDDED_COMPACTION_TIMEOUT_MS
        )


class TestCompactWithSafetyTimeout:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        async def _compact(signal: object) -> str:
            return "ok"

        result = await compact_with_safety_timeout(
            _compact, timeout_ms=1000
        )
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        async def _slow(signal: object) -> str:
            await asyncio.sleep(2.0)
            return "done"

        with pytest.raises(RuntimeError, match="timed out"):
            await compact_with_safety_timeout(
                _slow, timeout_ms=100
            )

    @pytest.mark.asyncio
    async def test_on_cancel_called(self) -> None:
        called: list = []

        async def _slow(signal: object) -> str:
            await asyncio.sleep(2.0)
            return "done"

        def _on_cancel() -> None:
            called.append("cancel")

        with pytest.raises(RuntimeError):
            await compact_with_safety_timeout(
                _slow,
                timeout_ms=100,
                on_cancel=_on_cancel,
            )
        assert called == ["cancel"]


class TestCompactContextEngineWithSafetyTimeout:
    @pytest.mark.asyncio
    async def test_calls_compact(self) -> None:
        called: list = []

        class _Engine:
            async def compact(self, params: object) -> dict:
                called.append(params)
                return {"ok": True}

        result = await compact_context_engine_with_safety_timeout(
            _Engine(), {}, timeout_ms=1000
        )
        assert result == {"ok": True}
        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_missing_compact(self) -> None:
        class _Engine:
            pass

        with pytest.raises(TypeError):
            await compact_context_engine_with_safety_timeout(
                _Engine(), {}
            )


# ============================================================================
# compaction-harness-model-provider
# ============================================================================


class TestBuildCompactionHarnessModelProvider:
    def test_minimal(self) -> None:
        result = build_compaction_harness_model_provider()
        assert result == {}

    def test_with_model(self) -> None:
        result = build_compaction_harness_model_provider(
            model={"api": "openai", "baseUrl": "https://api.openai.com"}
        )
        assert result["api"] == "openai"
        assert result["baseUrl"] == "https://api.openai.com"

    def test_with_plan(self) -> None:
        plan = {"modelRoute": {"api": "anthropic"}}
        result = build_compaction_harness_model_provider(
            model={"api": "openai"}, plan=plan
        )
        # Plan takes precedence.
        assert result["api"] == "anthropic"

    def test_with_prepared_auth(self) -> None:
        plan = {"modelRoute": {}}
        result = build_compaction_harness_model_provider(
            plan=plan, attempt={"kind": "explicit"}
        )
        assert "preparedAuth" in result
        assert result["preparedAuth"]["source"] == "explicit"


# ============================================================================
# thinking-replay-repair
# ============================================================================


class TestRepairRejectedThinkingReplay:
    def test_no_session_manager_method(self) -> None:
        class _SM:
            pass

        result = repair_rejected_thinking_replay_in_session_manager(
            _SM()
        )
        assert result["repaired"] is False
        assert "no get_branch" in result["reason"]

    def test_get_branch_raises(self) -> None:
        class _SM:
            def get_branch(self) -> list:
                raise RuntimeError("nope")

        result = repair_rejected_thinking_replay_in_session_manager(
            _SM()
        )
        assert result["repaired"] is False

    def test_no_thinking_blocks(self) -> None:
        class _SM:
            def get_branch(self) -> list:
                return [
                    {
                        "id": "a",
                        "type": "message",
                        "message": {
                            "role": "user",
                            "content": "hi",
                        },
                    }
                ]

        result = repair_rejected_thinking_replay_in_session_manager(
            _SM()
        )
        assert result["repaired"] is False
        assert "no thinking blocks" in result["reason"]

    def test_with_thinking_blocks(self) -> None:
        class _SM:
            def get_branch(self) -> list:
                return [
                    {
                        "id": "a",
                        "type": "message",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "thinking", "text": "x"},
                                {"type": "text", "text": "y"},
                            ],
                        },
                    }
                ]

        result = repair_rejected_thinking_replay_in_session_manager(
            _SM()
        )
        assert result["repaired"] is True
        assert result["repairedCount"] == 1


# ============================================================================
# post-compaction-loop-guard
# ============================================================================


class TestCreatePostCompactionLoopGuard:
    def test_default_window(self) -> None:
        guard = create_post_compaction_loop_guard()
        assert (
            POST_COMPACTION_WINDOW_SIZE == 3
        )  # DEFAULT_WINDOW_SIZE
        snap = guard["snapshot"]()
        assert snap["armed"] is False

    def test_arm_and_snapshot(self) -> None:
        guard = create_post_compaction_loop_guard()
        guard["armPostCompaction"]()
        snap = guard["snapshot"]()
        assert snap["armed"] is True
        assert snap["remainingAttempts"] == 3

    def test_observe_no_loop(self) -> None:
        guard = create_post_compaction_loop_guard()
        guard["armPostCompaction"]()
        v = guard["observe"]({
            "toolName": "bash",
            "argsHash": "h1",
            "resultHash": "r1",
        })
        assert v["shouldAbort"] is False
        assert v["armed"] is True

    def test_observe_loop_persists(self) -> None:
        guard = create_post_compaction_loop_guard(
            config={"windowSize": 2}
        )
        guard["armPostCompaction"]()
        # Two identical observations
        # → should abort.
        v1 = guard["observe"]({
            "toolName": "bash",
            "argsHash": "h1",
            "resultHash": "r1",
        })
        assert v1["shouldAbort"] is False
        v2 = guard["observe"]({
            "toolName": "bash",
            "argsHash": "h1",
            "resultHash": "r1",
        })
        assert v2["shouldAbort"] is True
        assert v2["detector"] == "compaction_loop_persisted"
        assert v2["toolName"] == "bash"

    def test_observe_disabled(self) -> None:
        guard = create_post_compaction_loop_guard(
            options={"enabled": False}
        )
        guard["armPostCompaction"]()
        v = guard["observe"]({
            "toolName": "bash",
            "argsHash": "h1",
            "resultHash": "r1",
        })
        assert v["armed"] is False
        assert v["shouldAbort"] is False

    def test_observe_not_armed(self) -> None:
        guard = create_post_compaction_loop_guard()
        # Not armed → no observation.
        v = guard["observe"]({
            "toolName": "bash",
            "argsHash": "h1",
            "resultHash": "r1",
        })
        assert v["armed"] is False


class TestPostCompactionLoopPersistedError:
    def test_basic(self) -> None:
        err = PostCompactionLoopPersistedError(
            "loop", {"count": 3, "toolName": "bash"}
        )
        assert err.detector == "compaction_loop_persisted"
        assert err.count == 3
        assert err.tool_name == "bash"
        assert err.name == "PostCompactionLoopPersistedError"

    def test_from_verdict(self) -> None:
        verdict = {
            "shouldAbort": True,
            "armed": False,
            "remainingAttempts": 0,
            "detector": "compaction_loop_persisted",
            "count": 5,
            "toolName": "read",
            "message": "loop",
        }
        err = PostCompactionLoopPersistedError.from_verdict(verdict)
        assert err.count == 5
        assert err.tool_name == "read"


# ============================================================================
# compaction-duplicate-user-messages
# ============================================================================


class TestDedupeDuplicateUserMessagesForCompaction:
    def test_empty(self) -> None:
        assert dedupe_duplicate_user_messages_for_compaction([]) == []

    def test_no_duplicates(self) -> None:
        messages = [
            {
                "role": "user",
                "timestamp": 1000,
                "content": "first message",
            },
            {
                "role": "user",
                "timestamp": 2000,
                "content": "second message",
            },
        ]
        result = dedupe_duplicate_user_messages_for_compaction(
            messages
        )
        assert len(result) == 2

    def test_duplicate_within_window(self) -> None:
        # text must be >= MIN_DUPLICATE_USER_MESSAGE_CHARS (24) per OpenClaw
        messages = [
            {
                "role": "user",
                "timestamp": 1000,
                "content": "this is a duplicate user message text",
            },
            {
                "role": "user",
                "timestamp": 30_000,  # 29s later, within 60s window
                "content": "this is a duplicate user message text",
            },
        ]
        result = dedupe_duplicate_user_messages_for_compaction(
            messages
        )
        # First kept, second dropped.
        assert len(result) == 1

    def test_duplicate_outside_window(self) -> None:
        # text must be >= MIN_DUPLICATE_USER_MESSAGE_CHARS (24) per OpenClaw
        messages = [
            {
                "role": "user",
                "timestamp": 1000,
                "content": "this is a duplicate user message text",
            },
            {
                "role": "user",
                "timestamp": 100_000,  # 99s later, outside 60s window
                "content": "this is a duplicate user message text",
            },
        ]
        result = dedupe_duplicate_user_messages_for_compaction(
            messages
        )
        # Both kept.
        assert len(result) == 2

    def test_short_text_ignored(self) -> None:
        # Below the min char count.
        messages = [
            {"role": "user", "timestamp": 1000, "content": "hi"},
            {"role": "user", "timestamp": 2000, "content": "hi"},
        ]
        result = dedupe_duplicate_user_messages_for_compaction(
            messages
        )
        # Both kept (text too short).
        assert len(result) == 2

    def test_non_user_messages_pass_through(self) -> None:
        messages = [
            {"role": "user", "timestamp": 1000, "content": "a message"},
            {"role": "assistant", "timestamp": 2000, "content": "reply"},
        ]
        result = dedupe_duplicate_user_messages_for_compaction(
            messages
        )
        assert len(result) == 2


class TestCollectDuplicateUserMessageEntryIdsForCompaction:
    def test_collects_duplicate_ids(self) -> None:
        # text must be >= MIN_DUPLICATE_USER_MESSAGE_CHARS (24) per OpenClaw
        entries = [
            {
                "id": "a",
                "type": "message",
                "message": {
                    "role": "user",
                    "timestamp": 1000,
                    "content": "this is a duplicate user message text",
                },
            },
            {
                "id": "b",
                "type": "message",
                "message": {
                    "role": "user",
                    "timestamp": 30_000,
                    "content": "this is a duplicate user message text",
                },
            },
            {
                "id": "c",
                "type": "message",
                "message": {
                    "role": "user",
                    "timestamp": 200_000,
                    "content": "this is a duplicate user message text",
                },
            },
        ]
        ids = collect_duplicate_user_message_entry_ids_for_compaction(
            entries
        )
        # Only "b" is within the
        # window of "a".
        assert ids == {"b"}

    def test_empty(self) -> None:
        assert (
            collect_duplicate_user_message_entry_ids_for_compaction([])
            == set()
        )

    def test_skip_non_message(self) -> None:
        entries = [
            {"id": "a", "type": "compaction", "summary": "x"},
        ]
        ids = collect_duplicate_user_message_entry_ids_for_compaction(
            entries
        )
        assert ids == set()


# ============================================================================
# compact-runtime STUB
# ============================================================================


class TestCompactEmbeddedAgentSessionDirect:
    @pytest.mark.asyncio
    async def test_delegates_to_compact_runtime(self) -> None:
        # Runtime is loaded dynamically and delegates to compact module
        result = await compact_embedded_agent_session_direct({})
        assert isinstance(result, dict)
        assert "ok" in result


# ============================================================================
# Constants
# ============================================================================


class TestConstants:
    def test_default_window_ms(self) -> None:
        assert (
            DEFAULT_DUPLICATE_USER_MESSAGE_WINDOW_MS == 60_000
        )

    def test_min_chars(self) -> None:
        assert MIN_DUPLICATE_USER_MESSAGE_CHARS == 24

    def test_default_compaction_timeout(self) -> None:
        assert EMBEDDED_COMPACTION_TIMEOUT_MS == 180_000

    def test_deferred_reason(self) -> None:
        assert (
            DEFERRED_CONTEXT_ENGINE_COMPACTION_REASON
            == "deferred to background context-engine maintenance"
        )
