"""Tests for src/agents/codex_harness.py.

Mirrors tests of extensions/codex/harness.ts in OpenClaw.
"""

from __future__ import annotations

from src.agents.codex_harness import (
    CODEX_HARNESS_ID,
    CODEX_HARNESS_LABEL,
    create_codex_app_server_agent_harness,
)


def test_create_codex_app_server_agent_harness_defaults():
    harness = create_codex_app_server_agent_harness()
    assert harness.id == CODEX_HARNESS_ID
    assert harness.label == CODEX_HARNESS_LABEL
    assert harness.provider_ids == ["codex", "openai"]
    assert harness.app_server_config.transport == "stdio"
    assert harness.app_server_config.homeScope == "agent"


def test_create_codex_app_server_agent_harness_custom():
    custom_cfg = {
        "transport": "websocket",
        "homeScope": "user",
        "url": "ws://localhost:39175",
        "authToken": "secret_token",
    }
    harness = create_codex_app_server_agent_harness("codex-custom", custom_cfg)
    assert harness.id == "codex-custom"
    assert harness.app_server_config.transport == "websocket"
    assert harness.app_server_config.homeScope == "user"
    assert harness.app_server_config.url == "ws://localhost:39175"
    assert harness.app_server_config.authToken == "secret_token"


def test_codex_harness_matches_openclaw_runtime_contract():
    harness = create_codex_app_server_agent_harness()

    assert harness.auto_selection == {"providerIds": ["codex", "openai"]}
    assert harness.cloud_placement == {
        "mode": "remote-exec",
        "devicePlacement": {
            "requiredNodeCommands": ["codex.exec-server.stdio.v1"],
            "consumesWorkerSlot": False,
        },
    }
    assert harness.delegated_execution_plugin_ids == ["voice-call"]
    assert harness.conversation_tool_policy_support == "exact"
    assert "image_generate" in harness.conversation_tool_policy_safe_deny_tools

    assert harness.supports({"provider": "codex", "requestedRuntime": "codex"}) == {
        "supported": True,
        "priority": 100,
    }
    assert harness.supports({"provider": "openai", "requestedRuntime": "codex"}) == {
        "supported": True,
        "priority": 100,
    }

    result = harness.supports(
        {
            "provider": "openai",
            "requestedRuntime": "codex",
            "modelProvider": {
                "requestTransportOverrides": "none",
                "preparedAuth": {"source": "harness"},
            },
        }
    )
    assert result["supported"] is False
    assert "not declared" in result["reason"]
