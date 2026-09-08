"""Tests for the Codex runtime route-selection pipeline.

Mirrors OpenClaw's ``src/agents/harness/policy.test.ts`` vectors through
the Jarvis port:

- ``src/agents/harness/policy.py`` (``resolveAgentHarnessPolicy``)
- ``src/agents/model_runtime_policy.py`` (``resolveModelRuntimePolicy``)
- ``src/agents/model_extra_params.py`` (authored-param detection)
- ``src/agents/openai_routing.py`` (implicit OpenAI runtime)
- ``extensions/openai/route_policy.py`` (provider-owned route facts)

Adaptations: OpenClaw wraps cases with ``migratePersistedImplicitMainRoster``
(persisted-roster normalization). Jarvis has no persisted-roster shape, so
configs pass through directly. Env isolation: each case passes ``env={}``
explicitly so ambient ``OPENAI_BASE_URL`` cannot leak into route facts.
"""

from __future__ import annotations

import pytest

from src.agents.harness.policy import resolve_agent_harness_policy


def _openai_provider_config(**overrides):  # type: ignore[no-untyped-def]
    return {
        "models": {
            "providers": {
                "openai": {
                    "api": "openai-responses",
                    "baseUrl": "https://api.openai.com/v1",
                    "models": [],
                    **overrides,
                }
            }
        }
    }


@pytest.mark.parametrize(
    ("name", "overrides", "runtime"),
    [
        ("official Responses route", {}, "codex"),
        ("HTTP official Responses route", {"baseUrl": "http://api.openai.com/v1"}, "openclaw"),
        (
            "HTTP official ChatGPT route",
            {
                "api": "openai-chatgpt-responses",
                "baseUrl": "http://chatgpt.com/backend-api/codex",
            },
            "openclaw",
        ),
        ("custom endpoint", {"baseUrl": "https://relay.example.test/v1"}, "openclaw"),
        ("authored Completions route", {"api": "openai-completions"}, "openclaw"),
        ("request override", {"headers": {"x-route": "custom"}}, "openclaw"),
    ],
)
def test_uses_provider_owned_runtime(name: str, overrides: dict, runtime: str) -> None:
    assert resolve_agent_harness_policy(
        {
            "provider": "openai",
            "modelId": "gpt-5.5",
            "env": {},
            "config": _openai_provider_config(**overrides),
        }
    ) == {"runtime": runtime, "runtimeSource": "implicit"}


def test_keeps_explicit_runtime_policy_authoritative() -> None:
    config = _openai_provider_config(agentRuntime={"id": "codex"})
    config["agents"] = {"defaults": {"params": {"temperature": 0.2}}}
    assert resolve_agent_harness_policy(
        {"provider": "openai", "modelId": "gpt-5.5", "config": config, "env": {}}
    ) == {"runtime": "codex", "runtimeSource": "provider"}


@pytest.mark.parametrize("runtime", ["default", "auto"])
def test_configured_default_runtime_uses_implicit_route_selection(runtime: str) -> None:
    anthropic_config = {
        "models": {
            "providers": {
                "anthropic": {
                    "api": "anthropic-messages",
                    "baseUrl": "https://api.anthropic.com",
                    "agentRuntime": {"id": runtime},
                    "models": [],
                }
            }
        }
    }
    assert resolve_agent_harness_policy(
        {
            "provider": "anthropic",
            "modelId": "claude-sonnet-4-6",
            "config": anthropic_config,
            "env": {},
        }
    ) == {"runtime": "auto", "runtimeSource": "implicit"}
    assert resolve_agent_harness_policy(
        {
            "provider": "openai",
            "modelId": "gpt-5.5",
            "config": _openai_provider_config(agentRuntime={"id": runtime}),
            "env": {},
        }
    ) == {"runtime": "codex", "runtimeSource": "implicit"}
    custom_config = _openai_provider_config(baseUrl="https://relay.example.test/v1")
    custom_config["agents"] = {
        "defaults": {"models": {"openai/gpt-5.5": {"agentRuntime": {"id": runtime}}}}
    }
    assert resolve_agent_harness_policy(
        {
            "provider": "openai",
            "modelId": "gpt-5.5",
            "config": custom_config,
            "env": {},
        }
    ) == {"runtime": "openclaw", "runtimeSource": "implicit"}


