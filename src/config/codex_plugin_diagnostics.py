"""jarvis.config.codex_plugin_diagnostics — Codex plugin diagnostic gate.

OpenClaw parity: mirrors
``openclaw-main/src/config/codex-plugin-diagnostics.ts``.

The route evaluation helpers default to the canonical implementations
(``src/agents/*``); callers (notably tests) may still inject alternatives
via the ``*_fn`` keyword arguments.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional


CODEX_PLUGIN_ID = "codex"
OPENAI_PROVIDER_ID = "openai"


def _default_resolve_model_runtime_policy(params: Any) -> Any:
    from src.agents.model_runtime_policy import resolve_model_runtime_policy  # noqa: PLC0415

    return resolve_model_runtime_policy(params)


def _default_list_agent_ids(cfg: Any) -> Any:
    from src.agents.agent_scope_config import list_agent_ids  # noqa: PLC0415

    return list_agent_ids(cfg)


def _default_resolve_openai_implicit_agent_runtime(params: Any) -> Any:
    from src.agents.openai_routing import resolve_openai_implicit_agent_runtime  # noqa: PLC0415

    return resolve_openai_implicit_agent_runtime(params)


def _default_is_default_agent_runtime_id(runtime: Any) -> Any:
    from src.agents.agent_runtime_id import is_default_agent_runtime_id  # noqa: PLC0415

    return is_default_agent_runtime_id(runtime)


def _default_normalize_optional_agent_runtime_id(raw: Any) -> Any:
    from src.agents.agent_runtime_id import normalize_optional_agent_runtime_id  # noqa: PLC0415

    return normalize_optional_agent_runtime_id(raw)


def _default_parse_model_catalog_ref(value: Any) -> Any:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    slash = trimmed.find("/")
    if slash <= 0 or slash >= len(trimmed) - 1:
        return None
    return {"provider": trimmed[:slash], "modelId": trimmed[slash + 1 :]}


def should_suppress_missing_codex_plugin_diagnostics(
    cfg: Any,
    env: Optional[dict] = None,
    *,
    resolve_model_runtime_policy_fn: Optional[Callable] = None,
    list_agent_ids_fn: Optional[Callable] = None,
    resolve_openai_implicit_agent_runtime_fn: Optional[Callable] = None,
    is_default_agent_runtime_id_fn: Optional[Callable] = None,
    normalize_optional_agent_runtime_id_fn: Optional[Callable] = None,
    parse_model_catalog_ref_fn: Optional[Callable] = None,
) -> bool:
    """Return whether missing Codex diagnostics should be suppressed.

    Mirrors :func:`shouldSuppressMissingCodexPluginDiagnostics`
    (``shared/config/codex-plugin-diagnostics.ts`).
    """
    if not isinstance(cfg, dict):
        return True
    env = env if env is not None else dict(os.environ)
    entries = (cfg.get("plugins") or {}).get("entries") or {}
    if not isinstance(entries, dict):
        return True
    entry_enabled: Optional[bool] = None
    for plugin_id, entry in entries.items():
        if isinstance(plugin_id, str) and plugin_id.strip().lower() == CODEX_PLUGIN_ID:
            entry_enabled = (entry or {}).get("enabled") if isinstance(entry, dict) else None
            break
    if entry_enabled is True:
        return False
    # A disabled entry is an explicit opt-out; the doctor reports
    # selected-route conflicts separately, so the missing-plugin diagnostic
    # stays suppressed. Mirrors the TS early return exactly.
    if entry_enabled is False:
        return True
    resolve_model_runtime_policy_fn = (
        resolve_model_runtime_policy_fn or _default_resolve_model_runtime_policy
    )
    list_agent_ids_fn = list_agent_ids_fn or _default_list_agent_ids
    resolve_openai_implicit_agent_runtime_fn = (
        resolve_openai_implicit_agent_runtime_fn or _default_resolve_openai_implicit_agent_runtime
    )
    is_default_agent_runtime_id_fn = (
        is_default_agent_runtime_id_fn or _default_is_default_agent_runtime_id
    )
    normalize_optional_agent_runtime_id_fn = (
        normalize_optional_agent_runtime_id_fn or _default_normalize_optional_agent_runtime_id
    )
    # parse_model_catalog_ref_fn is retained for signature compatibility so
    # existing injected callers keep working; the canonical path below owns
    # ref parsing inside route resolution and no longer needs it.
    _ = parse_model_catalog_ref_fn
    return not _config_needs_codex_for_openai(
        cfg,
        env,
        resolve_model_runtime_policy_fn=resolve_model_runtime_policy_fn,
        list_agent_ids_fn=list_agent_ids_fn,
        resolve_openai_implicit_agent_runtime_fn=resolve_openai_implicit_agent_runtime_fn,
        is_default_agent_runtime_id_fn=is_default_agent_runtime_id_fn,
        normalize_optional_agent_runtime_id_fn=normalize_optional_agent_runtime_id_fn,
    )


def _config_needs_codex_for_openai(
    cfg: Any,
    env: dict,
    *,
    resolve_model_runtime_policy_fn: Callable,
    list_agent_ids_fn: Callable,
    resolve_openai_implicit_agent_runtime_fn: Callable,
    is_default_agent_runtime_id_fn: Callable,
    normalize_optional_agent_runtime_id_fn: Callable,
) -> bool:
    """Return whether any effective OpenAI route selects the Codex runtime.

    Mirrors the ``configNeedsCodexForOpenAi`` / ``defaultOpenAiRouteNeedsCodex``
    / ``configuredProviderPoliciesNeedCodex`` core of
    ``codex-plugin-diagnostics.ts``: per-agent generic provider policy first,
    then explicit per-model rows under OpenAI providers. (The full
    alias/heartbeat/subagent/fallback sweep lives in model-selection and is
    a follow-up; the three documented deployment shapes are covered here.)
    """
    agent_ids = list_agent_ids_fn(cfg) or []
    for agent_id in agent_ids:
        policy = (
            resolve_model_runtime_policy_fn(
                {"config": cfg, "provider": OPENAI_PROVIDER_ID, "agentId": agent_id}
            ).get("policy")
            or {}
        )
        if _configured_runtime_needs_codex(
            cfg,
            env,
            policy.get("id"),
            agent_id=agent_id,
            resolve_openai_implicit_agent_runtime_fn=resolve_openai_implicit_agent_runtime_fn,
            is_default_agent_runtime_id_fn=is_default_agent_runtime_id_fn,
            normalize_optional_agent_runtime_id_fn=normalize_optional_agent_runtime_id_fn,
        ):
            return True
    providers = (cfg.get("models") or {}).get("providers") if isinstance(cfg, dict) else None
    if not isinstance(providers, dict):
        return False
    for provider_id, provider_config in providers.items():
        if (
            not isinstance(provider_id, str)
            or provider_id.strip().lower() != OPENAI_PROVIDER_ID
            or not isinstance(provider_config, dict)
        ):
            continue
        for row in provider_config.get("models") or []:
            if not isinstance(row, dict):
                continue
            model_id = row.get("id") if isinstance(row.get("id"), str) else None
            bare_id = _bare_model_id(model_id)
            for agent_id in agent_ids:
                policy = (
                    resolve_model_runtime_policy_fn(
                        {
                            "config": cfg,
                            "provider": OPENAI_PROVIDER_ID,
                            "modelId": bare_id,
                            "agentId": agent_id,
                        }
                    ).get("policy")
                    or {}
                )
                if _configured_runtime_needs_codex(
                    cfg,
                    env,
                    policy.get("id"),
                    model_id=bare_id,
                    agent_id=agent_id,
                    resolve_openai_implicit_agent_runtime_fn=resolve_openai_implicit_agent_runtime_fn,
                    is_default_agent_runtime_id_fn=is_default_agent_runtime_id_fn,
                    normalize_optional_agent_runtime_id_fn=normalize_optional_agent_runtime_id_fn,
                ):
                    return True
    return False


def _bare_model_id(model_id: Any) -> Any:
    """Strip a same-provider ``openai/`` prefix from a catalog row id."""
    if not isinstance(model_id, str):
        return model_id
    trimmed = model_id.strip()
    slash = trimmed.find("/")
    if slash > 0 and trimmed[:slash].strip().lower() == OPENAI_PROVIDER_ID:
        return trimmed[slash + 1 :].strip() or trimmed
    return trimmed


def _configured_runtime_needs_codex(
    cfg: Any,
    env: dict,
    runtime_id: Any,
    *,
    resolve_openai_implicit_agent_runtime_fn: Callable,
    is_default_agent_runtime_id_fn: Callable,
    normalize_optional_agent_runtime_id_fn: Callable,
    model_id: Any = None,
    agent_id: Any = None,
) -> bool:
    """Mirror ``configuredRuntimeNeedsCodex`` (codex-plugin-diagnostics.ts)."""
    norm_id = normalize_optional_agent_runtime_id_fn(runtime_id)
    if norm_id == CODEX_PLUGIN_ID:
        return True
    if not is_default_agent_runtime_id_fn(norm_id):
        return False
    params: dict[str, Any] = {"provider": OPENAI_PROVIDER_ID, "config": cfg, "env": env}
    if model_id is not None:
        params["modelId"] = model_id
    if agent_id is not None:
        params["agentId"] = agent_id
    return resolve_openai_implicit_agent_runtime_fn(params) == CODEX_PLUGIN_ID


__all__ = [
    "CODEX_PLUGIN_ID",
    "OPENAI_PROVIDER_ID",
    "should_suppress_missing_codex_plugin_diagnostics",
]
