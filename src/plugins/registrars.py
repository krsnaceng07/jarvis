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

from typing import Any, TypeAlias, cast


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


def _create_capability_registrars(_state: dict[str, Any]) -> dict[str, Any]:
    """Stub for ``createCapabilityRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-capabilities.ts`` exports.
    """
    def _append(list_key: str, plugin: dict[str, Any], item: Any | None = None) -> None:
        if plugin is None or item is None:
            return None
        entry: dict[str, Any] = {"ownerPluginId": plugin.get("id", "")}
        if isinstance(item, dict):
            entry.update(cast(dict[str, Any], item))
        else:
            entry["item"] = item
        _state["registry"].setdefault(list_key, []).append(entry)

    def register_session_scheduler_job(plugin: dict[str, Any], job: dict[str, Any] | None = None) -> None:
        return _append("sessionSchedulerJobs", plugin, job)

    def register_session_action(plugin: dict[str, Any], action: dict[str, Any] | None = None) -> None:
        return _append("sessionActions", plugin, action)

    def register_agent_event_subscription(plugin: dict[str, Any], sub: dict[str, Any] | None = None) -> None:
        return _append("agentEventSubscriptions", plugin, sub)

    def register_runtime_lifecycle(plugin: dict[str, Any], lifecycle: dict[str, Any] | None = None) -> None:
        return _append("runtimeLifecycles", plugin, lifecycle)

    def register_control_ui_descriptor(plugin: dict[str, Any], desc: dict[str, Any] | None = None) -> None:
        return _append("controlUiDescriptors", plugin, desc)

    def register_tool_metadata(plugin: dict[str, Any], meta: dict[str, Any] | None = None) -> None:
        return _append("toolMetadata", plugin, meta)

    def register_trusted_tool_policy(plugin: dict[str, Any], policy: dict[str, Any] | None = None) -> None:
        return _append("trustedToolPolicies", plugin, policy)

    def register_cron(plugin: dict[str, Any], job: dict[str, Any] | None = None) -> None:
        return _append("cronJobs", plugin, job)

    def register_doctor_contract(plugin: dict[str, Any], contract: dict[str, Any] | None = None) -> None:
        return _append("doctorContracts", plugin, contract)

    def register_skill(plugin: dict[str, Any], skill: Any | None = None) -> None:
        return _append("skills", plugin, skill)

    return {
        "registerSessionSchedulerJob": register_session_scheduler_job,
        "registerSessionAction": register_session_action,
        "registerAgentEventSubscription": register_agent_event_subscription,
        "registerRuntimeLifecycle": register_runtime_lifecycle,
        "registerControlUiDescriptor": register_control_ui_descriptor,
        "registerToolMetadata": register_tool_metadata,
        "registerTrustedToolPolicy": register_trusted_tool_policy,
        "registerCron": register_cron,
        "registerDoctorContract": register_doctor_contract,
        "registerSkill": register_skill,
    }


def _create_tool_hook_registrars(_state: dict[str, Any]) -> dict[str, Any]:
    """Stub for ``createToolHookRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-tools-hooks.ts`` exports.
    """
    def _normalize_names(raw_names: list[str] | None) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for n in raw_names or ():
            if not isinstance(n, str):
                continue
            t = n.strip()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out

    def register_tool(plugin: dict[str, Any], tool: Any, opts: dict[str, Any] | None = None) -> None:
        """Register a tool on behalf of `plugin`.

        Minimal host-side implementation: record the declaration in
        the registry under `registry['tools']` with owner metadata.
        This mirrors the SDK's `PluginApi.register_tool` enough for
        discovery and later wiring.
        """
        if plugin is None:
            return None
        opts = opts or {}
        # Collect names: opts.name, opts.names, and callable/tool.name
        names: list[str] = []
        if isinstance(opts.get("name"), str):
            names.append(opts["name"])
        if isinstance(opts.get("names"), list):
            names.extend([n for n in opts["names"] if isinstance(n, str)])
        if not callable(tool) and hasattr(tool, "name"):
            try:
                names.append(getattr(tool, "name"))
            except Exception:
                pass
        normalized = _normalize_names(names)
        entry: dict[str, Any] = {
            "ownerPluginId": plugin.get("id", ""),
            "tool": tool,
            "names": normalized,
        }
        _state["registry"]["tools"].append(entry)

    def register_hook(plugin: dict[str, Any], hook: Any) -> None:
        if plugin is None:
            return None
        _state["registry"]["hooks"].append({"ownerPluginId": plugin.get("id", ""), "hook": hook})

    def register_typed_hook(plugin: dict[str, Any], hook_name: str, handler: Any, policy: dict[str, Any] | None = None) -> None:
        if plugin is None:
            return None
        _state["registry"]["typedHooks"].append({"ownerPluginId": plugin.get("id", ""), "hookName": hook_name, "handler": handler, "policy": policy})

    def register_http_route(plugin: dict[str, Any], route: dict[str, Any]) -> None:
        if plugin is None:
            return None
        # Ensure route has path and handler
        if not isinstance(route, dict) or "path" not in route or "handler" not in route:
            _state["registry"]["diagnostics"].append({"level": "error", "message": "invalid http route"})
            return
        r = dict(route)
        r["_owner_id"] = plugin.get("id", "")
        _state["registry"]["httpRoutes"].append(r)

    def register_agent_tool_result_middleware(plugin: dict[str, Any], middleware: Any) -> None:
        if plugin is None:
            return None
        _state["registry"]["agentToolResultMiddlewares"].append({"ownerPluginId": plugin.get("id", ""), "middleware": middleware})

    return {
        "registerTool": register_tool,
        "registerHook": register_hook,
        "registerTypedHook": register_typed_hook,
        "registerHttpRoute": register_http_route,
        "registerHttpHandler": register_http_route,
        "registerAgentToolResultMiddleware": register_agent_tool_result_middleware,
    }


