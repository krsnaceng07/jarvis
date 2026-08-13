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
        return None

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
