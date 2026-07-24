"""jarvis_sdk.plugin_registry_types — shared plugin registry types.

OpenClaw parity: mirrors
``src/plugins/registry-types.ts`` (~520 LOC).
Shared registration types that make up the in-memory
plugin registry. Pure types — no runtime behavior. The
Python port uses ``TypedDict`` (and a few TypeAliases)
to mirror the OpenClaw object shapes; the public surface
is identical for any consumer that treats the registry
opaquely.

Key port decisions:
- OpenClaw ``type`` aliases (without runtime) map to
  ``TypeAlias`` in Python. The Python port uses
  ``TypeAlias = ...`` for each one.
- The large union of registration shapes uses
  ``TypedDict, total=False`` so optional fields match
  the OpenClaw ``field?: T`` shape.
- Many of the types reference OpenClaw types from
  ``./types.js`` (e.g. ``ChannelPlugin``,
  ``ProviderPlugin``, ``OpenClawPluginToolFactory``).
  The Python port exposes these as opaque ``TypeAlias``
  placeholders; consumers that need the full shape
  should add explicit imports from the corresponding
  Python modules when they're ported.
- This module imports nothing from other jarvis_sdk
  modules — pure shapes.
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict, TypeAlias

# Opaque TypeAlias placeholders for the many types
# OpenClaw imports from ``./types.js`` and other modules.
# Consumers should specialize these once those modules
# are ported.
ChannelPlugin: TypeAlias = Any
CliBackendPlugin: TypeAlias = Any
ImageGenerationProviderPlugin: TypeAlias = Any
MediaUnderstandingProviderPlugin: TypeAlias = Any
TranscriptSourceProvider: TypeAlias = Any
MusicGenerationProviderPlugin: TypeAlias = Any
OpenClawPluginCliCommandDescriptor: TypeAlias = Any
OpenClawPluginCliRegistrar: TypeAlias = Any
OpenClawPluginCommandDefinition: TypeAlias = Any
PluginInteractiveHandlerRegistration: TypeAlias = Any
OpenClawPluginGatewayRuntimeScopeSurface: TypeAlias = Any
OpenClawGatewayDiscoveryService: TypeAlias = Any
OpenClawPluginHttpRouteHandler: TypeAlias = Any
OpenClawPluginHttpRouteMatch: TypeAlias = Any
OpenClawPluginHttpRouteAuth: TypeAlias = Any
OpenClawPluginHttpRouteUpgradeHandler: TypeAlias = Any
OpenClawPluginHostedMediaResolver: TypeAlias = Any
OpenClawPluginReloadRegistration: TypeAlias = Any
OpenClawPluginSecurityAuditCollector: TypeAlias = Any
OpenClawPluginService: TypeAlias = Any
OpenClawPluginToolFactory: TypeAlias = Any
OpenClawPluginNodeHostCommand: TypeAlias = Any
OpenClawPluginNodeInvokePolicy: TypeAlias = Any
PluginConversationBindingResolvedEvent: TypeAlias = Any
TypedPluginHookRegistration: TypeAlias = Any
PluginLogger: TypeAlias = Any
PluginOrigin: TypeAlias = Any
PluginTextTransformRegistration: TypeAlias = Any
MigrationProviderPlugin: TypeAlias = Any
ProviderPlugin: TypeAlias = Any
RealtimeTranscriptionProviderPlugin: TypeAlias = Any
RealtimeVoiceProviderPlugin: TypeAlias = Any
SpeechProviderPlugin: TypeAlias = Any
VideoGenerationProviderPlugin: TypeAlias = Any
WebFetchProviderPlugin: TypeAlias = Any
WebSearchProviderPlugin: TypeAlias = Any
WorkerProvider: TypeAlias = Any
UnifiedModelCatalogProviderPlugin: TypeAlias = Any
PluginCompatCode: TypeAlias = Any
PluginActivationSource: TypeAlias = Any
PluginFormat: TypeAlias = Any
PluginBundleFormat: TypeAlias = Any
PluginConfigUiHint: TypeAlias = Any
PluginDiagnostic: TypeAlias = Any
PluginManifestContracts: TypeAlias = Any
MemoryEmbeddingProviderAdapter: TypeAlias = Any
PluginKind: TypeAlias = Any
PluginRuntime: TypeAlias = Any
SessionCatalogProvider: TypeAlias = Any
PluginDependencyStatus: TypeAlias = Any
JsonSchemaObject: TypeAlias = Any
HookEntry: TypeAlias = Any
GatewayMethodDescriptor: TypeAlias = Any
GatewayRequestHandlers: TypeAlias = Any
AgentHarness: TypeAlias = Any
AgentToolResultMiddleware: TypeAlias = Any
AgentToolResultMiddlewareRuntime: TypeAlias = Any
CodexAppServerExtensionFactory: TypeAlias = Any
EmbeddingProviderAdapter: TypeAlias = Any
PluginAgentEventSubscriptionRegistration: TypeAlias = Any
PluginControlUiDescriptor: TypeAlias = Any
PluginRuntimeLifecycleRegistration: TypeAlias = Any
PluginSessionActionRegistration: TypeAlias = Any
PluginSessionSchedulerJobRegistration: TypeAlias = Any
PluginSessionExtensionRegistration: TypeAlias = Any
PluginToolMetadataRegistration: TypeAlias = Any
PluginTrustedToolPolicyRegistration: TypeAlias = Any
PluginMcpServerConnectionResolverRegistration: TypeAlias = Any
CronServiceContract: TypeAlias = Any

# ── Registration shapes ─────────────────────────────────────────────


class PluginToolRegistration(TypedDict, total=False):
    """Agent tool factory registered by one plugin runtime."""

    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    factory: OpenClawPluginToolFactory
    names: list[str]
    declaredNames: list[str]  # noqa: N815
    optional: bool
    origin: PluginOrigin
    source: str
    rootDir: str  # noqa: N815


class PluginCliRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    register: OpenClawPluginCliRegistrar
    parentPath: list[str]  # noqa: N815
    commands: list[str]
    descriptors: list[OpenClawPluginCliCommandDescriptor]
    source: str
    rootDir: str  # noqa: N815


class PluginHttpRouteRegistration(TypedDict, total=False):
    """Gateway HTTP route registered by a plugin runtime."""

    pluginId: str  # noqa: N815
    path: str
    handler: OpenClawPluginHttpRouteHandler
    handleUpgrade: OpenClawPluginHttpRouteUpgradeHandler  # noqa: N815
    auth: OpenClawPluginHttpRouteAuth
    match: OpenClawPluginHttpRouteMatch
    gatewayRuntimeScopeSurface: OpenClawPluginGatewayRuntimeScopeSurface  # noqa: N815
    gatewayMethodDispatchAllowed: bool  # noqa: N815
    nodeCapability: dict[str, Any]  # { surface, ttlMs? }
    source: str


class PluginHostedMediaResolverRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    resolver: OpenClawPluginHostedMediaResolver
    source: str
    rootDir: str  # noqa: N815


class PluginChannelRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    plugin: ChannelPlugin
    origin: PluginOrigin
    source: str
    rootDir: str  # noqa: N815


class PluginChannelSetupRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    plugin: ChannelPlugin
    origin: PluginOrigin
    source: str
    enabled: bool
    rootDir: str  # noqa: N815


class PluginProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: ProviderPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginModelCatalogProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: UnifiedModelCatalogProviderPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginSessionCatalogRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: SessionCatalogProvider
    source: str
    rootDir: str  # noqa: N815


class PluginCliBackendRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    backend: CliBackendPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginTextTransformsRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    transforms: PluginTextTransformRegistration
    source: str
    rootDir: str  # noqa: N815


class PluginSpeechProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: SpeechProviderPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginEmbeddingProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: EmbeddingProviderAdapter
    source: str
    rootDir: str  # noqa: N815


class PluginRealtimeTranscriptionProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: RealtimeTranscriptionProviderPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginRealtimeVoiceProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: RealtimeVoiceProviderPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginMediaUnderstandingProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: MediaUnderstandingProviderPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginTranscriptsSourceProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: TranscriptSourceProvider
    source: str
    rootDir: str  # noqa: N815


class PluginImageGenerationProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: ImageGenerationProviderPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginVideoGenerationProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: VideoGenerationProviderPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginMusicGenerationProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: MusicGenerationProviderPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginWebFetchProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: WebFetchProviderPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginWebSearchProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: WebSearchProviderPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginWorkerProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: WorkerProvider
    source: str
    rootDir: str  # noqa: N815


class PluginMigrationProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: MigrationProviderPlugin
    source: str
    rootDir: str  # noqa: N815


class PluginMemoryEmbeddingProviderRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    provider: MemoryEmbeddingProviderAdapter
    source: str
    rootDir: str  # noqa: N815


class PluginCodexAppServerExtensionFactoryRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    rawFactory: CodexAppServerExtensionFactory  # noqa: N815
    factory: CodexAppServerExtensionFactory
    source: str
    rootDir: str  # noqa: N815


class PluginAgentToolResultMiddlewareRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    rawHandler: AgentToolResultMiddleware  # noqa: N815
    handler: AgentToolResultMiddleware
    runtimes: list[AgentToolResultMiddlewareRuntime]
    source: str
    rootDir: str  # noqa: N815


class PluginAgentHarnessRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    harness: AgentHarness
    source: str
    rootDir: str  # noqa: N815


class PluginHookRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    entry: HookEntry
    events: list[str]
    source: str
    rootDir: str  # noqa: N815


class PluginServiceRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    service: OpenClawPluginService
    source: str
    origin: PluginOrigin
    trustedOfficialInstall: bool  # noqa: N815
    rootDir: str  # noqa: N815


class PluginGatewayDiscoveryServiceRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    service: OpenClawGatewayDiscoveryService
    source: str
    rootDir: str  # noqa: N815


class PluginReloadRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    registration: OpenClawPluginReloadRegistration
    source: str
    rootDir: str  # noqa: N815


class PluginNodeHostCommandRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    command: OpenClawPluginNodeHostCommand
    source: str
    rootDir: str  # noqa: N815


class PluginNodeInvokePolicyRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    policy: OpenClawPluginNodeInvokePolicy
    pluginConfig: dict[str, Any]  # noqa: N815
    source: str
    rootDir: str  # noqa: N815


class PluginSecurityAuditCollectorRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    collector: OpenClawPluginSecurityAuditCollector
    source: str
    rootDir: str  # noqa: N815


class PluginCommandRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    command: OpenClawPluginCommandDefinition
    source: str
    rootDir: str  # noqa: N815


class PluginInteractiveHandlerRegistryRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    pluginRoot: str  # noqa: N815
    # Plus the PluginInteractiveHandlerRegistration fields
    # are spread in; opaque via TypeAlias above.


class PluginSessionExtensionRegistryRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    extension: PluginSessionExtensionRegistration
    source: str
    rootDir: str  # noqa: N815


class PluginTrustedToolPolicyRegistryRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    policy: PluginTrustedToolPolicyRegistration
    origin: Any  # PluginRecord["origin"] — circular, opaque
    source: str
    rootDir: str  # noqa: N815


class PluginToolMetadataRegistryRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    metadata: PluginToolMetadataRegistration
    source: str
    rootDir: str  # noqa: N815


class PluginControlUiDescriptorRegistryRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    descriptor: PluginControlUiDescriptor
    source: str
    rootDir: str  # noqa: N815


class PluginRuntimeLifecycleRegistryRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    lifecycle: PluginRuntimeLifecycleRegistration
    source: str
    rootDir: str  # noqa: N815


class PluginAgentEventSubscriptionRegistryRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    subscription: PluginAgentEventSubscriptionRegistration
    source: str
    rootDir: str  # noqa: N815


class PluginSessionSchedulerJobRegistryRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    job: PluginSessionSchedulerJobRegistration
    generation: int
    source: str
    rootDir: str  # noqa: N815


class PluginSessionActionRegistryRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    action: PluginSessionActionRegistration
    source: str
    rootDir: str  # noqa: N815


class PluginConversationBindingResolvedHandlerRegistration(TypedDict, total=False):
    pluginId: str  # noqa: N815
    pluginName: str  # noqa: N815
    pluginRoot: str  # noqa: N815
    handler: Any  # (event) -> None | Awaitable[None]
    source: str
    rootDir: str  # noqa: N815


# ── PluginRecord + PluginRegistry (the public surface) ──────────────


class PluginRecord(TypedDict, total=False):
    """One plugin's record in the registry.

    Mirrors OpenClaw's ``PluginRecord`` type. Most fields
    are optional; only ``id``, ``name``, ``source``,
    ``origin``, ``enabled``, ``status``, and the
    ``*-ids`` lists are guaranteed.
    """

    id: str
    name: str
    version: str
    packageName: str  # noqa: N815
    description: str
    format: PluginFormat
    bundleFormat: PluginBundleFormat  # noqa: N815
    bundleCapabilities: list[str]  # noqa: N815
    kind: Any  # PluginKind | PluginKind[]
    source: str
    rootDir: str  # noqa: N815
    origin: PluginOrigin
    workspaceDir: str  # noqa: N815
    trustedOfficialInstall: bool  # noqa: N815
    enabled: bool
    explicitlyEnabled: bool  # noqa: N815
    activated: bool
    imported: bool
    compat: list[PluginCompatCode]
    activationSource: PluginActivationSource  # noqa: N815
    activationReason: str  # noqa: N815
    status: Literal["loaded", "disabled", "error"]
    error: str
    failedAt: Any  # noqa: N815 — Date
    failurePhase: Literal["validation", "load", "register"]  # noqa: N815
    toolNames: list[str]  # noqa: N815
    hookNames: list[str]  # noqa: N815
    channelIds: list[str]  # noqa: N815
    cliBackendIds: list[str]  # noqa: N815
    providerIds: list[str]  # noqa: N815
    syntheticAuthRefs: list[str]  # noqa: N815
    embeddingProviderIds: list[str]  # noqa: N815
    speechProviderIds: list[str]  # noqa: N815
    realtimeTranscriptionProviderIds: list[str]  # noqa: N815
    realtimeVoiceProviderIds: list[str]  # noqa: N815
    mediaUnderstandingProviderIds: list[str]  # noqa: N815
    transcriptSourceProviderIds: list[str]  # noqa: N815
    imageGenerationProviderIds: list[str]  # noqa: N815
    videoGenerationProviderIds: list[str]  # noqa: N815
    musicGenerationProviderIds: list[str]  # noqa: N815
    webFetchProviderIds: list[str]  # noqa: N815
    webSearchProviderIds: list[str]  # noqa: N815
    migrationProviderIds: list[str]  # noqa: N815
    contextEngineIds: list[str]  # noqa: N815
    memoryEmbeddingProviderIds: list[str]  # noqa: N815
    agentHarnessIds: list[str]  # noqa: N815
    cliCommands: list[str]  # noqa: N815
    services: list[str]
    gatewayDiscoveryServiceIds: list[str]  # noqa: N815
    commands: list[str]
    httpRoutes: int  # noqa: N815
    hookCount: int  # noqa: N815
    configSchema: bool  # noqa: N815
    configUiHints: dict[str, PluginConfigUiHint]  # noqa: N815
    configJsonSchema: JsonSchemaObject  # noqa: N815
    contracts: PluginManifestContracts
    memorySlotSelected: bool  # noqa: N815
    dependencyStatus: PluginDependencyStatus  # noqa: N815


class PluginRegistry(TypedDict, total=False):
    """The in-memory plugin registry. All fields are
    arrays / maps of registrations; the registry is
    mutated in place by the domain registrars.
    """

    plugins: list[PluginRecord]
    tools: list[PluginToolRegistration]
    hooks: list[PluginHookRegistration]
    typedHooks: list[TypedPluginHookRegistration]  # noqa: N815
    channels: list[PluginChannelRegistration]
    channelSetups: list[PluginChannelSetupRegistration]  # noqa: N815
    providers: list[PluginProviderRegistration]
    modelCatalogProviders: list[PluginModelCatalogProviderRegistration]  # noqa: N815
    sessionCatalogs: list[PluginSessionCatalogRegistration]  # noqa: N815
    cliBackends: list[PluginCliBackendRegistration]  # noqa: N815
    textTransforms: list[PluginTextTransformsRegistration]  # noqa: N815
    embeddingProviders: list[PluginEmbeddingProviderRegistration]  # noqa: N815
    speechProviders: list[PluginSpeechProviderRegistration]  # noqa: N815
    realtimeTranscriptionProviders: list[PluginRealtimeTranscriptionProviderRegistration]  # noqa: N815
    realtimeVoiceProviders: list[PluginRealtimeVoiceProviderRegistration]  # noqa: N815
    mediaUnderstandingProviders: list[PluginMediaUnderstandingProviderRegistration]  # noqa: N815
    transcriptSourceProviders: list[PluginTranscriptsSourceProviderRegistration]  # noqa: N815
    imageGenerationProviders: list[PluginImageGenerationProviderRegistration]  # noqa: N815
    videoGenerationProviders: list[PluginVideoGenerationProviderRegistration]  # noqa: N815
    musicGenerationProviders: list[PluginMusicGenerationProviderRegistration]  # noqa: N815
    webFetchProviders: list[PluginWebFetchProviderRegistration]  # noqa: N815
    webSearchProviders: list[PluginWebSearchProviderRegistration]  # noqa: N815
    workerProviders: dict[str, PluginWorkerProviderRegistration]  # noqa: N815
    migrationProviders: list[PluginMigrationProviderRegistration]  # noqa: N815
    codexAppServerExtensionFactories: list[PluginCodexAppServerExtensionFactoryRegistration]  # noqa: N815
    agentToolResultMiddlewares: list[PluginAgentToolResultMiddlewareRegistration]  # noqa: N815
    memoryEmbeddingProviders: list[PluginMemoryEmbeddingProviderRegistration]  # noqa: N815
    agentHarnesses: list[PluginAgentHarnessRegistration]  # noqa: N815
    gatewayHandlers: GatewayRequestHandlers  # noqa: N815
    gatewayMethodDescriptors: list[GatewayMethodDescriptor]  # noqa: N815
    coreGatewayMethodNames: list[str]  # noqa: N815
    httpRoutes: list[PluginHttpRouteRegistration]  # noqa: N815
    hostedMediaResolvers: list[PluginHostedMediaResolverRegistration]  # noqa: N815
    mcpServerConnectionResolvers: list[PluginMcpServerConnectionResolverRegistration]  # noqa: N815
    cliRegistrars: list[PluginCliRegistration]  # noqa: N815
    reloads: list[PluginReloadRegistration]
    nodeHostCommands: list[PluginNodeHostCommandRegistration]  # noqa: N815
    nodeInvokePolicies: list[PluginNodeInvokePolicyRegistration]  # noqa: N815
    securityAuditCollectors: list[PluginSecurityAuditCollectorRegistration]  # noqa: N815
    services: list[PluginServiceRegistration]
    gatewayDiscoveryServices: list[PluginGatewayDiscoveryServiceRegistration]  # noqa: N815
    commands: list[PluginCommandRegistration]
    interactiveHandlers: list[PluginInteractiveHandlerRegistryRegistration]  # noqa: N815
    sessionExtensions: list[PluginSessionExtensionRegistryRegistration]  # noqa: N815
    trustedToolPolicies: list[PluginTrustedToolPolicyRegistryRegistration]  # noqa: N815
    toolMetadata: list[PluginToolMetadataRegistryRegistration]  # noqa: N815
    controlUiDescriptors: list[PluginControlUiDescriptorRegistryRegistration]  # noqa: N815
    runtimeLifecycles: list[PluginRuntimeLifecycleRegistryRegistration]  # noqa: N815
    agentEventSubscriptions: list[PluginAgentEventSubscriptionRegistryRegistration]  # noqa: N815
    sessionSchedulerJobs: list[PluginSessionSchedulerJobRegistryRegistration]  # noqa: N815
    sessionActions: list[PluginSessionActionRegistryRegistration]  # noqa: N815
    conversationBindingResolvedHandlers: list[PluginConversationBindingResolvedHandlerRegistration]  # noqa: N815
    diagnostics: list[PluginDiagnostic]


class PluginRegistryParams(TypedDict, total=False):
    """Parameters for creating a plugin registry. Mirrors
    OpenClaw's ``PluginRegistryParams``."""

    logger: PluginLogger
    coreGatewayHandlers: GatewayRequestHandlers  # noqa: N815
    coreGatewayMethodNames: list[str]  # noqa: N815
    runtime: PluginRuntime
    hostServices: dict[str, Any]  # noqa: N815
    activateGlobalSideEffects: bool  # noqa: N815


