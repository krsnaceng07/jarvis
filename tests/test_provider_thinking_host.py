"""Tests for host thinking-policy wiring (surface fallback + SDK default).

Covers the live chain consumed by ``api.runtime.agent.resolve_thinking_policy``
(llm-task thinking validation): bundled OpenAI owner surface answers when no
hook is installed, the host function shapes the policy for callers, and the
SDK global default is consulted before the empty fallback.
"""

from __future__ import annotations

from jarvis_sdk.api import PluginAgentApi, set_host_thinking_policy_resolver
from src.plugins.provider_thinking import (
    resolve_host_thinking_policy,
    resolve_provider_thinking_profile,
)


def test_bundled_openai_surface_answers_without_hook():
    profile = resolve_provider_thinking_profile(
        {
            "provider": "openai",
            "context": {
                "provider": "openai",
                "modelId": "gpt-5.6-sol",
                "agentRuntime": "openclaw",
            },
        }
    )
    assert profile is not None
    assert {level["id"] for level in profile["levels"]} >= {"low", "max", "ultra"}
    assert profile.get("defaultLevel") == "medium"


def test_unknown_provider_has_no_surface():
    assert (
        resolve_provider_thinking_profile({"provider": "anthropic", "context": {"modelId": "x"}})
        is None
    )


def test_host_fn_shapes_policy_for_callers():
    policy = resolve_host_thinking_policy(
        {"provider": "openai", "model": "gpt-5.6-sol", "agentRuntime": "openclaw"}
    )
    assert {level["id"] for level in policy["levels"]} >= {"low", "high", "ultra"}
    assert policy["default"] == "medium"


def test_host_fn_empty_for_unknown_provider():
    assert resolve_host_thinking_policy({"provider": "anthropic", "model": "x"}) == {"levels": []}
    assert resolve_host_thinking_policy(None) == {"levels": []}


def test_sdk_default_flows_into_plugin_api():
    api = PluginAgentApi()
    params = {"provider": "openai", "model": "gpt-5.6-sol", "agentRuntime": "openclaw"}
    # Historical fallback without an installed host default.
    assert api.resolve_thinking_policy(params) == {
        "levels": [{"id": "none", "label": "None"}],
        "default": "none",
    }
    set_host_thinking_policy_resolver(resolve_host_thinking_policy)
    try:
        policy = PluginAgentApi().resolve_thinking_policy(params)
        assert {level["id"] for level in policy["levels"]} >= {"low", "ultra"}
        # Per-api fn still wins over the global default.
        api.resolve_thinking_policy_fn = lambda _p: {"levels": [{"id": "off"}]}
        assert api.resolve_thinking_policy(params) == {"levels": [{"id": "off"}]}
    finally:
        set_host_thinking_policy_resolver(None)
    assert PluginAgentApi().resolve_thinking_policy(params)["default"] == "none"


def test_llm_task_level_validation_accepts_openai_levels():
    # Mirrors the llm-task check shape: levels + default from the host policy.
    set_host_thinking_policy_resolver(resolve_host_thinking_policy)
    try:
        policy = PluginAgentApi().resolve_thinking_policy(
            {"provider": "openai", "model": "gpt-5.6-sol", "agentRuntime": "openclaw"}
        )
    finally:
        set_host_thinking_policy_resolver(None)
    ids = {level["id"] for level in policy["levels"]}
    assert "low" in ids  # doc: astra-class models default to low-ish effort
    assert policy["default"] == "medium"
