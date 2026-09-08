"""jarvis.config.codex_compaction_migration — Codex compaction config repair.

OpenClaw parity: mirrors the decision core of
``openclaw-main/src/commands/doctor/shared/codex-route-compaction-scan.ts``
(``collectUnsupportedCodexCompactionOverrides``,
``collectLegacyLosslessCompactionConfigs``) and
``openclaw-main/src/commands/doctor/shared/codex-route-compaction-repair.ts``
(``removeUnsupportedCodexCompactionOverrides``,
``maybeMigrateLegacyLosslessCompactionConfig``).

Rules (same as OpenClaw):
- Codex compacts through its native app-server thread state. Authored
  ``compaction.model`` / ``compaction.provider`` overrides on Codex-runtime
  agents are ignored at runtime, so doctor removes them:
  ``Removed <path>; Codex runtime uses native server-side compaction.``
- ``compaction.provider: "lossless-claw"`` on a Codex-runtime agent belongs
  in ``plugins.slots.contextEngine``. OpenClaw auto-migrates only when safe;
  Jarvis ships no lossless extension yet, so this port records a
  manual-migration warning instead of writing a slot that points nowhere.

An agent "uses Codex" (mirrors ``agentUsesCodexRuntimeForCompaction``)
when its concrete runtime id is ``codex``, else when its primary model
ref resolves to the Codex runtime through the harness policy. Defaults
compaction is inherited by entries that set no local compaction; repair
paths point at the defining location.
"""

from __future__ import annotations

from typing import Any

from jarvis_config_core.legacy_codex import to_canonical_openai_model_ref

#: Override keys Codex ignores at runtime. Mirrors
#: ``COMPACTION_OVERRIDE_KEYS``.
COMPACTION_OVERRIDE_KEYS: tuple[str, ...] = ("model", "provider")

#: Lossless context-engine id. Mirrors ``LOSSLESS_CONTEXT_ENGINE_ID``.
LOSSLESS_CONTEXT_ENGINE_ID = "lossless-claw"


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _agent_entries(cfg: Any):
    """Yield ``(path, agent_id, agent_dict)`` for defaults + roster entries."""
    if not isinstance(cfg, dict):
        return
    agents = cfg.get("agents")
    if not isinstance(agents, dict):
        return
    defaults = agents.get("defaults")
    if isinstance(defaults, dict):
        yield "agents.defaults", None, defaults
    listing = agents.get("list")
    if isinstance(listing, list):
        for index, entry in enumerate(listing):
            if not isinstance(entry, dict):
                continue
            raw_id = entry.get("id")
            yield f"agents.list.{index}", raw_id if isinstance(raw_id, str) else None, entry
    entries = agents.get("entries")
    if isinstance(entries, dict):
        for key, entry in entries.items():
            if isinstance(entry, dict):
                yield f"agents.entries.{key}", key, entry


def _read_primary_model_ref(agent: Any) -> str | None:
    """Return an agent scope's primary model ref. Mirrors
    ``readAgentPrimaryModelRef`` (``str`` or ``{primary: str}``)."""
    if not isinstance(agent, dict):
        return None
    model = agent.get("model")
    if isinstance(model, str) and model.strip():
        return model.strip()
    if isinstance(model, dict):
        primary = model.get("primary")
        if isinstance(primary, str) and primary.strip():
            return primary.strip()
    return None


def _concrete_runtime_id(cfg: Any, agent: Any, defaults: Any) -> str | None:
    """Return the explicit agentRuntime id for an agent scope, if any.

    Agent entry wins; defaults apply otherwise. Mirrors the
    ``resolveRuntime({agentRuntime, defaultsRuntime})`` + ``concreteRuntimeId``
    pair (``auto``/``default`` are not concrete).
    """
    from src.agents.agent_runtime_id import normalize_optional_agent_runtime_id  # noqa: PLC0415

    for scope in (agent, defaults):
        if not isinstance(scope, dict):
            continue
        runtime = scope.get("agentRuntime")
        runtime_id = runtime.get("id") if isinstance(runtime, dict) else None
        normalized = normalize_optional_agent_runtime_id(runtime_id)
        if normalized and normalized not in ("auto", "default"):
            return normalized
    return None


def _agent_uses_codex_runtime(cfg: Any, agent: Any, agent_id: Any, defaults: Any, env: Any) -> bool:
    """Mirror ``agentUsesCodexRuntimeForCompaction``."""
    from src.agents.openai_routing import resolve_openai_implicit_agent_runtime  # noqa: PLC0415

    concrete = _concrete_runtime_id(cfg, agent, defaults)
    if concrete is not None:
        return concrete == "codex"
    model_ref = _read_primary_model_ref(agent) or _read_primary_model_ref(defaults)
    if not model_ref:
        # No model selected in scope: fall back to the implicit default
        # route check (mirrors resolveImplicitDefaultAgentModelRef use).
        return (
            resolve_openai_implicit_agent_runtime(
                {"provider": "openai", "config": cfg, "env": env or {}}
            )
            == "codex"
        )
    if to_canonical_openai_model_ref(model_ref) is not None:
        return True
    slash = model_ref.find("/")
    provider = model_ref[:slash].strip().lower() if slash > 0 else ""
    model_id = model_ref[slash + 1 :].strip() if slash > 0 else model_ref
    if provider != "openai":
        return False
    return (
        resolve_openai_implicit_agent_runtime(
            {
                "provider": "openai",
                "modelId": model_id,
                "config": cfg,
                "env": env or {},
                "agentId": agent_id,
            }
        )
        == "codex"
    )


