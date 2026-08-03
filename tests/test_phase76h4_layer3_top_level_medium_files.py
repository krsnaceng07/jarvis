"""Phase 7.6h-4 tests — 8 top-level medium/small files."""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

import pytest

# Ensure src/ is on sys.path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.agents.embedded_agent_runner.cli_backend_dispatch import (  # noqa: E402
    resolve_embedded_cli_backend_dispatch,
    run_embedded_agent_via_cli_backend_if_eligible,
    set_resolve_embedded_cli_backend_dispatch_hook,
    set_run_embedded_agent_via_cli_backend_if_eligible_hook,
)
from src.agents.embedded_agent_runner.cli_backend_dispatch_eligibility import (  # noqa: E402
    resolve_embedded_cli_backend_dispatch_eligibility,
    set_resolve_embedded_cli_backend_dispatch_eligibility_hook,
)
from src.agents.embedded_agent_runner.openrouter_model_capabilities import (  # noqa: E402
    FETCH_TIMEOUT_MS,
    OPENROUTER_MODELS_URL,
    OPENROUTER_MODELS_RESPONSE_MAX_BYTES,
    SQLITE_CACHE_MAX_ENTRIES,
    SQLITE_CACHE_NAMESPACE,
    SQLITE_CACHE_OWNER_ID,
    _reset_cache_for_testing,
    _seed_cache_for_testing,
    get_open_router_model_capabilities,
    load_open_router_model_capabilities,
    set_get_open_router_model_capabilities_hook,
    set_load_open_router_model_capabilities_hook,
)
from src.agents.embedded_agent_runner.result_fallback_classifier import (  # noqa: E402
    GENERIC_EXTERNAL_RUN_FAILURE_TEXT,
    classify_embedded_agent_run_result_for_model_fallback,
    has_deliberate_silent_terminal_reply,
    merge_embedded_agent_run_result_for_model_fallback_exhaustion,
    set_classify_embedded_agent_run_result_for_model_fallback_hook,
    set_has_deliberate_silent_terminal_reply_hook,
    set_merge_embedded_agent_run_result_for_model_fallback_exhaustion_hook,
)
from src.agents.embedded_agent_runner.sandbox_info import (  # noqa: E402
    build_embedded_sandbox_info,
    resolve_embedded_full_access_state,
    resolve_embedded_sandbox_info_exec_policy,
    set_build_embedded_sandbox_info_hook,
    set_resolve_embedded_full_access_state_hook,
    set_resolve_embedded_sandbox_info_exec_policy_hook,
)
from src.agents.embedded_agent_runner.stream_resolution import (  # noqa: E402
    describe_embedded_agent_stream_strategy,
    resolve_embedded_agent_api_key,
    resolve_embedded_agent_base_stream_fn,
    resolve_embedded_agent_stream_fn,
    set_describe_embedded_agent_stream_strategy_hook,
    set_resolve_embedded_agent_api_key_hook,
    set_resolve_embedded_agent_base_stream_fn_hook,
    set_resolve_embedded_agent_stream_fn_hook,
)
from src.agents.embedded_agent_runner.system_prompt import (  # noqa: E402
    apply_system_prompt_to_session,
    build_embedded_system_prompt,
    set_apply_system_prompt_to_session_hook,
    set_build_embedded_system_prompt_hook,
)
from src.agents.embedded_agent_runner.usage_accumulator import (  # noqa: E402
    create_usage_accumulator,
    merge_usage_into_accumulator,
    to_last_call_usage,
    to_normalized_usage,
    set_merge_usage_into_accumulator_hook,
    set_to_last_call_usage_hook,
    set_to_normalized_usage_hook,
)


# ============================================================================
# cli_backend_dispatch
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_cli_dispatch_hooks() -> None:
    set_resolve_embedded_cli_backend_dispatch_hook(None)
    set_run_embedded_agent_via_cli_backend_if_eligible_hook(None)
    set_resolve_embedded_cli_backend_dispatch_eligibility_hook(None)
    yield
    set_resolve_embedded_cli_backend_dispatch_hook(None)
    set_run_embedded_agent_via_cli_backend_if_eligible_hook(None)
    set_resolve_embedded_cli_backend_dispatch_eligibility_hook(None)