def _create_network_registrars(_state: dict[str, Any]) -> dict[str, Any]:
    """Stub for ``createNetworkRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-network.ts`` exports.
    """
    def _append(list_key: str, plugin: dict[str, Any], item: Any | None = None) -> None:
        if plugin is None or item is None:
            return None
        entry: dict[str, Any] = {"ownerPluginId": plugin.get("id", "")}
        if isinstance(item, dict):
            entry.update(cast(dict[str, Any], item))
        else:
            entry["item"] = item
        _state["registry"].setdefault(list_key, []).append(entry)

    def register_channel(plugin: dict[str, Any], channel: Any | None = None) -> None:
        if plugin is None or channel is None:
            return None
        if isinstance(channel, dict):
            registration = dict(cast(dict[str, Any], channel))
        else:
            registration = {"plugin": channel}
        registration["pluginId"] = plugin.get("id", "")
        registration["pluginName"] = plugin.get("name", "")
        registration["origin"] = plugin.get("origin")
        registration["source"] = plugin.get("source")
        _state["registry"].setdefault("channels", []).append(registration)

    def register_hosted_media_resolver(plugin: dict[str, Any], resolver: Any | None = None) -> None:
        return _append("hostedMediaResolvers", plugin, resolver)

    def register_mcp_server_connection_resolver(plugin: dict[str, Any], resolver: Any | None = None) -> None:
        return _append("mcpServerConnectionResolvers", plugin, resolver)

    def register_reload(plugin: dict[str, Any], reload: Any | None = None) -> None:
        return _append("reloads", plugin, reload)

    def register_node_host_command(plugin: dict[str, Any], command: Any | None = None) -> None:
        return _append("nodeHostCommands", plugin, command)

    def register_node_invoke_policy(plugin: dict[str, Any], policy: Any | None = None) -> None:
        return _append("nodeInvokePolicies", plugin, policy)

    def register_security_audit_collector(plugin: dict[str, Any], collector: Any | None = None) -> None:
        return _append("securityAuditCollectors", plugin, collector)

    return {
        "registerChannel": register_channel,
        "registerHostedMediaResolver": register_hosted_media_resolver,
        "registerMcpServerConnectionResolver": register_mcp_server_connection_resolver,
        "registerReload": register_reload,
        "registerNodeHostCommand": register_node_host_command,
        "registerNodeInvokePolicy": register_node_invoke_policy,
        "registerSecurityAuditCollector": register_security_audit_collector,
    }


