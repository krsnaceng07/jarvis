"""jarvis.agents.sessions.auth_storage_oauth_registry — per-instance OAuth registry.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/auth-storage-oauth-registry.ts``.

Weak-keyed per-``AuthStorage`` OAuth-provider
registry. The :class:`AuthStorage` exposes a
``getOAuthProviders()`` accessor; the
registry is owned by the auth-storage
instance so the model-registry can share the
same registry without adding lifecycle
methods to the public SDK class.

Phase 6.6 — auth storage.

Adaptations
-----------
- The OpenClaw source's ``WeakMap<object,
  OAuthProviderRegistry>`` is a JS
  ``WeakMap``. The Python port uses
  :func:`weakref.WeakKeyDictionary` for the
  same shape (per-auth-storage registry).
- The OpenClaw source's
  ``OAuthProviderRegistry`` is the LLM-side
  registry (Phase 6.7+). The Python port
  ships a minimal placeholder so the
  per-instance attachment is functional.
"""
from __future__ import annotations

import weakref
from typing import Any, Optional


# ============================================================================
# Minimal OAuthProviderRegistry placeholder
# ============================================================================


class OAuthProviderRegistry:
    """Placeholder for the LLM-side
    ``OAuthProviderRegistry``. Phase 6.6
    ships the structural shape; the full
    OAuth-provider surface lands in Phase
    6.7+ with the LLM provider facade."""

    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}

    def register(self, provider_id: str, provider: Any) -> None:
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> Optional[Any]:
        return self._providers.get(provider_id)

    def get_all(self) -> dict[str, Any]:
        return dict(self._providers)

    def get_api_key(
        self, provider_id: str, oauth_creds: dict
    ) -> Optional[dict]:
        """Refresh an OAuth API key. Phase 6.6
        ships a no-op stub; the full refresh
        flow lands in 6.7+."""
        return None


# ============================================================================
# Weak-keyed per-auth-storage registry
# ============================================================================


#: Per-``AuthStorage`` registry store. Mirrors
#: the OpenClaw source's
#: ``registries = new WeakMap<object, OAuthProviderRegistry>()``
#: (``auth-storage-oauth-registry.ts:5``).
_registries: "weakref.WeakKeyDictionary[Any, OAuthProviderRegistry]" = (
    weakref.WeakKeyDictionary()
)


def get_auth_storage_oauth_provider_registry(
    auth_storage: Any,
) -> OAuthProviderRegistry:
    """Return the OAuth-provider registry
    attached to ``auth_storage`` (creating a
    fresh one if needed). Mirrors
    ``getAuthStorageOAuthProviderRegistry``
    (``auth-storage-oauth-registry.ts:7-14``)."""
    registry = _registries.get(auth_storage)
    if registry is None:
        registry = OAuthProviderRegistry()
        _registries[auth_storage] = registry
    return registry


__all__ = [
    "OAuthProviderRegistry",
    "get_auth_storage_oauth_provider_registry",
]
