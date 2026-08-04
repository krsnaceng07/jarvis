"""jarvis.config.provider_policy — bundled provider-policy normalizer.

OpenClaw parity: mirrors
``openclaw-main/src/config/provider-policy.ts``.

Focused minimal port: defers to a caller-provided
``resolve_bundled_provider_policy_surface`` callable until the plugin
public-artifacts module lands.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


def normalize_provider_config_for_config_defaults(params: dict) -> Any:
    """Apply bundled provider-owned normalization to one provider config.

    Mirrors :func:`normalizeProviderConfigForConfigDefaults`
    (``shared/config/provider-policy.ts`).
    """
    provider = params.get("provider")
    provider_config = params.get("providerConfig")
    manifest_registry = params.get("manifestRegistry")
    resolve_surface: Optional[Callable] = params.get("resolve_bundled_provider_policy_surface_fn")
    if not callable(resolve_surface):
        return provider_config
    surface = resolve_surface(provider, {"manifestRegistry": manifest_registry})
    normalizer = (surface or {}).get("normalizeConfig")
    if not callable(normalizer):
        return provider_config
    normalized = normalizer({
        "provider": provider,
        "providerConfig": provider_config,
    })
    # Preserve object identity when the provider policy declines to change config.
    return normalized if normalized and normalized is not provider_config else provider_config


def apply_provider_config_defaults_for_config(params: dict) -> Any:
    """Apply bundled provider-owned defaults to the full config.

    Mirrors :func:`applyProviderConfigDefaultsForConfig`
    (``shared/config/provider-policy.ts`).
    """
    provider = params.get("provider")
    config = params.get("config")
    env = params.get("env")
    manifest_registry = params.get("manifestRegistry")
    resolve_surface: Optional[Callable] = params.get("resolve_bundled_provider_policy_surface_fn")
    if not callable(resolve_surface):
        return config
    surface = resolve_surface(provider, {"manifestRegistry": manifest_registry})
    applier = (surface or {}).get("applyConfigDefaults")
    if not callable(applier):
        return config
    return applier({
        "provider": provider,
        "config": config,
        "env": env,
    }) or config


__all__ = [
    "normalize_provider_config_for_config_defaults",
    "apply_provider_config_defaults_for_config",
]
