"""doctor — Core config migration contracts.

Mirrors OpenClaw's core doctor contracts.
"""

from typing import Any
import json
from jarvis_config_core import CONFIG_PATH
from jarvis_config_core.legacy_codex import (
    is_legacy_codex_provider_id,
    to_canonical_openai_model_ref,
)


def _migrate_tools_list(tools_list: Any, changes: list[str]) -> bool:
    if not isinstance(tools_list, list):
        return False
    modified = False
    for i, t in enumerate(tools_list):
        if t == "image":
            tools_list[i] = "view_image"
            changes.append("Migrated 'image' tool to 'view_image' in tool policy list")
            modified = True
    return modified


def _migrate_tool_filter(filter_dict: Any, changes: list[str]) -> bool:
    if not isinstance(filter_dict, dict):
        return False
    modified = False
    for key in ["include", "exclude", "allow", "deny"]:
        if key in filter_dict and _migrate_tools_list(filter_dict[key], changes):
            modified = True
    return modified


def _detect_and_migrate_image_tool(config: dict[str, Any], apply: bool) -> dict[str, Any]:
    """Detects and migrates the legacy 'image' tool to 'view_image'."""
    changes = []

    # Check top-level tools config (if it exists)
    tools_config = config.get("tools", {})
    if isinstance(tools_config, dict):
        if _migrate_tool_filter(tools_config.get("policy", {}), changes):
            pass
        if _migrate_tools_list(tools_config.get("allow"), changes):
            pass
        if _migrate_tools_list(tools_config.get("deny"), changes):
            pass

    # Check agent tools config
    agent_config = config.get("agent", {})
    if isinstance(agent_config, dict):
        agent_tools = agent_config.get("tools", {})
        if isinstance(agent_tools, dict):
            if _migrate_tool_filter(agent_tools.get("policy", {}), changes):
                pass
            if _migrate_tools_list(agent_tools.get("allow"), changes):
                pass
            if _migrate_tools_list(agent_tools.get("deny"), changes):
                pass

    # Check MCP tool filters
    mcp_config = config.get("mcp", {})
    if isinstance(mcp_config, dict):
        servers = mcp_config.get("servers", {})
        if isinstance(servers, dict):
            for server_name, server_config in servers.items():
                if isinstance(server_config, dict):
                    if _migrate_tool_filter(server_config.get("toolFilter", {}), changes):
                        pass

    return {"changes": changes if apply else [], "warnings": [], "has_findings": len(changes) > 0}


def detect_image_tool_migration(state_dir: Any, config: Any) -> Any:
    if not CONFIG_PATH.exists():
        return {"changes": [], "warnings": []}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {"changes": [], "warnings": []}

    res = _detect_and_migrate_image_tool(raw, apply=False)
    if res["has_findings"]:
        return [
            {"severity": "error", "message": "Legacy 'image' tool permission found in config.json"}
        ]
    return []


def apply_image_tool_migration(state_dir: Any, config: Any) -> Any:
    if not CONFIG_PATH.exists():
        return {"changes": [], "warnings": []}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        return {"changes": [], "warnings": [f"Failed to read config: {e}"]}

    res = _detect_and_migrate_image_tool(raw, apply=True)
    if res["changes"]:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2)
        except Exception as e:
            return {"changes": [], "warnings": [f"Failed to write config: {e}"]}
    return {"changes": res["changes"], "warnings": res["warnings"]}


core_config_doctor_contract = {
    "id": "core-config-image-tool-to-view-image",
    "version": "1.0.0",
    "detect": detect_image_tool_migration,
    "apply": apply_image_tool_migration,
}


# ---------------------------------------------------------------------------
# Legacy Codex model refs → openai/* (codex-route-model-ref parity)
# ---------------------------------------------------------------------------

#: Slots holding a primary model ref (legacy prefixes always rewrite).
#: Mirrors the primary/model/utility/compaction slots in the OpenClaw scan.
_PRIMARY_MODEL_SLOTS = frozenset({"model", "utilityModel", "pdfModel"})
#: Slots holding a media model ref (``codex/`` prefix is an intentional
#: bounded-turn routing signal and is preserved; ``openai-codex/`` still
#: rewrites — it is legacy everywhere). Mirrors the mediaModels
#: image/video slots in the OpenClaw scan, adapted to Jarvis's flat
#: ``*Model`` agent shape.
_IMAGE_MODEL_SLOTS = frozenset(
    {
        "imageModel",
        "visionModel",
        "imageGenerationModel",
        "videoGenerationModel",
        "musicGenerationModel",
        "voiceModel",
    }
)


