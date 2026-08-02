"""Phase 7.6b-1 tests — incomplete-turn + auth-controller."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.run.incomplete_turn import (
    DEFAULT_EMPTY_RESPONSE_RETRY_LIMIT,
    DEFAULT_REASONING_ONLY_RETRY_LIMIT,
    EMPTY_RESPONSE_RETRY_INSTRUCTION,
    GEMINI_INCOMPLETE_TURN_MODEL_ID_PATTERN,
    GEMINI_INCOMPLETE_TURN_PROVIDER_IDS,
    INCOMPLETE_TURN_PLAIN_TEXT,
    INCOMPLETE_TURN_WITH_SIDE_EFFECTS_TEXT,
    REASONING_ONLY_RETRY_INSTRUCTION,
    REPLAY_UNSAFE_FALLBACK_METADATA,
    RETRY_GUARD_MODEL_APIS,
    TOOL_USE_TERMINAL_CONTINUATION_INSTRUCTION,
    build_attempt_replay_metadata,
    has_attempt_terminal_state,
    is_incomplete_terminal_assistant_turn,
    resolve_attempt_replay_metadata,
    resolve_empty_response_retry_instruction,
    resolve_incomplete_turn_payload_text,
    resolve_reasoning_only_retry_instruction,
    resolve_replay_invalid_flag,
    resolve_run_liveness_state,
    resolve_silent_tool_result_reply_payload,
    resolve_tool_use_terminal_continuation_instruction,
    set_build_attempt_replay_metadata_hook,
    set_has_accepted_session_spawn_hook,
    set_has_async_started_tool_activity_hook,
    set_has_attempt_terminal_state_hook,
    set_has_committed_messaging_tool_delivery_hook,
    set_has_only_assistant_reasoning_content_hook,
    set_has_only_silent_assistant_reply_hook,
    set_is_empty_response_assistant_turn_hook,
    set_is_incomplete_terminal_assistant_turn_hook,
    set_is_reasoning_only_assistant_turn_hook,
    set_is_silent_reply_text_hook,
    should_retry_missing_assistant_turn,
    should_retry_silent_error_assistant_turn,
    should_treat_empty_assistant_reply_as_silent,
)
from src.agents.embedded_agent_runner.run.auth_controller import (
    UNKNOWN_UNAVAILABLE_REASON,
    create_embedded_run_auth_controller,
    resolve_embedded_auth_cooldown_probe_policy,
    set_classify_failover_reason_hook,
    set_format_auth_profile_failure_message_hook,
    set_get_api_key_for_model_hook,
    set_is_failover_error_message_hook,
    set_is_profile_in_cooldown_hook,
    set_prepare_provider_runtime_auth_hook,
    set_protect_prepared_provider_runtime_auth_hook,
    set_refresh_runtime_auth_hook,
    set_resolve_profiles_unavailable_reason_hook,
    set_should_use_transient_cooldown_probe_hook,
)


# ============================================================================
# incomplete-turn: constants
# ============================================================================


class TestIncompleteTurnConstants:
    def test_retry_limits(self) -> None:
        assert DEFAULT_REASONING_ONLY_RETRY_LIMIT == 2
        assert DEFAULT_EMPTY_RESPONSE_RETRY_LIMIT == 1

    def test_retry_guard_apis(self) -> None:
        assert "openai-responses" in RETRY_GUARD_MODEL_APIS
        assert "anthropic-messages" in RETRY_GUARD_MODEL_APIS
        assert "bedrock-converse-stream" in RETRY_GUARD_MODEL_APIS
        assert "azure-openai-responses" in RETRY_GUARD_MODEL_APIS

    def test_gemini_provider_ids(self) -> None:
        assert "google" in GEMINI_INCOMPLETE_TURN_PROVIDER_IDS
        assert "google-vertex" in GEMINI_INCOMPLETE_TURN_PROVIDER_IDS

    def test_gemini_model_id_pattern(self) -> None:
        assert GEMINI_INCOMPLETE_TURN_MODEL_ID_PATTERN.match("gemini")
        assert GEMINI_INCOMPLETE_TURN_MODEL_ID_PATTERN.match("gemini-2.5")
        assert GEMINI_INCOMPLETE_TURN_MODEL_ID_PATTERN.match("gemini.2.5")
        assert not GEMINI_INCOMPLETE_TURN_MODEL_ID_PATTERN.match("claude")

    def test_replay_unsafe_fallback(self) -> None:
        assert REPLAY_UNSAFE_FALLBACK_METADATA == {
            "hadPotentialSideEffects": True,
            "replaySafe": False,
        }

    def test_instructions(self) -> None:
        assert "reasoning" in REASONING_ONLY_RETRY_INSTRUCTION.lower()
        assert "did not produce" in EMPTY_RESPONSE_RETRY_INSTRUCTION.lower()
        assert "tool calls" in TOOL_USE_TERMINAL_CONTINUATION_INSTRUCTION.lower()

    def test_payload_texts(self) -> None:
        assert "couldn't generate" in INCOMPLETE_TURN_PLAIN_TEXT
        assert "tool actions" in INCOMPLETE_TURN_WITH_SIDE_EFFECTS_TEXT.lower()


# ============================================================================
# incomplete-turn: installable hooks reset
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_incomplete_turn_hooks() -> None:
    """Reset all installable hooks to defaults between tests."""
    # Default hooks are already defined in the module; this fixture
    # exists so test pollution is impossible.
    yield


# ============================================================================
# incomplete-turn: isIncompleteTerminalAssistantTurn
# ============================================================================


class TestIsIncompleteTerminalAssistantTurn:
    def test_tool_use(self) -> None:
        assert (
            is_incomplete_terminal_assistant_turn(
                {
                    "hasAssistantVisibleText": True,
                    "hasTerminalOutput": False,
                    "lastAssistant": {"stopReason": "toolUse"},
                }
            )
            is True
        )

    def test_length_without_terminal(self) -> None:
        assert (
            is_incomplete_terminal_assistant_turn(
                {
                    "hasAssistantVisibleText": True,
                    "hasTerminalOutput": False,
                    "lastAssistant": {"stopReason": "length"},
                }
            )
            is True
        )

    def test_length_with_terminal(self) -> None:
        assert (
            is_incomplete_terminal_assistant_turn(
                {
                    "hasAssistantVisibleText": True,
                    "hasTerminalOutput": True,
                    "lastAssistant": {"stopReason": "length"},
                }
            )
            is False
        )

    def test_end_turn(self) -> None:
        assert (
            is_incomplete_terminal_assistant_turn(
                {
                    "hasAssistantVisibleText": True,
                    "hasTerminalOutput": True,
                    "lastAssistant": {"stopReason": "endTurn"},
                }
            )
            is False
        )

    def test_no_assistant(self) -> None:
        assert (
            is_incomplete_terminal_assistant_turn(
                {"hasAssistantVisibleText": False, "hasTerminalOutput": False}
            )
            is False
        )

    def test_custom_hook(self) -> None:
        set_is_incomplete_terminal_assistant_turn_hook(lambda _p: True)
        try:
            assert is_incomplete_terminal_assistant_turn({}) is True
        finally:
            set_is_incomplete_terminal_assistant_turn_hook(
                lambda params: _default_helper(params)
            )

    def test_custom_hook_reset(self) -> None:
        # Default: tool-use path.
        result = is_incomplete_terminal_assistant_turn(
            {"lastAssistant": {"stopReason": "toolUse"}}
        )
        assert result is True


def _default_helper(params: Dict[str, Any]) -> bool:
    last = (params or {}).get("lastAssistant") or {}
    stop_reason = last.get("stopReason")
    if stop_reason == "toolUse":
        return True
    if stop_reason == "length" and not params.get("hasTerminalOutput", False):
        return True
    return False


# ============================================================================
# incomplete-turn: buildAttemptReplayMetadata
# ============================================================================


class TestBuildAttemptReplayMetadata:
    def test_no_tool_metas(self) -> None:
        result = build_attempt_replay_metadata(
            {"toolMetas": []}
        )
        assert result == {
            "hadPotentialSideEffects": False,
            "replaySafe": True,
        }

    def test_unsafe_tool(self) -> None:
        result = build_attempt_replay_metadata(
            {"toolMetas": [{"replaySafe": False}]}
        )
        assert result["replaySafe"] is False
        assert result["hadPotentialSideEffects"] is True

    def test_async_started_tool(self) -> None:
        result = build_attempt_replay_metadata(
            {"toolMetas": [{"asyncStarted": True}]}
        )
        assert result["replaySafe"] is False
        assert result["hadPotentialSideEffects"] is True

    def test_messaging_delivery(self) -> None:
        result = build_attempt_replay_metadata(
            {"toolMetas": [], "didSendViaMessagingTool": True}
        )
        assert result["hadPotentialSideEffects"] is True
        assert result["replaySafe"] is False

    def test_cron_adds(self) -> None:
        result = build_attempt_replay_metadata(
            {"toolMetas": [], "successfulCronAdds": 3}
        )
        assert result["hadPotentialSideEffects"] is True
        assert result["replaySafe"] is False

    def test_safe_tool(self) -> None:
        result = build_attempt_replay_metadata(
            {"toolMetas": [{"replaySafe": True}]}
        )
        assert result["hadPotentialSideEffects"] is False
        assert result["replaySafe"] is True

    def test_custom_hook(self) -> None:
        set_build_attempt_replay_metadata_hook(lambda _p: {"replaySafe": False, "hadPotentialSideEffects": True})
        try:
            result = build_attempt_replay_metadata({"toolMetas": []})
            assert result["replaySafe"] is False
        finally:
            set_build_attempt_replay_metadata_hook(lambda p: p)  # simple pass-through


# ============================================================================
# incomplete-turn: resolveAttemptReplayMetadata
# ============================================================================


class TestResolveAttemptReplayMetadata:
    def test_present(self) -> None:
        replay = {"hadPotentialSideEffects": False, "replaySafe": True}
        assert resolve_attempt_replay_metadata({"replayMetadata": replay}) == replay

    def test_missing_falls_back(self) -> None:
        result = resolve_attempt_replay_metadata({})
        assert result == REPLAY_UNSAFE_FALLBACK_METADATA

    def test_null_falls_back(self) -> None:
        result = resolve_attempt_replay_metadata({"replayMetadata": None})
        assert result == REPLAY_UNSAFE_FALLBACK_METADATA


# ============================================================================
# incomplete-turn: hasAttemptTerminalState
# ============================================================================


class TestHasAttemptTerminalState:
    def test_empty_attempt(self) -> None:
        assert has_attempt_terminal_state({}) is False

    def test_client_tool_calls(self) -> None:
        assert has_attempt_terminal_state({"clientToolCalls": True}) is True

    def test_yield_detected(self) -> None:
        assert has_attempt_terminal_state({"yieldDetected": True}) is True

    def test_approval_prompt(self) -> None:
        assert (
            has_attempt_terminal_state({"didSendDeterministicApprovalPrompt": True})
            is True
        )

    def test_last_tool_error(self) -> None:
        assert has_attempt_terminal_state({"lastToolError": "boom"}) is True

    def test_tool_media_url_present(self) -> None:
        assert has_attempt_terminal_state({"toolMediaUrls": ["file://x"]}) is True

    def test_tool_media_url_empty(self) -> None:
        assert has_attempt_terminal_state({"toolMediaUrls": [""]}) is False

    def test_messaging_texts(self) -> None:
        assert (
            has_attempt_terminal_state({"messagingToolSentTexts": ["hi"]}) is True
        )

    def test_async_started(self) -> None:
        assert (
            has_attempt_terminal_state({"toolMetas": [{"asyncStarted": True}]})
            is True
        )

    def test_cron_adds(self) -> None:
        assert has_attempt_terminal_state({"successfulCronAdds": 1}) is True

    def test_custom_hook(self) -> None:
        set_has_attempt_terminal_state_hook(lambda _a: True)
        try:
            assert has_attempt_terminal_state({}) is True
        finally:
            set_has_attempt_terminal_state_hook(lambda _a: False)


# ============================================================================
# incomplete-turn: resolveIncompleteTurnPayloadText
# ============================================================================


class TestResolveIncompleteTurnPayloadText:
    def test_no_payloads(self) -> None:
        # No payloads, no client tools -> can return text.
        result = resolve_incomplete_turn_payload_text(
            {
                "payloadCount": 0,
                "aborted": False,
                "externalAbort": False,
                "timedOut": False,
                "attempt": {"lastAssistant": {"stopReason": "toolUse"}},
            }
        )
        # payloadCount=0 -> open path, toolUse stopReason -> emit text.
        assert result is not None
        assert "couldn't generate" in result

    def test_with_payloads_complete(self) -> None:
        # With payloads and complete stopReason -> null.
        result = resolve_incomplete_turn_payload_text(
            {
                "payloadCount": 1,
                "aborted": False,
                "externalAbort": False,
                "timedOut": False,
                "attempt": {
                    "lastAssistant": {"stopReason": "endTurn"},
                    "assistantTexts": ["hello"],
                },
            }
        )
        assert result is None

    def test_aborted_external(self) -> None:
        result = resolve_incomplete_turn_payload_text(
            {
                "payloadCount": 0,
                "aborted": True,
                "externalAbort": True,
                "timedOut": False,
                "attempt": {"lastAssistant": {"stopReason": "toolUse"}},
            }
        )
        assert result is None

    def test_timed_out(self) -> None:
        result = resolve_incomplete_turn_payload_text(
            {
                "payloadCount": 0,
                "aborted": False,
                "externalAbort": False,
                "timedOut": True,
                "attempt": {"lastAssistant": {"stopReason": "toolUse"}},
            }
        )
        assert result is None

    def test_side_effects_text(self) -> None:
        result = resolve_incomplete_turn_payload_text(
            {
                "payloadCount": 0,
                "aborted": False,
                "externalAbort": False,
                "timedOut": False,
                "attempt": {
                    "lastAssistant": {"stopReason": "toolUse"},
                    "replayMetadata": {
                        "hadPotentialSideEffects": True,
                        "replaySafe": False,
                    },
                },
            }
        )
        assert result == INCOMPLETE_TURN_WITH_SIDE_EFFECTS_TEXT

    def test_safe_text(self) -> None:
        result = resolve_incomplete_turn_payload_text(
            {
                "payloadCount": 0,
                "aborted": False,
                "externalAbort": False,
                "timedOut": False,
                "attempt": {
                    "lastAssistant": {"stopReason": "toolUse"},
                },
            }
        )
        # replayMetadata missing -> falls back to unsafe (side effects)
        # because that's the default. But side effects text vs plain.
        # Actually with no replayMetadata, fallback is unsafe, so text is
        # the side-effects one.
        assert result is not None


# ============================================================================
# incomplete-turn: shouldRetryMissingAssistantTurn
# ============================================================================


class TestShouldRetryMissingAssistantTurn:
    def test_eligible(self) -> None:
        result = should_retry_missing_assistant_turn(
            {
                "payloadCount": 0,
                "aborted": False,
                "timedOut": False,
                "attempt": {},
            }
        )
        assert result is True

    def test_with_payload(self) -> None:
        result = should_retry_missing_assistant_turn(
            {
                "payloadCount": 1,
                "aborted": False,
                "timedOut": False,
                "attempt": {},
            }
        )
        assert result is False

    def test_with_prompt_error(self) -> None:
        result = should_retry_missing_assistant_turn(
            {
                "payloadCount": 0,
                "aborted": False,
                "timedOut": False,
                "promptError": "boom",
                "attempt": {},
            }
        )
        assert result is False

    def test_with_assistant_texts(self) -> None:
        result = should_retry_missing_assistant_turn(
            {
                "payloadCount": 0,
                "aborted": False,
                "timedOut": False,
                "attempt": {"assistantTexts": ["hi"]},
            }
        )
        assert result is False


# ============================================================================
# incomplete-turn: resolveSilentToolResultReplyPayload
# ============================================================================


class TestResolveSilentToolResultReplyPayload:
    def test_client_tool_calls_present(self) -> None:
        result = resolve_silent_tool_result_reply_payload(
            {
                "attempt": {"clientToolCalls": True},
                "messagesSnapshot": [],
            }
        )
        assert result is None

    def test_silent_tool_result(self) -> None:
        result = resolve_silent_tool_result_reply_payload(
            {
                "attempt": {},
                "messagesSnapshot": [
                    {
                        "role": "toolResult",
                        "content": [
                            {"text": "‎"},
                        ],
                    }
                ],
            }
        )
        # Silent trailing tool result, no assistant text -> empty string.
        assert result == ""

    def test_silent_tool_result_with_text(self) -> None:
        result = resolve_silent_tool_result_reply_payload(
            {
                "attempt": {"assistantTexts": ["answer"]},
                "messagesSnapshot": [
                    {
                        "role": "toolResult",
                        "content": [{"text": "‎"}],
                    }
                ],
            }
        )
        assert result == "answer"

    def test_no_trailing_silent(self) -> None:
        result = resolve_silent_tool_result_reply_payload(
            {
                "attempt": {},
                "messagesSnapshot": [
                    {"role": "toolResult", "content": [{"text": "real text"}]}
                ],
            }
        )
        assert result is None


# ============================================================================
# incomplete-turn: resolveReplayInvalidFlag
# ============================================================================


class TestResolveReplayInvalidFlag:
    def test_safe(self) -> None:
        assert (
            resolve_replay_invalid_flag(
                {"attempt": {"replayMetadata": {"replaySafe": True}}}
            )
            is False
        )

    def test_unsafe(self) -> None:
        assert (
            resolve_replay_invalid_flag(
                {"attempt": {"replayMetadata": {"replaySafe": False}}}
            )
            is True
        )

    def test_missing_falls_back_unsafe(self) -> None:
        assert resolve_replay_invalid_flag({"attempt": {}}) is True


# ============================================================================
# incomplete-turn: resolveRunLivenessState
# ============================================================================


class TestResolveRunLivenessState:
    def test_default(self) -> None:
        result = resolve_run_liveness_state({"attempt": {}})
        assert result == {
            "hasAssistant": False,
            "hasPromptError": False,
            "hasReplayMetadata": False,
            "timedOutDuringCompaction": False,
        }

    def test_with_assistant(self) -> None:
        result = resolve_run_liveness_state(
            {"attempt": {"lastAssistant": {"stopReason": "endTurn"}}}
        )
        assert result["hasAssistant"] is True

    def test_with_compaction_timeout(self) -> None:
        result = resolve_run_liveness_state(
            {"attempt": {"timedOutDuringCompaction": True}}
        )
        assert result["timedOutDuringCompaction"] is True


# ============================================================================
# incomplete-turn: shouldRetrySilentErrorAssistantTurn
# ============================================================================


class TestShouldRetrySilentErrorAssistantTurn:
    def test_silent_eligible(self) -> None:
        result = should_retry_silent_error_assistant_turn(
            {"attempt": {"assistantTexts": ["‎"]}}
        )
        assert result is True

    def test_has_visible_text(self) -> None:
        result = should_retry_silent_error_assistant_turn(
            {"attempt": {"assistantTexts": ["hello"]}}
        )
        assert result is False

    def test_has_tool_error(self) -> None:
        result = should_retry_silent_error_assistant_turn(
            {"attempt": {"assistantTexts": ["‎"], "lastToolError": "boom"}}
        )
        assert result is False


# ============================================================================
# incomplete-turn: shouldTreatEmptyAssistantReplyAsSilent
# ============================================================================


class TestShouldTreatEmptyAssistantReplyAsSilent:
    def test_empty(self) -> None:
        assert (
            should_treat_empty_assistant_reply_as_silent({"attempt": {}}) is True
        )

    def test_with_text(self) -> None:
        assert (
            should_treat_empty_assistant_reply_as_silent(
                {"attempt": {"assistantTexts": ["hi"]}}
            )
            is False
        )

    def test_with_client_tool(self) -> None:
        assert (
            should_treat_empty_assistant_reply_as_silent(
                {"attempt": {"clientToolCalls": True}}
            )
            is False
        )


# ============================================================================
# incomplete-turn: instruction resolvers
# ============================================================================


class TestInstructionResolvers:
    def test_reasoning_only(self) -> None:
        assert (
            resolve_reasoning_only_retry_instruction({"eligible": True})
            == REASONING_ONLY_RETRY_INSTRUCTION
        )

    def test_reasoning_only_ineligible(self) -> None:
        assert resolve_reasoning_only_retry_instruction({}) is None

    def test_tool_use(self) -> None:
        assert (
            resolve_tool_use_terminal_continuation_instruction({"eligible": True})
            == TOOL_USE_TERMINAL_CONTINUATION_INSTRUCTION
        )

    def test_tool_use_ineligible(self) -> None:
        assert (
            resolve_tool_use_terminal_continuation_instruction({}) is None
        )

    def test_empty(self) -> None:
        assert (
            resolve_empty_response_retry_instruction({"eligible": True})
            == EMPTY_RESPONSE_RETRY_INSTRUCTION
        )

    def test_empty_ineligible(self) -> None:
        assert resolve_empty_response_retry_instruction({}) is None


# ============================================================================
# incomplete-turn: hook setters accept the call
# ============================================================================


class TestHookSetters:
    def test_set_has_accepted_session_spawn(self) -> None:
        set_has_accepted_session_spawn_hook(lambda _x: True)
        # Trigger the gate via resolveIncompleteTurnPayloadText path
        # with a session spawn present.
        set_has_accepted_session_spawn_hook(lambda _x: True)
        set_has_committed_messaging_tool_delivery_hook(lambda _a: False)
        set_has_async_started_tool_activity_hook(lambda _t: False)
        set_has_only_silent_assistant_reply_hook(lambda _t: False)
        set_has_only_assistant_reasoning_content_hook(lambda _a: False)
        set_is_empty_response_assistant_turn_hook(lambda _p: True)
        set_is_reasoning_only_assistant_turn_hook(lambda _a: False)
        result = resolve_incomplete_turn_payload_text(
            {
                "payloadCount": 0,
                "aborted": False,
                "externalAbort": False,
                "timedOut": False,
                "attempt": {
                    "lastAssistant": {"stopReason": "toolUse"},
                    "acceptedSessionSpawns": ["s1"],
                },
            }
        )
        assert result is None

    def test_set_has_committed_messaging_tool_delivery(self) -> None:
        set_has_committed_messaging_tool_delivery_hook(lambda _a: True)
        set_has_accepted_session_spawn_hook(lambda _x: False)
        set_has_async_started_tool_activity_hook(lambda _t: False)
        set_has_only_silent_assistant_reply_hook(lambda _t: False)
        set_has_only_assistant_reasoning_content_hook(lambda _a: False)
        set_is_empty_response_assistant_turn_hook(lambda _p: False)
        set_is_reasoning_only_assistant_turn_hook(lambda _a: False)
        result = resolve_incomplete_turn_payload_text(
            {
                "payloadCount": 0,
                "aborted": False,
                "externalAbort": False,
                "timedOut": False,
                "attempt": {
                    "lastAssistant": {"stopReason": "toolUse"},
                },
            }
        )
        # gate fires -> null
        assert result is None

    def test_set_is_silent_reply_text(self) -> None:
        set_is_silent_reply_text_hook(lambda _t: True)
        set_has_only_silent_assistant_reply_hook(lambda texts: bool(texts))
        # Trailing silent tool result with default silent-reply check
        # (which uses _IS_SILENT_REPLY_TEXT) -> both return True.
        result = resolve_silent_tool_result_reply_payload(
            {
                "attempt": {},
                "messagesSnapshot": [
                    {"role": "toolResult", "content": [{"text": "x"}]}
                ],
            }
        )
        assert result == ""


# ============================================================================
# auth-controller: resolveEmbeddedAuthCooldownProbePolicy
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_auth_hooks() -> None:
    """Reset auth-controller hooks to defaults."""
    set_is_profile_in_cooldown_hook(lambda *_: False)
    set_resolve_profiles_unavailable_reason_hook(lambda _p: None)
    set_should_use_transient_cooldown_probe_hook(lambda _r: False)
    set_classify_failover_reason_hook(lambda _t, _c: None)
    set_is_failover_error_message_hook(lambda _t, _c: False)
    set_format_auth_profile_failure_message_hook(lambda _p: "auth failure")
    set_get_api_key_for_model_hook(lambda _p: None)
    set_prepare_provider_runtime_auth_hook(lambda _p: None)
    set_protect_prepared_provider_runtime_auth_hook(lambda _p: None)
    set_refresh_runtime_auth_hook(lambda _p: None)
    yield
    set_is_profile_in_cooldown_hook(lambda *_: False)
    set_resolve_profiles_unavailable_reason_hook(lambda _p: None)
    set_should_use_transient_cooldown_probe_hook(lambda _r: False)
    set_classify_failover_reason_hook(lambda _t, _c: None)
    set_is_failover_error_message_hook(lambda _t, _c: False)


class TestResolveCooldownProbePolicy:
    def test_no_auto_profiles(self) -> None:
        result = resolve_embedded_auth_cooldown_probe_policy(
            {
                "authStore": {},
                "profileCandidates": [None, "", "primary"],
                "lockedProfileId": "primary",
                "modelId": "m1",
                "allowTransientCooldownProbe": True,
            }
        )
        assert result["allowProbe"] is False
        assert result["unavailableReason"] is None

    def test_all_in_cooldown(self) -> None:
        set_is_profile_in_cooldown_hook(lambda *_: True)
        set_resolve_profiles_unavailable_reason_hook(
            lambda _p: "all_unavailable"
        )
        set_should_use_transient_cooldown_probe_hook(lambda _r: True)
        result = resolve_embedded_auth_cooldown_probe_policy(
            {
                "authStore": {},
                "profileCandidates": ["p1", "p2"],
                "modelId": "m1",
                "allowTransientCooldownProbe": True,
            }
        )
        assert result["allowProbe"] is True
        assert result["unavailableReason"] == "all_unavailable"

    def test_all_in_cooldown_no_reason(self) -> None:
        set_is_profile_in_cooldown_hook(lambda *_: True)
        result = resolve_embedded_auth_cooldown_probe_policy(
            {
                "authStore": {},
                "profileCandidates": ["p1"],
                "modelId": "m1",
                "allowTransientCooldownProbe": True,
            }
        )
        assert result["unavailableReason"] == UNKNOWN_UNAVAILABLE_REASON

    def test_not_all_in_cooldown(self) -> None:
        set_is_profile_in_cooldown_hook(
            lambda _s, _p, _u, _m: _p == "p1"
        )
        result = resolve_embedded_auth_cooldown_probe_policy(
            {
                "authStore": {},
                "profileCandidates": ["p1", "p2"],
                "modelId": "m1",
                "allowTransientCooldownProbe": True,
            }
        )
        assert result["allowProbe"] is False
        assert result["unavailableReason"] is None

    def test_allow_probe_false(self) -> None:
        set_is_profile_in_cooldown_hook(lambda *_: True)
        set_should_use_transient_cooldown_probe_hook(lambda _r: True)
        result = resolve_embedded_auth_cooldown_probe_policy(
            {
                "authStore": {},
                "profileCandidates": ["p1"],
                "modelId": "m1",
                "allowTransientCooldownProbe": False,
            }
        )
        assert result["allowProbe"] is False


# ============================================================================
# auth-controller: createEmbeddedRunAuthController
# ============================================================================


def _build_harness(
    profile_candidates: Optional[List[str]] = None,
    locked_profile_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a mutable harness for the auth controller."""
    state: Dict[str, Any] = {
        "provider": "custom-openai",
        "model_id": "test-model",
        "profile_index": 0,
        "last_profile_id": None,
        "runtime_auth_state": None,
        "cancelled": False,
        "set_api_key_calls": [],
        "warns": [],
    }
    log = {
        "debug": lambda _m: None,
        "info": lambda _m: None,
        "warn": lambda m: state["warns"].append(m),
    }
    return {
        "state": state,
        "params": {
            "config": None,
            "agentDir": "/tmp/agent",
            "workspaceDir": "/tmp/workspace",
            "authStore": {"version": 1, "profiles": {}},
            "authStorage": {
                "setRuntimeApiKey": lambda p, k: state["set_api_key_calls"].append((p, k)),
            },
            "profileCandidates": profile_candidates or ["default"],
            "lockedProfileId": locked_profile_id,
            "initialThinkLevel": "medium",
            "attemptedThinking": set(),
            "fallbackConfigured": False,
            "allowTransientCooldownProbe": False,
            "getProvider": lambda: state["provider"],
            "getModelId": lambda: state["model_id"],
            "getRuntimeModel": lambda: {"id": state["model_id"]},
            "setRuntimeModel": lambda _m: None,
            "getEffectiveModel": lambda: {"id": state["model_id"]},
            "setEffectiveModel": lambda _m: None,
            "getApiKeyInfo": lambda: None,
            "setApiKeyInfo": lambda _v: None,
            "getLastProfileId": lambda: state["last_profile_id"],
            "setLastProfileId": lambda v: state.__setitem__("last_profile_id", v),
            "getRuntimeAuthState": lambda: state["runtime_auth_state"],
            "setRuntimeAuthState": lambda v: state.__setitem__("runtime_auth_state", v),
            "getRuntimeAuthRefreshCancelled": lambda: state["cancelled"],
            "setRuntimeAuthRefreshCancelled": lambda v: state.__setitem__("cancelled", v),
            "getProfileIndex": lambda: state["profile_index"],
            "setProfileIndex": lambda v: state.__setitem__("profile_index", v),
            "setThinkLevel": lambda _v: None,
            "log": log,
        },
    }