class TestCliBackendDispatch:
    def test_resolve_requires_opt_in(self) -> None:
        out = resolve_embedded_cli_backend_dispatch(
            {"sessionFile": "/x.jsonl", "toolsAllow": ["read"]}
        )
        assert out is None

    def test_resolve_requires_session_file(self) -> None:
        out = resolve_embedded_cli_backend_dispatch(
            {"cliBackendDispatch": "subscription-auth", "toolsAllow": ["read"]}
        )
        assert out is None

    def test_resolve_requires_tools_allow(self) -> None:
        out = resolve_embedded_cli_backend_dispatch(
            {
                "cliBackendDispatch": "subscription-auth",
                "sessionFile": "/x.jsonl",
            }
        )
        assert out is None

    def test_resolve_rejects_wildcard(self) -> None:
        out = resolve_embedded_cli_backend_dispatch(
            {
                "cliBackendDispatch": "subscription-auth",
                "sessionFile": "/x.jsonl",
                "toolsAllow": ["*"],
            }
        )
        assert out is None

    def test_resolve_rejects_disable_tools(self) -> None:
        out = resolve_embedded_cli_backend_dispatch(
            {
                "cliBackendDispatch": "subscription-auth",
                "sessionFile": "/x.jsonl",
                "toolsAllow": ["read"],
                "disableTools": True,
            }
        )
        assert out is None

    def test_resolve_basic(self) -> None:
        out = resolve_embedded_cli_backend_dispatch(
            {
                "cliBackendDispatch": "subscription-auth",
                "sessionFile": "/x.jsonl",
                "toolsAllow": ["read", "write"],
                "provider": "claude-cli",
            }
        )
        assert out is not None
        assert out["sessionFile"] == "/x.jsonl"
        assert sorted(out["toolsAllow"]) == ["read", "write"]
        assert out["provider"] == "claude-cli"

    def test_resolve_with_hook(self) -> None:
        set_resolve_embedded_cli_backend_dispatch_hook(lambda _p: {"custom": True})
        out = resolve_embedded_cli_backend_dispatch({})
        assert out == {"custom": True}

    def test_run_returns_none_when_ineligible(self) -> None:
        out = asyncio.run(
            run_embedded_agent_via_cli_backend_if_eligible({})
        )
        assert out is None

    def test_run_with_hook(self) -> None:
        set_run_embedded_agent_via_cli_backend_if_eligible_hook(lambda _p: "stub")
        out = asyncio.run(
            run_embedded_agent_via_cli_backend_if_eligible({})
        )
        assert out == "stub"


# ============================================================================
# cli_backend_dispatch_eligibility
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_eligibility_hooks() -> None:
    set_resolve_embedded_cli_backend_dispatch_eligibility_hook(None)
    yield
    set_resolve_embedded_cli_backend_dispatch_eligibility_hook(None)


class TestCliBackendDispatchEligibility:
    def test_empty_provider(self) -> None:
        assert resolve_embedded_cli_backend_dispatch_eligibility({}) is None

    def test_claude_cli(self) -> None:
        out = resolve_embedded_cli_backend_dispatch_eligibility({"provider": "claude-cli"})
        assert out is not None
        assert out["provider"] == "claude-cli"

    def test_codex_cli(self) -> None:
        out = resolve_embedded_cli_backend_dispatch_eligibility({"provider": "codex-cli"})
        assert out == {"provider": "codex-cli"}

    def test_unknown_provider(self) -> None:
        assert resolve_embedded_cli_backend_dispatch_eligibility({"provider": "openai"}) is None

    def test_with_hook(self) -> None:
        set_resolve_embedded_cli_backend_dispatch_eligibility_hook(
            lambda _p: {"provider": "hooked"}
        )
        out = resolve_embedded_cli_backend_dispatch_eligibility({})
        assert out == {"provider": "hooked"}