def _is_image_slot(slot: str) -> bool:
    return slot in _IMAGE_MODEL_SLOTS


def _canonical_for_slot(value: Any, *, image_slot: bool) -> str | None:
    """Return the canonical rewrite for a legacy ref in *slot*, if any.

    ``openai-codex/`` rewrites in every slot; ``codex/`` rewrites in
    primary slots only (image slots keep it as the bounded-turn signal).
    """
    canonical = to_canonical_openai_model_ref(value)
    if canonical is None:
        return None
    if image_slot and isinstance(value, str) and value.strip().lower().startswith("codex/"):
        return None
    return canonical


def _iter_agent_scopes(raw: dict[str, Any]):
    """Yield ``(path, agent_dict)`` for defaults + every agent entry.

    Mirrors the defaults/list/entries roster walk: ``agents.defaults``,
    ``agents.list[]`` items, and ``agents.entries{}`` values.
    """
    agents = raw.get("agents")
    if not isinstance(agents, dict):
        return
    defaults = agents.get("defaults")
    if isinstance(defaults, dict):
        yield "agents.defaults", defaults
    listing = agents.get("list")
    if isinstance(listing, list):
        for index, entry in enumerate(listing):
            if isinstance(entry, dict):
                yield f"agents.list.{index}", entry
    entries = agents.get("entries")
    if isinstance(entries, dict):
        for key, entry in entries.items():
            if isinstance(entry, dict):
                yield f"agents.entries.{key}", entry


def _rewrite_model_value_slot(
    container: dict[str, Any], slot: str, path: str, *, apply: bool
) -> list[str]:
    """Rewrite one model-ref slot in place. Returns ``- path: old should
    become new.`` hit lines (OpenClaw warning shape)."""
    hits: list[str] = []
    value = container.get(slot)
    image_slot = _is_image_slot(slot)
    if isinstance(value, str):
        canonical = _canonical_for_slot(value, image_slot=image_slot)
        if canonical is not None and canonical != value.strip():
            hits.append(f"- {path}: {value.strip()} should become {canonical}.")
            if apply:
                container[slot] = canonical
    elif isinstance(value, dict):
        # ``{primary: "<ref>"}`` primary shape.
        primary = value.get("primary")
        if isinstance(primary, str):
            canonical = _canonical_for_slot(primary, image_slot=image_slot)
            if canonical is not None and canonical != primary.strip():
                hits.append(f"- {path}.primary: {primary.strip()} should become {canonical}.")
                if apply:
                    value["primary"] = canonical
        # ``{provider, model}`` split shape: legacy provider rewrites to openai.
        provider = value.get("provider")
        if isinstance(provider, str) and is_legacy_codex_provider_id(provider):
            hits.append(f"- {path}.provider: {provider.strip()} should become openai.")
            if apply:
                value["provider"] = "openai"
    return hits


def _rewrite_models_map_keys(
    models: Any, path: str, *, apply: bool, warnings: list[str]
) -> list[str]:
    """Rename legacy keys in an agent ``models`` map.

    Mirrors the models-map rewrite: rename when the canonical key is
    absent; when present the merge is blocked (user data is never dropped)
    and a warning is recorded instead.
    """
    hits: list[str] = []
    if not isinstance(models, dict):
        return hits
    for key in list(models.keys()):
        if not isinstance(key, str):
            continue
        canonical = to_canonical_openai_model_ref(key)
        if canonical is None or canonical == key:
            continue
        if canonical in models:
            warnings.append(
                f"- {path}.{key}: {key} should become {canonical} "
                "(canonical entry already present; merge manually)."
            )
            continue
        hits.append(f"- {path}.{key}: {key} should become {canonical}.")
        if apply:
            models[canonical] = models.pop(key)
    return hits


def _rewrite_allow_list(allow: Any, path: str, *, apply: bool) -> list[str]:
    """Rewrite legacy refs in a ``modelPolicy.allow`` list."""
    hits: list[str] = []
    if not isinstance(allow, list):
        return hits
    for index, entry in enumerate(allow):
        if not isinstance(entry, str):
            continue
        canonical = to_canonical_openai_model_ref(entry)
        if canonical is None or canonical == entry.strip():
            continue
        hits.append(f"- {path}.{index}: {entry.strip()} should become {canonical}.")
        if apply:
            allow[index] = canonical
    return hits


