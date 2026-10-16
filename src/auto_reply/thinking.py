"""auto_reply/thinking — thinking/reasoning level catalog helpers.

Mirrors OpenClaw ``src/auto-reply/thinking.ts`` +
``src/auto-reply/thinking.shared.ts``.

Ported functions (all with the same names as the TypeScript originals,
converted to snake_case):
  - normalize_think_level
  - is_session_default_directive_value
  - resolve_thinking_default_for_model
  - normalize_verbose_level
  - normalize_trace_level
  - normalize_usage_display / resolve_response_usage_mode
  - resolve_effective_response_usage
  - normalize_elevated_level
  - normalize_reasoning_level
  - normalize_fast_mode (passthrough)
  - list_thinking_levels / list_thinking_level_labels / list_thinking_level_options
  - format_thinking_levels
  - is_thinking_level_supported
  - resolve_supported_thinking_level
  - resolve_thinking_default_for_model (full catalog version)

Provider plugin hooks (resolve_provider_*) are importable from this module so
tests can patch them via module-attribute injection; they default to None-return
stubs.
"""

from __future__ import annotations

import re
from typing import Any, Literal, cast

# ── Canonical types ────────────────────────────────────────────────────

ThinkLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh", "adaptive", "max", "ultra"]
VerboseLevel = Literal["off", "on", "full"]
TraceLevel = Literal["off", "on", "raw"]
ElevatedLevel = Literal["off", "on", "ask", "full"]
ReasoningLevel = Literal["off", "on", "stream"]
FastMode = Literal["off", "on", "auto"]
UsageDisplayLevel = Literal["off", "tokens", "full"]

ALL_THINKING_LEVELS: tuple[ThinkLevel, ...] = (
    "off", "minimal", "low", "medium", "high", "xhigh", "adaptive", "max", "ultra",
)

BASE_THINKING_LEVELS: tuple[ThinkLevel, ...] = ("off", "minimal", "low", "medium", "high")

THINKING_LEVEL_RANKS: dict[str, int] = {
    "off": 0,
    "minimal": 10,
    "low": 20,
    "medium": 30,
    "high": 40,
    "adaptive": 30,
    "xhigh": 60,
    "max": 70,
    "ultra": 80,
}

THINKING_LEVELS_HELP: str = "|".join(ALL_THINKING_LEVELS)


# ── Provider plugin hook stubs (patched by tests / real plugins) ────────
# These must live at module level so the test can do:
#   thinking_mod.resolve_provider_binary_thinking = mock_fn

def resolve_provider_binary_thinking(params: Any) -> Any:  # noqa: ANN401
    return None

def resolve_provider_default_thinking_level(params: Any) -> Any:  # noqa: ANN401
    return None

def resolve_provider_thinking_profile(params: Any, options: dict[str, Any] | None = None) -> Any:  # noqa: ANN401
    return None


def resolve_provider_xhigh_thinking(params: Any) -> Any:  # noqa: ANN401
    return None


# ── Helpers ────────────────────────────────────────────────────────────