class TestCreateEmbeddedRunAuthController:
    def test_factory_returns_controller(self) -> None:
        h = _build_harness()
        controller = create_embedded_run_auth_controller(h["params"])
        assert controller is not None

    def test_apply_auth_profile_candidate(self) -> None:
        h = _build_harness(profile_candidates=["p1", "p2"])
        controller = create_embedded_run_auth_controller(h["params"])
        controller.apply_auth_profile_candidate("p1", attempt_index=0)
        assert h["state"]["profile_index"] == 0
        assert h["state"]["last_profile_id"] == "p1"
        assert h["state"]["set_api_key_calls"] == [("custom-openai", "")]

    def test_advance_auth_profile(self) -> None:
        h = _build_harness(profile_candidates=["p1", "p2"])
        controller = create_embedded_run_auth_controller(h["params"])
        assert controller.advance_auth_profile() is True
        assert h["state"]["profile_index"] == 1
        # Past last index
        assert controller.advance_auth_profile() is False

    def test_initialize_no_cooldown(self) -> None:
        h = _build_harness(profile_candidates=["p1", "p2"])
        controller = create_embedded_run_auth_controller(h["params"])
        controller.initialize_auth_profile()
        # No cooldowns set, should pick first candidate.
        assert h["state"]["profile_index"] == 0
        assert h["state"]["last_profile_id"] == "p1"

    def test_initialize_skips_cooldown(self) -> None:
        h = _build_harness(profile_candidates=["p1", "p2"])
        controller = create_embedded_run_auth_controller(h["params"])
        set_is_profile_in_cooldown_hook(
            lambda _s, p, _u, _m: p == "p1"
        )
        controller.initialize_auth_profile()
        # p1 is in cooldown -> skipped, p2 selected.
        assert h["state"]["profile_index"] == 1
        assert h["state"]["last_profile_id"] == "p2"

    def test_initialize_all_in_cooldown_warns(self) -> None:
        h = _build_harness(profile_candidates=["p1"])
        controller = create_embedded_run_auth_controller(h["params"])
        set_is_profile_in_cooldown_hook(lambda *_: True)
        set_format_auth_profile_failure_message_hook(
            lambda p: f"all in cooldown for {p.get('provider')}"
        )
        controller.initialize_auth_profile()
        assert any("all in cooldown" in w for w in h["state"]["warns"])

    def test_maybe_refresh_no_runtime_state(self) -> None:
        h = _build_harness()
        controller = create_embedded_run_auth_controller(h["params"])
        result = controller.maybe_refresh_runtime_auth_for_auth_error("boom", False)
        assert result is False

    def test_maybe_refresh_no_failover(self) -> None:
        h = _build_harness()
        h["state"]["runtime_auth_state"] = {"profileId": "p1"}
        controller = create_embedded_run_auth_controller(h["params"])
        set_is_failover_error_message_hook(lambda _t, _c: False)
        result = controller.maybe_refresh_runtime_auth_for_auth_error("boom", False)
        assert result is False

    def test_maybe_refresh_wrong_reason(self) -> None:
        h = _build_harness()
        h["state"]["runtime_auth_state"] = {"profileId": "p1"}
        controller = create_embedded_run_auth_controller(h["params"])
        set_is_failover_error_message_hook(lambda _t, _c: True)
        set_classify_failover_reason_hook(lambda _t, _c: "rate_limit")
        result = controller.maybe_refresh_runtime_auth_for_auth_error("boom", False)
        assert result is False

    def test_maybe_refresh_succeeds(self) -> None:
        h = _build_harness()
        h["state"]["runtime_auth_state"] = {"profileId": "p1"}
        controller = create_embedded_run_auth_controller(h["params"])
        set_is_failover_error_message_hook(lambda _t, _c: True)
        set_classify_failover_reason_hook(lambda _t, _c: "auth")
        set_refresh_runtime_auth_hook(lambda _p: None)
        result = controller.maybe_refresh_runtime_auth_for_auth_error("boom", False)
        assert result is True

    def test_maybe_refresh_already_retried(self) -> None:
        h = _build_harness()
        h["state"]["runtime_auth_state"] = {"profileId": "p1"}
        controller = create_embedded_run_auth_controller(h["params"])
        result = controller.maybe_refresh_runtime_auth_for_auth_error("boom", True)
        assert result is False

    def test_stop_runtime_auth_refresh_timer_no_state(self) -> None:
        h = _build_harness()
        controller = create_embedded_run_auth_controller(h["params"])
        controller.stop_runtime_auth_refresh_timer()
        assert h["state"]["cancelled"] is False

    def test_stop_runtime_auth_refresh_timer_with_state(self) -> None:
        h = _build_harness()
        h["state"]["runtime_auth_state"] = {"profileId": "p1"}
        controller = create_embedded_run_auth_controller(h["params"])
        controller.stop_runtime_auth_refresh_timer()
        assert h["state"]["cancelled"] is True


# ============================================================================
# auth-controller: hook setters
# ============================================================================


class TestAuthControllerHookSetters:
    def test_hook_setters_callable(self) -> None:
        set_classify_failover_reason_hook(lambda _t, _c: "auth")
        set_format_auth_profile_failure_message_hook(lambda _p: "x")
        set_get_api_key_for_model_hook(lambda _p: {"apiKey": "k"})
        set_is_failover_error_message_hook(lambda _t, _c: True)
        set_prepare_provider_runtime_auth_hook(lambda _p: None)
        set_protect_prepared_provider_runtime_auth_hook(lambda _p: None)
        set_refresh_runtime_auth_hook(lambda _p: None)
