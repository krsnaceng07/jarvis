"""plugins.capability_provider_runtime — capability-backed provider lookup.

OpenClaw parity: mirrors the provider-capability runtime seam used by
embedding-provider lookup. This layer resolves provider records from the
process-global active registry without requiring the full plugin capability
system to be ported yet.
"""
from __future__ import annotations

from typing import Any

from jarvis_normalization_core.string_coerce import (
    normalize_lowercase_string_or_empty,
)

from .runtime_state_key import get_plugin_registry_state

__all__ = [
    "resolve_plugin_capability_providers",
    "resolve_plugin_capability_provider",
]


def _normalize_provider_id(provider: Any) -> str:
    return normalize_lowercase_string_or_empty(provider)


def _matches_provider_id(provider: dict[str, Any], provider_id: str) -> bool:
    normalized = _normalize_provider_id(provider_id)
    if not normalized:
        return False
    if _normalize_provider_id(provider.get("id")) == normalized:
        return True
    aliases = list(provider.get("aliases") or []) + list(
        provider.get("hookAliases") or []
    )
    return any(_normalize_provider_id(alias) == normalized for alias in aliases)


def _iter_active_registry_providers() -> list[dict[str, Any]]:
    state = get_plugin_registry_state()
    if not isinstance(state, dict):
        return []
    active_registry = state.get("activeRegistry")
    if not isinstance(active_registry, dict):
        return []
    providers = active_registry.get("providers")
    if not isinstance(providers, list):
        return []
    result: list[dict[str, Any]] = []
    for entry in providers:
        if isinstance(entry, dict):
            provider = entry.get("provider")
            if isinstance(provider, dict):
                result.append(provider)
            elif isinstance(entry, dict) and entry:
                result.append(entry)
    return result


def _key_variants(key: str) -> set[str]:
    candidates = {normalize_lowercase_string_or_empty(key)}
    if not candidates:
        return set()
    lowered = next(iter(candidates))
    if lowered.endswith("s"):
        candidates.add(lowered[:-1])
    else:
        candidates.add(f"{lowered}s")
    return {candidate for candidate in candidates if candidate}


def resolve_plugin_capability_providers(params: dict[str, Any]) -> list[dict[str, Any]]:
    """List providers for a capability key from the active registry state."""
    key = str(params.get("key") or "")
    providers = _iter_active_registry_providers()
    if not key:
        return providers

    key_matches = _key_variants(key)

    def _matches_key(provider: dict[str, Any]) -> bool:
        kind = provider.get("kind")
        if isinstance(kind, str):
            kind_norm = normalize_lowercase_string_or_empty(kind)
            if kind_norm and kind_norm in key_matches:
                return True
        elif isinstance(kind, list):
            if any(
                normalize_lowercase_string_or_empty(item) in key_matches
                for item in kind
            ):
                return True

        capability = provider.get("capability")
        if isinstance(capability, str):
            capability_norm = normalize_lowercase_string_or_empty(capability)
            if capability_norm and capability_norm in key_matches:
                return True
        elif isinstance(capability, list):
            if any(
                normalize_lowercase_string_or_empty(item) in key_matches
                for item in capability
            ):
                return True

        provider_key = normalize_lowercase_string_or_empty(provider.get("key"))
        if provider_key and provider_key in key_matches:
            return True

        return False

    return [provider for provider in providers if _matches_key(provider)]


def resolve_plugin_capability_provider(params: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a capability provider from the active registry by id or alias."""
    provider_id = str(params.get("providerId") or "")
    providers = resolve_plugin_capability_providers(params)
    if not provider_id:
        return providers[0] if providers else None
    for provider in providers:
        if _matches_provider_id(provider, provider_id):
            return provider

    # Fallback: some active-registry entries carry the capability key in the
    # provider record, but not every provider does; alias-driven lookup still
    # needs to work against the full active registry for a given id.
    for provider in _iter_active_registry_providers():
        if _matches_provider_id(provider, provider_id):
            return provider
    return None
