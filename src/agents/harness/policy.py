"""jarvis.agents.harness.policy — configured native harness policy.

OpenClaw parity: mirrors ``openclaw-main/src/agents/harness/policy.ts``.

Resolves model/provider/runtime config into the canonical harness runtime
id for a turn. Explicit ``agentRuntime`` policy is authoritative; ``auto``
(or absent) falls back to the provider-owned implicit runtime (today:
OpenAI official HTTPS routes resolve to Codex).
"""

from __future__ import annotations

from typing import Any

from src.agents.agent_runtime_id import (
    AUTO_AGENT_RUNTIME_ID,
    normalize_optional_agent_runtime_id,
)


def resolve_agent_harness_policy(params: dict[str, Any]) -> dict[str, Any]:
    """Resolve the effective harness runtime policy for a turn.

    Mirrors ``resolveAgentHarnessPolicy``. Returns ``{"runtime": ...,
    "runtimeSource": "model"|"provider"|"implicit"}`` (plus
    ``forcedByEnvironment`` when the QA override applies).
    """
    from src.agents.model_runtime_policy import resolve_model_runtime_policy  # noqa: PLC0415
    from src.agents.openai_routing import resolve_openai_implicit_agent_runtime  # noqa: PLC0415

    configured = resolve_model_runtime_policy(params)
    policy = configured.get("policy") if isinstance(configured, dict) else None
    configured_runtime = normalize_optional_agent_runtime_id(
        policy.get("id") if isinstance(policy, dict) else None
    )
    runtime = (
        configured_runtime
        if configured_runtime and configured_runtime != "default"
        else AUTO_AGENT_RUNTIME_ID
    )
    runtime_source = (
        "implicit"
        if runtime == AUTO_AGENT_RUNTIME_ID
        else (configured.get("source") if isinstance(configured, dict) else None) or "implicit"
    )
    if runtime != "auto":
        resolved: dict[str, Any] = {"runtime": runtime, "runtimeSource": runtime_source}
        if isinstance(configured, dict) and configured.get("forcedByEnvironment"):
            resolved["forcedByEnvironment"] = True
        return resolved
    implicit = resolve_openai_implicit_agent_runtime(
        {
            **params,
            "api": params.get("modelApi"),
            "baseUrl": params.get("modelBaseUrl"),
        }
    )
    if implicit:
        return {"runtime": implicit, "runtimeSource": runtime_source}
    return {"runtime": runtime, "runtimeSource": runtime_source}


__all__ = ["resolve_agent_harness_policy"]
