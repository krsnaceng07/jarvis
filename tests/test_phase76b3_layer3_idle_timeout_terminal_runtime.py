"""Phase 7.6b-3 tests — llm-idle-timeout + terminal-preparation + terminal-resolution + runtime-preparation."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.run.llm_idle_timeout import (
    CLOUD_LLM_FIRST_EVENT_TIMEOUT_MS,
    CRON_LLM_IDLE_TIMEOUT_MS,
    DEFAULT_LLM_IDLE_TIMEOUT_MS,
    LOCAL_LLM_FIRST_EVENT_TIMEOUT_MS,
    LOCAL_PROVIDER_AUTH_MARKERS,
    MAX_TIMER_TIMEOUT_MS,
    SELF_HOSTED_LLM_IDLE_TIMEOUT_MS,
    SELF_HOSTED_PROVIDER_ID_PREFIXES,
    has_local_provider_auth_marker,
    is_bare_provider_hostname_base_url,
    is_explicit_local_hostname_base_url,
    is_local_provider_base_url,
    is_ollama_cloud_model,
    is_self_hosted_provider_id,
    resolve_llm_first_event_timeout_ms,
    resolve_llm_idle_timeout_ms,
    resolve_runtime_model_locality,
    set_clamp_timer_timeout_ms_hook,
    set_create_stream_iterator_wrapper_hook,
    set_find_configured_provider_config_hook,
    set_finite_seconds_to_timer_safe_milliseconds_hook,
    set_get_last_tool_activity_ms_hook,
    set_on_llm_request_activity_hook,
    set_on_tool_activity_hook,
    stream_with_idle_timeout,
)
from src.agents.embedded_agent_runner.run.terminal_preparation import (
    prepare_embedded_run_terminal,
    set_build_embedded_run_payloads_hook,
    set_build_trace_tool_summary_hook,
    set_build_usage_agent_meta_fields_hook,
    set_copy_reply_payload_metadata_hook,
    set_merge_attempt_tool_media_payloads_hook,
    set_resolve_embedded_run_failure_signal_hook,
    set_resolve_final_assistant_raw_text_hook,
    set_resolve_final_assistant_visible_text_hook,
    set_resolve_reported_model_ref_hook,
)
from src.agents.embedded_agent_runner.run.terminal_resolution import (
    BEFORE_AGENT_FINALIZE_RETRY_PROMPT_PREFIX,
    COMPACTION_CONTINUATION_RETRY_INSTRUCTION,
    MAX_BEFORE_AGENT_FINALIZE_REVISIONS,
    MAX_MISSING_ASSISTANT_RETRIES,
    MAX_TOOL_USE_TERMINAL_CONTINUATIONS,
    copy_attempt_delivery_state,
    resolve_embedded_run_terminal,
    set_activate_internal_prompt_hook,
    set_freeze_diagnostic_trace_context_hook,
    set_mark_embedded_run_auth_profile_failure_hook,
    set_mark_embedded_run_auth_profile_success_hook,
    set_mark_embedded_run_replay_hook,
    set_report_embedded_run_successful_auth_binding_hook,
    set_resolve_embedded_run_failure_signal_hook as set_resolve_embedded_run_failure_signal_hook_tr,
)
from src.agents.embedded_agent_runner.run.runtime_preparation import (
    prepare_embedded_run_runtime,
    set_can_run_prepared_agent_runtime_auth_attempt_hook,
    set_create_embedded_run_stage_tracker_hook,
    set_format_embedded_run_stage_summary_hook,
    set_has_prepared_auth_attempt_model_metadata_hook,
    set_resolve_embedded_run_effective_model_hook,
    set_resolve_embedded_run_model_setup_hook,
    set_resolve_initial_think_level_hook,
    set_select_embedded_run_harness_for_prepared_attempts_hook,
    set_select_embedded_run_harness_hook,
)


# ============================================================================
# llm-idle-timeout: constants
# ============================================================================


class TestIdleTimeoutConstants:
    def test_defaults(self) -> None:
        assert DEFAULT_LLM_IDLE_TIMEOUT_MS == 120_000
        assert SELF_HOSTED_LLM_IDLE_TIMEOUT_MS == 300_000
        assert CLOUD_LLM_FIRST_EVENT_TIMEOUT_MS == 120_000
        assert LOCAL_LLM_FIRST_EVENT_TIMEOUT_MS == 300_000
        assert CRON_LLM_IDLE_TIMEOUT_MS == 60_000
        assert MAX_TIMER_TIMEOUT_MS == 2_147_483_647

    def test_local_provider_markers(self) -> None:
        assert "custom-local" in LOCAL_PROVIDER_AUTH_MARKERS
        assert "ollama-local" in LOCAL_PROVIDER_AUTH_MARKERS

    def test_self_hosted_prefixes(self) -> None:
        assert "ollama" in SELF_HOSTED_PROVIDER_ID_PREFIXES
        assert "lmstudio" in SELF_HOSTED_PROVIDER_ID_PREFIXES
        assert "vllm" in SELF_HOSTED_PROVIDER_ID_PREFIXES


# ============================================================================
# llm-idle-timeout: isLocalProviderBaseUrl
# ============================================================================


class TestIsLocalProviderBaseUrl:
    def test_localhost(self) -> None:
        assert is_local_provider_base_url("http://localhost:1234/v1") is True

    def test_loopback(self) -> None:
        assert is_local_provider_base_url("http://127.0.0.1:1234") is True
        assert is_local_provider_base_url("http://127.0.0.5:1234") is True

    def test_private(self) -> None:
        assert is_local_provider_base_url("http://10.0.0.1:1234") is True
        assert is_local_provider_base_url("http://192.168.1.1:1234") is True
        assert is_local_provider_base_url("http://172.16.0.1:1234") is True
        # Outside 172.16-31 -> not private
        assert is_local_provider_base_url("http://172.15.0.1:1234") is False
        assert is_local_provider_base_url("http://172.32.0.1:1234") is False

    def test_cgnat(self) -> None:
        assert is_local_provider_base_url("http://100.64.0.1:1234") is True
        assert is_local_provider_base_url("http://100.127.255.255:1234") is True
        assert is_local_provider_base_url("http://100.63.0.1:1234") is False
        assert is_local_provider_base_url("http://100.128.0.1:1234") is False

    def test_mdns(self) -> None:
        assert is_local_provider_base_url("http://printer.local") is True

    def test_ipv6_loopback(self) -> None:
        assert is_local_provider_base_url("http://[::1]:1234") is True
        assert is_local_provider_base_url("http://[::ffff:127.0.0.1]:1234") is True

    def test_ipv6_unique_local(self) -> None:
        assert is_local_provider_base_url("http://[fc00::1]:1234") is True
        assert is_local_provider_base_url("http://[fd00::1]:1234") is True

    def test_ipv6_link_local(self) -> None:
        assert is_local_provider_base_url("http://[fe80::1]:1234") is True

    def test_public(self) -> None:
        assert is_local_provider_base_url("https://api.openai.com/v1") is False
        assert is_local_provider_base_url("https://8.8.8.8:1234") is False

    def test_invalid(self) -> None:
        assert is_local_provider_base_url("") is False
        assert is_local_provider_base_url("not-a-url") is False


# ============================================================================
# llm-idle-timeout: isExplicitLocalHostnameBaseUrl
# ============================================================================


class TestIsExplicitLocalHostnameBaseUrl:
    def test_internal_aliases(self) -> None:
        assert is_explicit_local_hostname_base_url("http://docker.orb.internal:1234") is True
        assert is_explicit_local_hostname_base_url("http://host.docker.internal:1234") is True
        assert is_explicit_local_hostname_base_url("http://kubernetes.default:1234") is True

    def test_internal_tld(self) -> None:
        assert is_explicit_local_hostname_base_url("http://foo.internal:1234") is True
        assert is_explicit_local_hostname_base_url("http://foo.lan:1234") is True

    def test_public(self) -> None:
        assert is_explicit_local_hostname_base_url("https://api.openai.com") is False

    def test_invalid(self) -> None:
        assert is_explicit_local_hostname_base_url("") is False
        assert is_explicit_local_hostname_base_url("not-a-url") is False


# ============================================================================
# llm-idle-timeout: isBareProviderHostnameBaseUrl
# ============================================================================


class TestIsBareProviderHostnameBaseUrl:
    def test_bare(self) -> None:
        assert is_bare_provider_hostname_base_url("http://ollama:1234") is True
        assert is_bare_provider_hostname_base_url("http://lmstudio:1234") is True

    def test_dotted(self) -> None:
        assert is_bare_provider_hostname_base_url("http://api.openai.com") is False
        assert is_bare_provider_hostname_base_url("http://localhost") is False
        assert is_bare_provider_hostname_base_url("http://printer.local") is False

    def test_invalid(self) -> None:
        assert is_bare_provider_hostname_base_url("") is False
        assert is_bare_provider_hostname_base_url("not-a-url") is False


# ============================================================================
# llm-idle-timeout: isSelfHostedProviderId
# ============================================================================


class TestIsSelfHostedProviderId:
    def test_match(self) -> None:
        assert is_self_hosted_provider_id("ollama-local") is True
        assert is_self_hosted_provider_id("vllm") is True
        assert is_self_hosted_provider_id("lmstudio") is True

    def test_no_match(self) -> None:
        assert is_self_hosted_provider_id("openai") is False
        assert is_self_hosted_provider_id("anthropic") is False
        assert is_self_hosted_provider_id("") is False
        assert is_self_hosted_provider_id(None) is False  # type: ignore[arg-type]


# ============================================================================
# llm-idle-timeout: hasLocalProviderAuthMarker
# ============================================================================


class TestHasLocalProviderAuthMarker:
    def test_match(self) -> None:
        assert has_local_provider_auth_marker("Bearer custom-local-key") is True

    def test_no_match(self) -> None:
        assert has_local_provider_auth_marker("sk-abc") is False
        assert has_local_provider_auth_marker("") is False
        assert has_local_provider_auth_marker(None) is False  # type: ignore[arg-type]


# ============================================================================
# llm-idle-timeout: isOllamaCloudModel
# ============================================================================


class TestIsOllamaCloudModel:
    def test_ollama_cloud(self) -> None:
        assert is_ollama_cloud_model({"provider": "ollama", "id": "cloud-llama"}) is True
        assert is_ollama_cloud_model({"provider": "ollama-local", "id": "cloud-mistral"}) is True

    def test_ollama_local(self) -> None:
        assert is_ollama_cloud_model({"provider": "ollama", "id": "llama3"}) is False

    def test_non_ollama(self) -> None:
        assert is_ollama_cloud_model({"provider": "openai", "id": "gpt-4"}) is False
        assert is_ollama_cloud_model({}) is False
        assert is_ollama_cloud_model(None) is False  # type: ignore[arg-type]


# ============================================================================
# llm-idle-timeout: resolveRuntimeModelLocality
# ============================================================================


class TestResolveRuntimeModelLocality:
    def setup_method(self) -> None:
        set_find_configured_provider_config_hook(
            lambda _c, _p: None
        )

    def test_cloud(self) -> None:
        result = resolve_runtime_model_locality(
            {"model": {"provider": "openai", "baseUrl": "https://api.openai.com"}}
        )
        assert result == "cloud"

    def test_local_auth_marker(self) -> None:
        result = resolve_runtime_model_locality(
            {"model": {"provider": "openai", "apiKey": "custom-local-key"}}
        )
        assert result == "local"

    def test_self_hosted_provider(self) -> None:
        result = resolve_runtime_model_locality(
            {"model": {"provider": "ollama", "baseUrl": "https://api.ollama.com"}}
        )
        assert result == "self-hosted"

    def test_ollama_cloud(self) -> None:
        result = resolve_runtime_model_locality(
            {"model": {"provider": "ollama", "id": "cloud-model"}}
        )
        assert result == "cloud"

    def test_local_url(self) -> None:
        result = resolve_runtime_model_locality(
            {"model": {"provider": "openai", "baseUrl": "http://localhost:1234"}}
        )
        assert result == "local"

    def test_internal_url(self) -> None:
        result = resolve_runtime_model_locality(
            {"model": {"provider": "openai", "baseUrl": "http://foo.internal:1234"}}
        )
        assert result == "local"

    def test_provider_config_local(self) -> None:
        set_find_configured_provider_config_hook(
            lambda _c, p: {"localService": True} if p == "p1" else None
        )
        result = resolve_runtime_model_locality(
            {"model": {"provider": "p1", "baseUrl": "https://example.com"}, "config": {}}
        )
        assert result == "local"


# ============================================================================
# llm-idle-timeout: resolveLlmIdleTimeoutMs
# ============================================================================


class TestResolveLlmIdleTimeoutMs:
    def test_default(self) -> None:
        result = resolve_llm_idle_timeout_ms(
            {"model": {"provider": "openai", "baseUrl": "https://api.openai.com"}}
        )
        assert result == DEFAULT_LLM_IDLE_TIMEOUT_MS

    def test_cron(self) -> None:
        result = resolve_llm_idle_timeout_ms(
            {
                "model": {"provider": "openai", "baseUrl": "https://api.openai.com"},
                "trigger": "cron",
            }
        )
        assert result == CRON_LLM_IDLE_TIMEOUT_MS

    def test_local(self) -> None:
        result = resolve_llm_idle_timeout_ms(
            {"model": {"provider": "ollama", "baseUrl": "http://localhost:1234"}}
        )
        assert result == SELF_HOSTED_LLM_IDLE_TIMEOUT_MS

    def test_configured(self) -> None:
        result = resolve_llm_idle_timeout_ms(
            {
                "model": {"provider": "openai", "baseUrl": "https://api.openai.com"},
                "config": {"llm": {"idleTimeoutMs": 60_000}},
            }
        )
        assert result == 60_000


# ============================================================================
# llm-idle-timeout: resolveLlmFirstEventTimeoutMs
# ============================================================================


class TestResolveLlmFirstEventTimeoutMs:
    def test_cloud(self) -> None:
        result = resolve_llm_first_event_timeout_ms(
            {"model": {"provider": "openai", "baseUrl": "https://api.openai.com"}}
        )
        assert result == CLOUD_LLM_FIRST_EVENT_TIMEOUT_MS

    def test_local(self) -> None:
        result = resolve_llm_first_event_timeout_ms(
            {"model": {"provider": "ollama", "baseUrl": "http://localhost:1234"}}
        )
        assert result == LOCAL_LLM_FIRST_EVENT_TIMEOUT_MS


# ============================================================================
# llm-idle-timeout: streamWithIdleTimeout
# ============================================================================


class TestStreamWithIdleTimeout:
    def test_delegates_to_hook(self) -> None:
        captured: Dict[str, Any] = {}

        def _hook(p: Dict[str, Any]) -> Any:
            captured.update(p)
            return {"wrapped": True}

        set_create_stream_iterator_wrapper_hook(_hook)
        try:
            result = asyncio.run(
                stream_with_idle_timeout(
                    {
                        "model": {"provider": "openai", "baseUrl": "https://api.openai.com"},
                        "stream": None,
                    }
                )
            )
            assert result == {"wrapped": True}
            assert captured["idleTimeoutMs"] == DEFAULT_LLM_IDLE_TIMEOUT_MS
            assert captured["firstEventTimeoutMs"] == CLOUD_LLM_FIRST_EVENT_TIMEOUT_MS
        finally:
            set_create_stream_iterator_wrapper_hook(lambda _p: None)


# ============================================================================
# llm-idle-timeout: hook setters
# ============================================================================


class TestIdleTimeoutHookSetters:
    def test_setters(self) -> None:
        set_clamp_timer_timeout_ms_hook(lambda ms: ms)
        set_finite_seconds_to_timer_safe_milliseconds_hook(lambda s: int(s))
        set_get_last_tool_activity_ms_hook(lambda: 0)
        set_on_llm_request_activity_hook(lambda _cb: None)
        set_on_tool_activity_hook(lambda _cb: None)


# ============================================================================
# terminal-preparation
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_terminal_hooks() -> None:
    set_build_embedded_run_payloads_hook(lambda _p: [])
    set_build_trace_tool_summary_hook(lambda _a: {})
    set_build_usage_agent_meta_fields_hook(lambda _p: {})
    set_copy_reply_payload_metadata_hook(lambda _a, _b: None)
    set_merge_attempt_tool_media_payloads_hook(
        lambda payloads, _a: list(payloads or [])
    )
    set_resolve_embedded_run_failure_signal_hook(lambda _p: None)
    set_resolve_final_assistant_raw_text_hook(lambda _p: None)
    set_resolve_final_assistant_visible_text_hook(lambda _p: None)
    set_resolve_reported_model_ref_hook(
        lambda p: {"provider": p.get("provider") or "", "model": p.get("model") or ""}
    )
    yield
    set_build_embedded_run_payloads_hook(lambda _p: [])
    set_build_trace_tool_summary_hook(lambda _a: {})
    set_build_usage_agent_meta_fields_hook(lambda _p: {})
    set_copy_reply_payload_metadata_hook(lambda _a, _b: None)
    set_merge_attempt_tool_media_payloads_hook(
        lambda payloads, _a: list(payloads or [])
    )
    set_resolve_embedded_run_failure_signal_hook(lambda _p: None)
    set_resolve_final_assistant_raw_text_hook(lambda _p: None)
    set_resolve_final_assistant_visible_text_hook(lambda _p: None)
    set_resolve_reported_model_ref_hook(
        lambda p: {"provider": p.get("provider") or "", "model": p.get("model") or ""}
    )


class TestPrepareEmbeddedRunTerminal:
    def test_basic(self) -> None:
        result = prepare_embedded_run_terminal(
            {
                "runParams": {"toolResultFormat": "default"},
                "attempt": {"sessionId": "s1"},
                "provider": "p1",
                "model": "m1",
                "authProfileStore": {"version": 1, "profiles": {}},
                "sessionIdUsed": "s1",
                "outerContextTokenMeta": {},
                "usageAccumulator": {},
                "contextRecoveryState": {},
                "resolvedToolResultFormat": "default",
                "terminalInterrupted": False,
                "terminalTimedOut": False,
                "timedOutDuringCompaction": False,
                "timedOutDuringToolExecution": False,
            }
        )
        assert result["agentMeta"]["provider"] == "p1"
        assert result["agentMeta"]["model"] == "m1"
        assert result["reportedModelRef"] == {"provider": "p1", "model": "m1"}
        assert result["payloads"] == []
        assert result["timedOutDuringPrompt"] is False
        assert result["hasSuccessfulFinalAssistantAfterPromptTimeout"] is False

    def test_timed_out_during_prompt(self) -> None:
        result = prepare_embedded_run_terminal(
            {
                "runParams": {"toolResultFormat": "default"},
                "attempt": {"sessionId": "s1"},
                "provider": "p1",
                "model": "m1",
                "authProfileStore": {},
                "sessionIdUsed": "s1",
                "outerContextTokenMeta": {},
                "usageAccumulator": {},
                "contextRecoveryState": {},
                "resolvedToolResultFormat": "default",
                "terminalInterrupted": False,
                "terminalTimedOut": True,
                "timedOutDuringCompaction": False,
                "timedOutDuringToolExecution": False,
            }
        )
        assert result["timedOutDuringPrompt"] is True

    def test_timed_out_during_compaction_excluded(self) -> None:
        result = prepare_embedded_run_terminal(
            {
                "runParams": {"toolResultFormat": "default"},
                "attempt": {"sessionId": "s1"},
                "provider": "p1",
                "model": "m1",
                "authProfileStore": {},
                "sessionIdUsed": "s1",
                "outerContextTokenMeta": {},
                "usageAccumulator": {},
                "contextRecoveryState": {},
                "resolvedToolResultFormat": "default",
                "terminalInterrupted": False,
                "terminalTimedOut": True,
                "timedOutDuringCompaction": True,
                "timedOutDuringToolExecution": False,
            }
        )
        assert result["timedOutDuringPrompt"] is False

    def test_payloads_built(self) -> None:
        set_build_embedded_run_payloads_hook(
            lambda _p: [{"text": "hello"}]
        )
        set_merge_attempt_tool_media_payloads_hook(
            lambda payloads, _a: payloads + [{"media": "url"}]
        )
        result = prepare_embedded_run_terminal(
            {
                "runParams": {"toolResultFormat": "default"},
                "attempt": {"sessionId": "s1"},
                "provider": "p1",
                "model": "m1",
                "authProfileStore": {},
                "sessionIdUsed": "s1",
                "outerContextTokenMeta": {},
                "usageAccumulator": {},
                "contextRecoveryState": {},
                "resolvedToolResultFormat": "default",
                "terminalInterrupted": False,
                "terminalTimedOut": False,
                "timedOutDuringCompaction": False,
                "timedOutDuringToolExecution": False,
            }
        )
        assert result["payloads"] == [{"text": "hello"}]
        assert result["payloadsWithToolMedia"] == [
            {"text": "hello"},
            {"media": "url"},
        ]

    def test_final_assistant_text(self) -> None:
        set_resolve_final_assistant_visible_text_hook(lambda _p: "hello world")
        result = prepare_embedded_run_terminal(
            {
                "runParams": {"toolResultFormat": "default"},
                "attempt": {"sessionId": "s1"},
                "provider": "p1",
                "model": "m1",
                "authProfileStore": {},
                "sessionIdUsed": "s1",
                "outerContextTokenMeta": {},
                "usageAccumulator": {},
                "contextRecoveryState": {},
                "resolvedToolResultFormat": "default",
                "terminalInterrupted": False,
                "terminalTimedOut": False,
                "timedOutDuringCompaction": False,
                "timedOutDuringToolExecution": False,
            }
        )
        assert result["finalAssistantVisibleText"] == "hello world"
        assert result["hasPartialAssistantTextAfterPromptTimeout"] is True

    def test_failure_signal(self) -> None:
        set_resolve_embedded_run_failure_signal_hook(lambda _p: "fatal")
        result = prepare_embedded_run_terminal(
            {
                "runParams": {"toolResultFormat": "default"},
                "attempt": {"sessionId": "s1"},
                "provider": "p1",
                "model": "m1",
                "authProfileStore": {},
                "sessionIdUsed": "s1",
                "outerContextTokenMeta": {},
                "usageAccumulator": {},
                "contextRecoveryState": {},
                "resolvedToolResultFormat": "default",
                "terminalInterrupted": False,
                "terminalTimedOut": False,
                "timedOutDuringCompaction": False,
                "timedOutDuringToolExecution": False,
            }
        )
        assert result["failureSignal"] == "fatal"


# ============================================================================
# terminal-resolution
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_terminal_resolution_hooks() -> None:
    set_activate_internal_prompt_hook(lambda _p, _b: None)
    set_freeze_diagnostic_trace_context_hook(lambda _t: None)
    set_mark_embedded_run_auth_profile_failure_hook(lambda _p: asyncio.sleep(0))
    set_mark_embedded_run_auth_profile_success_hook(lambda _p: None)
    set_mark_embedded_run_replay_hook(lambda _p: None)
    set_report_embedded_run_successful_auth_binding_hook(lambda _p: None)
    set_resolve_embedded_run_failure_signal_hook_tr(lambda _p: None)
    yield
    set_activate_internal_prompt_hook(lambda _p, _b: None)
    set_freeze_diagnostic_trace_context_hook(lambda _t: None)
    set_mark_embedded_run_auth_profile_failure_hook(lambda _p: asyncio.sleep(0))
    set_mark_embedded_run_auth_profile_success_hook(lambda _p: None)
    set_mark_embedded_run_replay_hook(lambda _p: None)
    set_report_embedded_run_successful_auth_binding_hook(lambda _p: None)
    set_resolve_embedded_run_failure_signal_hook_tr(lambda _p: None)


class TestTerminalResolutionConstants:
    def test_constants(self) -> None:
        assert MAX_MISSING_ASSISTANT_RETRIES == 1
        assert MAX_TOOL_USE_TERMINAL_CONTINUATIONS == 1
        assert MAX_BEFORE_AGENT_FINALIZE_REVISIONS == 1
        assert "compacted" in COMPACTION_CONTINUATION_RETRY_INSTRUCTION.lower()
        assert "revision" in BEFORE_AGENT_FINALIZE_RETRY_PROMPT_PREFIX.lower()


class TestCopyAttemptDeliveryState:
    def test_basic(self) -> None:
        attempt: Dict[str, Any] = {
            "toolMetas": [{"toolName": "read"}],
            "didSendViaMessagingTool": True,
            "messagingToolSentTexts": ["hi"],
            "messagingToolSentMediaUrls": ["url"],
            "messagingToolSentTargets": ["t1"],
            "successfulCronAdds": 1,
            "messagingToolSourceReplyPayloads": [{"text": "r"}],
            "didDeliverSourceReplyViaMessageTool": True,
        }
        result = copy_attempt_delivery_state(attempt)
        assert result["toolMetas"] == [{"toolName": "read"}]
        assert result["didSendViaMessagingTool"] is True
        assert result["messagingToolSentTexts"] == ["hi"]
        assert result["successfulCronAdds"] == 1

    def test_empty(self) -> None:
        # OpenClaw always returns the shape with default-empty fields;
        # the test just confirms the call doesn't blow up on empty.
        result = copy_attempt_delivery_state({})
        assert result["toolMetas"] == []
        assert result["didSendViaMessagingTool"] is None
        assert result["successfulCronAdds"] is None


class TestResolveEmbeddedRunTerminal:
    def test_basic_complete(self) -> None:
        result = asyncio.run(
            resolve_embedded_run_terminal(
                {
                    "runParams": {"sessionId": "s1"},
                    "retryState": {},
                    "attempt": {
                        "runId": "r1",
                        "sessionId": "s1",
                        "sessionKey": "k1",
                        "sessionFile": "/tmp/s.jsonl",
                    },
                    "agentMeta": {"provider": "p1", "model": "m1"},
                    "payloadsWithToolMedia": [{"text": "hi"}],
                    "attemptToolSummary": {},
                    "maxReasoningOnlyRetryAttempts": 0,
                    "maxEmptyResponseRetryAttempts": 0,
                    "attemptCompactionCount": 0,
                    "terminalAborted": False,
                    "terminalTimedOut": False,
                    "externalAbort": False,
                    "startedAtMs": 0,
                    "provider": "p1",
                    "modelId": "m1",
                    "authProfileId": "ap1",
                    "profileFailureStore": {"version": 1, "profiles": {}},
                }
            )
        )
        assert result["action"] == "complete"
        assert result["result"]["runId"] == "r1"
        assert result["result"]["agentMeta"] == {"provider": "p1", "model": "m1"}
        assert result["result"]["aborted"] is False
        assert result["result"]["timedOut"] is False

    def test_aborted(self) -> None:
        result = asyncio.run(
            resolve_embedded_run_terminal(
                {
                    "runParams": {},
                    "retryState": {},
                    "attempt": {"sessionId": "s1"},
                    "agentMeta": {},
                    "payloadsWithToolMedia": [],
                    "attemptToolSummary": {},
                    "maxReasoningOnlyRetryAttempts": 0,
                    "maxEmptyResponseRetryAttempts": 0,
                    "attemptCompactionCount": 0,
                    "terminalAborted": True,
                    "terminalTimedOut": False,
                    "externalAbort": False,
                    "startedAtMs": 0,
                    "provider": "p1",
                    "modelId": "m1",
                }
            )
        )
        assert result["action"] == "complete"
        assert result["result"]["aborted"] is True

    def test_auth_profile_success_marked(self) -> None:
        captured: List[Dict[str, Any]] = []

        def _hook(p: Dict[str, Any]) -> None:
            captured.append(p)

        set_mark_embedded_run_auth_profile_success_hook(_hook)
        result = asyncio.run(
            resolve_embedded_run_terminal(
                {
                    "runParams": {},
                    "retryState": {},
                    "attempt": {"sessionId": "s1"},
                    "agentMeta": {},
                    "payloadsWithToolMedia": [],
                    "attemptToolSummary": {},
                    "maxReasoningOnlyRetryAttempts": 0,
                    "maxEmptyResponseRetryAttempts": 0,
                    "attemptCompactionCount": 0,
                    "terminalAborted": False,
                    "terminalTimedOut": False,
                    "externalAbort": False,
                    "startedAtMs": 0,
                    "provider": "p1",
                    "modelId": "m1",
                    "authProfileId": "ap1",
                }
            )
        )
        assert result["action"] == "complete"
        assert len(captured) == 1
        assert captured[0]["provider"] == "p1"
        assert captured[0]["modelId"] == "m1"
        assert captured[0]["authProfileId"] == "ap1"

    def test_auth_profile_success_not_marked_on_error(self) -> None:
        captured: List[Dict[str, Any]] = []

        def _hook(p: Dict[str, Any]) -> None:
            captured.append(p)

        set_mark_embedded_run_auth_profile_success_hook(_hook)
        result = asyncio.run(
            resolve_embedded_run_terminal(
                {
                    "runParams": {},
                    "retryState": {},
                    "attempt": {"sessionId": "s1"},
                    "agentMeta": {},
                    "payloadsWithToolMedia": [],
                    "attemptToolSummary": {},
                    "maxReasoningOnlyRetryAttempts": 0,
                    "maxEmptyResponseRetryAttempts": 0,
                    "attemptCompactionCount": 0,
                    "terminalAborted": True,
                    "terminalTimedOut": False,
                    "externalAbort": False,
                    "startedAtMs": 0,
                    "provider": "p1",
                    "modelId": "m1",
                }
            )
        )
        assert len(captured) == 0


# ============================================================================
# runtime-preparation
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_runtime_prep_hooks() -> None:
    set_can_run_prepared_agent_runtime_auth_attempt_hook(lambda _p: True)
    set_create_embedded_run_stage_tracker_hook(lambda: {})
    set_format_embedded_run_stage_summary_hook(lambda _t: "")
    set_has_prepared_auth_attempt_model_metadata_hook(lambda _p: False)
    set_resolve_embedded_run_effective_model_hook(
        lambda p: {
            "effectiveModel": p.get("runtimeModel"),
            "contextWindowInfo": None,
            "contextTokenBudget": None,
        }
    )
    set_resolve_embedded_run_model_setup_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_resolve_initial_think_level_hook(lambda _p: "medium")
    set_select_embedded_run_harness_for_prepared_attempts_hook(
        lambda _m, _a: {"id": "openclaw"}
    )
    set_select_embedded_run_harness_hook(
        lambda _p: {"id": "openclaw", "authBootstrap": None}
    )
    yield
    set_resolve_embedded_run_model_setup_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestPrepareEmbeddedRunRuntime:
    def test_basic(self) -> None:
        async def _setup_hook(_p: Any) -> Any:
            return {
                "provider": "p1",
                "modelId": "m1",
                "agentHarness": {"id": "openclaw", "authBootstrap": None},
                "model": {"id": "m1"},
            }

        set_resolve_embedded_run_model_setup_hook(_setup_hook)
        result = asyncio.run(
            prepare_embedded_run_runtime(
                {
                    "runParams": {},
                    "provider": "p1",
                    "modelId": "m1",
                    "agentDir": "/tmp/agent",
                    "workspaceDir": "/tmp/workspace",
                    "globalLane": "main",
                    "hookRunner": None,
                    "hookContext": {},
                    "markStartupStage": lambda _s: None,
                    "fallbackConfigured": False,
                }
            )
        )
        assert result["provider"] == "p1"
        assert result["modelId"] == "m1"
        assert result["agentHarness"] == {"id": "openclaw", "authBootstrap": None}
        assert result["initialThinkLevel"] == "medium"

    def test_initial_think_level_custom(self) -> None:
        async def _setup_hook(_p: Any) -> Any:
            return {
                "provider": "p1",
                "modelId": "m1",
                "agentHarness": {"id": "openclaw", "authBootstrap": None},
                "model": {"id": "m1"},
            }

        set_resolve_embedded_run_model_setup_hook(_setup_hook)
        set_resolve_initial_think_level_hook(lambda _p: "high")
        result = asyncio.run(
            prepare_embedded_run_runtime(
                {
                    "runParams": {},
                    "provider": "p1",
                    "modelId": "m1",
                    "agentDir": "/tmp",
                    "workspaceDir": "/tmp",
                    "globalLane": "main",
                    "hookRunner": None,
                    "hookContext": {},
                    "markStartupStage": lambda _s: None,
                    "fallbackConfigured": False,
                }
            )
        )
        assert result["initialThinkLevel"] == "high"