#: Legacy ChatGPT adapter id, renamed upstream. Mirrors
#: ``LEGACY_OPENAI_CODEX_RESPONSES_API``.
_LEGACY_CODEX_RESPONSES_API = "openai-codex-responses"
#: Canonical adapter id. Mirrors the ``openai-chatgpt-responses`` target.
_CHATGPT_RESPONSES_API = "openai-chatgpt-responses"


def _rewrite_legacy_provider_api(container: Any, path: str, *, apply: bool) -> list[str]:
    """Rewrite a legacy ``openai-codex-responses`` adapter id in place.

    Mirrors ``normalizeLegacyOpenAIResponsesApi`` (exact match only).
    Returns ``Moved ... → ...`` change lines.
    """
    changes: list[str] = []
    if not isinstance(container, dict):
        return changes
    if container.get("api") == _LEGACY_CODEX_RESPONSES_API:
        changes.append(
            f'Moved {path}.api "{_LEGACY_CODEX_RESPONSES_API}" → "{_CHATGPT_RESPONSES_API}".'
        )
        if apply:
            container["api"] = _CHATGPT_RESPONSES_API
    models = container.get("models")
    if isinstance(models, list):
        for index, row in enumerate(models):
            if isinstance(row, dict) and row.get("api") == _LEGACY_CODEX_RESPONSES_API:
                changes.append(
                    f"Moved {path}.models[{index}].api "
                    f'"{_LEGACY_CODEX_RESPONSES_API}" → "{_CHATGPT_RESPONSES_API}".'
                )
                if apply:
                    row["api"] = _CHATGPT_RESPONSES_API
    return changes


def _detect_and_migrate_legacy_codex_refs(raw: Any, apply: bool) -> dict[str, Any]:
    """Scan config model-ref slots for legacy Codex provider prefixes."""
    changes: list[str] = []
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return {"changes": changes, "warnings": warnings, "has_findings": False}
    # Provider tables (OpenClaw fleet shape): legacy adapter ids first.
    providers = raw.get("models")
    providers = providers.get("providers") if isinstance(providers, dict) else None
    if isinstance(providers, dict):
        for provider_id, provider_config in providers.items():
            if not isinstance(provider_id, str):
                continue
            changes.extend(
                _rewrite_legacy_provider_api(
                    provider_config, f"models.providers.{provider_id.strip()}", apply=apply
                )
            )
    # Top-level slots (canonical Jarvis shape).
    for slot in sorted(_PRIMARY_MODEL_SLOTS):
        if isinstance(raw.get(slot), (str, dict)):
            changes.extend(_rewrite_model_value_slot(raw, slot, slot, apply=apply))
    for slot in sorted(_IMAGE_MODEL_SLOTS):
        if isinstance(raw.get(slot), (str, dict)):
            changes.extend(_rewrite_model_value_slot(raw, slot, slot, apply=apply))
    # Agent roster slots (OpenClaw fleet shape).
    for scope_path, agent in _iter_agent_scopes(raw):
        for slot in sorted(_PRIMARY_MODEL_SLOTS):
            if isinstance(agent.get(slot), (str, dict)):
                changes.extend(
                    _rewrite_model_value_slot(agent, slot, f"{scope_path}.{slot}", apply=apply)
                )
        for slot in sorted(_IMAGE_MODEL_SLOTS):
            if isinstance(agent.get(slot), (str, dict)):
                changes.extend(
                    _rewrite_model_value_slot(agent, slot, f"{scope_path}.{slot}", apply=apply)
                )
        # Nested model holders (heartbeat / subagents / compaction). The
        # compaction slot is also covered by the codex-compaction migration,
        # which removes (rather than rewrites) overrides on Codex-runtime
        # agents; rewriting legacy refs here first is order-independent
        # because that removal is value-agnostic.
        for holder in ("heartbeat", "subagents", "compaction"):
            nested = agent.get(holder)
            if isinstance(nested, dict) and isinstance(nested.get("model"), (str, dict)):
                changes.extend(
                    _rewrite_model_value_slot(
                        nested, "model", f"{scope_path}.{holder}.model", apply=apply
                    )
                )
        changes.extend(
            _rewrite_models_map_keys(
                agent.get("models"), f"{scope_path}.models", apply=apply, warnings=warnings
            )
        )
        policy = agent.get("modelPolicy")
        if isinstance(policy, dict):
            changes.extend(
                _rewrite_allow_list(
                    policy.get("allow"), f"{scope_path}.modelPolicy.allow", apply=apply
                )
            )
    return {"changes": changes, "warnings": warnings, "has_findings": bool(changes or warnings)}


