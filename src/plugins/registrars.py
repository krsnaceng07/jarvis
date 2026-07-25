"""plugins.registrars — domain registrars composition.

OpenClaw parity: mirrors
``src/plugins/registry-registrars.ts`` (~25 LOC).
Composes domain registrars over one explicit mutable
registry state. Each registrar file owns a slice of the
public registration API (``registerTool``,
``registerChannel``, ``registerProvider``, etc.).

Public API:
- ``create_plugin_registrars(state)`` — returns a dict
  of all domain registrars spread together. The shape
  matches OpenClaw's ``PluginRegistrars`` type.

Key port decisions:
- The individual registrar files (``host``, ``memory``,
  ``network``, ``operation``, ``provider``, ``tool-hook``,
  ``capability``) are not ported yet — they are stubbed
  as no-op registrars. A future phase will replace the
  stubs with the real per-domain implementations.
- The composition shape is identical to the OpenClaw
  source; only the underlying function implementations
  are placeholders.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from .state import PluginRegistryState


# ── Per-domain registrar stubs ─────────────────────────────────────
# These will be replaced in a follow-up phase with the
# full port of:
#   - registry-registrars-capabilities.ts
#   - registry-registrars-host.ts
#   - registry-registrars-memory.ts
#   - registry-registrars-network.ts
#   - registry-registrars-operations.ts
#   - registry-registrars-providers.ts
#   - registry-registrars-tools-hooks.ts
#
# The stubs preserve the public method names so the
# composition shape matches OpenClaw's ``PluginRegistrars``.


def _noop(*_args: Any, **_kwargs: Any) -> None:
    """No-op registrar placeholder."""
    return None


def _create_capability_registrars(_state: PluginRegistryState) -> dict[str, Any]:
    """Stub for ``createCapabilityRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-capabilities.ts`` exports.
    """
    return {
        "registerSessionSchedulerJob": _noop,
        "registerSessionAction": _noop,
        "registerAgentEventSubscription": _noop,
        "registerRuntimeLifecycle": _noop,
        "registerControlUiDescriptor": _noop,
        "registerToolMetadata": _noop,
        "registerTrustedToolPolicy": _noop,
    }


def _create_tool_hook_registrars(_state: PluginRegistryState) -> dict[str, Any]:
    """Stub for ``createToolHookRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-tools-hooks.ts`` exports.
    """
    return {
        "registerTool": _noop,
        "registerHook": _noop,
        "registerTypedHook": _noop,
        "registerHttpRoute": _noop,
        "registerAgentToolResultMiddleware": _noop,
    }


def _create_network_registrars(_state: PluginRegistryState) -> dict[str, Any]:
    """Stub for ``createNetworkRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-network.ts`` exports.
    """
    return {
        "registerChannel": _noop,
        "registerHostedMediaResolver": _noop,
        "registerMcpServerConnectionResolver": _noop,
        "registerReload": _noop,
        "registerNodeHostCommand": _noop,
        "registerNodeInvokePolicy": _noop,
        "registerSecurityAuditCollector": _noop,
    }


def _create_provider_registrars(_state: PluginRegistryState) -> dict[str, Any]:
    """Stub for ``createProviderRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-providers.ts`` exports.
    """
    return {
        "registerProvider": _noop,
        "registerWorkerProvider": _noop,
        "registerEmbeddingProvider": _noop,
        "registerAgentHarness": _noop,
        "registerDetachedTaskRuntime": _noop,
        "registerSpeechProvider": _noop,
        "registerRealtimeTranscriptionProvider": _noop,
        "registerRealtimeVoiceProvider": _noop,
        "registerMediaUnderstandingProvider": _noop,
        "registerTranscriptSourceProvider": _noop,
        "registerImageGenerationProvider": _noop,
        "registerVideoGenerationProvider": _noop,
        "registerMusicGenerationProvider": _noop,
        "registerWebFetchProvider": _noop,
        "registerWebSearchProvider": _noop,
        "registerMigrationProvider": _noop,
        "registerService": _noop,
        "registerGatewayDiscoveryService": _noop,
    }


def _create_operation_registrars(_state: PluginRegistryState) -> dict[str, Any]:
    """Stub for ``createOperationRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-operations.ts`` exports.
    """
    return {
        "registerGatewayMethod": _noop,
        "registerSessionCatalog": _noop,
        "registerCliBackend": _noop,
        "registerTextTransforms": _noop,
        "registerCli": _noop,
        "registerCommand": _noop,
        "registerSessionExtension": _noop,
        "registerCodexAppServerExtensionFactory": _noop,
        "registerInteractiveHandler": _noop,
        "registerConversationBindingResolvedHandler": _noop,
        "registerContextEngine": _noop,
        "registerCompactionProvider": _noop,
    }


def _create_host_registrars(_state: PluginRegistryState) -> dict[str, Any]:
    """Stub for ``createHostRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-host.ts`` exports.
    """
    return {
        "registerMemoryCapability": _noop,
        "registerMemoryPromptSection": _noop,
        "registerMemoryPromptSupplement": _noop,
        "registerMemoryPromptPreparation": _noop,
        "registerMemoryCorpusSupplement": _noop,
        "registerMemoryFlushPlan": _noop,
        "registerMemoryRuntime": _noop,
        "registerMemoryEmbeddingProvider": _noop,
    }


def _create_memory_registrars(_state: PluginRegistryState) -> dict[str, Any]:
    """Stub for ``createMemoryRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-memory.ts`` exports.
    """
    return {
        "rollbackHooks": _noop,
    }


# ── Composition (mirrors OpenClaw's ``createPluginRegistrars``) ─────


def create_plugin_registrars(state: PluginRegistryState) -> dict[str, Any]:
    """Compose domain registrars over one mutable state.

    Mirrors OpenClaw's ``createPluginRegistrars``. The
    returned dict has the same shape as the source's
    ``PluginRegistrars`` type. The model-catalog
    registrar comes from the state (already wired in
    ``plugin_registry_state.py``).
    """
    return {
        **_create_capability_registrars(state),
        **_create_tool_hook_registrars(state),
        **_create_network_registrars(state),
        **_create_provider_registrars(state),
        **_create_operation_registrars(state),
        **_create_host_registrars(state),
        **_create_memory_registrars(state),
        "registerModelCatalogProvider": state["registerModelCatalogProvider"],
    }


# Type alias matching OpenClaw's ``PluginRegistrars``.
PluginRegistrars: TypeAlias = dict[str, Any]


__all__ = [
    "create_plugin_registrars",
    "PluginRegistrars",
]