# ============================================================================
# openrouter_model_capabilities
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_openrouter_hooks() -> None:
    _reset_cache_for_testing()
    set_load_open_router_model_capabilities_hook(None)
    set_get_open_router_model_capabilities_hook(None)
    yield
    _reset_cache_for_testing()
    set_load_open_router_model_capabilities_hook(None)
    set_get_open_router_model_capabilities_hook(None)


class TestOpenRouterModelCapabilities:
    def test_constants(self) -> None:
        assert OPENROUTER_MODELS_URL == "https://openrouter.ai/api/v1/models"
        assert FETCH_TIMEOUT_MS == 10_000
        assert OPENROUTER_MODELS_RESPONSE_MAX_BYTES == 16 * 1024 * 1024
        assert SQLITE_CACHE_OWNER_ID == "core:openrouter-model-capabilities"
        assert SQLITE_CACHE_NAMESPACE == "models.v3"
        assert SQLITE_CACHE_MAX_ENTRIES == 10_000

    def test_get_empty_cache(self) -> None:
        assert get_open_router_model_capabilities("foo") is None

    def test_load_empty(self) -> None:
        asyncio.run(load_open_router_model_capabilities("unknown"))

    def test_get_with_hook(self) -> None:
        set_get_open_router_model_capabilities_hook(
            lambda _id: {"name": "stub", "input": ["text"], "reasoning": True, "contextWindow": 1000, "maxTokens": 100}
        )
        out = get_open_router_model_capabilities("any")
        assert out is not None
        assert out["name"] == "stub"

    def test_load_with_hook(self) -> None:
        async def _hook(_id):
            return "ok"
        set_load_open_router_model_capabilities_hook(_hook)
        asyncio.run(load_open_router_model_capabilities("any"))

    def test_seed_cache(self) -> None:
        _seed_cache_for_testing(
            {
                "gpt-4o": {
                    "name": "GPT-4o",
                    "input": ["text", "image"],
                    "reasoning": False,
                    "contextWindow": 128_000,
                    "maxTokens": 8192,
                }
            }
        )
        out = get_open_router_model_capabilities("gpt-4o")
        assert out is not None
        assert out["name"] == "GPT-4o"

    def test_seed_rejects_invalid(self) -> None:
        _seed_cache_for_testing(
            {"bad": {"name": 1, "input": [], "reasoning": "yes", "contextWindow": 1, "maxTokens": 1}}
        )
        assert get_open_router_model_capabilities("bad") is None


# ============================================================================
# result_fallback_classifier
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_fallback_hooks() -> None:
    set_classify_embedded_agent_run_result_for_model_fallback_hook(None)
    set_merge_embedded_agent_run_result_for_model_fallback_exhaustion_hook(None)
    set_has_deliberate_silent_terminal_reply_hook(None)
    yield
    set_classify_embedded_agent_run_result_for_model_fallback_hook(None)
    set_merge_embedded_agent_run_result_for_model_fallback_exhaustion_hook(None)
    set_has_deliberate_silent_terminal_reply_hook(None)


