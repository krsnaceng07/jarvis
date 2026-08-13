"""jarvis.plugins.provider_thinking — provider thinking-level policy.

OpenClaw parity: mirrors
``openclaw-main/src/plugins/provider-thinking.ts``.

Resolves provider thinking-level policy from active plugins or plugin
metadata.

Adaptations
-----------
- The OpenClaw source's public-artifact fallback
  (``resolveProviderPublicPolicySurface`` →
  ``getCurrentPluginMetadataSnapshot`` +
  ``resolveProviderPolicySurface``) reads the bundled provider policy
  surface from the plugin manifest registry. That registry projection
  has no Python port yet; the port exposes the same seam via a
  module-level hook
  (:func:`set_resolve_provider_public_policy_surface_hook`) that
  defaults to ``None`` (no bundled surface). The active-registry path
  is fully ported.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from .provider_thinking_active import (
    resolve_active_provider_binary_thinking,
    resolve_active_provider_default_thinking_level,
    resolve_active_provider_thinking_profile,
    resolve_active_provider_xhigh_thinking,
)

#: The bundled policy-surface hook. Mirrors
#: ``resolveProviderPublicPolicySurface``
#: (``provider-thinking.ts:15-23``); returns an object/dict with an
#: optional ``resolveThinkingProfile`` callable, or ``None``.
_resolve_provider_public_policy_surface_hook: Optional[
    Callable[[str], Any]
] = None


def set_resolve_provider_public_policy_surface_hook(
    hook: Optional[Callable[[str], Any]],
) -> None:
    """Install/clear the bundled policy-surface hook (adaptation seam)."""
    global _resolve_provider_public_policy_surface_hook
    _resolve_provider_public_policy_surface_hook = hook


def _resolve_provider_public_policy_surface(provider_id: str) -> Any:
    """Mirrors ``resolveProviderPublicPolicySurface``
    (``provider-thinking.ts:15-23``) via the installed hook."""
    if _resolve_provider_public_policy_surface_hook is None:
        return None
    return _resolve_provider_public_policy_surface_hook(provider_id)


def resolve_provider_binary_thinking(params: dict) -> Any:
    """Resolves whether a provider treats thinking as binary on/off.
    Mirrors ``resolveProviderBinaryThinking``
    (``provider-thinking.ts:31-35``)."""
    return resolve_active_provider_binary_thinking(params)


def resolve_provider_xhigh_thinking(params: dict) -> Any:
    """Resolves whether a provider supports xhigh thinking. Mirrors
    ``resolveProviderXHighThinking``
    (``provider-thinking.ts:38-42``)."""
    return resolve_active_provider_xhigh_thinking(params)


def resolve_provider_thinking_profile(
    params: dict,
    options: Optional[dict] = None,
) -> Any:
    """Resolves a provider thinking profile from active plugins or the
    bundled policy surface. Mirrors
    ``resolveProviderThinkingProfile``
    (``provider-thinking.ts:45-59``)."""
    active_profile = resolve_active_provider_thinking_profile(params)
    if active_profile is not None:
        return active_profile
    if options and options.get("allowPublicArtifactFallback") is False:
        return None
    surface = _resolve_provider_public_policy_surface(
        params.get("provider", "")
    )
    if surface is None:
        return None
    resolve = (
        surface.get("resolveThinkingProfile")
        if isinstance(surface, dict)
        else getattr(surface, "resolve_thinking_profile", None)
    )
    if not callable(resolve):
        return None
    return resolve(params.get("context"))


def resolve_provider_default_thinking_level(params: dict) -> Any:
    """Resolves the provider default thinking level from the active
    plugin registry. Mirrors
    ``resolveProviderDefaultThinkingLevel``
    (``provider-thinking.ts:62-66``)."""
    return resolve_active_provider_default_thinking_level(params)


__all__ = [
    "resolve_provider_binary_thinking",
    "resolve_provider_default_thinking_level",
    "resolve_provider_thinking_profile",
    "resolve_provider_xhigh_thinking",
    "set_resolve_provider_public_policy_surface_hook",
]
