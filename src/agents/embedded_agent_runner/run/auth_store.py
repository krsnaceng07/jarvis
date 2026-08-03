"""jarvis.agents.embedded_agent_runner.run.auth_store — create a scoped auth-profile store.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/auth-store.ts``.

Public surface:

- :func:`create_scoped_auth_profile_store`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Auth profile store shape.
AuthProfileStore = Dict[str, Any]


#: Installable hook for the create-scoped-auth-profile-store step.
_CREATE_SCOPED_AUTH_PROFILE_STORE: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {"version": 1, "profiles": {}}


def set_create_scoped_auth_profile_store_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom createScopedAuthProfileStore hook."""
    global _CREATE_SCOPED_AUTH_PROFILE_STORE
    _CREATE_SCOPED_AUTH_PROFILE_STORE = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_scoped_auth_profile_store(
    params: Dict[str, Any],
) -> AuthProfileStore:
    """Create a scoped auth-profile store.

    Mirrors :func:`createScopedAuthProfileStore`
    (``auth-store.ts``).
    """
    store = _CREATE_SCOPED_AUTH_PROFILE_STORE(dict(params or {}))
    if not isinstance(store, dict):
        store = {"version": 1, "profiles": {}}
    return store


__all__ = [
    "AuthProfileStore",
    "create_scoped_auth_profile_store",
    "set_create_scoped_auth_profile_store_hook",
]