class TestResultFallbackClassifier:
    def test_constants(self) -> None:
        assert GENERIC_EXTERNAL_RUN_FAILURE_TEXT == "Sorry, I couldn't complete that request."

    def test_classify_non_result(self) -> None:
        assert (
            classify_embedded_agent_run_result_for_model_fallback(
                {"provider": "p", "model": "m", "result": None}
            )
            is None
        )

    def test_classify_aborted(self) -> None:
        result = {"meta": {"aborted": True}, "payloads": []}
        assert (
            classify_embedded_agent_run_result_for_model_fallback(
                {"provider": "p", "model": "m", "result": result}
            )
            is None
        )

    def test_classify_empty_payloads(self) -> None:
        result = {"meta": {}, "payloads": []}
        out = classify_embedded_agent_run_result_for_model_fallback(
            {"provider": "openai", "model": "gpt-5", "result": result}
        )
        assert out is not None
        assert out["code"] == "empty_result"
        assert "openai/gpt-5" in out["message"]

    def test_classify_reasoning_only(self) -> None:
        result = {"meta": {}, "payloads": [{"isReasoning": True}]}
        out = classify_embedded_agent_run_result_for_model_fallback(
            {"provider": "openai", "model": "gpt-5", "result": result}
        )
        assert out is not None
        assert out["code"] == "reasoning_only_result"

    def test_classify_with_visible_text(self) -> None:
        result = {
            "meta": {"finalAssistantVisibleText": "Here you go."},
            "payloads": [],
        }
        assert (
            classify_embedded_agent_run_result_for_model_fallback(
                {"provider": "openai", "model": "gpt-5", "result": result}
            )
            is None
        )

    def test_classify_hook_block(self) -> None:
        result = {
            "meta": {"error": {"kind": "hook_block"}},
            "payloads": [],
        }
        assert (
            classify_embedded_agent_run_result_for_model_fallback(
                {"provider": "openai", "model": "gpt-5", "result": result}
            )
            is None
        )

    def test_classify_harness_empty(self) -> None:
        result = {
            "meta": {"agentHarnessResultClassification": "empty"},
            "payloads": [{"text": "actual answer"}],
        }
        out = classify_embedded_agent_run_result_for_model_fallback(
            {"provider": "p", "model": "m", "result": result}
        )
        assert out is not None
        assert out["code"] == "empty_result"

    def test_classify_harness_reasoning(self) -> None:
        result = {
            "meta": {"agentHarnessResultClassification": "reasoning-only"},
            "payloads": [{"text": "ignored"}],
        }
        out = classify_embedded_agent_run_result_for_model_fallback(
            {"provider": "p", "model": "m", "result": result}
        )
        assert out is not None
        assert out["code"] == "reasoning_only_result"

    def test_classify_harness_planning(self) -> None:
        result = {
            "meta": {"agentHarnessResultClassification": "planning-only"},
            "payloads": [{"text": "ignored"}],
        }
        out = classify_embedded_agent_run_result_for_model_fallback(
            {"provider": "p", "model": "m", "result": result}
        )
        assert out is not None
        assert out["code"] == "planning_only_result"

    def test_classify_generic_external_failure(self) -> None:
        result = {
            "meta": {},
            "payloads": [{"text": GENERIC_EXTERNAL_RUN_FAILURE_TEXT}],
        }
        out = classify_embedded_agent_run_result_for_model_fallback(
            {"provider": "p", "model": "m", "result": result}
        )
        assert out is not None
        assert out["code"] == "generic_external_run_failure"

    def test_classify_with_hook(self) -> None:
        set_classify_embedded_agent_run_result_for_model_fallback_hook(
            lambda _p: {"custom": True}
        )
        out = classify_embedded_agent_run_result_for_model_fallback({})
        assert out == {"custom": True}

    def test_merge_same_result(self) -> None:
        result = {"payloads": [], "meta": {}}
        out = merge_embedded_agent_run_result_for_model_fallback_exhaustion(
            {"latestResult": result, "preferredResult": result}
        )
        assert out is result

    def test_merge_different(self) -> None:
        latest = {"payloads": [], "meta": {}}
        preferred = {"payloads": [{"text": "hi"}], "meta": {"error": None}}
        out = merge_embedded_agent_run_result_for_model_fallback_exhaustion(
            {"latestResult": latest, "preferredResult": preferred}
        )
        assert out["payloads"] == [{"text": "hi"}]

    def test_merge_with_hook(self) -> None:
        set_merge_embedded_agent_run_result_for_model_fallback_exhaustion_hook(
            lambda _p: {"hooked": True}
        )
        out = merge_embedded_agent_run_result_for_model_fallback_exhaustion({})
        assert out == {"hooked": True}

    def test_silent_terminal_reply_hook_block(self) -> None:
        result = {"meta": {"error": {"kind": "hook_block"}}}
        assert has_deliberate_silent_terminal_reply(result) is True

    def test_silent_terminal_reply_silent_text(self) -> None:
        result = {"meta": {"finalAssistantVisibleText": "(no reply)"}}
        assert has_deliberate_silent_terminal_reply(result) is True

    def test_silent_terminal_reply_no_match(self) -> None:
        result = {"meta": {"finalAssistantVisibleText": "Hello world"}}
        assert has_deliberate_silent_terminal_reply(result) is False

    def test_silent_terminal_reply_with_hook(self) -> None:
        set_has_deliberate_silent_terminal_reply_hook(lambda _r: True)
        assert has_deliberate_silent_terminal_reply({}) is True


