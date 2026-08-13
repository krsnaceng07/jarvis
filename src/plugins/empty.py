"""plugins.empty — empty plugin registry factory.

OpenClaw parity: mirrors
``src/plugins/registry-empty.ts`` (59 LOC).
Provides the empty plugin registry used before discovery
completes. Returns a ``PluginRegistry`` shape with every
list field empty and the ``workerProviders`` map empty.

Public API:
- ``create_empty_plugin_registry()`` — returns a fresh
  empty ``PluginRegistry``.

Key port decisions:
- Direct port; the shape mirrors ``PluginRegistry`` from
  ``plugin_registry_types.py``.
- ``workerProviders`` is a dict (OpenClaw's ``Map``).
"""
from __future__ import annotations

from .types import PluginRegistry


def create_empty_plugin_registry() -> PluginRegistry:
    """Return a fresh empty ``PluginRegistry``.

    Mirrors OpenClaw's ``createEmptyPluginRegistry``.
    All list fields are empty; the ``workerProviders``
    map is empty; ``gatewayHandlers`` is an empty dict;
    the diagnostic list is empty.
    """
    return {
        "plugins": [],
        "tools": [],
        "hooks": [],
        "typedHooks": [],
        "channels": [],
        "channelSetups": [],
        "providers": [],
        "modelCatalogProviders": [],
        "sessionCatalogs": [],
        "cliBackends": [],
        "textTransforms": [],
        "embeddingProviders": [],
        "speechProviders": [],
        "realtimeTranscriptionProviders": [],
        "realtimeVoiceProviders": [],
        "mediaUnderstandingProviders": [],
        "transcriptSourceProviders": [],
        "imageGenerationProviders": [],
        "videoGenerationProviders": [],
        "musicGenerationProviders": [],
        "webFetchProviders": [],
        "webSearchProviders": [],
        "workerProviders": {},
        "migrationProviders": [],
        "codexAppServerExtensionFactories": [],
        "agentToolResultMiddlewares": [],
        "memoryEmbeddingProviders": [],
        "agentHarnesses": [],
        "gatewayHandlers": {},
        "gatewayMethodDescriptors": [],
        "coreGatewayMethodNames": [],
        "httpRoutes": [],
        "hostedMediaResolvers": [],
        "mcpServerConnectionResolvers": [],
        "cliRegistrars": [],
        "reloads": [],
        "nodeHostCommands": [],
        "nodeInvokePolicies": [],
        "securityAuditCollectors": [],
        "services": [],
        "gatewayDiscoveryServices": [],
        "commands": [],
        "interactiveHandlers": [],
        "sessionExtensions": [],
        "trustedToolPolicies": [],
        "toolMetadata": [],
        "controlUiDescriptors": [],
        "runtimeLifecycles": [],
        "agentEventSubscriptions": [],
        "sessionSchedulerJobs": [],
        "sessionActions": [],
        "conversationBindingResolvedHandlers": [],
        "cronJobs": [],
        "doctorContracts": [],
        "skills": [],
        "diagnostics": [],
    }


__all__ = ["create_empty_plugin_registry"]