def _lower(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.strip().lower()


def _collapse(key: str) -> str:
    return re.sub(r"[\s_\-]+", "", key)


# ── Core normalisers ───────────────────────────────────────────────────

def normalize_think_level(raw: str | None) -> ThinkLevel | None:
    """Normalize user-provided thinking level strings to the canonical enum."""
    key = _lower(raw)
    if not key:
        return None
    collapsed = _collapse(key)
    if collapsed in ("adaptive", "auto"):
        return "adaptive"
    if collapsed == "max":
        return "max"
    if collapsed == "ultra":
        return "ultra"
    if collapsed in ("xhigh", "extrahigh"):
        return "xhigh"
    if key == "off":
        return "off"
    if key in ("on", "enable", "enabled"):
        return "low"
    if key in ("min", "minimal"):
        return "minimal"
    if key in ("low", "thinkhard", "think-hard", "think_hard"):
        return "low"
    if key in ("mid", "med", "medium", "thinkharder", "think-harder", "harder"):
        return "medium"
    if key in ("high", "ultrathink", "thinkhardest", "highest"):
        return "high"
    if key == "think":
        return "minimal"
    return None


def is_session_default_directive_value(raw: str | None) -> bool:
    key = _lower(raw)
    if not key:
        return False
    return key in ("default", "inherit", "inherited", "clear", "reset", "unpin")


def normalize_fast_mode(raw: str | None) -> FastMode | None:
    key = _lower(raw)
    if not key:
        return None
    if key in ("off", "false", "no", "0"):
        return "off"
    if key in ("on", "true", "yes", "1"):
        return "on"
    if key in ("auto",):
        return "auto"
    return None


def normalize_verbose_level(raw: str | None) -> VerboseLevel | None:
    key = _lower(raw)
    if not key:
        return None
    if key in ("off", "false", "no", "0"):
        return "off"
    if key in ("full", "all", "everything"):
        return "full"
    if key in ("on", "minimal", "true", "yes", "1"):
        return "on"
    return None


def normalize_trace_level(raw: str | None) -> TraceLevel | None:
    key = _lower(raw)
    if not key:
        return None
    if key in ("off", "false", "no", "0"):
        return "off"
    if key in ("on", "true", "yes", "1"):
        return "on"
    if key in ("raw", "unfiltered"):
        return "raw"
    return None


def normalize_elevated_level(raw: str | None) -> ElevatedLevel | None:
    if not raw:
        return None
    key = _lower(raw)
    if key in ("off", "false", "no", "0"):
        return "off"
    if key in ("full", "auto", "auto-approve", "autoapprove"):
        return "full"
    if key in ("ask", "prompt", "approval", "approve"):
        return "ask"
    if key in ("on", "true", "yes", "1"):
        return "on"
    return None


def normalize_reasoning_level(raw: str | None) -> ReasoningLevel | None:
    if not raw:
        return None
    key = _lower(raw)
    if key in ("off", "false", "no", "0", "hide", "hidden", "disable", "disabled"):
        return "off"
    if key in ("on", "true", "yes", "1", "show", "visible", "enable", "enabled"):
        return "on"
    if key in ("stream", "streaming", "draft", "live"):
        return "stream"
    return None


def normalize_usage_display(raw: str | None) -> UsageDisplayLevel | None:
    if not raw:
        return None
    key = _lower(raw)
    if key in ("off", "false", "no", "0", "disable", "disabled"):
        return "off"
    if key in ("on", "true", "yes", "1", "enable", "enabled"):
        return "tokens"
    if key in ("tokens", "token", "tok", "minimal", "min"):
        return "tokens"
    if key in ("full", "session"):
        return "full"
    return None


def resolve_response_usage_mode(raw: str | None) -> UsageDisplayLevel:
    return normalize_usage_display(raw) or "off"


def _resolve_messages_response_usage_default(
    configured: Any,
    channel: str | None = None,
) -> str | None:
    if isinstance(configured, str):
        return configured
    if isinstance(configured, dict):
        # Narrow types: prefer channel-specific string, then explicit "default" string.
        cfg = cast(dict[str, Any], configured)
        ch_val = cfg.get(channel) if channel else None
        if isinstance(ch_val, str):
            return ch_val
        default_val = cfg.get("default")
        if isinstance(default_val, str):
            return default_val
        return None
    return None


def resolve_effective_response_usage(
    session_raw: str | None,
    configured: Any,
    channel: str | None = None,
) -> UsageDisplayLevel:
    session_normalized = normalize_usage_display(session_raw)
    if session_normalized is not None:
        return session_normalized
    config_default = _resolve_messages_response_usage_default(configured, channel)
    return resolve_response_usage_mode(config_default)


# ── Catalog-level helpers ──────────────────────────────────────────────


def _resolve_catalog_entry(
    provider: str | None,
    model: str | None,
    catalog: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if not catalog:
        return None
    provider = provider or ""
    model = model or ""
    for entry in catalog:
        if not isinstance(entry, dict):
            continue
        entry_provider = entry.get("provider")
        entry_id = entry.get("id")
        if entry_provider == provider and entry_id == model:
            return cast(dict[str, Any], entry)
        if entry_provider == provider and entry_id in {model, f"{provider}/{model}"}:
            return cast(dict[str, Any], entry)
    return None


def _normalize_catalog_list(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    catalog_list: list[dict[str, Any]] = []
    for item in cast(list[Any], value):
        if isinstance(item, dict):
            catalog_list.append(cast(dict[str, Any], item))
    return catalog_list


def _normalize_supported_levels(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    string_levels: list[str] = []
    for item in cast(list[Any], value):
        if isinstance(item, str):
            string_levels.append(item)
    return string_levels


def _catalog_reasoning(catalog: list[dict[str, Any]] | None, provider: str | None, model: str | None) -> bool | None:
    entry = _resolve_catalog_entry(provider, model, catalog)
    if entry is None:
        return None
    value = entry.get("reasoning")
    if isinstance(value, bool):
        return value
    return None


def _catalog_compat(catalog: list[dict[str, Any]] | None, provider: str | None, model: str | None) -> dict[str, Any]:
    entry = _resolve_catalog_entry(provider, model, catalog)
    if entry is None:
        return {}
    compat = entry.get("compat")
    if isinstance(compat, dict):
        return cast(dict[str, Any], compat)
    return {}


def _catalog_default_level(catalog: list[dict[str, Any]] | None, provider: str | None, model: str | None) -> str | None:
    entry = _resolve_catalog_entry(provider, model, catalog)
    if entry is None:
        return None
    if isinstance(entry.get("defaultThinkingLevel"), str):
        return entry.get("defaultThinkingLevel")
    return None


def _looks_like_claude_like(provider: str | None, model: str | None, catalog_entry: dict[str, Any] | None) -> bool:
    provider_key = (provider or "").lower()
    model_key = (model or "").lower()
    canonical = None
    if catalog_entry and isinstance(catalog_entry.get("params"), dict):
        canonical_value = catalog_entry["params"].get("canonicalModelId")
        if isinstance(canonical_value, str):
            canonical = canonical_value
    if isinstance(canonical, str) and canonical.lower().startswith("claude"):
        return True
    if provider_key in {"anthropic", "jdcloud-anthropic", "microsoft-foundry", "proxy", "claude-cli"}:
        api = catalog_entry.get("api") if catalog_entry else None
        if isinstance(api, str) and api != "anthropic-messages":
            return False
        return model_key.startswith("claude") or model_key.startswith("anthropic")
    if model_key.startswith("claude") or model_key.startswith("anthropic"):
        return True
    return False


def _build_provider_payload(
    provider: str | None,
    model: str | None,
    catalog: list[dict[str, Any]] | None,
    agent_runtime: str | None,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": provider or "",
        "model": model or "",
        "catalog": catalog or [],
        "context": {
            "modelId": model or "",
            "reasoning": _catalog_reasoning(catalog, provider, model),
            "compat": _catalog_compat(catalog, provider, model),
            "agentRuntime": agent_runtime or "codex",
        },
    }
    if params:
        payload.update(params)
    return payload


def _normalize_profile_levels(raw_levels: Any) -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = []
    if not isinstance(raw_levels, list):
        return levels
    for raw in cast(list[Any], raw_levels):
        if isinstance(raw, str):
            normalized = normalize_think_level(raw)
            if normalized:
                levels.append({"id": normalized, "label": normalized})
        elif isinstance(raw, dict):
            raw_dict = cast(dict[str, Any], raw)
            level_id = raw_dict.get("id") or raw_dict.get("level")
            normalized = normalize_think_level(level_id if isinstance(level_id, str) else None)
            if normalized:
                levels.append({
                    "id": normalized,
                    "label": raw_dict.get("label") or normalized,
                })
    return levels


def _resolve_profile_levels(
    provider: str | None,
    model: str | None,
    catalog: list[dict[str, Any]] | None,
    agent_runtime: str | None,
    *,
    options: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    payload = _build_provider_payload(provider, model, catalog, agent_runtime)
    profile = resolve_provider_thinking_profile(payload, options)
    if not isinstance(profile, dict):
        return [], None
    profile_dict = cast(dict[str, Any], profile)
    levels = _normalize_profile_levels(profile_dict.get("levels"))
    return levels, profile_dict


def _resolve_supported_levels(
    provider: str | None,
    model: str | None,
    catalog: list[dict[str, Any]] | None,
    agent_runtime: str | None,
    *,
    options: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    profile_levels, profile = _resolve_profile_levels(
        provider, model, catalog, agent_runtime, options=options
    )
    reasoning = _catalog_reasoning(catalog, provider, model)
    preserve = (
        isinstance(profile, dict)
        and profile.get("preserveWhenCatalogReasoningFalse") is True
    )
    if profile_levels and (reasoning is not False or preserve):
        return profile_levels, profile

    payload = _build_provider_payload(provider, model, catalog, agent_runtime)
    binary = resolve_provider_binary_thinking(payload)
    if binary is True:
        return [
            {"id": "off", "label": "off"},
            {"id": "low", "label": "on"},
        ], None

    catalog_entry = _resolve_catalog_entry(provider, model, catalog)
    claude_like = _looks_like_claude_like(provider, model, catalog_entry)
    if reasoning is False and not claude_like:
        return [{"id": "off", "label": "off"}], None

    supports_xhigh = False
    xhigh_result = resolve_provider_xhigh_thinking(payload)
    if xhigh_result is True:
        supports_xhigh = True
    elif (provider or "").lower() in {"openai", "github-copilot"} and (model or "") in {
        "gpt-5.4",
        "gpt-5.4-pro",
        "gpt-5.3-codex-spark",
    }:
        supports_xhigh = True
    elif claude_like:
        supports_xhigh = True
    else:
        provider_key = (provider or "").lower()
        if provider_key not in {"anthropic", "jdcloud-anthropic", "microsoft-foundry", "proxy", "claude-cli"}:
            compat = _catalog_compat(catalog, provider, model)
            support_list = compat.get("supportedReasoningEfforts")
            if isinstance(support_list, list):
                for item in cast(list[Any], support_list):
                    if isinstance(item, str) and item == "xhigh":
                        supports_xhigh = True
                        break

    if claude_like:
        levels = [
            {"id": "off", "label": "off"},
            {"id": "minimal", "label": "minimal"},
            {"id": "low", "label": "low"},
            {"id": "medium", "label": "medium"},
            {"id": "adaptive", "label": "adaptive"},
            {"id": "high", "label": "high"},
        ]
        if supports_xhigh:
            levels.append({"id": "xhigh", "label": "xhigh"})
        levels.append({"id": "max", "label": "max"})
        return levels, None

    if reasoning is True:
        levels = [
            {"id": "off", "label": "off"},
            {"id": "minimal", "label": "minimal"},
            {"id": "low", "label": "low"},
            {"id": "medium", "label": "medium"},
            {"id": "high", "label": "high"},
        ]
        if supports_xhigh:
            levels.append({"id": "xhigh", "label": "xhigh"})
        return levels, None

    base = [
        {"id": "off", "label": "off"},
        {"id": "minimal", "label": "minimal"},
        {"id": "low", "label": "low"},
        {"id": "medium", "label": "medium"},
        {"id": "high", "label": "high"},
    ]
    if supports_xhigh:
        base.append({"id": "xhigh", "label": "xhigh"})
    return base, None


def _coerce_thinking_payload(
    provider: Any,
    model: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
    agent_runtime: str | None = None,
    *,
    level: str | None = None,
    supported: list[str] | None = None,
) -> tuple[str | None, str | None, list[dict[str, Any]] | None, str | None, str | None, list[str] | None]:
    if isinstance(provider, dict):
        payload = cast(dict[str, Any], provider)
        provider_name = payload.get("provider")
        model_name = payload.get("model") or payload.get("modelId")
        catalog_value = _normalize_catalog_list(payload.get("catalog"))
        runtime = payload.get("agentRuntime")
        level_value = payload.get("level")
        supported_value = _normalize_supported_levels(payload.get("supported"))
        return (
            provider_name if isinstance(provider_name, str) else None,
            model_name if isinstance(model_name, str) else None,
            catalog_value,
            runtime if isinstance(runtime, str) else None,
            level_value if isinstance(level_value, str) else None,
            supported_value,
        )
    return provider, model, catalog, agent_runtime, level, supported


def resolve_thinking_default_for_model(
    provider: Any = "",
    model: str = "",
    catalog: list[dict[str, Any]] | None = None,
    *,
    params: dict[str, Any] | None = None,
) -> ThinkLevel:
    provider_name, model_name, catalog_value, agent_runtime, _level, _supported = _coerce_thinking_payload(provider, model, catalog, None)

    payload = _build_provider_payload(provider_name, model_name, catalog_value, agent_runtime, params=params)
    plugin_result = resolve_provider_default_thinking_level(payload)
    if plugin_result and isinstance(plugin_result, str):
        normalized = normalize_think_level(plugin_result)
        if normalized:
            return normalized

    binary = resolve_provider_binary_thinking(payload)
    if binary is True:
        return "low"

    reasoning = _catalog_reasoning(catalog_value, provider_name, model_name)
    catalog_entry = _resolve_catalog_entry(provider_name, model_name, catalog_value)
    if reasoning is False and not _looks_like_claude_like(provider_name, model_name, catalog_entry):
        return "off"

    _, profile = _resolve_profile_levels(provider_name, model_name, catalog_value, agent_runtime)
    if profile and isinstance(profile.get("defaultLevel"), str):
        normalized = normalize_think_level(profile.get("defaultLevel"))
        if normalized:
            return normalized

    if catalog_entry and isinstance(catalog_entry.get("params"), dict):
        canonical = catalog_entry["params"].get("canonicalModelId")
        if isinstance(canonical, str) and canonical == "claude-fable-5":
            return "high"

    reasoning = _catalog_reasoning(catalog_value, provider_name, model_name)
    if reasoning is False:
        return "off"
    if reasoning is True:
        return "medium"
    return "off"


def list_thinking_levels(
    provider: Any = None,
    model: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
    agent_runtime: str | None = None,
) -> list[ThinkLevel]:
    provider_name, model_name, catalog_value, runtime, _, _ = _coerce_thinking_payload(provider, model, catalog, agent_runtime)
    levels, _ = _resolve_supported_levels(provider_name, model_name, catalog_value, runtime)
    return [entry["id"] for entry in levels]


def list_thinking_level_labels(
    provider: Any = None,
    model: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
    agent_runtime: str | None = None,
) -> list[str]:
    provider_name, model_name, catalog_value, runtime, _, _ = _coerce_thinking_payload(provider, model, catalog, agent_runtime)
    levels, _ = _resolve_supported_levels(provider_name, model_name, catalog_value, runtime)
    return [entry["label"] for entry in levels]


def list_thinking_level_options(
    provider: Any = None,
    model: str | None = None,
    catalog: list[dict[str, Any]] | None = None,
    agent_runtime: str | None = None,
) -> list[dict[str, Any]]:
    provider_name, model_name, catalog_value, runtime, _, _ = _coerce_thinking_payload(provider, model, catalog, agent_runtime)
    levels, _ = _resolve_supported_levels(provider_name, model_name, catalog_value, runtime)
    return [{"id": entry["id"], "label": entry["label"]} for entry in levels]


def format_thinking_levels(
    provider: Any = None,
    model: str | None = None,
    separator: str = "|",
    catalog: list[dict[str, Any]] | None = None,
    agent_runtime: str | None = None,
) -> str:
    levels = list_thinking_levels(provider, model, catalog, agent_runtime)
    return separator.join(levels)


def is_thinking_level_supported(
    level: Any,
    supported: Any = None,
) -> bool:
    if isinstance(level, dict):
        payload = cast(dict[str, Any], level)
        provider_name = payload.get("provider") if isinstance(payload.get("provider"), str) else None
        model_name = payload.get("model") or payload.get("modelId")
        model_name = model_name if isinstance(model_name, str) else None
        catalog_value = _normalize_catalog_list(payload.get("catalog"))
        runtime = payload.get("agentRuntime") if isinstance(payload.get("agentRuntime"), str) else None
        level_value = payload.get("level")
        level_value = level_value if isinstance(level_value, str) else None
        supported_levels = _normalize_supported_levels(payload.get("supported"))
    else:
        provider_name = None
        model_name = None
        catalog_value = None
        runtime = None
        level_value = level
        supported_levels = _normalize_supported_levels(supported)

    if level_value is None:
        return False
    normalized = normalize_think_level(level_value)
    if not normalized:
        return False
    if supported_levels is not None:
        return any(normalize_think_level(s) == normalized for s in supported_levels)
    levels, _ = _resolve_supported_levels(provider_name, model_name, catalog_value, runtime)
    return any(entry["id"] == normalized for entry in levels)


def resolve_supported_thinking_level(
    preferred: Any = None,
    supported: Any = None,
    fallback: ThinkLevel = "off",
) -> ThinkLevel:
    if isinstance(preferred, dict):
        payload = cast(dict[str, Any], preferred)
        provider_name = payload.get("provider") if isinstance(payload.get("provider"), str) else None
        model_name = payload.get("model") or payload.get("modelId")
        model_name = model_name if isinstance(model_name, str) else None
        catalog_value = _normalize_catalog_list(payload.get("catalog"))
        runtime = payload.get("agentRuntime") if isinstance(payload.get("agentRuntime"), str) else None
        preferred_level = payload.get("level") if isinstance(payload.get("level"), str) else None
        supported_levels = _normalize_supported_levels(payload.get("supported"))
        options = None
        if payload.get("providerPolicySource") == "active":
            options = {"allowPublicArtifactFallback": False}
    else:
        provider_name = None
        model_name = None
        catalog_value = None
        runtime = None
        preferred_level = preferred
        supported_levels = _normalize_supported_levels(supported)
        options = None

    if supported_levels is None:
        levels, _ = _resolve_supported_levels(
            provider_name, model_name, catalog_value, runtime, options=options
        )
        supported_levels = [entry["id"] for entry in levels]

    if not preferred_level or not supported_levels:
        return fallback

    preferred_norm = normalize_think_level(preferred_level)
    if preferred_norm and is_thinking_level_supported(preferred_norm, supported_levels):
        return preferred_norm

    preferred_rank = THINKING_LEVEL_RANKS.get(preferred_norm or "", 0)
    best: ThinkLevel | None = None
    best_rank = -1
    for s in supported_levels:
        norm = normalize_think_level(s)
        if not norm:
            continue
        rank = THINKING_LEVEL_RANKS.get(norm, 0)
        if rank <= preferred_rank and rank > best_rank:
            best = norm
            best_rank = rank

    if best is None and preferred_norm == "off":
        chosen: ThinkLevel | None = None
        chosen_rank = 10**9
        for s in supported_levels:
            norm = normalize_think_level(s)
            if not norm:
                continue
            rank = THINKING_LEVEL_RANKS.get(norm, 0)
            if rank < chosen_rank:
                chosen = norm
                chosen_rank = rank
        return chosen or fallback

    return best or fallback


# ── ThinkingConfig (for Wave 20 compat) ───────────────────────────────

from dataclasses import dataclass


@dataclass
class ThinkingConfig:
    level: ThinkLevel = "medium"
    budget_tokens: int = 2048


def resolve_thinking_level(model_name: str, config: dict[str, Any] | None = None) -> ThinkingConfig:
    """Resolve reasoning/thinking level configuration for a model (Wave-20 compat)."""
    if not config or not isinstance(config, dict):
        return ThinkingConfig()

    thinking_cfg: Any = config.get("thinking")
    if not isinstance(thinking_cfg, dict):
        return ThinkingConfig()

    thinking_cfg_dict = cast(dict[str, Any], thinking_cfg)
    lvl_raw = thinking_cfg_dict.get("level", "medium")
    budget_value = thinking_cfg_dict.get("budget_tokens")
    budget = budget_value if isinstance(budget_value, int) else 2048
    lvl = normalize_think_level(str(lvl_raw)) or "medium"
    return ThinkingConfig(level=lvl, budget_tokens=budget)


__all__ = [
    "ALL_THINKING_LEVELS",
    "BASE_THINKING_LEVELS",
    "ElevatedLevel",
    "FastMode",
    "ReasoningLevel",
    "ThinkLevel",
    "ThinkingConfig",
    "ThinkingLevel",
    "THINKING_LEVEL_RANKS",
    "THINKING_LEVELS_HELP",
    "TraceLevel",
    "UsageDisplayLevel",
    "VerboseLevel",
    "format_thinking_levels",
    "is_session_default_directive_value",
    "is_thinking_level_supported",
    "list_thinking_level_labels",
    "list_thinking_level_options",
    "list_thinking_levels",
    "normalize_elevated_level",
    "normalize_fast_mode",
    "normalize_reasoning_level",
    "normalize_think_level",
    "normalize_trace_level",
    "normalize_usage_display",
    "normalize_verbose_level",
    "resolve_effective_response_usage",
    "resolve_provider_binary_thinking",
    "resolve_provider_default_thinking_level",
    "resolve_provider_thinking_profile",
    "resolve_provider_xhigh_thinking",
    "resolve_response_usage_mode",
    "resolve_supported_thinking_level",
    "resolve_thinking_default_for_model",
    "resolve_thinking_level",
]

# Alias used in some imports
ThinkingLevel = ThinkLevel  # type: ignore[assignment]
