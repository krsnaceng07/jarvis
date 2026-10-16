"""plugins.registry — main plugin registry facade.

OpenClaw parity: mirrors ``src/plugins/registry.ts`` (~95 LOC).
Composes the registry state, domain registrars, scoped
runtime, and plugin API.

This module is **partially ported** in Phase 5.6b:
- The composition (state + registrars) is wired up.
- The host ``createApi`` factory is implemented in
  ``registry_api.py`` and exposed through this facade.

What works today:
- ``create_plugin_registry(params)`` returns the state
  + the registrars + a working ``createApi`` factory.
- Many host-side registry domain registrars now append
  live entries into the host registry state.
- The public surface matches OpenClaw's
  ``createPluginRegistry`` return shape.

What is partial:
- Some host-side registrar behavior remains incomplete
  (especially memory-specific and rollback lifecycle
  contracts).
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

from dataclasses import dataclass, field
from pathlib import Path

from .empty import create_empty_plugin_registry
from .registrars import create_plugin_registrars
from .registry_api import create_api_factory
from .state import create_plugin_registry_state
from .types import (
    PluginRecord,
    PluginRegistry,
    PluginRegistryParams,
)


@dataclass
class PluginContext:
    plugin_id: str
    plugin_kind: str
    config: Any = None
    secrets: Any = None
    logger: Any = None
    data_dir: Path = field(default_factory=Path.cwd)
    workspace: Path = field(default_factory=Path.cwd)

    def log(self, msg: str, *, level: str = "info") -> None:
        if self.logger is not None:
            log_fn = getattr(self.logger, level, self.logger.info)
            log_fn(msg)
        else:
            print(f"[{self.plugin_id}] {level}: {msg}")


class PluginApi:
    def __init__(
        self,
        ctx: PluginContext,
        registrars: dict[str, Any] | None = None,
        record: dict[str, Any] | None = None,
        logger: Any = None,
    ) -> None:
        self.ctx = ctx
        self.logger = logger or ctx.logger
        self.runtime = None
        self._plugin_config = None
        self._registrars = registrars or {}
        self._record = record or {}

    def set_manifest(self, manifest: Any) -> None:
        self.manifest = manifest

    def set_config(self, cfg: Any) -> None:
        self._plugin_config = cfg

    def __getattr__(self, name: str):
        if name.startswith("register_"):
            registrar_name = "".join(
                part.title() if index else part
                for index, part in enumerate(name.split("_"))
            )
            registrar = self._registrars.get(registrar_name)
            if registrar is not None:
                def _wrapper(*args: Any, **kwargs: Any) -> Any:
                    return registrar(self._record, *args, **kwargs)

                return _wrapper

            def _noop(*_a: Any, **_k: Any) -> Any:
                return None

            return _noop
        raise AttributeError(name)

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
    create_api = create_api_factory(state, registrars)

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
        # Accept either a plugin id (str) or a plugin record (dict) as first arg.
        plugin_id: str | None = None
        if _args:
            first = _args[0]
            if isinstance(first, str):
                plugin_id = first
            elif isinstance(first, dict):
                plugin_id = first.get("id")
        if plugin_id is None:
            # nothing to do
            return None

        # First call targeted clear helpers for complex subsystems.
        try:
            # Clear plugin commands
            clear_plugin_commands_for_plugin(plugin_id)
        except Exception:
            pass
        try:
            # Clear interactive handlers
            clear_plugin_interactive_handlers_for_plugin(plugin_id)
        except Exception:
            pass
        try:
            # Clear code-mode namespaces (best-effort)
            clear_code_mode_namespaces_for_plugin(plugin_id)
        except Exception:
            pass
        try:
            # Explicitly clear common runtime registries that may not follow
            # the simple ownerPluginId shape handled below.
            reg = state.get("registry", {})
            # tools
            try:
                tools = reg.get("tools", [])
                reg["tools"] = [t for t in tools if not (isinstance(t, dict) and (t.get("ownerPluginId") == plugin_id or t.get("pluginId") == plugin_id))]
            except Exception:
                pass
            # hooks
            try:
                hooks = reg.get("hooks", [])
                reg["hooks"] = [h for h in hooks if not (isinstance(h, dict) and (h.get("ownerPluginId") == plugin_id or h.get("pluginId") == plugin_id))]
            except Exception:
                pass
            # typedHooks
            try:
                th = reg.get("typedHooks", [])
                reg["typedHooks"] = [t for t in th if not (isinstance(t, dict) and (t.get("ownerPluginId") == plugin_id or t.get("pluginId") == plugin_id))]
            except Exception:
                pass
            # httpRoutes
            try:
                routes = reg.get("httpRoutes", [])
                reg["httpRoutes"] = [r for r in routes if not (isinstance(r, dict) and (r.get("_owner_id") == plugin_id or r.get("ownerPluginId") == plugin_id or r.get("pluginId") == plugin_id))]
            except Exception:
                pass
            # channels
            try:
                ch = reg.get("channels", [])
                reg["channels"] = [c for c in ch if not (isinstance(c, dict) and (c.get("pluginId") == plugin_id or c.get("ownerPluginId") == plugin_id))]
            except Exception:
                pass
            # providers (lists)
            try:
                for pk in ("providers", "embeddingProviders", "speechProviders", "workerProviders"):
                    val = reg.get(pk)
                    if isinstance(val, list):
                        reg[pk] = [p for p in val if not (isinstance(p, dict) and (p.get("ownerPluginId") == plugin_id or p.get("pluginId") == plugin_id))]
                    elif isinstance(val, dict):
                        # map-like: remove keys owned by plugin
                        to_del = [k for k, v in list(val.items()) if isinstance(v, dict) and (v.get("ownerPluginId") == plugin_id or v.get("pluginId") == plugin_id)]
                        for k in to_del:
                            val.pop(k, None)
            except Exception:
                pass
        except Exception:
            pass
        try:
            # Clear context engines owned by this plugin via context_engine registry
            from src.context_engine.registry import clear_context_engines_for_owner

            clear_context_engines_for_owner(plugin_id)
        except Exception:
            pass

        # Remove registered items that reference this plugin as owner.
        reg = state.get("registry", {})
        for key, val in list(reg.items()):
            # Only operate on list-like registries
            if isinstance(val, list):
                new_list = []
                for item in val:
                    try:
                        owner = None
                        if isinstance(item, dict):
                            owner = item.get("ownerPluginId") or item.get("pluginId") or item.get("plugin", {}).get("id") if isinstance(item.get("plugin"), dict) else None
                        if owner == plugin_id:
                            # drop this entry
                            continue
                    except Exception:
                        # on any odd item shape, keep it rather than risk data loss
                        new_list.append(item)
                        continue
                    new_list.append(item)
                reg[key] = new_list
            elif isinstance(val, dict):
                # workerProviders and similar maps: remove entries owned by plugin
                to_delete = []
                for k2, v2 in list(val.items()):
                    try:
                        owner = None
                        if isinstance(v2, dict):
                            owner = v2.get("ownerPluginId") or v2.get("pluginId")
                        if owner == plugin_id:
                            to_delete.append(k2)
                    except Exception:
                        continue
                for k2 in to_delete:
                    val.pop(k2, None)

        # Clear side-effect guards for plugin
        try:
            if isinstance(state.get("pluginSideEffectGuards"), dict):
                state["pluginSideEffectGuards"].pop(plugin_id, None)
        except Exception:
            pass

        # Invoke any registrar-level rollback hooks if present
        try:
            rb = registrars.get("rollbackHooks")
            if callable(rb):
                try:
                    rb(plugin_id)
                except TypeError:
                    rb()
        except Exception:
            pass

        # Invoke any plugin-hook-specific rollback callbacks recorded in state
        try:
            hooks = state.get("pluginHookRollback") or {}
            if isinstance(hooks, dict):
                for k, fn in list(hooks.items()):
                    try:
                        if callable(fn):
                            fn(plugin_id)
                    except TypeError:
                        try:
                            fn()
                        except Exception:
                            pass
        except Exception:
            pass

        return None

    # Helper: clear commands registered by a plugin
    def clear_plugin_commands_for_plugin(pid: str | None) -> None:
        if pid is None:
            return None
        try:
            cmds = state.get("registry", {}).get("commands", [])
            state["registry"]["commands"] = [c for c in cmds if not (isinstance(c, dict) and (c.get("ownerPluginId") == pid or c.get("pluginId") == pid))]
        except Exception:
            pass

    # Helper: clear interactive handlers registered by a plugin
    def clear_plugin_interactive_handlers_for_plugin(pid: str | None) -> None:
        if pid is None:
            return None
        try:
            handlers = state.get("registry", {}).get("interactiveHandlers", [])
            state["registry"]["interactiveHandlers"] = [h for h in handlers if not (isinstance(h, dict) and (h.get("ownerPluginId") == pid or h.get("pluginId") == pid))]
        except Exception:
            pass

    # Helper: best-effort removal of code-mode namespaces (if stored in toolMetadata)
    def clear_code_mode_namespaces_for_plugin(pid: str | None) -> None:
        if pid is None:
            return None
        try:
            meta = state.get("registry", {}).get("toolMetadata", [])
            new_meta = []
            for item in meta:
                try:
                    owner = item.get("ownerPluginId") or item.get("pluginId")
                    if owner == pid:
                        # drop item
                        continue
                    # drop if item appears to contain codeMode namespace owned by pid
                    if isinstance(item, dict) and item.get("codeMode") and owner == pid:
                        continue
                except Exception:
                    pass
                new_meta.append(item)
            state["registry"]["toolMetadata"] = new_meta
        except Exception:
            pass

    return {
        # Public surface.
        "registry": state["registry"],
        "createApi": create_api,
        "rollbackPluginGlobalSideEffects": _rollback_plugin_global_side_effects,
        "pushDiagnostic": state["pushDiagnostic"],
        # Domain registrars (no-op until the per-domain
        # registrar files are ported).
        **registrars,
    }