# ============================================================================
# sandbox_info
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_sandbox_info_hooks() -> None:
    set_resolve_embedded_full_access_state_hook(None)
    set_resolve_embedded_sandbox_info_exec_policy_hook(None)
    set_build_embedded_sandbox_info_hook(None)
    yield
    set_resolve_embedded_full_access_state_hook(None)
    set_resolve_embedded_sandbox_info_exec_policy_hook(None)
    set_build_embedded_sandbox_info_hook(None)


class TestSandboxInfo:
    def test_full_access_default(self) -> None:
        # No exec policy block + no elevated config = treat as unavailable by default.
        out = resolve_embedded_full_access_state({})
        assert out["available"] is False
        assert out["blockedReason"] == "host-policy"

    def test_full_access_blocked_by_policy(self) -> None:
        out = resolve_embedded_full_access_state(
            {"execPolicy": {"mode": "non-full", "ask": "off"}}
        )
        assert out["available"] is False
        assert out["blockedReason"] == "host-policy"

    def test_full_access_blocked_by_ask_always(self) -> None:
        out = resolve_embedded_full_access_state(
            {"execPolicy": {"ask": "always"}}
        )
        assert out["available"] is False

    def test_full_access_elevated_explicit_true(self) -> None:
        out = resolve_embedded_full_access_state(
            {"execElevated": {"fullAccessAvailable": True}}
        )
        assert out["available"] is True

    def test_full_access_elevated_explicit_false(self) -> None:
        out = resolve_embedded_full_access_state(
            {"execElevated": {"fullAccessAvailable": False, "fullAccessBlockedReason": "x"}}
        )
        assert out["available"] is False
        assert out["blockedReason"] == "x"

    def test_full_access_elevated_disabled(self) -> None:
        out = resolve_embedded_full_access_state(
            {"execElevated": {"enabled": False, "allowed": False}}
        )
        assert out["available"] is False

    def test_full_access_with_hook(self) -> None:
        set_resolve_embedded_full_access_state_hook(lambda _p: {"available": "hooked"})
        out = resolve_embedded_full_access_state({})
        assert out["available"] == "hooked"

    def test_exec_policy_default(self) -> None:
        out = resolve_embedded_sandbox_info_exec_policy({})
        assert out["mode"] == "full"
        assert out["security"] == "full"
        assert out["ask"] == "off"

    def test_exec_policy_with_hook(self) -> None:
        set_resolve_embedded_sandbox_info_exec_policy_hook(
            lambda _p: {"mode": "hooked", "security": "hooked", "ask": "hooked"}
        )
        out = resolve_embedded_sandbox_info_exec_policy({})
        assert out["mode"] == "hooked"

    def test_build_disabled(self) -> None:
        out = build_embedded_sandbox_info(None, None, None, None)
        assert out is None
        out = build_embedded_sandbox_info({"enabled": False}, None, None, None)
        assert out is None

    def test_build_basic_enabled(self) -> None:
        sandbox = {
            "enabled": True,
            "workspaceDir": "/host",
            "containerWorkdir": "/container",
            "workspaceAccess": "rw",
        }
        out = build_embedded_sandbox_info(sandbox, None, None, None)
        assert out is not None
        assert out["enabled"] is True
        assert out["workspaceDir"] == "/host"
        assert out["containerWorkspaceDir"] == "/container"

    def test_build_with_ro_mount(self) -> None:
        sandbox = {
            "enabled": True,
            "workspaceDir": "/host",
            "containerWorkdir": "/container",
            "workspaceAccess": "ro",
        }
        out = build_embedded_sandbox_info(sandbox, None, None, None)
        assert out["agentWorkspaceMount"] == "/agent"

    def test_build_with_elevated(self) -> None:
        sandbox = {
            "enabled": True,
            "workspaceDir": "/host",
            "containerWorkdir": "/container",
            "workspaceAccess": "rw",
        }
        out = build_embedded_sandbox_info(
            sandbox, {"enabled": True, "allowed": True, "defaultLevel": "ask"}, None, None
        )
        assert "elevated" in out
        assert out["elevated"]["allowed"] is True
        assert out["elevated"]["defaultLevel"] == "ask"

    def test_build_with_elevated_blocked(self) -> None:
        sandbox = {
            "enabled": True,
            "workspaceDir": "/host",
            "containerWorkdir": "/container",
            "workspaceAccess": "rw",
        }
        out = build_embedded_sandbox_info(
            sandbox,
            {"enabled": True, "allowed": True, "defaultLevel": "ask"},
            {"mode": "sandbox", "security": "sandbox", "ask": "off"},
            None,
        )
        assert "elevated" in out
        assert out["elevated"]["fullAccessAvailable"] is False
        assert out["elevated"]["fullAccessBlockedReason"] == "host-policy"

    def test_build_with_hook(self) -> None:
        set_build_embedded_sandbox_info_hook(
            lambda _p: {"hooked": True}
        )
        out = build_embedded_sandbox_info({"enabled": True}, None, None, None)
        assert out == {"hooked": True}


