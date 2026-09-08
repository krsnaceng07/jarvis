"""jarvis.agents.openai_routing — OpenAI provider routing decisions.

OpenClaw parity: mirrors ``openclaw-main/src/agents/openai-routing.ts``.

Custom OpenAI-compatible base URLs intentionally bypass Codex-runtime
defaults. Only an exact official HTTPS Platform/ChatGPT route with no
authored provider request override may select Codex implicitly.
"""

from __future__ import annotations

from typing import Any

#: Canonical provider id for OpenAI-hosted model routes.
OPENAI_PROVIDER_ID = "openai"


def is_openai_provider(provider: Any) -> bool:
    """Mirror ``isOpenAIProvider``."""
    return isinstance(provider, str) and provider.strip().lower() == OPENAI_PROVIDER_ID


def parse_model_ref_provider(value: Any) -> str | None:
    """Parse the provider portion from a provider/model ref.

    Mirrors ``parseModelRefProvider``.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    slash = trimmed.find("/")
    if slash <= 0:
        return None
    return trimmed[:slash].strip().lower() or None


def resolve_openai_implicit_agent_runtime(params: dict[str, Any]) -> str | None:
    """Resolve the provider-owned implicit runtime for one OpenAI route.

    Mirrors ``resolveOpenAIImplicitAgentRuntime``: non-OpenAI providers
    return ``None``; unresolvable routes stay on the core OpenClaw runtime
    (endpoint/adapter ownership stays in the provider artifact).
    """
    from src.agents.model_extra_params import has_authored_provider_request_params  # noqa: PLC0415
    from src.agents.model_runtime_policy import resolve_agent_runtime_policy_agent_id  # noqa: PLC0415
    from src.agents.openai_model_routes import resolve_openai_model_routes  # noqa: PLC0415

    if not is_openai_provider(params.get("provider")):
        return None
    model_id = params.get("modelId")
    agent_id = resolve_agent_runtime_policy_agent_id(params)
    has_configured_params = has_authored_provider_request_params(
        {
            "config": params.get("config"),
            "provider": params.get("provider") or OPENAI_PROVIDER_ID,
            "modelId": model_id,
            "agentId": agent_id,
        }
    )
    transport_overrides = (
        "present"
        if params.get("requestTransportOverrides") == "present" or has_configured_params
        else "none"
    )
    resolution = resolve_openai_model_routes(
        {
            "provider": params.get("provider"),
            "modelId": model_id,
            "api": params.get("api"),
            "baseUrl": params.get("baseUrl"),
            "config": params.get("config"),
            "env": params.get("env"),
            "requestTransportOverrides": transport_overrides,
        }
    )
    if resolution is None:
        return "openclaw"
    if resolution.get("kind") != "incompatible" and resolution.get("defaultRuntimeId") == "codex":
        return "codex"
    return "openclaw"


def model_selection_should_ensure_codex_plugin(params: dict[str, Any]) -> bool:
    """Return whether model selection should ensure the Codex plugin exists.

    Mirrors ``modelSelectionShouldEnsureCodexPlugin``: explicit configured
    runtimes win; otherwise the implicit OpenAI route decides. The shipped
    whole-agent opt-out still suppresses implicit installation.
    """
    from src.agents.agent_runtime_id import (  # noqa: PLC0415
        is_default_agent_runtime_id,
        normalize_optional_agent_runtime_id,
        resolve_agent_scoped_runtime_override,
    )
    from src.agents.model_runtime_policy import resolve_model_runtime_policy  # noqa: PLC0415

    provider = parse_model_ref_provider(params.get("model"))
    if provider != OPENAI_PROVIDER_ID:
        return False
    model_ref = (params.get("model") or "").strip() if isinstance(params.get("model"), str) else ""
    slash = model_ref.find("/")
    model_id = model_ref[slash + 1 :] if slash >= 0 else None
    configured_policy = resolve_model_runtime_policy(
        {
            "config": params.get("config"),
            "provider": provider,
            "modelId": model_id,
            "agentId": params.get("agentId"),
        }
    ).get("policy")
    configured_runtime = normalize_optional_agent_runtime_id(
        configured_policy.get("id") if isinstance(configured_policy, dict) else None
    )
    if configured_runtime and not is_default_agent_runtime_id(configured_runtime):
        return configured_runtime == "codex"
    if configured_policy is None:
        agent_runtime = resolve_agent_scoped_runtime_override(
            {"config": params.get("config"), "agentId": params.get("agentId")}
        )
        if agent_runtime and not is_default_agent_runtime_id(agent_runtime):
            return agent_runtime == "codex"
    return (
        resolve_openai_implicit_agent_runtime(
            {
                "provider": provider,
                "modelId": model_id,
                "config": params.get("config"),
                "agentId": params.get("agentId"),
            }
        )
        == "codex"
    )


__all__ = [
    "OPENAI_PROVIDER_ID",
    "is_openai_provider",
    "model_selection_should_ensure_codex_plugin",
    "parse_model_ref_provider",
    "resolve_openai_implicit_agent_runtime",
]
