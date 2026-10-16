"""Tests that host startup installs the agent host defaults.

Locks the wiring added to ``src/plugins/runtime_entry.py``: after
``install_host_runtime``, a bare ``PluginAgentApi`` resolves OpenAI
thinking levels and effective runtimes instead of the empty fallbacks.
Global SDK state is always restored so test order cannot leak.
"""

from __future__ import annotations

from jarvis_sdk.api import (
    PluginAgentApi,
    set_host_effective_agent_runtime_resolver,
    set_host_thinking_policy_resolver,
)
from src.plugins.runtime_entry import install_host_runtime


def _clear_host_defaults():
    set_host_thinking_policy_resolver(None)
    set_host_effective_agent_runtime_resolver(None)


def test_install_host_runtime_wires_agent_defaults():
    _clear_host_defaults()
    api = PluginAgentApi()
    params = {"provider": "openai", "model": "gpt-5.6-sol", "agentRuntime": "openclaw"}
    assert api.resolve_thinking_policy(params)["default"] == "none"
    assert api.resolve_effective_agent_runtime(params) is None

    registry = install_host_runtime(registry_params={"logger": None})
    try:
        assert isinstance(registry, dict)
        policy = PluginAgentApi().resolve_thinking_policy(params)
        assert {level["id"] for level in policy["levels"]} >= {"low", "ultra"}
        assert policy["default"] == "medium"
        # gpt-5.6-sol is dual-route: projection answers the policy runtime
        # (fail-closed enforcement belongs to selection, not this probe).
        assert PluginAgentApi().resolve_effective_agent_runtime(params) == "codex"
    finally:
        _clear_host_defaults()

    assert PluginAgentApi().resolve_thinking_policy(params)["default"] == "none"
    assert PluginAgentApi().resolve_effective_agent_runtime(params) is None