# ============================================================================
# stream_resolution
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_stream_resolution_hooks() -> None:
    set_resolve_embedded_agent_base_stream_fn_hook(None)
    set_describe_embedded_agent_stream_strategy_hook(None)
    set_resolve_embedded_agent_api_key_hook(None)
    set_resolve_embedded_agent_stream_fn_hook(None)
    yield
    set_resolve_embedded_agent_base_stream_fn_hook(None)
    set_describe_embedded_agent_stream_strategy_hook(None)
    set_resolve_embedded_agent_api_key_hook(None)
    set_resolve_embedded_agent_stream_fn_hook(None)


class TestStreamResolution:
    def test_base_stream_fn(self) -> None:
        def _stream(): pass
        session = {"agent": {"streamFn": _stream}}
        out = resolve_embedded_agent_base_stream_fn({"session": session})
        assert out is _stream

    def test_base_stream_fn_missing(self) -> None:
        with pytest.raises(RuntimeError):
            resolve_embedded_agent_base_stream_fn({"session": {}})

    def test_base_stream_fn_with_hook(self) -> None:
        set_resolve_embedded_agent_base_stream_fn_hook(lambda _p: "hooked")
        out = resolve_embedded_agent_base_stream_fn({})
        assert out == "hooked"

    def test_describe_provider(self) -> None:
        out = describe_embedded_agent_stream_strategy(
            {"providerStreamFn": lambda: None, "model": {}}
        )
        assert out == "provider"

    def test_describe_anthropic_vertex(self) -> None:
        out = describe_embedded_agent_stream_strategy(
            {"model": {"provider": "anthropic-vertex", "api": ""}}
        )
        assert out == "anthropic-vertex"

    def test_describe_codex_responses(self) -> None:
        out = describe_embedded_agent_stream_strategy(
            {"model": {"provider": "openai", "api": "openai-chatgpt-responses"}}
        )
        assert out == "openclaw-native-codex-responses"

    def test_describe_proxied_anthropic(self) -> None:
        out = describe_embedded_agent_stream_strategy(
            {"model": {"provider": "pioneer", "api": "anthropic-messages"}}
        )
        assert out == "boundary-aware:anthropic-messages"

    def test_describe_with_explicit_key(self) -> None:
        out = describe_embedded_agent_stream_strategy(
            {"model": {"provider": "openai", "api": "openai-chat"}, "resolvedApiKey": "k"}
        )
        assert out == "boundary-aware:openai-chat"

    def test_describe_with_hook(self) -> None:
        set_describe_embedded_agent_stream_strategy_hook(lambda _p: "hooked")
        out = describe_embedded_agent_stream_strategy({})
        assert out == "hooked"

    def test_api_key_explicit(self) -> None:
        out = asyncio.run(
            resolve_embedded_agent_api_key({"provider": "p", "resolvedApiKey": "k"})
        )
        assert out == "k"

    def test_api_key_no_storage(self) -> None:
        out = asyncio.run(
            resolve_embedded_agent_api_key({"provider": "p"})
        )
        assert out is None

    def test_api_key_with_storage(self) -> None:
        class _S:
            async def getApiKey(self, provider):
                return f"key-for-{provider}"
        out = asyncio.run(
            resolve_embedded_agent_api_key({"provider": "anthropic", "authStorage": _S()})
        )
        assert out == "key-for-anthropic"

    def test_api_key_with_hook(self) -> None:
        async def _hook(_p):
            return "hooked"
        set_resolve_embedded_agent_api_key_hook(_hook)
        out = asyncio.run(resolve_embedded_agent_api_key({}))
        assert out == "hooked"

    def test_stream_fn_provider(self) -> None:
        out = resolve_embedded_agent_stream_fn(
            {"providerStreamFn": "provider_stream"}
        )
        assert out == "provider_stream"

    def test_stream_fn_with_hook(self) -> None:
        set_resolve_embedded_agent_stream_fn_hook(lambda _p: "hooked")
        out = resolve_embedded_agent_stream_fn({})
        assert out == "hooked"