def _read_raw_config() -> dict[str, Any] | None:
    if not CONFIG_PATH.exists():
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def detect_legacy_codex_model_refs(state_dir: Any, config: Any) -> Any:
    raw = _read_raw_config()
    if raw is None:
        return []
    res = _detect_and_migrate_legacy_codex_refs(raw, apply=False)
    findings = [
        {"severity": "error", "message": f"Legacy Codex model ref found in config.json: {hit}"}
        for hit in res["changes"]
    ]
    findings.extend(
        {"severity": "warning", "message": f"Legacy Codex model ref needs manual merge: {w}"}
        for w in res["warnings"]
    )
    return findings


def apply_legacy_codex_model_refs(state_dir: Any, config: Any) -> Any:
    raw = _read_raw_config()
    if raw is None:
        return {"changes": [], "warnings": []}
    res = _detect_and_migrate_legacy_codex_refs(raw, apply=True)
    applied = [f"Rewrote legacy Codex model ref in config.json: {hit}" for hit in res["changes"]]
    if res["changes"]:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2)
        except Exception as e:
            return {"changes": [], "warnings": [f"Failed to write config: {e}"]}
    return {"changes": applied, "warnings": res["warnings"]}


core_legacy_codex_refs_doctor_contract = {
    "id": "core-config-legacy-codex-refs",
    "version": "1.0.0",
    "detect": detect_legacy_codex_model_refs,
    "apply": apply_legacy_codex_model_refs,
}


# ---------------------------------------------------------------------------
# Codex compaction overrides (codex-route-compaction parity)
# ---------------------------------------------------------------------------


def _codex_compaction_fns():
    """Lazy workspace-runtime import of the compaction migration.

    ``config_core`` stays importable standalone; the migration itself
    lives in ``src.config`` next to the harness policy it evaluates.
    """
    from src.config.codex_compaction_migration import (  # noqa: PLC0415
        apply_codex_compaction_repairs,
        collect_codex_compaction_repairs,
    )

    return collect_codex_compaction_repairs, apply_codex_compaction_repairs


def detect_codex_compaction_overrides(state_dir: Any, config: Any) -> Any:
    import os

    raw = _read_raw_config()
    if raw is None:
        return []
    try:
        collect, _apply = _codex_compaction_fns()
    except ImportError:
        return [
            {
                "severity": "warning",
                "message": "Codex compaction migration unavailable outside the workspace runtime.",
            }
        ]
    repairs = collect(raw, dict(os.environ))
    findings = [
        {
            "severity": "error",
            "message": f"Legacy Codex compaction override found in config.json: "
            f"{hit['path']} ({hit['value']})",
        }
        for hit in repairs["remove"]
    ]
    findings.extend(
        {
            "severity": "warning",
            "message": f"Lossless compaction on a Codex agent needs manual migration: "
            f"{hit['provider_path']} (no lossless extension ships yet).",
        }
        for hit in repairs["lossless_warn"]
    )
    return findings


def apply_codex_compaction_overrides(state_dir: Any, config: Any) -> Any:
    import os

    raw = _read_raw_config()
    if raw is None:
        return {"changes": [], "warnings": []}
    try:
        collect, apply = _codex_compaction_fns()
    except ImportError:
        return {
            "changes": [],
            "warnings": ["Codex compaction migration unavailable outside the workspace runtime."],
        }
    repairs = collect(raw, dict(os.environ))
    warnings = [
        f"Lossless compaction on a Codex agent needs manual migration: "
        f"{hit['provider_path']} (no lossless extension ships yet)."
        for hit in repairs["lossless_warn"]
    ]
    changes = apply(raw, dict(os.environ))
    if changes:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2)
        except Exception as e:
            return {"changes": [], "warnings": [f"Failed to write config: {e}"]}
    return {"changes": changes, "warnings": warnings}


core_codex_compaction_doctor_contract = {
    "id": "core-config-codex-compaction",
    "version": "1.0.0",
    "detect": detect_codex_compaction_overrides,
    "apply": apply_codex_compaction_overrides,
}