__all__ = [
    # Opaque type aliases (TypeAlias placeholders for OpenClaw types).
    # Listed for clarity; consumers can re-import from the ported
    # ``types.py`` once it's available.
    "ChannelPlugin",
    "CliBackendPlugin",
    "ImageGenerationProviderPlugin",
    "MediaUnderstandingProviderPlugin",
    "TranscriptSourceProvider",
    "MusicGenerationProviderPlugin",
    "OpenClawPluginCliCommandDescriptor",
    "OpenClawPluginCliRegistrar",
    "OpenClawPluginCommandDefinition",
    "PluginInteractiveHandlerRegistration",
    "OpenClawPluginGatewayRuntimeScopeSurface",
    "OpenClawGatewayDiscoveryService",
    "OpenClawPluginHttpRouteHandler",
    "OpenClawPluginHttpRouteMatch",
    "OpenClawPluginHttpRouteAuth",
    "OpenClawPluginHttpRouteUpgradeHandler",
    "OpenClawPluginHostedMediaResolver",
    "OpenClawPluginReloadRegistration",
    "OpenClawPluginSecurityAuditCollector",
    "OpenClawPluginService",
    "OpenClawPluginToolFactory",
    "OpenClawPluginNodeHostCommand",
    "OpenClawPluginNodeInvokePolicy",
    "PluginConversationBindingResolvedEvent",
    "TypedPluginHookRegistration",
    "PluginLogger",
    "PluginOrigin",
    "PluginTextTransformRegistration",
    "MigrationProviderPlugin",
    "ProviderPlugin",
    "RealtimeTranscriptionProviderPlugin",
    "RealtimeVoiceProviderPlugin",
    "SpeechProviderPlugin",
    "VideoGenerationProviderPlugin",
    "WebFetchProviderPlugin",
    "WebSearchProviderPlugin",
    "WorkerProvider",
    "UnifiedModelCatalogProviderPlugin",
    "PluginCompatCode",
    "PluginActivationSource",
    "PluginFormat",
    "PluginBundleFormat",
    "PluginConfigUiHint",
    "PluginDiagnostic",
    "PluginManifestContracts",
    "MemoryEmbeddingProviderAdapter",
    "PluginKind",
    "PluginRuntime",
    "SessionCatalogProvider",
    "PluginDependencyStatus",
    "JsonSchemaObject",
    "HookEntry",
    "GatewayMethodDescriptor",
    "GatewayRequestHandlers",
    "AgentHarness",
    "AgentToolResultMiddleware",
    "AgentToolResultMiddlewareRuntime",
    "CodexAppServerExtensionFactory",
    "EmbeddingProviderAdapter",
    "PluginAgentEventSubscriptionRegistration",
    "PluginControlUiDescriptor",
    "PluginRuntimeLifecycleRegistration",
    "PluginSessionActionRegistration",
    "PluginSessionSchedulerJobRegistration",
    "PluginSessionExtensionRegistration",
    "PluginToolMetadataRegistration",
    "PluginTrustedToolPolicyRegistration",
    "PluginMcpServerConnectionResolverRegistration",
    "CronServiceContract",
    # Registration shapes.
    "PluginToolRegistration",
    "PluginCliRegistration",
    "PluginHttpRouteRegistration",
    "PluginHostedMediaResolverRegistration",
    "PluginChannelRegistration",
    "PluginChannelSetupRegistration",
    "PluginProviderRegistration",
    "PluginModelCatalogProviderRegistration",
    "PluginSessionCatalogRegistration",
    "PluginCliBackendRegistration",
    "PluginTextTransformsRegistration",
    "PluginSpeechProviderRegistration",
    "PluginEmbeddingProviderRegistration",
    "PluginRealtimeTranscriptionProviderRegistration",
    "PluginRealtimeVoiceProviderRegistration",
    "PluginMediaUnderstandingProviderRegistration",
    "PluginTranscriptsSourceProviderRegistration",
    "PluginImageGenerationProviderRegistration",
    "PluginVideoGenerationProviderRegistration",
    "PluginMusicGenerationProviderRegistration",
    "PluginWebFetchProviderRegistration",
    "PluginWebSearchProviderRegistration",
    "PluginWorkerProviderRegistration",
    "PluginMigrationProviderRegistration",
    "PluginMemoryEmbeddingProviderRegistration",
    "PluginCodexAppServerExtensionFactoryRegistration",
    "PluginAgentToolResultMiddlewareRegistration",
    "PluginAgentHarnessRegistration",
    "PluginHookRegistration",
    "PluginServiceRegistration",
    "PluginGatewayDiscoveryServiceRegistration",
    "PluginReloadRegistration",
    "PluginNodeHostCommandRegistration",
    "PluginNodeInvokePolicyRegistration",
    "PluginSecurityAuditCollectorRegistration",
    "PluginCommandRegistration",
    "PluginInteractiveHandlerRegistryRegistration",
    "PluginSessionExtensionRegistryRegistration",
    "PluginTrustedToolPolicyRegistryRegistration",
    "PluginToolMetadataRegistryRegistration",
    "PluginControlUiDescriptorRegistryRegistration",
    "PluginRuntimeLifecycleRegistryRegistration",
    "PluginAgentEventSubscriptionRegistryRegistration",
    "PluginSessionSchedulerJobRegistryRegistration",
    "PluginSessionActionRegistryRegistration",
    "PluginConversationBindingResolvedHandlerRegistration",
    # Public surface.
    "PluginRecord",
    "PluginRegistry",
    "PluginRegistryParams",
]