# ============================================================================
# system_prompt
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_system_prompt_hooks() -> None:
    set_build_embedded_system_prompt_hook(None)
    set_apply_system_prompt_to_session_hook(None)
    yield
    set_build_embedded_system_prompt_hook(None)
    set_apply_system_prompt_to_session_hook(None)


class TestSystemPrompt:
    def test_build_basic(self) -> None:
        out = build_embedded_system_prompt(
            {
                "workspaceDir": "/tmp",
                "runtimeInfo": {
                    "model": "claude-sonnet-4",
                    "provider": "anthropic",
                    "host": "local",
                },
                "tools": [{"name": "read"}, {"name": "write"}],
            }
        )
        assert "claude-sonnet-4" in out
        assert "anthropic" in out
        assert "read" in out
        assert "write" in out
        assert "/tmp" in out

    def test_build_with_hook(self) -> None:
        set_build_embedded_system_prompt_hook(lambda _p: "hooked")
        out = build_embedded_system_prompt({})
        assert out == "hooked"

    def test_apply_to_session(self) -> None:
        class _S:
            def __init__(self):
                self.value = None
            def setBaseSystemPrompt(self, prompt):
                self.value = prompt
        s = _S()
        apply_system_prompt_to_session(s, "  hello world  ")
        assert s.value == "hello world"

    def test_apply_with_hook(self) -> None:
        seen = {}
        def _hook(s, p):
            seen["s"] = s
            seen["p"] = p
        set_apply_system_prompt_to_session_hook(_hook)
        apply_system_prompt_to_session("sess", "prompt")
        assert seen["s"] == "sess"
        assert seen["p"] == "prompt"

    def test_apply_no_method(self) -> None:
        # Should not throw even if session has no setter
        apply_system_prompt_to_session({}, "hello")


# ============================================================================
# usage_accumulator
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_usage_hooks() -> None:
    set_merge_usage_into_accumulator_hook(None)
    set_to_normalized_usage_hook(None)
    set_to_last_call_usage_hook(None)
    yield
    set_merge_usage_into_accumulator_hook(None)
    set_to_normalized_usage_hook(None)
    set_to_last_call_usage_hook(None)