@pytest.mark.parametrize(
    ("name", "agents", "agent_id", "session_key"),
    [
        (
            "global params",
            {"defaults": {"params": {"temperature": 0.2}}},
            None,
            None,
        ),
        (
            "model params",
            {"defaults": {"models": {"openai/gpt-5.5": {"params": {"text_verbosity": "low"}}}}},
            None,
            None,
        ),
        (
            "agent params",
            {"list": [{"id": "writer", "params": {"temperature": 0.2}}]},
            "writer",
            None,
        ),
        (
            "session agent params",
            {"list": [{"id": "writer", "params": {"temperature": 0.2}}]},
            None,
            "agent:writer:main",
        ),
    ],
)
def test_authored_params_stay_on_openclaw(
    name: str, agents: dict, agent_id: str | None, session_key: str | None
) -> None:
    config = _openai_provider_config()
    config["agents"] = agents
    params = {
        "provider": "openai",
        "modelId": "gpt-5.5",
        "config": config,
        "env": {},
    }
    if agent_id is not None:
        params["agentId"] = agent_id
    if session_key is not None:
        params["sessionKey"] = session_key
    assert resolve_agent_harness_policy(params) == {
        "runtime": "openclaw",
        "runtimeSource": "implicit",
    }


def test_prepared_request_overrides_stay_on_openclaw() -> None:
    assert resolve_agent_harness_policy(
        {
            "provider": "openai",
            "modelId": "gpt-5.5",
            "modelApi": "openai-responses",
            "modelBaseUrl": "https://api.openai.com/v1",
            "requestTransportOverrides": "present",
            "env": {},
        }
    ) == {"runtime": "openclaw", "runtimeSource": "implicit"}


def test_global_params_apply_before_concrete_model_selection() -> None:
    config = _openai_provider_config()
    config["agents"] = {"defaults": {"params": {"temperature": 0.2}}}
    assert resolve_agent_harness_policy({"provider": "openai", "config": config, "env": {}}) == {
        "runtime": "openclaw",
        "runtimeSource": "implicit",
    }


@pytest.mark.parametrize(
    ("name", "models", "runtime"),
    [
        (
            "later route facts fill an omitted adapter",
            [{"id": "gpt-5.5"}, {"id": "gpt-5.5", "api": "openai-completions"}],
            "openclaw",
        ),
        (
            "a provider-looking native id stays distinct",
            [
                {"id": "openai/gpt-5.5", "api": "openai-responses"},
                {"id": "gpt-5.5", "api": "openai-completions"},
            ],
            "openclaw",
        ),
        (
            "an authored empty header map stays authoritative",
            [{"id": "gpt-5.5", "headers": {}}, {"id": "gpt-5.5", "headers": {"x-route": "custom"}}],
            "codex",
        ),
        (
            "later headers fill an omitted header map",
            [{"id": "gpt-5.5"}, {"id": "gpt-5.5", "headers": {"x-route": "custom"}}],
            "openclaw",
        ),
    ],
)
def test_duplicate_model_config_stays_aligned(name: str, models: list, runtime: str) -> None:
    assert resolve_agent_harness_policy(
        {
            "provider": "openai",
            "modelId": "gpt-5.5",
            "config": _openai_provider_config(models=models),
            "env": {},
        }
    ) == {"runtime": runtime, "runtimeSource": "implicit"}


def test_fail_closed_codex_policy_selects_codex() -> None:
    """Past-doc deployment shape: provider agentRuntime.id codex is fail-closed."""
    config = _openai_provider_config(agentRuntime={"id": "codex"})
    config["plugins"] = {"entries": {"codex": {"enabled": True}}}
    config["agents"] = {"defaults": {"model": "openai/gpt-5.6-sol"}}
    assert resolve_agent_harness_policy(
        {
            "provider": "openai",
            "modelId": "gpt-5.6-sol",
            "config": config,
            "env": {},
        }
    ) == {"runtime": "codex", "runtimeSource": "provider"}


def test_named_codex_agent_selects_codex() -> None:
    """Past-doc mixed deployment: a named agent with a codex model policy."""
    config = _openai_provider_config()
    config["plugins"] = {"entries": {"codex": {"enabled": True}}}
    config["agents"] = {
        "defaults": {"model": "anthropic/claude-opus-4-6"},
        "list": [
            {"id": "main", "model": "anthropic/claude-opus-4-6"},
            {
                "id": "codex",
                "model": "openai/gpt-5.6-sol",
                "models": {"openai/gpt-5.6-sol": {"agentRuntime": {"id": "codex"}}},
            },
        ],
    }
    assert resolve_agent_harness_policy(
        {
            "provider": "openai",
            "modelId": "gpt-5.6-sol",
            "config": config,
            "agentId": "codex",
            "env": {},
        }
    ) == {"runtime": "codex", "runtimeSource": "model"}