def _effective_compaction(
    agent: dict[str, Any], defaults: dict[str, Any] | None
) -> tuple[Any, str | None]:
    """Return ``(compaction_dict_or_None, defining_path_or_None)``.

    Entry-local compaction wins; otherwise defaults compaction is
    inherited. The caller supplies the entry path; defaults resolve to
    ``agents.defaults.compaction``.
    """
    local = agent.get("compaction")
    if isinstance(local, dict):
        return local, None  # path filled by caller
    if isinstance(defaults, dict) and isinstance(defaults.get("compaction"), dict):
        return defaults["compaction"], "agents.defaults.compaction"
    return None, None


def collect_codex_compaction_repairs(cfg: Any, env: Any = None) -> dict[str, list[dict[str, Any]]]:
    """Collect Codex compaction repairs without mutating *cfg*.

    Returns ``{"remove": [{path, key, value}], "lossless_warn":
    [{path, provider_path, provider_value, model_path?, model_value?}]}``.
    Mirrors ``collectUnsupportedCodexCompactionOverrides`` +
    ``collectLegacyLosslessCompactionConfigs`` (deduped).
    """
    remove: list[dict[str, Any]] = []
    lossless_warn: list[dict[str, Any]] = []
    seen_remove: set[str] = set()
    seen_lossless: set[str] = set()
    if not isinstance(cfg, dict):
        return {"remove": remove, "lossless_warn": lossless_warn}
    agents = cfg.get("agents")
    defaults = agents.get("defaults") if isinstance(agents, dict) else None
    defaults_dict = defaults if isinstance(defaults, dict) else None
    for scope_path, agent_id, agent in _agent_entries(cfg):
        if not _agent_uses_codex_runtime(cfg, agent, agent_id, defaults_dict, env):
            continue
        compaction, inherited_path = _effective_compaction(agent, defaults_dict)
        if not isinstance(compaction, dict):
            continue
        base_path = inherited_path or f"{scope_path}.compaction"
        provider = compaction.get("provider")
        if isinstance(provider, str) and provider.strip().lower() == LOSSLESS_CONTEXT_ENGINE_ID:
            model = compaction.get("model")
            hit: dict[str, Any] = {
                "path": scope_path,
                "provider_path": f"{base_path}.provider",
                "provider_value": provider.strip(),
            }
            if isinstance(model, str) and _is_nonempty_str(model):
                hit["model_path"] = f"{base_path}.model"
                hit["model_value"] = model.strip()
            key = f"{hit['provider_path']}\0{hit['provider_value']}\0{hit.get('model_path', '')}"
            if key not in seen_lossless:
                seen_lossless.add(key)
                lossless_warn.append(hit)
            continue
        for key in COMPACTION_OVERRIDE_KEYS:
            value = compaction.get(key)
            if not isinstance(value, str) or not _is_nonempty_str(value):
                continue
            hit_path = f"{base_path}.{key}"
            dedupe = f"{hit_path}\0{key}\0{value.strip()}"
            if dedupe in seen_remove:
                continue
            seen_remove.add(dedupe)
            remove.append({"path": hit_path, "key": key, "value": value.strip()})
    return {"remove": remove, "lossless_warn": lossless_warn}


def _delete_path_key(cfg: Any, dotted_path: str, key: str) -> bool:
    """Delete *key* at dot *path* (ending in ``.compaction``); prune empties.

    Numeric parts address list indices (``agents.list.0``). Agent ids are
    assumed dot-free (matches OpenClaw path building).
    """
    parts = dotted_path.split(".")
    node: Any = cfg
    trail: list[tuple[Any, Any]] = []
    for part in parts:
        if isinstance(node, list) and part.isdigit():
            index = int(part)
            if index >= len(node):
                return False
            trail.append((node, index))
            node = node[index]
            continue
        if not isinstance(node, dict) or part not in node:
            return False
        trail.append((node, part))
        node = node[part]
    if not isinstance(node, dict) or key not in node:
        return False
    del node[key]
    # Prune empty compaction dicts back up (mirrors the TS empty-check).
    for parent, part in reversed(trail):
        child = parent[part]
        if isinstance(child, dict) and len(child) == 0 and part == "compaction":
            del parent[part]
        else:
            break
    return True


def apply_codex_compaction_repairs(cfg: Any, env: Any = None) -> list[str]:
    """Apply Codex compaction repairs to *cfg* in place. Returns changes.

    Removes unsupported ``model``/``provider`` overrides on Codex-runtime
    agents (``Removed <path>; Codex runtime uses native server-side
    compaction.``). Lossless hits are NOT auto-migrated (no lossless
    extension ships yet) — they stay warnings via
    ``collect_codex_compaction_repairs``.
    """
    repairs = collect_codex_compaction_repairs(cfg, env)
    changes: list[str] = []
    for hit in repairs["remove"]:
        path, key = hit["path"], hit["key"]
        parent_path = path.rsplit(".", 1)[0] if "." in path else ""
        if parent_path and _delete_path_key(cfg, parent_path, key):
            changes.append(f"Removed {path}; Codex runtime uses native server-side compaction.")
    return changes


__all__ = [
    "COMPACTION_OVERRIDE_KEYS",
    "LOSSLESS_CONTEXT_ENGINE_ID",
    "apply_codex_compaction_repairs",
    "collect_codex_compaction_repairs",
]
