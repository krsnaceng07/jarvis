"""jarvis.config.codex_plugin_diagnostics — Codex plugin diagnostic gate.

OpenClaw parity: mirrors
``openclaw-main/src/config/codex-plugin-diagnostics.ts``.

Focused minimal port: exposes the diagnostic gate as a thin facade.
The route evaluation helpers are delegated to caller-provided callables
until the agent/runtime-policy and model-selection modules land.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional


CODEX_PLUGIN_ID = "codex"
OPENAI_PROVIDER_ID = "openai"


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
    # Disabled or missing entry: defer to the more expensive route check when
    # the helper wiring is in place; otherwise default to suppress.
    if not (
        callable(resolve_model_runtime_policy_fn)
        and callable(list_agent_ids_fn)
        and callable(resolve_openai_implicit_agent_runtime_fn)
        and callable(is_default_agent_runtime_id_fn)
        and callable(normalize_optional_agent_runtime_id_fn)
        and callable(parse_model_catalog_ref_fn)
    ):
        return entry_enabled is None
    agent_ids = list_agent_ids_fn(cfg)
    for agent_id in agent_ids:
        runtime_id = resolve_model_runtime_policy_fn({
            "config": cfg, "provider": OPENAI_PROVIDER_ID, "agentId": agent_id,
        }).get("policy", {}).get("id")
        if _configured_runtime_needs_codex(
            cfg, env, runtime_id, resolve_model_runtime_policy_fn=resolve_model_runtime_policy_fn,
            resolve_openai_implicit_agent_runtime_fn=resolve_openai_implicit_agent_runtime_fn,
            is_default_agent_runtime_id_fn=is_default_agent_runtime_id_fn,
            normalize_optional_agent_runtime_id_fn=normalize_optional_agent_runtime_id_fn,
        ):
            return False
    return True


def _configured_runtime_needs_codex(
    cfg: Any,
    env: dict,
    runtime_id: Any,
    *,
    resolve_model_runtime_policy_fn: Callable,
    resolve_openai_implicit_agent_runtime_fn: Callable,
    is_default_agent_runtime_id_fn: Callable,
    normalize_optional_agent_runtime_id_fn: Callable,
) -> bool:
    norm_id = normalize_optional_agent_runtime_id_fn(runtime_id)
    if norm_id == CODEX_PLUGIN_ID:
        return True
    if not is_default_agent_runtime_id_fn(norm_id):
        return False
    return resolve_openai_implicit_agent_runtime_fn({
        "provider": OPENAI_PROVIDER_ID,
        "config": cfg,
        "env": env,
    }) == CODEX_PLUGIN_ID


__all__ = [
    "CODEX_PLUGIN_ID",
    "OPENAI_PROVIDER_ID",
    "should_suppress_missing_codex_plugin_diagnostics",
]
