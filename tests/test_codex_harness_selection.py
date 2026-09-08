"""Tests for harness selection decisions (policy → availability → decision)
plus the host effective-runtime probe (projection mode, never raises).

OpenClaw parity: mirrors the decision core of
``openclaw-main/src/agents/harness/selection.ts``
(``selectAgentHarnessDecision``) and
``openclaw-main/src/agents/harness/availability.ts``, including the
fail-closed errors:

- ``Requested agent harness "<id>" is not registered.``
  (``MissingAgentHarnessError``)
- ``Requested agent harness "<id>" does not support <ref>.``
"""

from __future__ import annotations

import pytest

from src.agents.harness.selection import (
    HarnessNotSupportedError,
    MissingAgentHarnessError,
    resolve_host_effective_agent_runtime,
    select_agent_harness,
)

CODEX_HARNESS = {"id": "codex", "providers": ["openai", "codex"]}


def _openai_codex_forced_config():
    return {
        "models": {"providers": {"openai": {"agentRuntime": {"id": "codex"}}}},
        "plugins": {"entries": {"codex": {"enabled": True}}},
        "agents": {"defaults": {"model": "openai/gpt-5.6-sol"}},
    }


def test_openclaw_runtime_is_forced_openclaw():
    decision = select_agent_harness(
        {
            "provider": "openai",
            "modelId": "gpt-5.5",
            "config": {"models": {"providers": {"openai": {"agentRuntime": {"id": "openclaw"}}}}},
            "env": {},
        }
    )
    assert decision["harness_id"] == "openclaw"
    assert decision["reason"] == "forced_openclaw"


def test_auto_without_policy_is_auto_openclaw():
    decision = select_agent_harness(
        {"provider": "anthropic", "modelId": "claude-opus-4-6", "config": {}, "env": {}}
    )
    assert decision["harness_id"] == "openclaw"
    assert decision["reason"] == "auto_openclaw"


def test_explicit_codex_registered_and_supported_is_forced_plugin():
    decision = select_agent_harness(
        {
            "provider": "openai",
            "modelId": "gpt-5.6-sol",
            "config": _openai_codex_forced_config(),
            "env": {},
            "registered_harnesses": [CODEX_HARNESS],
        }
    )
    assert decision["harness_id"] == "codex"
    assert decision["reason"] == "forced_plugin"
    assert decision["policy"]["runtimeSource"] == "provider"


def test_explicit_codex_unregistered_fails_closed():
    with pytest.raises(MissingAgentHarnessError) as exc:
        select_agent_harness(
            {
                "provider": "openai",
                "modelId": "gpt-5.6-sol",
                "config": _openai_codex_forced_config(),
                "env": {},
                "registered_harnesses": [],
            }
        )
    assert str(exc.value) == 'Requested agent harness "codex" is not registered.'


def test_explicit_codex_unsupported_provider_fails_closed():
    with pytest.raises(HarnessNotSupportedError) as exc:
        select_agent_harness(
            {
                "provider": "anthropic",
                "modelId": "claude-opus-4-6",
                "config": {
                    "models": {"providers": {"anthropic": {"agentRuntime": {"id": "codex"}}}}
                },
                "env": {},
                "registered_harnesses": [CODEX_HARNESS],
            }
        )
    assert "does not support anthropic/claude-opus-4-6" in str(exc.value)


def test_declared_fallback_covers_unsupported_provider():
    harness = {**CODEX_HARNESS, "fallback": "openclaw"}
    decision = select_agent_harness(
        {
            "provider": "anthropic",
            "modelId": "claude-opus-4-6",
            "config": {"models": {"providers": {"anthropic": {"agentRuntime": {"id": "codex"}}}}},
            "env": {},
            "registered_harnesses": [harness],
        }
    )
    assert decision["harness_id"] == "openclaw"
    assert decision["reason"] == "plugin_declared_fallback_openclaw"


def test_implicit_codex_unregistered_falls_back_openclaw():
    config = {
        "models": {
            "providers": {
                "openai": {"api": "openai-responses", "baseUrl": "https://api.openai.com/v1"}
            }
        }
    }
    decision = select_agent_harness(
        {
            "provider": "openai",
            "modelId": "gpt-5.5",
            "config": config,
            "env": {},
            "registered_harnesses": [],
        }
    )
    assert decision["harness_id"] == "openclaw"
    assert decision["reason"] == "implicit_plugin_unavailable_openclaw"


def test_implicit_codex_registered_is_forced_plugin():
    config = {
        "models": {
            "providers": {
                "openai": {"api": "openai-responses", "baseUrl": "https://api.openai.com/v1"}
            }
        }
    }
    decision = select_agent_harness(
        {
            "provider": "openai",
            "modelId": "gpt-5.5",
            "config": config,
            "env": {},
            "registered_harnesses": [CODEX_HARNESS],
        }
    )
    assert decision["harness_id"] == "codex"
    assert decision["reason"] == "forced_plugin"
    assert decision["policy"]["runtimeSource"] == "implicit"


def test_pinned_harness_overrides_policy():
    decision = select_agent_harness(
        {
            "provider": "openai",
            "modelId": "gpt-5.5",
            "config": {},
            "env": {},
            "agent_harness_id": "codex",
            "registered_harnesses": [CODEX_HARNESS],
        }
    )
    assert decision["harness_id"] == "codex"
    assert decision["policy"]["runtimeSource"] == "model"


def test_provider_none_skips_support_revalidation():
    # Mirrors selection.ts: without a provider the pinned owner is not
    # revalidated — the decision stays available.
    decision = select_agent_harness(
        {
            "config": {},
            "env": {},
            "agent_harness_id": "codex",
            "registered_harnesses": [CODEX_HARNESS],
        }
    )
    assert decision["harness_id"] == "codex"
    assert decision["reason"] == "forced_plugin"


def test_host_effective_runtime_answers_policy_without_raising():
    # Mirrors resolveEffectiveAgentRuntime projection mode: explicit codex
    # answers "codex" (fail-closed enforcement belongs to selection, not
    # this probe), implicit/auto answer "openclaw".
    assert (
        resolve_host_effective_agent_runtime(
            {
                "cfg": _openai_codex_forced_config(),
                "provider": "openai",
                "modelId": "gpt-5.6-sol",
            }
        )
        == "codex"
    )
    assert (
        resolve_host_effective_agent_runtime({"cfg": {}, "provider": "anthropic"})
        == "openclaw"
    )
    assert resolve_host_effective_agent_runtime({}) is None
    assert resolve_host_effective_agent_runtime(None) is None


def test_host_effective_runtime_flows_into_plugin_api():
    from jarvis_sdk.api import (
        PluginAgentApi,
        set_host_effective_agent_runtime_resolver,
    )

    api = PluginAgentApi()
    params = {"cfg": {}, "provider": "openai", "modelId": "gpt-5.5"}
    assert api.resolve_effective_agent_runtime(params) is None
    set_host_effective_agent_runtime_resolver(resolve_host_effective_agent_runtime)
    try:
        # gpt-5.5 is dual-route: implicit policy answers codex in probe mode.
        assert PluginAgentApi().resolve_effective_agent_runtime(params) == "codex"
        forced = {"cfg": _openai_codex_forced_config(), "provider": "openai", "modelId": "x"}
        assert PluginAgentApi().resolve_effective_agent_runtime(forced) == "codex"
        api.resolve_effective_agent_runtime_fn = lambda _p: "custom"
        assert api.resolve_effective_agent_runtime(params) == "custom"
    finally:
        set_host_effective_agent_runtime_resolver(None)
    assert PluginAgentApi().resolve_effective_agent_runtime(params) is None
