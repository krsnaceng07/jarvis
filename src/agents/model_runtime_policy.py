"""jarvis.agents.model_runtime_policy — model runtime policy resolution.

OpenClaw parity: mirrors ``openclaw-main/src/agents/model-runtime-policy.ts``.

Resolves the effective ``agentRuntime`` policy for an agent/model/provider
selection. Precedence (highest first):

1. agent ``models`` map, exact model match
2. provider ``models`` list, exact model match
3. agent ``models`` map, provider-wildcard (``*``) match
4. provider ``agentRuntime``

An unqualified model id matching entries under multiple providers resolves
to ambiguous (no policy) rather than picking arbitrarily.
"""

from __future__ import annotations

import os
from typing import Any

from src.routing.agent_id import normalize_agent_id


def _normalize_provider_id(provider: Any) -> str:
    """Lowercase + strip a provider id. Mirrors ``normalizeProviderId``."""
    return provider.strip().lower() if isinstance(provider, str) else ""


def _parse_model_catalog_ref(value: Any) -> dict[str, str] | None:
    """Split a ``provider/model`` ref. Mirrors ``parseModelCatalogRef``."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    slash = trimmed.find("/")
    if slash <= 0 or slash >= len(trimmed) - 1:
        return None
    return {"provider": trimmed[:slash], "modelId": trimmed[slash + 1 :]}


def _has_runtime_policy(value: Any) -> bool:
    return (
        isinstance(value, dict) and isinstance(value.get("id"), str) and bool(value["id"].strip())
    )


def _resolve_provider_config(cfg: Any, provider: str | None) -> dict[str, Any] | None:
    """Find the provider config by exact then normalized id.

    Mirrors ``resolveProviderConfig``.
    """
    if not isinstance(cfg, dict) or not (isinstance(provider, str) and provider.strip()):
        return None
    providers = cfg.get("models")
    providers = providers.get("providers") if isinstance(providers, dict) else None
    if not isinstance(providers, dict):
        return None
    direct = providers.get(provider)
    if isinstance(direct, dict):
        return direct
    normalized = _normalize_provider_id(provider)
    for candidate_id, candidate_cfg in providers.items():
        if isinstance(candidate_cfg, dict) and _normalize_provider_id(candidate_id) == normalized:
            return candidate_cfg
    return None


def _normalize_model_id_for_provider(provider: str | None, model_id: str | None) -> str | None:
    """Strip a provider prefix only when it belongs to the selected provider.

    Mirrors ``normalizeModelIdForProvider``.
    """
    trimmed = model_id.strip() if isinstance(model_id, str) else ""
    if not trimmed:
        return None
    slash = trimmed.find("/")
    if slash <= 0:
        return trimmed
    model_provider = _normalize_provider_id(trimmed[:slash])
    expected = _normalize_provider_id(provider or "")
    if expected and model_provider != expected:
        return trimmed
    return trimmed[slash + 1 :].strip() or None


def _resolve_effective_provider(provider: str | None, model_id: str | None) -> str | None:
    """Resolve the effective provider from the caller or the model ref.

    Mirrors ``resolveEffectiveProvider``.
    """
    normalized = _normalize_provider_id(provider or "")
    if normalized:
        return normalized
    parsed = _parse_model_catalog_ref((model_id or "").strip() if model_id else "")
    return _normalize_provider_id(parsed["provider"]) if parsed else None


def _resolve_policy_match(matches: list[dict[str, Any]], caller_provider: str) -> dict[str, Any]:
    """Prefer caller-provider matches; flag cross-provider ambiguity.

    Mirrors ``resolvePolicyMatch``.
    """
    provider_matches = (
        [m for m in matches if m["provider"] == caller_provider] if caller_provider else []
    )
    candidates = provider_matches if provider_matches else matches
    if not candidates:
        return {}
    first = candidates[0]
    if not caller_provider and any(m["provider"] != first["provider"] for m in candidates):
        return {"ambiguous": True}
    return {
        "policy": first["policy"],
        "source": "model",
        "matchedProvider": first["provider"] or caller_provider,
    }


def _model_entry_match_kind(entry_id: Any, provider: str | None, model_id: str) -> str:
    """Classify an agent-models-map key against a resolved model.

    Mirrors ``modelEntryMatchKind``; returns ``"exact"``,
    ``"provider-wildcard"``, or ``"none"``.
    """
    trimmed = entry_id.strip() if isinstance(entry_id, str) else ""
    if not trimmed:
        return "none"
    if trimmed == model_id:
        return "exact"
    parsed = _parse_model_catalog_ref(trimmed)
    if parsed is None:
        return "none"
    caller_provider = _normalize_provider_id(provider or "")
    if caller_provider and _normalize_provider_id(parsed["provider"]) != caller_provider:
        return "none"
    if parsed["modelId"] == model_id:
        return "exact"
    if parsed["modelId"] == "*":
        return "provider-wildcard"
    return "none"


def _resolve_agent_entry(cfg: Any, agent_id: str | None) -> dict[str, Any] | None:
    """Point lookup of one raw agent entry. Mirrors the TS roster projection.

    NOTE: resolve_agent_config() projects entries (dropping agentRuntime),
    so match the raw entry via list_agent_entries instead.
    """
    from src.agents.agent_scope_config import list_agent_entries  # noqa: PLC0415

    if not isinstance(cfg, dict) or not (isinstance(agent_id, str) and agent_id.strip()):
        return None
    try:
        wanted = normalize_agent_id(agent_id)
    except Exception:
        return None
    for entry in list_agent_entries(cfg):
        try:
            if normalize_agent_id(entry.get("id", "")) == wanted:
                return entry
        except Exception:
            continue
    return None


def _resolve_agent_model_entry_runtime_policy(params: dict[str, Any]) -> dict[str, Any]:
    """Resolve runtime policy from agent/defaults ``models`` maps.

    Mirrors ``resolveAgentModelEntryRuntimePolicy``.
    """
    cfg = params.get("config")
    model_id = _normalize_model_id_for_provider(params.get("provider"), params.get("modelId"))
    match_kind = params.get("matchKind")
    if not isinstance(cfg, dict) or (not model_id and match_kind != "provider-wildcard"):
        return {}
    agent_id = params.get("agentId")
    agent_entry = _resolve_agent_entry(cfg, agent_id) if agent_id else None
    agents_block = cfg.get("agents")
    defaults = agents_block.get("defaults") if isinstance(agents_block, dict) else None
    model_maps = [
        agent_entry.get("models") if isinstance(agent_entry, dict) else None,
        defaults.get("models") if isinstance(defaults, dict) else None,
    ]
    caller_provider = _normalize_provider_id(params.get("provider") or "")
    for models in model_maps:
        scope_matches: list[dict[str, Any]] = []
        if not isinstance(models, dict):
            continue
        for key, entry in models.items():
            if _model_entry_match_kind(key, params.get("provider"), model_id or "") != match_kind:
                continue
            policy = entry.get("agentRuntime") if isinstance(entry, dict) else None
            if not _has_runtime_policy(policy):
                continue
            parsed = _parse_model_catalog_ref(key)
            scope_matches.append(
                {
                    "provider": _normalize_provider_id(parsed["provider"]) if parsed else "",
                    "policy": policy,
                }
            )
        resolved = _resolve_policy_match(scope_matches, caller_provider)
        if resolved.get("policy") is not None or resolved.get("ambiguous"):
            return resolved
    return {}


def _resolve_model_config(
    provider_config: dict[str, Any] | None, provider: str | None, model_id: str | None
) -> dict[str, Any] | None:
    """Find the exact provider-catalog model row. Mirrors ``resolveModelConfig``."""
    normalized = _normalize_model_id_for_provider(provider, model_id)
    if not normalized or not isinstance(provider_config, dict):
        return None
    models = provider_config.get("models")
    if not isinstance(models, list):
        return None
    for entry in models:
        if not isinstance(entry, dict):
            continue
        if _model_entry_match_kind(entry.get("id"), provider, normalized) == "exact":
            return entry
    return None


def _resolve_session_agent_id(cfg: Any, agent_id: Any, session_key: Any) -> str | None:
    """Resolve the session-owning agent id. Mirrors ``resolveSessionAgentIds``."""
    if isinstance(agent_id, str) and agent_id.strip():
        try:
            return normalize_agent_id(agent_id)
        except Exception:
            return None
    if isinstance(session_key, str) and session_key.startswith("agent:"):
        tail = session_key[len("agent:") :]
        candidate = tail.split(":", 1)[0] if ":" in tail else tail
        if candidate and candidate != "*":
            try:
                return normalize_agent_id(candidate)
            except Exception:
                return None
    return None


def resolve_agent_runtime_policy_agent_id(params: dict[str, Any]) -> str | None:
    """Resolve request hints; prepared owner facts never re-admit.

    Mirrors ``resolveAgentRuntimePolicyAgentId``.
    """
    from src.agents.agent_scope_config import resolve_default_agent_id  # noqa: PLC0415

    scope = params.get("agentScope")
    if isinstance(scope, dict) and scope.get("kind") == "prepared":
        return scope.get("agentId")
    cfg = params.get("config")
    agent_id = params.get("agentId")
    session_key = params.get("sessionKey")
    has_hint = (isinstance(agent_id, str) and bool(agent_id.strip())) or (
        isinstance(session_key, str) and bool(session_key.strip())
    )
    if cfg is not None and has_hint:
        resolved = _resolve_session_agent_id(cfg, agent_id, session_key)
        if resolved is not None:
            return resolved
        try:
            return resolve_default_agent_id(cfg)
        except Exception:
            return None
    return agent_id if isinstance(agent_id, str) else None


def resolve_model_runtime_policy(params: dict[str, Any]) -> dict[str, Any]:
    """Resolve the effective runtime policy for an agent/model/provider selection.

    Mirrors ``resolveModelRuntimePolicy``.
    """
    if os.environ.get("OPENCLAW_BUILD_PRIVATE_QA") == "1":
        forced = (os.environ.get("OPENCLAW_QA_FORCE_RUNTIME") or "").strip().lower()
        if forced in ("openclaw", "codex"):
            return {"policy": {"id": forced}, "source": "model", "forcedByEnvironment": True}

    caller_provider = _normalize_provider_id(params.get("provider") or "")
    effective_provider = _resolve_effective_provider(params.get("provider"), params.get("modelId"))
    inferred_matched = None if caller_provider else effective_provider

    has_scope = bool(
        params.get("agentScope") is not None
        or (isinstance(params.get("agentId"), str) and params["agentId"].strip())
        or (isinstance(params.get("sessionKey"), str) and params["sessionKey"].strip())
    )
    agent_id = resolve_agent_runtime_policy_agent_id(params) if has_scope else params.get("agentId")

    agent_model_policy = _resolve_agent_model_entry_runtime_policy(
        {**params, "agentId": agent_id, "provider": effective_provider, "matchKind": "exact"}
    )
    if agent_model_policy.get("ambiguous"):
        return {}
    if agent_model_policy.get("policy") is not None:
        return agent_model_policy

    provider_config = _resolve_provider_config(params.get("config"), effective_provider)
    model_config = _resolve_model_config(provider_config, effective_provider, params.get("modelId"))
    model_runtime = model_config.get("agentRuntime") if isinstance(model_config, dict) else None
    if isinstance(model_runtime, dict) and _has_runtime_policy(model_runtime):
        resolved: dict[str, Any] = {
            "policy": model_runtime,
            "source": "model",
        }
        if inferred_matched:
            resolved["matchedProvider"] = inferred_matched
        return resolved

    agent_wildcard_policy = _resolve_agent_model_entry_runtime_policy(
        {
            **params,
            "agentId": agent_id,
            "provider": effective_provider,
            "matchKind": "provider-wildcard",
        }
    )
    if agent_wildcard_policy.get("policy") is not None:
        return agent_wildcard_policy

    provider_runtime = (
        provider_config.get("agentRuntime") if isinstance(provider_config, dict) else None
    )
    if isinstance(provider_runtime, dict) and _has_runtime_policy(provider_runtime):
        resolved = {
            "policy": provider_runtime,
            "source": "provider",
        }
        if inferred_matched:
            resolved["matchedProvider"] = inferred_matched
        return resolved
    return {}


__all__ = [
    "resolve_agent_runtime_policy_agent_id",
    "resolve_model_runtime_policy",
]
