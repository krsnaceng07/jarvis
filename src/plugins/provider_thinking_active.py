"""jarvis.plugins.provider_thinking_active — active-registry thinking policy.

OpenClaw parity: mirrors
``openclaw-main/src/plugins/provider-thinking-active.ts``.

Reads provider thinking policy from the active runtime registry only.
The registry state lives in the process-global slot published by
:mod:`src.plugins.runtime_state_key` (the OpenClaw source reads
``globalThis[PLUGIN_REGISTRY_STATE]``).

Shapes (all dict-based; mirrors the TS structural types):

- ``ActiveThinkingProvider`` — ``{"id", "aliases"?, "hookAliases"?,
  "isBinaryThinking"?, "supportsXHighThinking"?,
  "resolveThinkingProfile"?, "resolveDefaultThinkingLevel"?}`` where
  the last four are callables taking a context dict.
- ``ActiveThinkingRegistryState`` — ``{"activeRegistry":
  {"providers": [{"provider": ActiveThinkingProvider}, ...]}}``.
"""
from __future__ import annotations

from typing import Any, Optional

from jarvis_normalization_core.string_coerce import (
    normalize_lowercase_string_or_empty,
)

from .runtime_state_key import get_plugin_registry_state


def _normalize_provider_id(provider: Any) -> str:
    """Mirrors ``normalizeProviderId``
    (``model-catalog-core/provider-id.ts:6-8``) — plain lowercase
    coercion."""
    return normalize_lowercase_string_or_empty(provider)


def _matches_provider_id(provider: dict, provider_id: str) -> bool:
    """Mirrors ``matchesProviderId``
    (``provider-thinking-active.ts:38-49``)."""
    normalized = _normalize_provider_id(provider_id)
    if not normalized:
        return False
    if _normalize_provider_id(provider.get("id")) == normalized:
        return True
    aliases = list(provider.get("aliases") or []) + list(
        provider.get("hookAliases") or []
    )
    return any(
        _normalize_provider_id(alias) == normalized for alias in aliases
    )


def _resolve_active_thinking_provider(
    provider_id: str,
) -> Optional[dict]:
    """Mirrors ``resolveActiveThinkingProvider``
    (``provider-thinking-active.ts:51-60``)."""
    state = get_plugin_registry_state()
    if not isinstance(state, dict):
        return None
    active_registry = state.get("activeRegistry")
    if not isinstance(active_registry, dict):
        return None
    providers = active_registry.get("providers")
    if not isinstance(providers, list):
        return None
    for entry in providers:
        if not isinstance(entry, dict):
            continue
        provider = entry.get("provider")
        if isinstance(provider, dict) and _matches_provider_id(
            provider, provider_id
        ):
            return provider
    return None


def _call_hook(params: dict, hook_name: str) -> Any:
    """Shared ``provider?.hook?.(context)`` optional-chain body."""
    provider = _resolve_active_thinking_provider(params.get("provider", ""))
    if provider is None:
        return None
    hook = provider.get(hook_name)
    if not callable(hook):
        return None
    return hook(params.get("context"))


def resolve_active_provider_binary_thinking(params: dict) -> Any:
    """Mirrors ``resolveActiveProviderBinaryThinking``
    (``provider-thinking-active.ts:62-66``)."""
    return _call_hook(params, "isBinaryThinking")


def resolve_active_provider_xhigh_thinking(params: dict) -> Any:
    """Mirrors ``resolveActiveProviderXHighThinking``
    (``provider-thinking-active.ts:68-72``)."""
    return _call_hook(params, "supportsXHighThinking")


def resolve_active_provider_thinking_profile(params: dict) -> Any:
    """Mirrors ``resolveActiveProviderThinkingProfile``
    (``provider-thinking-active.ts:74-78``)."""
    return _call_hook(params, "resolveThinkingProfile")


def resolve_active_provider_default_thinking_level(params: dict) -> Any:
    """Mirrors ``resolveActiveProviderDefaultThinkingLevel``
    (``provider-thinking-active.ts:80-86``)."""
    return _call_hook(params, "resolveDefaultThinkingLevel")


__all__ = [
    "resolve_active_provider_binary_thinking",
    "resolve_active_provider_default_thinking_level",
    "resolve_active_provider_thinking_profile",
    "resolve_active_provider_xhigh_thinking",
]
