"""Tests for plugin_registry_types + plugin_registry_empty + plugin_registry_lifecycle + plugin_registry_state.

Covers the public surface of the 4 clean plugin-registry
modules ported in Phase 5.6a.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the SDK importable when running this file in isolation.
_PKG_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PKG_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from plugins.empty import (  # noqa: E402
    create_empty_plugin_registry,
)
from plugins.lifecycle import (  # noqa: E402
    is_plugin_registry_activated,
    is_plugin_registry_retired,
    mark_plugin_registry_active,
    mark_plugin_registry_retired,
)
from plugins.state import (  # noqa: E402
    create_plugin_registry_state,
    resolve_plugin_registration_capabilities,
    resolve_typed_hook_timeout_ms,
)
from plugins.types import (  # noqa: E402
    PluginRecord,
    PluginRegistry,
)


# ── plugin_registry_empty ──────────────────────────────────────────


def test_empty_registry_has_empty_lists() -> None:
    """Every list field on the empty registry is an empty list."""
    registry = create_empty_plugin_registry()
    list_fields = [
        "plugins",
        "tools",
        "hooks",
        "typedHooks",
        "channels",
        "channelSetups",
        "providers",
        "modelCatalogProviders",
        "sessionCatalogs",
        "cliBackends",
        "textTransforms",
        "embeddingProviders",
        "speechProviders",
        "realtimeTranscriptionProviders",
        "realtimeVoiceProviders",
        "mediaUnderstandingProviders",
        "transcriptSourceProviders",
        "imageGenerationProviders",
        "videoGenerationProviders",
        "musicGenerationProviders",
        "webFetchProviders",
        "webSearchProviders",
        "migrationProviders",
        "codexAppServerExtensionFactories",
        "agentToolResultMiddlewares",
        "memoryEmbeddingProviders",
        "agentHarnesses",
        "gatewayMethodDescriptors",
        "coreGatewayMethodNames",
        "httpRoutes",
        "hostedMediaResolvers",
        "mcpServerConnectionResolvers",
        "cliRegistrars",
        "reloads",
        "nodeHostCommands",
        "nodeInvokePolicies",
        "securityAuditCollectors",
        "services",
        "gatewayDiscoveryServices",
        "commands",
        "interactiveHandlers",
        "sessionExtensions",
        "trustedToolPolicies",
        "toolMetadata",
        "controlUiDescriptors",
        "runtimeLifecycles",
        "agentEventSubscriptions",
        "sessionSchedulerJobs",
        "sessionActions",
        "conversationBindingResolvedHandlers",
        "diagnostics",
    ]
    for field in list_fields:
        assert registry[field] == [], f"{field} should be an empty list"  # type: ignore[literal-required]


def test_empty_registry_worker_providers_is_empty_dict() -> None:
    """``workerProviders`` is a dict (OpenClaw's ``Map``)."""
    registry = create_empty_plugin_registry()
    assert registry["workerProviders"] == {}


def test_empty_registry_gateway_handlers_is_empty_dict() -> None:
    """``gatewayHandlers`` starts as an empty dict."""
    registry = create_empty_plugin_registry()
    assert registry["gatewayHandlers"] == {}


def test_empty_registry_is_independent() -> None:
    """Each call returns a fresh registry (no shared state)."""
    r1 = create_empty_plugin_registry()
    r2 = create_empty_plugin_registry()
    r1["plugins"].append({"id": "x", "name": "x", "source": "s", "origin": "o", "enabled": True, "status": "loaded", "toolNames": [], "hookNames": [], "channelIds": [], "cliBackendIds": [], "providerIds": [], "embeddingProviderIds": [], "speechProviderIds": [], "realtimeTranscriptionProviderIds": [], "realtimeVoiceProviderIds": [], "mediaUnderstandingProviderIds": [], "transcriptSourceProviderIds": [], "imageGenerationProviderIds": [], "videoGenerationProviderIds": [], "musicGenerationProviderIds": [], "webFetchProviderIds": [], "webSearchProviderIds": [], "migrationProviderIds": [], "memoryEmbeddingProviderIds": [], "agentHarnessIds": [], "cliCommands": [], "services": [], "gatewayDiscoveryServiceIds": [], "commands": [], "httpRoutes": 0, "hookCount": 0, "configSchema": False})
    assert r2["plugins"] == []


# ── plugin_registry_lifecycle ──────────────────────────────────────


def test_lifecycle_new_registry_neither_active_nor_retired() -> None:
    """A fresh registry is neither active nor retired."""
    registry = create_empty_plugin_registry()
    assert is_plugin_registry_activated(registry) is False
    assert is_plugin_registry_retired(registry) is False


def test_lifecycle_mark_active() -> None:
    """``mark_plugin_registry_active`` sets the active flag."""
    registry = create_empty_plugin_registry()
    mark_plugin_registry_active(registry)
    assert is_plugin_registry_activated(registry) is True
    assert is_plugin_registry_retired(registry) is False


def test_lifecycle_mark_retired() -> None:
    """``mark_plugin_registry_retired`` sets the retired flag."""
    registry = create_empty_plugin_registry()
    mark_plugin_registry_retired(registry)
    assert is_plugin_registry_retired(registry) is True
    assert is_plugin_registry_activated(registry) is False


def test_lifecycle_active_clears_retired() -> None:
    """Marking a registry active clears any previous retired state."""
    registry = create_empty_plugin_registry()
    mark_plugin_registry_retired(registry)
    assert is_plugin_registry_retired(registry) is True
    mark_plugin_registry_active(registry)
    assert is_plugin_registry_retired(registry) is False
    assert is_plugin_registry_activated(registry) is True


def test_lifecycle_none_is_noop() -> None:
    """``None`` inputs are silently ignored (matches the source guard)."""
    mark_plugin_registry_active(None)  # no error
    mark_plugin_registry_retired(None)  # no error


def test_lifecycle_independent_registries() -> None:
    """Each registry has its own lifecycle flag."""
    r1 = create_empty_plugin_registry()
    r2 = create_empty_plugin_registry()
    mark_plugin_registry_active(r1)
    mark_plugin_registry_retired(r2)
    assert is_plugin_registry_activated(r1) is True
    assert is_plugin_registry_retired(r1) is False
    assert is_plugin_registry_activated(r2) is False
    assert is_plugin_registry_retired(r2) is True


# ── plugin_registry_types (TypedDict shape sanity) ─────────────────


def test_plugin_record_minimal_required_fields() -> None:
    """A ``PluginRecord`` accepts only the required fields."""
    # The shape is permissive (TypedDict total=False) so we
    # just confirm we can construct a record with the
    # bare-minimum required fields.
    record: PluginRecord = {
        "id": "test-plugin",
        "name": "Test Plugin",
        "source": "/path/to/plugin",
        "origin": "user",
        "enabled": True,
        "status": "loaded",
        "toolNames": [],
        "hookNames": [],
        "channelIds": [],
        "cliBackendIds": [],
        "providerIds": [],
        "embeddingProviderIds": [],
        "speechProviderIds": [],
        "realtimeTranscriptionProviderIds": [],
        "realtimeVoiceProviderIds": [],
        "mediaUnderstandingProviderIds": [],
        "transcriptSourceProviderIds": [],
        "imageGenerationProviderIds": [],
        "videoGenerationProviderIds": [],
        "musicGenerationProviderIds": [],
        "webFetchProviderIds": [],
        "webSearchProviderIds": [],
        "migrationProviderIds": [],
        "memoryEmbeddingProviderIds": [],
        "agentHarnessIds": [],
        "cliCommands": [],
        "services": [],
        "gatewayDiscoveryServiceIds": [],
        "commands": [],
        "httpRoutes": 0,
        "hookCount": 0,
        "configSchema": False,
    }
    assert record["id"] == "test-plugin"
    assert record["status"] == "loaded"


def test_plugin_registry_shape() -> None:
    """A ``PluginRegistry`` matches the expected TypedDict shape."""
    registry: PluginRegistry = create_empty_plugin_registry()
    # The shape mirrors the OpenClaw source.
    assert "plugins" in registry
    assert "tools" in registry
    assert "hooks" in registry
    assert "channels" in registry
    assert "httpRoutes" in registry
    assert "diagnostics" in registry
    # And the long tail of fields.
    assert "modelCatalogProviders" in registry
    assert "memoryEmbeddingProviders" in registry
    assert "agentHarnesses" in registry
    assert "sessionSchedulerJobs" in registry
    assert "sessionActions" in registry


# -- plugin_registry_state � resolve_plugin_registration_capabilities -


def test_resolve_capabilities_full() -> None:
    """``"full"`` mode enables all capability flags."""
    caps = resolve_plugin_registration_capabilities("full")
    assert caps["capabilityHandlers"] is True
    assert caps["setupRuntimeHandlers"] is False
    assert caps["runtimeChannel"] is True


def test_resolve_capabilities_discovery() -> None:
    """``"discovery"`` mode enables capability handlers + runtime channel."""
    caps = resolve_plugin_registration_capabilities("discovery")
    assert caps["capabilityHandlers"] is True
    assert caps["setupRuntimeHandlers"] is False
    assert caps["runtimeChannel"] is True


def test_resolve_capabilities_tool_discovery() -> None:
    """``"tool-discovery"`` enables capability handlers but suppresses runtime channel."""
    caps = resolve_plugin_registration_capabilities("tool-discovery")
    assert caps["capabilityHandlers"] is True
    assert caps["setupRuntimeHandlers"] is False
    assert caps["runtimeChannel"] is False


def test_resolve_capabilities_setup_runtime() -> None:
    """``"setup-runtime"`` mode enables setup-runtime handlers only."""
    caps = resolve_plugin_registration_capabilities("setup-runtime")
    assert caps["capabilityHandlers"] is False
    assert caps["setupRuntimeHandlers"] is True
    assert caps["runtimeChannel"] is True


def test_resolve_capabilities_setup_only() -> None:
    """``"setup-only"`` mode suppresses capability handlers + runtime channel."""
    caps = resolve_plugin_registration_capabilities("setup-only")
    assert caps["capabilityHandlers"] is False
    assert caps["setupRuntimeHandlers"] is False
    assert caps["runtimeChannel"] is False


# -- plugin_registry_state � resolve_typed_hook_timeout_ms -----------


def test_resolve_timeout_from_policy_timeouts() -> None:
    """``policy.timeouts[hook_name]`` wins when set."""
    timeout = resolve_typed_hook_timeout_ms(
        hook_name="my_hook",
        opts={"timeoutMs": 100},
        policy={
            "timeoutMs": 200,
            "timeouts": {"my_hook": 300},
        },
    )
    assert timeout == 300


def test_resolve_timeout_from_policy_default() -> None:
    """``policy.timeoutMs`` is used when no per-hook override is set."""
    timeout = resolve_typed_hook_timeout_ms(
        hook_name="my_hook",
        policy={"timeoutMs": 200},
    )
    assert timeout == 200


def test_resolve_timeout_from_opts() -> None:
    """``opts.timeoutMs`` is the final fallback."""
    timeout = resolve_typed_hook_timeout_ms(
        hook_name="my_hook",
        opts={"timeoutMs": 100},
    )
    assert timeout == 100


def test_resolve_timeout_none_when_unset() -> None:
    """``None`` is returned when no source provides a timeout."""
    assert resolve_typed_hook_timeout_ms(hook_name="x") is None


def test_resolve_timeout_rejects_non_positive() -> None:
    """Non-positive / non-finite values are dropped (skipped, not normalized)."""
    for bad in (0, -1, -100):
        assert resolve_typed_hook_timeout_ms(
            hook_name="x",
            opts={"timeoutMs": bad},
        ) is None


# -- plugin_registry_state � create_plugin_registry_state ----------


def test_create_state_returns_empty_registry() -> None:
    """The state factory starts from an empty ``PluginRegistry``."""
    state = create_plugin_registry_state({"logger": None})
    assert state["registry"]["plugins"] == []
    assert state["registry"]["tools"] == []


def test_create_state_core_gateway_method_names_sorted() -> None:
    """``coreGatewayMethodNames`` is sorted + de-duped."""
    state = create_plugin_registry_state(
        {
            "logger": None,
            "coreGatewayMethodNames": ["zeta", "alpha", "mu"],
            "coreGatewayHandlers": {"alpha": None, "beta": None},
        }
    )
    # Sorted + de-duped: alpha, beta, mu, zeta
    assert state["registry"]["coreGatewayMethodNames"] == ["alpha", "beta", "mu", "zeta"]


def test_create_state_dedupes_core_gateway_method_names() -> None:
    """Duplicates between handlers + params are dropped."""
    state = create_plugin_registry_state(
        {
            "logger": None,
            "coreGatewayMethodNames": ["a", "b"],
            "coreGatewayHandlers": {"a": None, "c": None},
        }
    )
    assert state["registry"]["coreGatewayMethodNames"] == ["a", "b", "c"]


def test_create_state_push_diagnostic() -> None:
    """``pushDiagnostic`` appends to the registry's diagnostic list."""
    state = create_plugin_registry_state({"logger": None})
    state["pushDiagnostic"]({"level": "error", "message": "boom"})
    assert len(state["registry"]["diagnostics"]) == 1
    assert state["registry"]["diagnostics"][0]["message"] == "boom"


def test_create_state_has_rollback_map() -> None:
    """The state carries an empty ``pluginHookRollback`` map."""
    state = create_plugin_registry_state({"logger": None})
    assert state["pluginHookRollback"] == {}


def test_create_state_has_side_effect_guards() -> None:
    """The state carries an empty ``pluginSideEffectGuards`` map."""
    state = create_plugin_registry_state({"logger": None})
    assert state["pluginSideEffectGuards"] == {}


def test_create_state_has_channel_conflict_set() -> None:
    """The state carries an empty ``pluginsWithChannelRegistrationConflict`` set."""
    state = create_plugin_registry_state({"logger": None})
    assert state["pluginsWithChannelRegistrationConflict"] == set()


def test_create_state_get_host_cron_service() -> None:
    """``getHostCronService`` reads from the params at call time."""
    class _FakeCron:
        pass

    fake = _FakeCron()
    state = create_plugin_registry_state(
        {"logger": None, "hostServices": {"cron": fake}}
    )
    assert state["getHostCronService"]() is fake


def test_create_state_get_host_cron_service_default_none() -> None:
    """``getHostCronService`` returns ``None`` when no host service is configured."""
    state = create_plugin_registry_state({"logger": None})
    assert state["getHostCronService"]() is None


# -- plugin_registry_registrars � composition -----------------------


def test_create_plugin_registrars_returns_full_shape() -> None:
    """The composition includes every public registrar name.

    Mirrors OpenClaw's ``createPluginRegistrars`` which
    spreads the 7 per-domain registrar factories +
    exposes ``registerModelCatalogProvider`` from the
    state.
    """
    from plugins.registrars import create_plugin_registrars
    from plugins.state import create_plugin_registry_state

    state = create_plugin_registry_state({"logger": None})
    registrars = create_plugin_registrars(state)

    # Capability registrars.
    assert "registerSessionSchedulerJob" in registrars
    assert "registerSessionAction" in registrars
    assert "registerAgentEventSubscription" in registrars
    assert "registerRuntimeLifecycle" in registrars
    assert "registerControlUiDescriptor" in registrars
    assert "registerToolMetadata" in registrars
    assert "registerTrustedToolPolicy" in registrars

    # Tool / hook registrars.
    assert "registerTool" in registrars
    assert "registerHook" in registrars
    assert "registerTypedHook" in registrars
    assert "registerHttpRoute" in registrars
    assert "registerAgentToolResultMiddleware" in registrars

    # Network registrars.
    assert "registerChannel" in registrars
    assert "registerHostedMediaResolver" in registrars
    assert "registerMcpServerConnectionResolver" in registrars
    assert "registerReload" in registrars
    assert "registerNodeHostCommand" in registrars
    assert "registerNodeInvokePolicy" in registrars
    assert "registerSecurityAuditCollector" in registrars

    # Provider registrars.
    assert "registerProvider" in registrars
    assert "registerWorkerProvider" in registrars
    assert "registerEmbeddingProvider" in registrars
    assert "registerAgentHarness" in registrars
    assert "registerSpeechProvider" in registrars
    assert "registerRealtimeTranscriptionProvider" in registrars
    assert "registerRealtimeVoiceProvider" in registrars
    assert "registerMediaUnderstandingProvider" in registrars
    assert "registerTranscriptSourceProvider" in registrars
    assert "registerImageGenerationProvider" in registrars
    assert "registerVideoGenerationProvider" in registrars
    assert "registerMusicGenerationProvider" in registrars
    assert "registerWebFetchProvider" in registrars
    assert "registerWebSearchProvider" in registrars
    assert "registerMigrationProvider" in registrars
    assert "registerService" in registrars
    assert "registerGatewayDiscoveryService" in registrars

    # Operation registrars.
    assert "registerGatewayMethod" in registrars
    assert "registerSessionCatalog" in registrars
    assert "registerCliBackend" in registrars
    assert "registerTextTransforms" in registrars
    assert "registerCli" in registrars
    assert "registerCommand" in registrars
    assert "registerSessionExtension" in registrars
    assert "registerCodexAppServerExtensionFactory" in registrars
    assert "registerInteractiveHandler" in registrars
    assert "registerContextEngine" in registrars
    assert "registerCompactionProvider" in registrars

    # Host registrars (memory).
    assert "registerMemoryCapability" in registrars
    assert "registerMemoryPromptSection" in registrars
    assert "registerMemoryPromptSupplement" in registrars
    assert "registerMemoryPromptPreparation" in registrars
    assert "registerMemoryCorpusSupplement" in registrars
    assert "registerMemoryFlushPlan" in registrars
    assert "registerMemoryRuntime" in registrars
    assert "registerMemoryEmbeddingProvider" in registrars

    # Memory registrars (rollback).
    assert "rollbackHooks" in registrars

    # Model-catalog registrar (from state).
    assert "registerModelCatalogProvider" in registrars


def test_create_plugin_registry_wires_state_and_registrars() -> None:
    """``create_plugin_registry`` exposes both the state and the registrars.

    Mirrors OpenClaw's ``createPluginRegistry`` return
    shape: ``registry`` (the state) + ``createApi`` +
    ``rollbackPluginGlobalSideEffects`` +
    ``pushDiagnostic`` + the registrars spread in.
    """
    from plugins.registry import create_plugin_registry

    result = create_plugin_registry({"logger": None})

    assert "registry" in result
    assert "createApi" in result
    assert "rollbackPluginGlobalSideEffects" in result
    assert "pushDiagnostic" in result
    assert "registerTool" in result  # from registrars spread
    assert "registerChannel" in result
    assert "registerProvider" in result


def test_create_plugin_registry_create_api_is_callable() -> None:
    """The stub ``createApi`` returns a dict with the expected shape."""
    from plugins.registry import create_plugin_registry

    result = create_plugin_registry({"logger": None})
    api = result["createApi"](
        {
            "id": "x",
            "name": "x",
            "source": "s",
            "origin": "user",
            "enabled": True,
            "status": "loaded",
        },
        {"config": {}},
    )
    assert isinstance(api, dict)
    assert api["id"] == ""
    # The stub exposes a registerCli / registerChannel no-op.
    assert "registerCli" in api
    assert "registerChannel" in api


def test_create_plugin_registry_registrars_are_noop_by_default() -> None:
    """The composition uses no-op registrars (until the
    per-domain registrar files are ported)."""
    from plugins.registry import create_plugin_registry

    result = create_plugin_registry({"logger": None})
    # Calling any registrar is safe (no-op).
    result["registerTool"](None, None)
    result["registerChannel"](None)
    result["registerProvider"](None)


def test_registrars_share_state() -> None:
    """Two registry instances have independent state + registrars."""
    from plugins.registry import create_plugin_registry

    r1 = create_plugin_registry({"logger": None})
    r2 = create_plugin_registry({"logger": None})

    # Mutating r1's diagnostics doesn't affect r2.
    r1["pushDiagnostic"]({"level": "error", "message": "boom"})
    assert len(r1["registry"]["diagnostics"]) == 1
    assert len(r2["registry"]["diagnostics"]) == 0