class TestUsageAccumulator:
    def test_create(self) -> None:
        a = create_usage_accumulator()
        assert a["input"] == 0
        assert a["output"] == 0
        assert a["cacheRead"] == 0
        assert a["lastContextUsage"] is None
        assert a["lastTotal"] == 0

    def test_merge_no_usage(self) -> None:
        a = create_usage_accumulator()
        merge_usage_into_accumulator(a, None)
        assert a["input"] == 0

    def test_merge_basic(self) -> None:
        a = create_usage_accumulator()
        merge_usage_into_accumulator(a, {"input": 100, "output": 50, "total": 150})
        assert a["input"] == 100
        assert a["output"] == 50
        assert a["total"] == 150
        assert a["lastInput"] == 100
        assert a["lastTotal"] == 150

    def test_merge_implied_total(self) -> None:
        a = create_usage_accumulator()
        merge_usage_into_accumulator(
            a, {"input": 100, "output": 50, "cacheRead": 25, "cacheWrite": 5}
        )
        # total is implied: 100 + 50 + 25 + 5 = 180
        assert a["total"] == 180

    def test_merge_accumulates(self) -> None:
        a = create_usage_accumulator()
        merge_usage_into_accumulator(a, {"input": 100, "output": 50, "total": 150})
        merge_usage_into_accumulator(a, {"input": 200, "output": 100, "total": 300})
        assert a["input"] == 300
        assert a["output"] == 150
        assert a["total"] == 450
        assert a["lastInput"] == 200
        assert a["lastTotal"] == 300

    def test_merge_with_context_usage(self) -> None:
        a = create_usage_accumulator()
        merge_usage_into_accumulator(
            a,
            {
                "input": 100,
                "output": 50,
                "contextUsage": {
                    "state": "available",
                    "promptTokens": 80,
                    "totalTokens": 1024,
                },
            },
        )
        assert a["lastContextUsage"]["state"] == "available"
        assert a["lastContextUsage"]["promptTokens"] == 80

    def test_merge_with_reasoning(self) -> None:
        a = create_usage_accumulator()
        merge_usage_into_accumulator(a, {"input": 100, "reasoningTokens": 30, "total": 130})
        assert a["reasoningTokens"] == 30
        assert a["lastReasoningTokens"] == 30

    def test_merge_with_hook(self) -> None:
        seen = {}
        def _hook(t, u):
            seen["t"] = t
            seen["u"] = u
        set_merge_usage_into_accumulator_hook(_hook)
        merge_usage_into_accumulator({}, {"input": 1})
        assert seen["u"]["input"] == 1

    def test_to_normalized_empty(self) -> None:
        assert to_normalized_usage(create_usage_accumulator()) is None

    def test_to_normalized_basic(self) -> None:
        a = create_usage_accumulator()
        merge_usage_into_accumulator(a, {"input": 100, "output": 50, "total": 150})
        out = to_normalized_usage(a)
        assert out is not None
        assert out["input"] == 100
        assert out["output"] == 50
        assert out["total"] == 150

    def test_to_normalized_with_reasoning(self) -> None:
        a = create_usage_accumulator()
        merge_usage_into_accumulator(a, {"input": 100, "reasoningTokens": 30, "total": 130})
        out = to_normalized_usage(a)
        assert out["reasoningTokens"] == 30

    def test_to_normalized_with_hook(self) -> None:
        set_to_normalized_usage_hook(lambda _a: {"hooked": True})
        out = to_normalized_usage({})
        assert out == {"hooked": True}

    def test_to_last_call_empty(self) -> None:
        assert to_last_call_usage(create_usage_accumulator()) is None

    def test_to_last_call_basic(self) -> None:
        a = create_usage_accumulator()
        merge_usage_into_accumulator(a, {"input": 100, "output": 50, "total": 150})
        out = to_last_call_usage(a)
        assert out is not None
        assert out["input"] == 100
        assert out["output"] == 50
        assert out["total"] == 150

    def test_to_last_call_only_last(self) -> None:
        a = create_usage_accumulator()
        merge_usage_into_accumulator(a, {"input": 100, "output": 50, "total": 150})
        merge_usage_into_accumulator(a, {"input": 200, "output": 100, "total": 300})
        out = to_last_call_usage(a)
        # lastInput is 200, lastOutput is 100, lastTotal is 300
        assert out["input"] == 200
        assert out["output"] == 100
        assert out["total"] == 300

    def test_to_last_call_with_hook(self) -> None:
        set_to_last_call_usage_hook(lambda _a: {"hooked": True})
        out = to_last_call_usage({})
        assert out == {"hooked": True}
