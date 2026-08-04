"""jarvis.config.local_model_lean_auto — onboarding-owned local-model lean auto.

OpenClaw parity: mirrors
``openclaw-main/src/config/local-model-lean-auto.ts``.
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict


#: Provider ids that get the lean default.
AUTO_LOCAL_MODEL_LEAN_PROVIDER_IDS = frozenset({"lmstudio", "ollama"})


def normalize_provider_id(provider_id) -> str:
    """Lowercase + strip the provider id for membership checks."""
    if not isinstance(provider_id, str):
        return ""
    return provider_id.strip().lower()


def should_auto_enable_local_model_lean(provider_id: str) -> bool:
    return normalize_provider_id(provider_id) in AUTO_LOCAL_MODEL_LEAN_PROVIDER_IDS


def _resolve_default_model_ref(config: dict):
    model = ((config or {}).get("agents") or {}).get("defaults", {}).get("model")
    if isinstance(model, str):
        return model
    if isinstance(model, dict):
        return model.get("primary")
    return None


def _clear_auto_model(config: dict) -> dict:
    wizard = dict((config or {}).get("wizard") or {})
    wizard.pop("localModelLeanAutoModel", None)
    new_config = dict(config or {})
    new_config["wizard"] = wizard
    return new_config


def apply_auto_local_model_lean(params: dict) -> dict:
    """Maintain the onboarding-owned lean default while preserving explicit config.

    Mirrors :func:`applyAutoLocalModelLean`
    (``shared/config/local-model-lean-auto.ts``).
    """
    config = params.get("config") or {}
    provider_id = params.get("providerId") or ""
    model_ref = params.get("modelRef") or ""
    defaults = (config.get("agents") or {}).get("defaults") or {}
    local_model_lean = defaults.get("experimental", {}).get("localModelLean")
    auto_model = (config.get("wizard") or {}).get("localModelLeanAutoModel")
    onboarding_owns_setting = (
        auto_model is not None and _resolve_default_model_ref(config) == auto_model
    )
    if not should_auto_enable_local_model_lean(provider_id):
        if not auto_model:
            return {"config": config, "changed": False, "enabled": False}
        new_config = _clear_auto_model(config)
        if not onboarding_owns_setting or local_model_lean is not True:
            return {"config": new_config, "changed": True, "enabled": False}
        experimental = dict(defaults.get("experimental") or {})
        experimental.pop("localModelLean", None)
        agents = dict(config.get("agents") or {})
        agents["defaults"] = {**defaults, "experimental": experimental}
        new_config["agents"] = agents
        return {"config": new_config, "changed": True, "enabled": False}
    if local_model_lean is not None:
        if not auto_model:
            return {"config": config, "changed": False, "enabled": False}
        if not onboarding_owns_setting or not local_model_lean:
            return {"config": _clear_auto_model(config), "changed": True, "enabled": False}
        if auto_model == model_ref:
            return {"config": config, "changed": False, "enabled": False}
        wizard = dict(config.get("wizard") or {})
        wizard["localModelLeanAutoModel"] = model_ref
        new_config = dict(config)
        new_config["wizard"] = wizard
        return {"config": new_config, "changed": True, "enabled": False}
    wizard = dict(config.get("wizard") or {})
    wizard["localModelLeanAutoModel"] = model_ref
    experimental = dict(defaults.get("experimental") or {})
    experimental["localModelLean"] = True
    agents = dict(config.get("agents") or {})
    agents["defaults"] = {**defaults, "experimental": experimental}
    new_config = dict(config)
    new_config["wizard"] = wizard
    new_config["agents"] = agents
    return {"config": new_config, "changed": True, "enabled": True}


__all__ = [
    "AUTO_LOCAL_MODEL_LEAN_PROVIDER_IDS",
    "should_auto_enable_local_model_lean",
    "apply_auto_local_model_lean",
]
