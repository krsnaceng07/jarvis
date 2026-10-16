"""jarvis_sdk.plugin_registry — main plugin registry facade.

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

from typing import Any, Callable, cast

from .plugin_registry_empty import create_empty_plugin_registry
from .plugin_registry_registrars import create_plugin_registrars
from .plugin_registry_state import create_plugin_registry_state
from .plugin_registry_types import (
    PluginRecord,
    PluginRegistry,
    PluginRegistryParams,
)
from .api import PluginApi
from .context import PluginContext

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
    registrars: dict[str, Callable[..., Any]] = create_plugin_registrars(state)

    def _create_api(
        record: dict[str, Any] | None = None, opts: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Stub for the full ``createApi`` factory.

        The real implementation lives in
        ``registry-api.ts`` and wires 60+ domain
        registrars into a single ``OpenClawPluginApi``
        envelope. The Python port of Phase 5.6b does not
        include the full factory — only the
        ``createApi`` placeholder. A follow-up phase
        will port the full factory.
        """
        # Build a PluginContext + PluginApi so the returned factory
        # behaves like the real host `createApi` (plugins get a live
        # PluginApi instance to call into).
        record = record or {}
        opts = opts or {}

        plugin_id = record.get("id", "")
        plugin_kind = record.get("kind", "plugin")
        ctx = PluginContext(plugin_id=plugin_id, plugin_kind=plugin_kind)
        api_obj = PluginApi(ctx)

        # Provide manifest/config if present.
        manifest = cast(
            dict[str, Any],
            record.get("manifest") or record.get("package") or {},
        )
        try:
            api_obj.set_manifest(manifest)
        except Exception:
            # set_manifest is best-effort in older SDK shapes.
            pass
        try:
            api_obj.set_config(opts.get("config"))
        except Exception:
            pass

        # Build the plain dict view expected by legacy consumers.
        out: dict[str, Any] = {
            # Legacy host stub returns an empty id/name in the plain dict view.
            # Advanced consumers must use ``pluginApi`` for the live plugin identity.
            "id": "",
            "name": "",
            "config": api_obj._plugin_config or {},
            "logger": api_obj.logger,
            "runtime": api_obj.runtime,
        }
        # Expose the live PluginApi instance for advanced host consumers.
        out["pluginApi"] = api_obj

        # Helper: map CamelCase registrar name to PluginApi snake_case method
        def camel_to_snake(name: str) -> str:
            # registerTool -> register_tool
            s = name[0].lower()
            for ch in name[1:]:
                if ch.isupper():
                    s += "_" + ch.lower()
                else:
                    s += ch
            return s

        # Attach registrar wrappers that call the PluginApi instance
        for name, fn in registrars.items():
            snake = camel_to_snake(name)
            if hasattr(api_obj, snake) and callable(getattr(api_obj, snake)):
                meth = getattr(api_obj, snake)

                def _bind(m: Callable[..., Any]) -> Callable[..., Any]:
                    def _call(*a: Any, **k: Any) -> Any:
                        return m(*a, **k)

                    return _call

                out[name] = _bind(meth)
            else:
                # Fallback to the registrar stub (wrapped)
                def _wrap(f: Callable[..., Any]) -> Callable[..., Any]:
                    def _call(*a: Any, **k: Any) -> Any:
                        return f(*a, **k)

                    return _call

                out[name] = _wrap(fn)

        # Historical aliases
        out.setdefault("registerCli", out.get("registerCli", _noop_registrar))
        out.setdefault("registerChannel", out.get("registerChannel", _noop_registrar))

        return out

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
