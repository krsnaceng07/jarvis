"""jarvis.config.model_input — model input config normalization.

OpenClaw parity: mirrors
``openclaw-main/src/config/model-input.ts``.

Focused minimal port: exposes the agent-model helpers. The
provider-id normalization (Google/Together) and the model catalog
parser are delegated to caller-provided callables until those
subsystems land.
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class AgentModelConfig(TypedDict, total=False):
    primary: str
    fallbacks: list


class AgentToolModelConfig(TypedDict, total=False):
    primary: str
    fallbacks: list
    timeoutMs: int
    params: dict


AgentModelInput = dict


def resolve_agent_model_primary_value(model: Optional[dict]) -> Optional[str]:
    """Return the primary model ref from string or object-style config."""
    if not model:
        return None
    if isinstance(model, str):
        return model.strip() or None
    if isinstance(model, dict):
        primary = model.get("primary")
        return primary.strip() if isinstance(primary, str) and primary.strip() else None
    return None


def resolve_agent_model_fallback_values(model: Optional[dict]) -> list:
    if not isinstance(model, dict):
        return []
    fallbacks = model.get("fallbacks")
    return list(fallbacks) if isinstance(fallbacks, list) else []


def resolve_agent_model_timeout_ms_value(model: Optional[dict]) -> Optional[int]:
    if not isinstance(model, dict):
        return None
    timeout = model.get("timeoutMs")
    if not isinstance(timeout, (int, float)) or timeout != timeout or timeout <= 0:
        return None
    return int(timeout)


def to_agent_model_list_like(model: Optional[dict]) -> Optional[dict]:
    if isinstance(model, str):
        primary = model.strip()
        return {"primary": primary} if primary else None
    if isinstance(model, dict):
        return dict(model)
    return None


def normalize_agent_model_ref_for_config(
    model: str,
    *,
    parse_model_catalog_ref: Optional[Any] = None,
    normalize_google_preview_model_id: Optional[Any] = None,
    normalize_together_model_id: Optional[Any] = None,
    model_key: Optional[Any] = None,
    is_record: Optional[Any] = None,
) -> str:
    """Canonicalize provider/model refs before they are persisted to config.

    Mirrors :func:`normalizeAgentModelRefForConfig`
    (``shared/config/model-input.ts`).
    """
    if not isinstance(model, str):
        return model
    trimmed = model.strip()
    if callable(parse_model_catalog_ref):
        parsed = parse_model_catalog_ref(trimmed)
    else:
        parsed = None
    if not parsed:
        return trimmed
    provider = parsed.get("provider", "")
    model_suffix = parsed.get("modelId", "")
    google_ids = {"google", "google-gemini-cli", "google-vertex"}
    if (provider in google_ids or model_suffix.startswith("google/")) and callable(normalize_google_preview_model_id):
        normalized_model = normalize_google_preview_model_id(model_suffix)
    elif provider == "together" and callable(normalize_together_model_id):
        normalized_model = normalize_together_model_id(model_suffix)
    else:
        normalized_model = model_suffix
    if callable(model_key):
        return model_key(provider, normalized_model)
    return f"{provider}/{normalized_model}" if provider else normalized_model


def merge_agent_model_entry_for_config(existing, incoming) -> Any:
    if not (isinstance(existing, dict) and isinstance(incoming, dict)):
        return incoming
    existing_params = existing.get("params") if isinstance(existing.get("params"), dict) else None
    incoming_params = incoming.get("params") if isinstance(incoming.get("params"), dict) else None
    out = {**existing, **incoming}
    if existing_params or incoming_params:
        out["params"] = {**(existing_params or {}), **(incoming_params or {})}
    return out


def normalize_agent_model_map_for_config(
    models,
    *,
    normalize_agent_model_ref_for_config_fn=None,
) -> Any:
    """Normalize model map keys and merge entries that collapse to the same canonical ref."""
    if not isinstance(models, dict):
        return models
    next_: dict = {}
    mutated = False
    for key, entry in models.items():
        if callable(normalize_agent_model_ref_for_config_fn):
            normalized_key = normalize_agent_model_ref_for_config_fn(key)
        else:
            normalized_key = normalize_agent_model_ref_for_config(key)
        if normalized_key != key or normalized_key in next_:
            mutated = True
        next_[normalized_key] = merge_agent_model_entry_for_config(
            next_.get(normalized_key), entry
        )
    return next_ if mutated else models


__all__ = [
    "AgentModelConfig",
    "AgentToolModelConfig",
    "resolve_agent_model_primary_value",
    "resolve_agent_model_fallback_values",
    "resolve_agent_model_timeout_ms_value",
    "to_agent_model_list_like",
    "normalize_agent_model_ref_for_config",
    "normalize_agent_model_map_for_config",
]