def _create_provider_registrars(_state: dict[str, Any]) -> dict[str, Any]:
    """Stub for ``createProviderRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-providers.ts`` exports.
    """
    def _ensure_provider_id(provider: dict[str, Any]) -> str | None:
        if not isinstance(provider, dict):
            return None
        pid = provider.get("id")
        if not isinstance(pid, str) or not pid:
            return None
        return pid

    def _register_generic(list_key: str, plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        if plugin is None or provider is None:
            return None
        pid = _ensure_provider_id(provider)
        if pid is None:
            _state["registry"]["diagnostics"].append({"level": "error", "message": "provider missing id"})
            return
        # check duplicates
        existing: list[dict[str, Any]] = []
        for item in cast(list[Any], _state["registry"].get(list_key, [])):
            if isinstance(item, dict) and cast(dict[str, Any], item)["id"] == pid:
                existing.append(cast(dict[str, Any], item))
        if existing:
            _state["registry"]["diagnostics"].append(
                {"level": "error", "message": f"provider already registered: {pid}"}
            )
            return
        _state["registry"].setdefault(list_key, []).append(provider)

    def register_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("providers", plugin, provider)

    def register_worker_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        if plugin is None:
            return None
        if provider is None:
            return None
        pid = _ensure_provider_id(provider)
        if pid is None:
            _state["registry"]["diagnostics"].append({"level": "error", "message": "worker provider missing id"})
            return
        # workerProviders is a map
        workers = _state["registry"].setdefault("workerProviders", {})
        if pid in workers:
            _state["registry"]["diagnostics"].append({"level": "error", "message": f"worker provider already registered: {pid}"})
            return
        workers[pid] = {"ownerPluginId": plugin.get("id", ""), "provider": provider}

    def register_embedding_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("embeddingProviders", plugin, provider)

    def register_agent_harness(plugin: dict[str, Any], harness: dict[str, Any] | None = None) -> None:
        return _register_generic("agentHarnesses", plugin, harness)

    def register_detached_task_runtime(plugin: dict[str, Any], runtime: dict[str, Any] | None = None) -> None:
        return _register_generic("migrationProviders", plugin, runtime)

    def register_speech_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("speechProviders", plugin, provider)

    def register_realtime_transcription_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("realtimeTranscriptionProviders", plugin, provider)

    def register_realtime_voice_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("realtimeVoiceProviders", plugin, provider)

    def register_media_understanding_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("mediaUnderstandingProviders", plugin, provider)

    def register_transcript_source_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("transcriptSourceProviders", plugin, provider)

    def register_image_generation_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("imageGenerationProviders", plugin, provider)

    def register_video_generation_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("videoGenerationProviders", plugin, provider)

    def register_music_generation_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("musicGenerationProviders", plugin, provider)

    def register_web_fetch_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("webFetchProviders", plugin, provider)

    def register_web_search_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("webSearchProviders", plugin, provider)

    def register_migration_provider(plugin: dict[str, Any], provider: dict[str, Any] | None = None) -> None:
        return _register_generic("migrationProviders", plugin, provider)

    def register_service(plugin: dict[str, Any], service: dict[str, Any] | None = None) -> None:
        return _register_generic("services", plugin, service)

    def register_gateway_discovery_service(plugin: dict[str, Any], service: dict[str, Any] | None = None) -> None:
        return _register_generic("gatewayDiscoveryServices", plugin, service)

    return {
        "registerProvider": register_provider,
        "registerWorkerProvider": register_worker_provider,
        "registerEmbeddingProvider": register_embedding_provider,
        "registerAgentHarness": register_agent_harness,
        "registerDetachedTaskRuntime": register_detached_task_runtime,
        "registerSpeechProvider": register_speech_provider,
        "registerRealtimeTranscriptionProvider": register_realtime_transcription_provider,
        "registerRealtimeVoiceProvider": register_realtime_voice_provider,
        "registerMediaUnderstandingProvider": register_media_understanding_provider,
        "registerTranscriptSourceProvider": register_transcript_source_provider,
        "registerImageGenerationProvider": register_image_generation_provider,
        "registerVideoGenerationProvider": register_video_generation_provider,
        "registerMusicGenerationProvider": register_music_generation_provider,
        "registerWebFetchProvider": register_web_fetch_provider,
        "registerWebSearchProvider": register_web_search_provider,
        "registerMigrationProvider": register_migration_provider,
        "registerService": register_service,
        "registerGatewayDiscoveryService": register_gateway_discovery_service,
    }


def _create_operation_registrars(_state: dict[str, Any]) -> dict[str, Any]:
    """Stub for ``createOperationRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-operations.ts`` exports.
    """
    def _append(list_key: str, plugin: dict[str, Any], item: Any | None = None) -> None:
        if plugin is None or item is None:
            return None
        _state["registry"].setdefault(list_key, []).append({"ownerPluginId": plugin.get("id", ""), **({"item": item} if not isinstance(item, dict) else item)})

    def register_gateway_method(plugin: dict[str, Any], desc: dict[str, Any] | None = None) -> None:
        if desc is None:
            return None
        _state["registry"].setdefault("gatewayMethodDescriptors", []).append({"ownerPluginId": plugin.get("id", ""), **desc})

    def register_session_catalog(plugin: dict[str, Any], catalog: dict[str, Any] | None = None) -> None:
        return _append("sessionCatalogs", plugin, catalog)

    def register_cli_backend(plugin: dict[str, Any], backend: dict[str, Any] | None = None) -> None:
        return _append("cliBackends", plugin, backend)

    def register_text_transforms(plugin: dict[str, Any], transforms: Any | None = None) -> None:
        return _append("textTransforms", plugin, transforms)

    def register_cli(plugin: dict[str, Any], cli_reg: Any | None = None) -> None:
        return _append("cliRegistrars", plugin, cli_reg)

    def register_command(plugin: dict[str, Any], cmd: dict[str, Any] | None = None) -> None:
        return _append("commands", plugin, cmd)

    def register_session_extension(plugin: dict[str, Any], ext: Any | None = None) -> None:
        return _append("sessionExtensions", plugin, ext)

    def register_codex_app_server_extension_factory(plugin: dict[str, Any], factory: Any | None = None) -> None:
        return _append("codexAppServerExtensionFactories", plugin, factory)

    def register_interactive_handler(plugin: dict[str, Any], handler: Any | None = None) -> None:
        return _append("interactiveHandlers", plugin, handler)

    def register_conversation_binding_resolved_handler(plugin: dict[str, Any], handler: Any | None = None) -> None:
        return _append("conversationBindingResolvedHandlers", plugin, handler)

    def register_context_engine(plugin: dict[str, Any], engine: Any | None = None) -> None:
        return _append("runtimeLifecycles", plugin, engine)

    def register_compaction_provider(plugin: dict[str, Any], provider: Any | None = None) -> None:
        return _append("compactionProviders", plugin, provider)

    return {
        "registerGatewayMethod": register_gateway_method,
        "registerSessionCatalog": register_session_catalog,
        "registerCliBackend": register_cli_backend,
        "registerTextTransforms": register_text_transforms,
        "registerTextTransform": register_text_transforms,
        "registerCli": register_cli,
        "registerCommand": register_command,
        "registerSessionExtension": register_session_extension,
        "registerCodexAppServerExtensionFactory": register_codex_app_server_extension_factory,
        "registerInteractiveHandler": register_interactive_handler,
        "registerConversationBindingResolvedHandler": register_conversation_binding_resolved_handler,
        "registerContextEngine": register_context_engine,
        "registerCompactionProvider": register_compaction_provider,
    }


def _create_host_registrars(_state: dict[str, Any]) -> dict[str, Any]:
    """Stub for ``createHostRegistrars``.

    Returns the registrar names that OpenClaw's
    ``registry-registrars-host.ts`` exports.
    """
    def _host_append(list_key: str, plugin: dict[str, Any], item: Any | None = None) -> None:
        if plugin is None or item is None:
            return None
        _state["registry"].setdefault(list_key, []).append({"ownerPluginId": plugin.get("id", ""), **({"item": item} if not isinstance(item, dict) else item)})

    def register_memory_prompt_section(plugin: dict[str, Any], section: Any | None = None) -> None:
        return _host_append("toolMetadata", plugin, section)

    def register_memory_prompt_supplement(plugin: dict[str, Any], supplement: Any | None = None) -> None:
        return _host_append("toolMetadata", plugin, supplement)

    def register_memory_prompt_preparation(plugin: dict[str, Any], prep: Any | None = None) -> None:
        return _host_append("toolMetadata", plugin, prep)

    def register_memory_corpus_supplement(plugin: dict[str, Any], sup: Any | None = None) -> None:
        return _host_append("toolMetadata", plugin, sup)

    def register_memory_flush_plan(plugin: dict[str, Any], plan: Any | None = None) -> None:
        return _host_append("reloads", plugin, plan)

    def register_memory_runtime(plugin: dict[str, Any], runtime: Any | None = None) -> None:
        return _host_append("runtimeLifecycles", plugin, runtime)

    def register_memory_embedding_provider(plugin: dict[str, Any], adapter: dict[str, Any] | None = None) -> None:
        if plugin is None or adapter is None:
            return None
        _state["registry"]["memoryEmbeddingProviders"].append({"ownerPluginId": plugin.get("id", ""), "provider": adapter})

    def register_memory_capability(plugin: dict[str, Any], capability: Any | None = None) -> None:
        # Prefer the memory-specific registrar in _create_memory_registrars; this host stub
        # will delegate to the memory path if present on the composition.
        return _host_append("toolMetadata", plugin, capability)

    return {
        "registerMemoryCapability": register_memory_capability,
        "registerMemoryPromptSection": register_memory_prompt_section,
        "registerMemoryPromptSupplement": register_memory_prompt_supplement,
        "registerMemoryPromptPreparation": register_memory_prompt_preparation,
        "registerMemoryCorpusSupplement": register_memory_corpus_supplement,
        "registerMemoryFlushPlan": register_memory_flush_plan,
        "registerMemoryRuntime": register_memory_runtime,
        "registerMemoryEmbeddingProvider": register_memory_embedding_provider,
    }


def _create_memory_registrars(_state: dict[str, Any]) -> dict[str, Any]:
    """Port of the memory-specific registrar behavior for the OpenClaw suite."""

    from .memory_state import (
        register_memory_capability,
        register_memory_corpus_supplement,
        register_memory_flush_plan_resolver_for_plugin,
        register_memory_prompt_preparation,
        register_memory_prompt_section_for_plugin,
        register_memory_prompt_supplement,
        register_memory_runtime_for_plugin,
    )
    from .memory_embedding_providers import (
        get_registered_memory_embedding_provider,
        register_memory_embedding_provider,
    )

    def _append_tool_metadata(item: Any, plugin: dict[str, Any]) -> None:
        if plugin is None or item is None:
            return None
        if isinstance(item, dict):
            payload = cast(dict[str, Any], item)
            _state["registry"].setdefault("toolMetadata", []).append(
                {"ownerPluginId": plugin.get("id", ""), **payload}
            )
        else:
            _state["registry"].setdefault("toolMetadata", []).append(
                {"ownerPluginId": plugin.get("id", ""), "item": item}
            )

    def _append_reload(plugin: dict[str, Any], plan: Any) -> None:
        if plugin is None or plan is None:
            return None
        if isinstance(plan, dict):
            payload = cast(dict[str, Any], plan)
            _state["registry"].setdefault("reloads", []).append(
                {"ownerPluginId": plugin.get("id", ""), **payload}
            )
        else:
            _state["registry"].setdefault("reloads", []).append(
                {"ownerPluginId": plugin.get("id", ""), "item": plan}
            )

    def _append_runtime_lifecycle(plugin: dict[str, Any], runtime: Any) -> None:
        if plugin is None or runtime is None:
            return None
        if isinstance(runtime, dict):
            payload = cast(dict[str, Any], runtime)
            _state["registry"].setdefault("runtimeLifecycles", []).append(
                {"ownerPluginId": plugin.get("id", ""), **payload}
            )
        else:
            _state["registry"].setdefault("runtimeLifecycles", []).append(
                {"ownerPluginId": plugin.get("id", ""), "item": runtime}
            )

    def register_memory_capability_registrar(plugin: dict[str, Any], capability: dict[str, Any]) -> None:
        if plugin.get("kind") == "memory":
            register_memory_capability(plugin["id"], capability)
            _append_tool_metadata(capability, plugin)
            return
        if isinstance(plugin.get("kind"), list) and "memory" in plugin.get("kind", []):
            if plugin.get("memorySlotSelected"):
                register_memory_capability(plugin["id"], capability)
                _append_tool_metadata(capability, plugin)
                return
            _state["registry"]["diagnostics"].append(
                {
                    "level": "warn",
                    "message": "dual-kind plugin not selected for memory slot",
                }
            )
            return
        raise ValueError("only memory plugins can register a memory capability")

    def _plugin_owns_memory_slot(plugin: dict[str, Any]) -> bool:
        if plugin.get("kind") == "memory":
            return True
        if isinstance(plugin.get("kind"), list) and "memory" in plugin.get("kind", []):
            return bool(plugin.get("memorySlotSelected"))
        return False

    def register_memory_prompt_section_registrar(plugin: dict[str, Any], builder: Any) -> None:
        if _plugin_owns_memory_slot(plugin):
            if not callable(builder):
                _state["registry"]["diagnostics"].append(
                    {
                        "level": "error",
                        "message": "memory prompt section registration requires a callable builder",
                    }
                )
                return
            register_memory_prompt_section_for_plugin(plugin["id"], cast(Any, builder))
        _append_tool_metadata(builder, plugin)

    def register_memory_prompt_supplement_registrar(
        plugin: dict[str, Any], builder: Any
    ) -> None:
        if _plugin_owns_memory_slot(plugin):
            if not callable(builder):
                _state["registry"]["diagnostics"].append(
                    {
                        "level": "error",
                        "message": "memory prompt supplement registration missing builder",
                    }
                )
                return
            register_memory_prompt_supplement(plugin["id"], cast(Any, builder))
        _append_tool_metadata(builder, plugin)

    def register_memory_prompt_preparation_registrar(plugin: dict[str, Any], preparer: Any) -> None:
        if _plugin_owns_memory_slot(plugin):
            if not callable(preparer):
                _state["registry"]["diagnostics"].append(
                    {
                        "level": "error",
                        "message": "memory prompt preparation registration requires a callable preparer",
                    }
                )
                return
            register_memory_prompt_preparation(plugin["id"], cast(Any, preparer))
        _append_tool_metadata(preparer, plugin)

    def register_memory_corpus_supplement_registrar(plugin: dict[str, Any], supplement: Any) -> None:
        if plugin is None or supplement is None:
            return None
        if _plugin_owns_memory_slot(plugin):
            register_memory_corpus_supplement(plugin["id"], supplement)
        _append_tool_metadata(supplement, plugin)

    def register_memory_flush_plan_registrar(plugin: dict[str, Any], plan: Any | None = None) -> None:
        if plugin is None or plan is None:
            return None
        if _plugin_owns_memory_slot(plugin):
            if not callable(plan):
                _state["registry"]["diagnostics"].append(
                    {
                        "level": "error",
                        "message": "memory flush plan registration requires a callable resolver",
                    }
                )
                return
            register_memory_flush_plan_resolver_for_plugin(plugin["id"], cast(Any, plan))
        _append_tool_metadata(plan, plugin)
        _append_reload(plugin, plan)

    def register_memory_runtime_registrar(plugin: dict[str, Any], runtime: Any | None = None) -> None:
        if plugin is None or runtime is None:
            return None
        if _plugin_owns_memory_slot(plugin):
            register_memory_runtime_for_plugin(plugin["id"], runtime)
        _append_tool_metadata(runtime, plugin)
        _append_runtime_lifecycle(plugin, runtime)

    def register_memory_embedding_provider_registrar(
        plugin: dict[str, Any], adapter: dict[str, Any]
    ) -> None:
        provider_id = adapter.get("id")
        if provider_id is None:
            return
        existing = get_registered_memory_embedding_provider(provider_id)
        if existing is not None:
            owner_plugin_id = existing.get("ownerPluginId") if isinstance(existing, dict) else None
            _state["registry"]["diagnostics"].append(
                {
                    "level": "error",
                    "message": (
                        f"memory embedding provider already registered: {provider_id}"
                        f" (owner: {owner_plugin_id})"
                    ),
                }
            )
            return

        owns_memory_slot = plugin.get("kind") == "memory"
        owns_memory_slot = owns_memory_slot or bool(
            plugin.get("memorySlotSelected")
        )
        has_contract = bool(
            plugin.get("contracts", {}).get("memoryEmbeddingProviders")
        )
        if not owns_memory_slot and not has_contract:
            _state["registry"]["diagnostics"].append(
                {
                    "level": "error",
                    "message": (
                        "plugin must own memory slot or declare "
                        f"contracts.memoryEmbeddingProviders for adapter: {provider_id}"
                    ),
                }
            )
            return

        register_memory_embedding_provider(cast(Any, adapter), {"ownerPluginId": plugin["id"]})
        _state["registry"]["memoryEmbeddingProviders"].append(
            {"pluginId": plugin["id"], "provider": adapter}
        )

    return {
        "rollbackHooks": _noop,
        "registerMemoryCapability": register_memory_capability_registrar,
        "registerMemoryPromptSection": register_memory_prompt_section_registrar,
        "registerMemoryPromptSupplement": register_memory_prompt_supplement_registrar,
        "registerMemoryPromptPreparation": register_memory_prompt_preparation_registrar,
        "registerMemoryCorpusSupplement": register_memory_corpus_supplement_registrar,
        "registerMemoryFlushPlan": register_memory_flush_plan_registrar,
        "registerMemoryRuntime": register_memory_runtime_registrar,
        "registerMemoryEmbeddingProvider": register_memory_embedding_provider_registrar,
    }


# ── Composition (mirrors OpenClaw's ``createPluginRegistrars``) ─────


def create_plugin_registrars(state: dict[str, Any]) -> dict[str, Any]:
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
