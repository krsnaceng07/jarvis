"""jarvis_sdk.plugin_registry — main plugin registry facade (STUB).

OpenClaw parity: mirrors ``src/plugins/registry.ts`` (~95 LOC).
Composes the registry state, domain registrars, scoped
runtime, and plugin API. This module is a **minimal
stub** for Phase 5.6a — the full port requires the
domain-registrar + runtime-resolver + plugin-API
factories (see ``registry-registrars.ts``,
``registry-runtime.ts``, ``registry-api.ts`` in the
OpenClaw source). A later phase will replace this
stub with the full composition.

What works today (Phase 5.6a):
- ``create_empty_plugin_registry`` (re-export) — fully
  ported.
- ``PluginRecord`` / ``PluginRegistry`` types
  (re-exports) — fully ported.
- ``create_plugin_registry(params)`` — returns a
  partial-facade object with the state + empty
  registrars. A full port will land in a follow-up phase.

What is stubbed:
- Domain registrars (registerTool, registerChannel,
  etc.) are returned as no-op callables. The full
  implementations live in ``registry-registrars.ts``
  (OpenClaw) and are not ported yet.
- ``createApi`` / ``rollbackPluginGlobalSideEffects``
  are placeholders. The full lifecycle wiring is in
  ``registry-api.ts`` (OpenClaw) and is not ported yet.

Consumers should treat this module as a placeholder
until the follow-up phase lands.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .plugin_registry_empty import create_empty_plugin_registry
from .plugin_registry_state import create_plugin_registry_state
from .plugin_registry_types import (
    PluginRecord,
    PluginRegistry,
    PluginRegistryParams,
)

# Re-exports — fully ported surfaces from Phase 5.6a.
__all__ = [
    "create_plugin_registry",
    "create_empty_plugin_registry",
    "PluginRecord",
    "PluginRegistry",
    "PluginRegistryParams",
]


def _noop_registrar(*_args: Any, **_kwargs: Any) -> None:
    """No-op placeholder for domain registrars.

    Each domain registrar (``registerTool``,
    ``registerChannel``, etc.) is returned as a
    ``_noop_registrar`` instance until the full
    ``registry-registrars.ts`` port lands. Calling
    them is safe but does nothing.
    """
    return None


if TYPE_CHECKING:
    pass


def create_plugin_registry(
    registry_params: PluginRegistryParams,
) -> dict[str, Any]:
    """Compose the registry state, registrars, runtime, and API.

    Mirrors OpenClaw's ``createPluginRegistry``. The
    Python port of Phase 5.6a returns a partial object:
    - ``registry`` — the empty ``PluginRegistry`` shape
    - ``pushDiagnostic`` — pushes into ``registry.diagnostics``
    - ``createApi`` — a placeholder; the full factory
      (from ``registry-api.ts``) is not ported yet
    - ``rollbackPluginGlobalSideEffects`` — a placeholder;
      the full rollback (from ``registry-api.ts``) is
      not ported yet
    - Domain registrars (``registerTool``,
      ``registerChannel``, etc.) — no-op callables

    A later phase will replace this with the full
    composition (matching the OpenClaw surface).
    """
    state = create_plugin_registry_state(registry_params)

    def _create_api(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        """Placeholder for ``createPluginApiFactory``.

        The real implementation wires
        ``deactivatePluginSideEffectGuards`` for rollback
        and exposes the domain registrars. A later phase
        will port the full factory.
        """
        return {
            "createApi": _create_api,
            "deactivatePluginSideEffectGuards": _noop_registrar,
        }

    def _rollback_plugin_global_side_effects(*_args: Any, **_kwargs: Any) -> None:
        """Placeholder for the global side-effect rollback.

        The real implementation calls
        ``clearPluginCommandsForPlugin``,
        ``clearPluginInteractiveHandlersForPlugin``,
        ``clearCodeModeNamespacesForPlugin``,
        ``clearContextEnginesForOwner``, and
        ``registrars.rollbackHooks``. A later phase will
        port the full rollback chain.
        """
        return None

    return {
        "registry": state["registry"],
        "createApi": _create_api,
        "rollbackPluginGlobalSideEffects": _rollback_plugin_global_side_effects,
        "pushDiagnostic": state["pushDiagnostic"],
        # Domain registrars — placeholders until Phase 5.6b ports
        # ``registry-registrars.ts``. Each is a no-op callable so
        # the public surface matches the OpenClaw source.
        "registerTool": _noop_registrar,
        "registerChannel": _noop_registrar,
        "registerHostedMediaResolver": _noop_registrar,
        "registerMcpServerConnectionResolver": _noop_registrar,
        "registerProvider": _noop_registrar,
        "registerWorkerProvider": _noop_registrar,
        "registerModelCatalogProvider": _noop_registrar,
        "registerAgentHarness": _noop_registrar,
        "registerCliBackend": _noop_registrar,
        "registerTextTransforms": _noop_registrar,
        "registerEmbeddingProvider": _noop_registrar,
        "registerSpeechProvider": _noop_registrar,
        "registerRealtimeTranscriptionProvider": _noop_registrar,
        "registerRealtimeVoiceProvider": _noop_registrar,
        "registerMediaUnderstandingProvider": _noop_registrar,
        "registerTranscriptSourceProvider": _noop_registrar,
        "registerImageGenerationProvider": _noop_registrar,
        "registerVideoGenerationProvider": _noop_registrar,
        "registerMusicGenerationProvider": _noop_registrar,
        "registerWebSearchProvider": _noop_registrar,
        "registerMigrationProvider": _noop_registrar,
        "registerGatewayMethod": _noop_registrar,
        "registerSessionCatalog": _noop_registrar,
        "registerCli": _noop_registrar,
        "registerReload": _noop_registrar,
        "registerNodeHostCommand": _noop_registrar,
        "registerSecurityAuditCollector": _noop_registrar,
        "registerService": _noop_registrar,
        "registerCommand": _noop_registrar,
        "registerSessionExtension": _noop_registrar,
        "registerTrustedToolPolicy": _noop_registrar,
        "registerToolMetadata": _noop_registrar,
        "registerControlUiDescriptor": _noop_registrar,
        "registerRuntimeLifecycle": _noop_registrar,
        "registerAgentEventSubscription": _noop_registrar,
        "registerSessionSchedulerJob": _noop_registrar,
        "registerSessionAction": _noop_registrar,
        "registerHook": _noop_registrar,
        "registerTypedHook": _noop_registrar,
    }
