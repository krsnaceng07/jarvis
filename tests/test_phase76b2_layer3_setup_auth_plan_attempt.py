"""Phase 7.6b-2 tests — setup + auth-plan + attempt-result + attempt-execution-settle."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.run.setup import (
    AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE,
    AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE,
    DEFAULT_CONTEXT_TOKENS,
    DEFAULT_AGENT_RUNTIME_ID,
    OPENCLAW_AGENT_RUNTIME_ID,
    build_before_model_resolve_attachments,
    create_native_model_owned_runtime_model,
    resolve_agent_harness_run_admission_error,
    resolve_embedded_runtime_model_policy,
    resolve_hook_model_selection,
    resolve_native_model_owned_harness_id,
    set_evaluate_context_window_guard_hook,
    set_format_context_window_block_message_hook,
    set_format_context_window_warning_message_hook,
    set_is_agent_harness_session_key_hook,
    set_is_default_agent_runtime_id_hook,
    set_is_valid_agent_harness_session_store_entry_hook,
    set_normalize_optional_agent_runtime_id_hook,
    set_read_agent_model_context_tokens_hook,
    set_resolve_agent_harness_session_store_entry_error_hook,
    set_resolve_context_window_info_hook,
)
from src.agents.embedded_agent_runner.run.auth_plan import (
    OPENAI_PROVIDER_ID,
    prepare_embedded_run_auth_plan,
    set_create_prepared_runtime_model_materializer_hook,
    set_ensure_auth_profile_store_hook,
    set_ensure_auth_profile_store_without_external_hook,
    set_prepare_agent_runtime_auth_hook,
    set_provider_uses_credential_scoped_model_metadata_hook,
    set_resolve_external_cli_auth_overlay_scope_hook,
    set_resolve_model_async_hook,
    set_select_harness_for_prepared_attempts_hook,
)
from src.agents.embedded_agent_runner.run.attempt_result import (
    complete_embedded_attempt_result,
    set_build_agent_hook_context_channel_fields_hook,
    set_build_agent_hook_context_identity_fields_hook,
    set_finalize_embedded_attempt_hook,
    set_freeze_diagnostic_trace_context_hook,
    set_is_cloud_code_assist_format_error_hook,
    set_observe_replay_metadata_hook,
    set_record_stage_cache_trace_hook,
    set_replay_metadata_from_state_hook,
    set_run_llm_output_hook_hook,
    set_should_run_llm_output_hooks_for_attempt_hook,
)
from src.agents.embedded_agent_runner.run.attempt_execution_settle import (
    run_embedded_attempt_settled_phase,
    set_clear_active_embedded_run_hook,
    set_clear_attempt_timeout_timers_hook,
    set_cleanup_embedded_attempt_stream_execution_hook,
    set_detach_backend_hook,
    set_finalize_embedded_attempt_stream_phase_hook,
    set_remove_attempt_abort_signal_listener_hook,
    set_run_embedded_attempt_prompt_phase_hook,
    set_settle_requester_after_session_spawns_hook,
    set_unsubscribe_hook,
)


# ============================================================================
# setup: constants
# ============================================================================


class TestSetupConstants:
    def test_default_context_tokens(self) -> None:
        assert DEFAULT_CONTEXT_TOKENS == 200_000

    def test_openclaw_runtime_id(self) -> None:
        assert OPENCLAW_AGENT_RUNTIME_ID == "openclaw"

    def test_default_runtime_id(self) -> None:
        assert DEFAULT_AGENT_RUNTIME_ID == "default"

    def test_locked_message(self) -> None:
        assert "locked" in AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE

    def test_reserved_message(self) -> None:
        assert "reserved" in AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE


# ============================================================================
# setup: resolveAgentHarnessRunAdmissionError
# ============================================================================


class TestResolveAgentHarnessRunAdmissionError:
    def setup_method(self) -> None:
        set_is_agent_harness_session_key_hook(lambda _k: False)
        set_is_valid_agent_harness_session_store_entry_hook(lambda _k, _e: False)
        set_resolve_agent_harness_session_store_entry_error_hook(
            lambda _k, _e: None
        )
        set_normalize_optional_agent_runtime_id_hook(
            lambda v: v.strip() if isinstance(v, str) and v.strip() else None
        )
        set_is_default_agent_runtime_id_hook(
            lambda v: v == DEFAULT_AGENT_RUNTIME_ID
        )

    def test_no_session_key(self) -> None:
        assert resolve_agent_harness_run_admission_error({"sessionId": "s1"}) is None

    def test_no_entry(self) -> None:
        assert (
            resolve_agent_harness_run_admission_error(
                {"sessionId": "s1", "sessionKey": "k1"}
            )
            is None
        )

    def test_no_entry_with_reserved_key(self) -> None:
        set_is_agent_harness_session_key_hook(lambda _k: True)
        result = resolve_agent_harness_run_admission_error(
            {"sessionId": "s1", "sessionKey": "agent:k1"}
        )
        assert result == AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE

    def test_not_locked(self) -> None:
        result = resolve_agent_harness_run_admission_error(
            {
                "sessionId": "s1",
                "sessionKey": "k1",
                "entry": {"modelSelectionLocked": False},
            }
        )
        assert result is None

    def test_durable_entry_error(self) -> None:
        set_resolve_agent_harness_session_store_entry_error_hook(
            lambda _k, _e: "durable error"
        )
        result = resolve_agent_harness_run_admission_error(
            {
                "sessionId": "s1",
                "sessionKey": "k1",
                "entry": {
                    "modelSelectionLocked": True,
                    "sessionId": "s1",
                    "agentHarnessId": "openclaw",
                },
            }
        )
        assert result == "durable error"

    def test_matching_requested_and_durable(self) -> None:
        set_is_valid_agent_harness_session_store_entry_hook(
            lambda _k, _e: True
        )
        set_normalize_optional_agent_runtime_id_hook(
            lambda v: v.strip() if isinstance(v, str) and v.strip() else None
        )
        result = resolve_agent_harness_run_admission_error(
            {
                "sessionId": "s1",
                "sessionKey": "k1",
                "entry": {
                    "modelSelectionLocked": True,
                    "sessionId": "s1",
                    "agentHarnessId": "harness1",
                },
                "agentHarnessId": "harness1",
                "modelSelectionLocked": True,
            }
        )
        assert result is None

    def test_mismatch_durable_runtime(self) -> None:
        set_is_valid_agent_harness_session_store_entry_hook(
            lambda _k, _e: True
        )
        result = resolve_agent_harness_run_admission_error(
            {
                "sessionId": "s1",
                "sessionKey": "k1",
                "entry": {
                    "modelSelectionLocked": True,
                    "sessionId": "s2",  # different sessionId
                    "agentHarnessId": "harness1",
                },
                "agentHarnessId": "harness1",
                "modelSelectionLocked": True,
            }
        )
        assert result == AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE


# ============================================================================
# setup: resolveHookModelSelection
# ============================================================================


class TestResolveHookModelSelection:
    def setup_method(self) -> None:
        set_is_agent_harness_session_key_hook(lambda _k: False)
        set_is_valid_agent_harness_session_store_entry_hook(lambda _k, _e: False)
        set_resolve_agent_harness_session_store_entry_error_hook(
            lambda _k, _e: None
        )

    def test_locked_skips_hooks(self) -> None:
        result = _run_sync(
            resolve_hook_model_selection(
                {
                    "provider": "p1",
                    "modelId": "m1",
                    "modelSelectionLocked": True,
                    "hookContext": {},
                }
            )
        )
        assert result["provider"] == "p1"
        assert result["modelId"] == "m1"
        assert result["beforeAgentStartResult"] is None

    def test_no_hooks(self) -> None:
        result = _run_sync(
            resolve_hook_model_selection(
                {
                    "provider": "p1",
                    "modelId": "m1",
                    "hookContext": {},
                }
            )
        )
        assert result["provider"] == "p1"
        assert result["modelId"] == "m1"

    def test_with_before_model_resolve_override(self) -> None:
        class FakeRunner:
            def hasHooks(self, name: str) -> bool:
                return name == "before_model_resolve"

            async def runBeforeModelResolve(self, event, ctx):
                return {"providerOverride": "p2", "modelOverride": "m2"}

        result = _run_sync(
            resolve_hook_model_selection(
                {
                    "provider": "p1",
                    "modelId": "m1",
                    "hookRunner": FakeRunner(),
                    "hookContext": {},
                }
            )
        )
        assert result["provider"] == "p2"
        assert result["modelId"] == "m2"

    def test_with_before_agent_start_override(self) -> None:
        class FakeRunner:
            def hasHooks(self, name: str) -> bool:
                return name == "before_agent_start"

            async def runBeforeAgentStart(self, event, ctx):
                return {"providerOverride": "p2", "modelOverride": "m2"}

        result = _run_sync(
            resolve_hook_model_selection(
                {
                    "provider": "p1",
                    "modelId": "m1",
                    "hookRunner": FakeRunner(),
                    "hookContext": {},
                }
            )
        )
        assert result["provider"] == "p2"
        assert result["modelId"] == "m2"


# ============================================================================
# setup: buildBeforeModelResolveAttachments
# ============================================================================


class TestBuildBeforeModelResolveAttachments:
    def test_none(self) -> None:
        assert build_before_model_resolve_attachments(None) is None

    def test_empty(self) -> None:
        assert build_before_model_resolve_attachments([]) is None

    def test_with_images(self) -> None:
        result = build_before_model_resolve_attachments(
            [{"mimeType": "image/png"}, {"mimeType": "image/jpeg"}]
        )
        assert result == [
            {"kind": "image", "mimeType": "image/png"},
            {"kind": "image", "mimeType": "image/jpeg"},
        ]


# ============================================================================
# setup: resolveNativeModelOwnedHarnessId
# ============================================================================


class TestResolveNativeModelOwnedHarnessId:
    def setup_method(self) -> None:
        set_normalize_optional_agent_runtime_id_hook(
            lambda v: v.strip() if isinstance(v, str) and v.strip() else None
        )
        set_is_default_agent_runtime_id_hook(
            lambda v: v == DEFAULT_AGENT_RUNTIME_ID
        )

    def test_not_locked(self) -> None:
        assert (
            resolve_native_model_owned_harness_id(
                {"selectedHarnessId": "h1", "modelSelectionLocked": False}
            )
            is None
        )

    def test_default_runtime(self) -> None:
        assert (
            resolve_native_model_owned_harness_id(
                {
                    "agentHarnessId": "default",
                    "modelSelectionLocked": True,
                    "selectedHarnessId": "default",
                }
            )
            is None
        )

    def test_openclaw_runtime(self) -> None:
        assert (
            resolve_native_model_owned_harness_id(
                {
                    "agentHarnessId": OPENCLAW_AGENT_RUNTIME_ID,
                    "modelSelectionLocked": True,
                    "selectedHarnessId": OPENCLAW_AGENT_RUNTIME_ID,
                }
            )
            is None
        )

    def test_mismatch(self) -> None:
        assert (
            resolve_native_model_owned_harness_id(
                {
                    "agentHarnessId": "h1",
                    "modelSelectionLocked": True,
                    "selectedHarnessId": "h2",
                }
            )
            is None
        )

    def test_match(self) -> None:
        assert (
            resolve_native_model_owned_harness_id(
                {
                    "agentHarnessId": "h1",
                    "modelSelectionLocked": True,
                    "selectedHarnessId": "h1",
                }
            )
            == "h1"
        )


# ============================================================================
# setup: createNativeModelOwnedRuntimeModel
# ============================================================================


class TestCreateNativeModelOwnedRuntimeModel:
    def test_basic(self) -> None:
        result = create_native_model_owned_runtime_model(
            {"provider": "p1", "modelId": "m1"}
        )
        assert result["provider"] == "p1"
        assert result["id"] == "m1"
        assert result["name"] == "m1"
        assert result["contextWindow"] == DEFAULT_CONTEXT_TOKENS
        assert result["maxTokens"] == DEFAULT_CONTEXT_TOKENS
        assert result["api"] == "openai-responses"


# ============================================================================
# setup: resolveEmbeddedRuntimeModelPolicy
# ============================================================================


class TestResolveEmbeddedRuntimeModelPolicy:
    def setup_method(self) -> None:
        set_resolve_context_window_info_hook(
            lambda _p: {
                "tokens": DEFAULT_CONTEXT_TOKENS,
                "source": "default",
                "referenceTokens": DEFAULT_CONTEXT_TOKENS,
            }
        )
        set_evaluate_context_window_guard_hook(
            lambda _p: {"shouldBlock": False, "shouldWarn": False, "tokens": 0}
        )
        set_format_context_window_warning_message_hook(lambda _p: "")
        set_format_context_window_block_message_hook(
            lambda _p: "context window too small"
        )
        set_read_agent_model_context_tokens_hook(lambda _m: None)

    def test_native_model_owned_returns_runtime_model(self) -> None:
        result = resolve_embedded_runtime_model_policy(
            {
                "nativeModelOwned": True,
                "runtimeModel": {"id": "m1"},
            }
        )
        assert result["effectiveModel"] == {"id": "m1"}
        assert "contextWindowInfo" not in result

    def test_resolve_with_default_tokens(self) -> None:
        result = resolve_embedded_runtime_model_policy(
            {
                "nativeModelOwned": False,
                "provider": "p1",
                "modelId": "m1",
                "runtimeModel": {"contextWindow": 100_000, "id": "m1"},
                "cfg": None,
            }
        )
        # Default tokens = 200K, runtime contextWindow = 100K, so
        # 200K < 100K is False, so effective model is the runtime model.
        assert result["contextTokenBudget"] == DEFAULT_CONTEXT_TOKENS
        assert result["effectiveModel"]["id"] == "m1"

    def test_resolve_smaller_window(self) -> None:
        set_resolve_context_window_info_hook(
            lambda _p: {
                "tokens": 50_000,
                "source": "config",
                "referenceTokens": 100_000,
            }
        )
        result = resolve_embedded_runtime_model_policy(
            {
                "nativeModelOwned": False,
                "provider": "p1",
                "modelId": "m1",
                "runtimeModel": {"contextWindow": 100_000, "id": "m1"},
                "cfg": None,
            }
        )
        # 50K < 100K, so effective model is the runtime model with
        # contextWindow overridden to 50K.
        assert result["effectiveModel"]["contextWindow"] == 50_000

    def test_blocked_raises(self) -> None:
        set_evaluate_context_window_guard_hook(
            lambda _p: {"shouldBlock": True, "shouldWarn": False, "tokens": 1}
        )
        with pytest.raises(RuntimeError):
            resolve_embedded_runtime_model_policy(
                {
                    "nativeModelOwned": False,
                    "provider": "p1",
                    "modelId": "m1",
                    "runtimeModel": {"contextWindow": 100_000, "id": "m1"},
                    "cfg": None,
                }
            )


# ============================================================================
# auth-plan: constants
# ============================================================================


class TestAuthPlanConstants:
    def test_openai_provider_id(self) -> None:
        assert OPENAI_PROVIDER_ID == "openai"


# ============================================================================
# auth-plan: prepareEmbeddedRunAuthPlan
# ============================================================================


def _build_auth_plan_harness() -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "agent_harness": {"id": "openclaw", "authBootstrap": None},
        "effective_model": {"api": "openai-responses"},
        "runtime_model": {"id": "m1"},
    }
    return {
        "state": state,
        "params": {
            "runParams": {
                "config": None,
                "agentId": "a1",
                "authProfileId": None,
                "authProfileIdSource": None,
            },
            "provider": "openai",
            "modelId": "m1",
            "model": {"api": "openai-responses", "id": "m1"},
            "agentDir": "/tmp/agent",
            "workspaceDir": "/tmp/workspace",
            "authStorage": None,
            "modelRegistry": None,
            "getAgentHarness": lambda: state["agent_harness"],
            "setAgentHarness": lambda h: state.__setitem__("agent_harness", h),
            "getRuntimeModel": lambda: state["runtime_model"],
            "getEffectiveModel": lambda: state["effective_model"],
            "applyResolvedRuntimeModel": lambda _m: None,
            "selectHarnessForPreparedAttempts": lambda _m, _a: state["agent_harness"],
            "nativeModelOwned": False,
        },
    }


class TestPrepareEmbeddedRunAuthPlan:
    def setup_method(self) -> None:
        set_resolve_external_cli_auth_overlay_scope_hook(
            lambda _p: {"ignoreAutoPreferredProfile": False, "providerIds": None}
        )
        set_ensure_auth_profile_store_hook(
            lambda _p: {"version": 1, "profiles": {}}
        )
        set_ensure_auth_profile_store_without_external_hook(
            lambda _p: {"version": 1, "profiles": {}}
        )
        set_prepare_agent_runtime_auth_hook(
            lambda _p: {"attempts": [], "plan": {}}
        )
        set_provider_uses_credential_scoped_model_metadata_hook(
            lambda _p: False
        )
        set_create_prepared_runtime_model_materializer_hook(
            lambda _p: {
                "materialize": lambda _plan: None,
                "materializeUncached": lambda _plan: None,
            }
        )
        set_resolve_model_async_hook(lambda *a, **k: None)
        set_select_harness_for_prepared_attempts_hook(
            lambda _m, _a: {"id": "openclaw"}
        )

    def test_openai_routing(self) -> None:
        h = _build_auth_plan_harness()
        result = _run_sync(prepare_embedded_run_auth_plan(h["params"]))
        assert result["usesOpenAIAuthRouting"] is True
        assert result["lockedProfileId"] is None
        assert result["preferredProfileId"] is None
        assert result["preparedAuthAttempts"] == []
        assert result["providerUsesProfileScopedModelMetadata"] is False

    def test_external_profiles(self) -> None:
        h = _build_auth_plan_harness()
        h["params"]["provider"] = "anthropic"
        set_resolve_external_cli_auth_overlay_scope_hook(
            lambda _p: {
                "ignoreAutoPreferredProfile": False,
                "providerIds": ["anthropic"],
            }
        )
        result = _run_sync(prepare_embedded_run_auth_plan(h["params"]))
        assert result["usesOpenAIAuthRouting"] is False
        assert result["lockedProfileId"] is None

    def test_harness_mismatch_throws(self) -> None:
        h = _build_auth_plan_harness()
        h["params"]["provider"] = "anthropic"
        # Simulate a non-converging selector: first call returns a
        # different harness, second call returns yet another harness
        # so the post-replacement confirmation does not match the
        # just-set harness.
        call_count = {"n": 0}

        def _selector(_m: Any, _a: Any) -> Any:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"id": "harness-other"}
            return {"id": "harness-another"}

        set_select_harness_for_prepared_attempts_hook(_selector)
        with pytest.raises(RuntimeError):
            _run_sync(prepare_embedded_run_auth_plan(h["params"]))

    def test_user_locked_profile(self) -> None:
        h = _build_auth_plan_harness()
        h["params"]["runParams"]["authProfileId"] = "user-profile"
        h["params"]["runParams"]["authProfileIdSource"] = "user"
        result = _run_sync(prepare_embedded_run_auth_plan(h["params"]))
        assert result["lockedProfileId"] == "user-profile"


# ============================================================================
# attempt-result: completeEmbeddedAttemptResult
# ============================================================================


class TestCompleteEmbeddedAttemptResult:
    def setup_method(self) -> None:
        set_build_agent_hook_context_channel_fields_hook(lambda _a: {})
        set_build_agent_hook_context_identity_fields_hook(lambda _a: {})
        set_finalize_embedded_attempt_hook(lambda _p: None)
        set_freeze_diagnostic_trace_context_hook(lambda _t: None)
        set_is_cloud_code_assist_format_error_hook(lambda _e: False)
        set_observe_replay_metadata_hook(lambda _s, _m: None)
        set_record_stage_cache_trace_hook(lambda _p: None)
        set_replay_metadata_from_state_hook(lambda _s: {})
        set_run_llm_output_hook_hook(lambda _p: None)
        set_should_run_llm_output_hooks_for_attempt_hook(lambda _p: False)

    def test_basic(self) -> None:
        subscription = {
            "getReplayState": lambda: None,
            "didSendViaMessagingTool": lambda: False,
            "getMessagingToolSentTexts": lambda: [],
            "getMessagingToolSentMediaUrls": lambda: [],
            "getAcceptedSessionSpawns": lambda: [],
            "getSuccessfulCronAdds": lambda: 0,
            "toolMetas": [],
        }
        result = complete_embedded_attempt_result(
            {
                "attempt": {
                    "runId": "r1",
                    "sessionId": "s1",
                    "sessionKey": "k1",
                    "sessionFile": "/tmp/s.jsonl",
                    "agentId": "a1",
                    "provider": "p1",
                    "modelId": "m1",
                },
                "state": {"aborted": False},
                "subscription": subscription,
                "cache": {"observabilityEnabled": False},
                "clientToolCallSlots": [],
            }
        )
        assert result["runId"] == "r1"
        assert result["sessionId"] == "s1"
        assert result["toolMetas"] == []
        assert result["clientToolCalls"] == []
        assert result["aborted"] is False

    def test_completed_client_tool_calls(self) -> None:
        subscription = {
            "getReplayState": lambda: None,
            "didSendViaMessagingTool": lambda: False,
            "getMessagingToolSentTexts": lambda: [],
            "getMessagingToolSentMediaUrls": lambda: [],
            "getAcceptedSessionSpawns": lambda: [],
            "getSuccessfulCronAdds": lambda: 0,
            "toolMetas": [],
        }
        result = complete_embedded_attempt_result(
            {
                "attempt": {"runId": "r1", "sessionId": "s1"},
                "state": {},
                "subscription": subscription,
                "cache": {"observabilityEnabled": False},
                "clientToolCallSlots": [
                    {
                        "toolCallId": "t1",
                        "name": "n1",
                        "params": {"a": 1},
                        "completed": True,
                    },
                    {
                        "toolCallId": "t2",
                        "name": "n2",
                        "params": None,
                        "completed": False,
                    },
                ],
            }
        )
        assert result["clientToolCalls"] == [{"name": "n1", "params": {"a": 1}}]

    def test_tool_metas_normalization(self) -> None:
        subscription = {
            "getReplayState": lambda: None,
            "didSendViaMessagingTool": lambda: False,
            "getMessagingToolSentTexts": lambda: [],
            "getMessagingToolSentMediaUrls": lambda: [],
            "getAcceptedSessionSpawns": lambda: [],
            "getSuccessfulCronAdds": lambda: 0,
            "toolMetas": [
                {
                    "toolName": "read",
                    "meta": "abc",
                    "replaySafe": True,
                    "isError": True,
                    "asyncStarted": False,
                },
                {"toolName": "", "replaySafe": True},  # filtered out
                "not-a-dict",  # filtered out
            ],
        }
        result = complete_embedded_attempt_result(
            {
                "attempt": {"runId": "r1", "sessionId": "s1"},
                "state": {},
                "subscription": subscription,
                "cache": {"observabilityEnabled": False},
                "clientToolCallSlots": [],
            }
        )
        assert len(result["toolMetas"]) == 1
        assert result["toolMetas"][0]["toolName"] == "read"
        assert result["toolMetas"][0]["isError"] is True

    def test_finalize_hook_override(self) -> None:
        set_finalize_embedded_attempt_hook(
            lambda p: {"aborted": True, "extra": "value"}
        )
        subscription = {
            "getReplayState": lambda: None,
            "didSendViaMessagingTool": lambda: False,
            "getMessagingToolSentTexts": lambda: [],
            "getMessagingToolSentMediaUrls": lambda: [],
            "getAcceptedSessionSpawns": lambda: [],
            "getSuccessfulCronAdds": lambda: 0,
            "toolMetas": [],
        }
        result = complete_embedded_attempt_result(
            {
                "attempt": {"runId": "r1", "sessionId": "s1"},
                "state": {"aborted": False},
                "subscription": subscription,
                "cache": {"observabilityEnabled": False},
                "clientToolCallSlots": [],
            }
        )
        assert result["aborted"] is True
        assert result.get("extra") == "value"

    def test_replay_metadata(self) -> None:
        set_replay_metadata_from_state_hook(
            lambda _s: {"replaySafe": False, "hadPotentialSideEffects": True}
        )
        subscription = {
            "getReplayState": lambda: None,
            "didSendViaMessagingTool": lambda: False,
            "getMessagingToolSentTexts": lambda: [],
            "getMessagingToolSentMediaUrls": lambda: [],
            "getAcceptedSessionSpawns": lambda: [],
            "getSuccessfulCronAdds": lambda: 0,
            "toolMetas": [],
        }
        result = complete_embedded_attempt_result(
            {
                "attempt": {"runId": "r1", "sessionId": "s1"},
                "state": {},
                "subscription": subscription,
                "cache": {"observabilityEnabled": False},
                "clientToolCallSlots": [],
            }
        )
        assert result["replayMetadata"] == {
            "replaySafe": False,
            "hadPotentialSideEffects": True,
        }


# ============================================================================
# attempt-execution-settle: runEmbeddedAttemptSettledPhase
# ============================================================================


class TestRunEmbeddedAttemptSettledPhase:
    def setup_method(self) -> None:
        set_clear_active_embedded_run_hook(lambda _p: None)
        set_clear_attempt_timeout_timers_hook(lambda _p: None)
        set_cleanup_embedded_attempt_stream_execution_hook(lambda _p: None)
        set_detach_backend_hook(lambda _p: None)
        set_finalize_embedded_attempt_stream_phase_hook(
            lambda _p: asyncio_empty()
        )
        set_remove_attempt_abort_signal_listener_hook(lambda _p: None)
        set_run_embedded_attempt_prompt_phase_hook(lambda _p: asyncio_empty())
        set_settle_requester_after_session_spawns_hook(
            lambda _p: asyncio_empty()
        )
        set_unsubscribe_hook(lambda _p: None)

    def test_basic(self) -> None:
        result = _run_sync(
            run_embedded_attempt_settled_phase(
                {
                    "attempt": {
                        "runId": "r1",
                        "sessionId": "s1",
                        "sessionKey": "k1",
                        "sessionFile": "/tmp/s.jsonl",
                        "agentId": "a1",
                    },
                    "state": {"aborted": False},
                    "preparedStreamRuntime": {},
                }
            )
        )
        assert result["runId"] == "r1"
        assert result["sessionId"] == "s1"
        assert result["aborted"] is False

    def test_prompt_phase_returns_state(self) -> None:
        async def _phase(_p: Any) -> Any:
            return {"aborted": True, "promptError": "boom"}

        set_run_embedded_attempt_prompt_phase_hook(_phase)
        set_finalize_embedded_attempt_stream_phase_hook(
            lambda _p: asyncio_empty()
        )
        result = _run_sync(
            run_embedded_attempt_settled_phase(
                {
                    "attempt": {"runId": "r1", "sessionId": "s1"},
                    "state": {},
                    "preparedStreamRuntime": {},
                }
            )
        )
        assert result["aborted"] is True
        assert result["promptError"] == "boom"

    def test_settle_phase_returns_state(self) -> None:
        async def _settle(_p: Any) -> Any:
            return {"timedOut": True, "lastAssistant": {"stopReason": "endTurn"}}

        set_finalize_embedded_attempt_stream_phase_hook(_settle)
        result = _run_sync(
            run_embedded_attempt_settled_phase(
                {
                    "attempt": {"runId": "r1", "sessionId": "s1"},
                    "state": {},
                    "preparedStreamRuntime": {},
                }
            )
        )
        assert result["timedOut"] is True


# ============================================================================
# Helpers
# ============================================================================


def _run_sync(coro: Any) -> Any:
    import asyncio
    return asyncio.run(coro)


async def asyncio_empty() -> None:
    return None
