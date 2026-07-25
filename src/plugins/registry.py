"""plugins.registry — main plugin registry facade.

OpenClaw parity: mirrors ``src/plugins/registry.ts`` (~95 LOC).
Composes the registry state, domain registrars, scoped
runtime, and plugin API.

This module is **partially ported** in Phase 5.6b:
- The composition (state + registrars) is wired up.
- The API factory is a stub (the real ``createApi`` is
  not ported yet — see ``registry-api.ts`` which
  requires the full lifecycle wiring).

What works today:
- ``create_plugin_registry(params)`` returns the state
  + the registrars + a stub ``createApi``.
- Domain registrars are exposed as no-op callables.
- The public surface matches OpenClaw's
  ``createPluginRegistry`` return shape.

What is stubbed:
- The real ``createApi`` factory (from
  ``registry-api.ts``) — deferred to a follow-up
  phase. The stub here just returns an empty object.
- ``rollbackPluginGlobalSideEffects`` is a no-op
  placeholder. The full rollback chain
  (clear commands / interactive handlers / code mode
  namespaces / context engines / hooks) is deferred.

Consumers should treat the individual registrars as
no-ops until the per-domain registrar files are
ported. The composition surface (the public method
names) is stable.
"""
from __future__ import annotations

from typing import Any

from .empty import create_empty_plugin_registry
from .registrars import create_plugin_registrars
from .state import create_plugin_registry_state
from .types import (
    PluginRecord,
    PluginRegistry,
    PluginRegistryParams,
)

# Re-exports — fully ported surfaces.
__all__ = [
    "create_plugin_registry",
    "create_empty_plugin_registry",
    "PluginRecord",
    "PluginRegistry",
    "PluginRegistryParams",
]


def _noop_registrar(*_args: Any, **_kwargs: Any) -> None:
    """No-op registrar placeholder for the createApi stub."""
    return None


def create_plugin_registry(
    registry_params: PluginRegistryParams,
) -> dict[str, Any]:
    """Compose the registry state, registrars, runtime, and API.

    Mirrors OpenClaw's ``createPluginRegistry``. Returns
    a dict with the same shape as the source's return
    value: the registry, the registrars, the API factory
    (stub), and the rollback helper (stub).
    """
    state = create_plugin_registry_state(registry_params)
    registrars = create_plugin_registrars(state)

    def _create_api(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        """Stub for the full ``createApi`` factory.

        The real implementation lives in
        ``registry-api.ts`` and wires 60+ domain
        registrars into a single ``OpenClawPluginApi``
        envelope. The Python port of Phase 5.6b does not
        include the full factory — only the
        ``createApi`` placeholder. A follow-up phase
        will port the full factory.
        """
        return {
            "id": "",
            "name": "",
            "config": {},
            "logger": None,
            "runtime": None,
            "registerCli": _noop_registrar,
            "registerChannel": _noop_registrar,
        }

    def _rollback_plugin_global_side_effects(*_args: Any, **_kwargs: Any) -> None:
        """Stub for the full rollback chain.

        The real implementation calls
        ``clearPluginCommandsForPlugin``,
        ``clearPluginInteractiveHandlersForPlugin``,
        ``clearCodeModeNamespacesForPlugin``,
        ``clearContextEnginesForOwner``, and
        ``registrars.rollbackHooks``. A follow-up phase
        will port the full chain.
        """
        return None

    return {
        # Public surface.
        "registry": state["registry"],
        "createApi": _create_api,
        "rollbackPluginGlobalSideEffects": _rollback_plugin_global_side_effects,
        "pushDiagnostic": state["pushDiagnostic"],
        # Domain registrars (no-op until the per-domain
        # registrar files are ported).
        **registrars,
    }
