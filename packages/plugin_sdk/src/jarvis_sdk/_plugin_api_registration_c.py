"""PluginApi registration helpers for host services and provider adapters."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, cast

if TYPE_CHECKING:
    from .types import SpeechProvider

JSON = dict[str, Any]


class PluginApiRegistrationsC:
    _ctx: Any
    _services: list[dict[str, Any]]
    _gateway_methods: list[dict[str, Any]]
    _node_invoke_policies: list[dict[str, Any]]
    _hosted_media_resolvers: list[dict[str, Any]]
    _mcp_server_connection_resolvers: list[dict[str, Any]]
    _reload_handlers: list[dict[str, Any]]
    _node_host_commands: list[dict[str, Any]]
    _security_audit_collectors: list[dict[str, Any]]
    _worker_providers: list[dict[str, Any]]
    _embedding_providers: list[dict[str, Any]]
    _agent_harnesses: list[dict[str, Any]]
    _detached_task_runtimes: list[dict[str, Any]]
    _realtime_transcription_providers: list[dict[str, Any]]
    _realtime_voice_providers: list[dict[str, Any]]
    _transcript_source_providers: list[dict[str, Any]]
    _image_generation_providers: list[dict[str, Any]]
    _video_generation_providers: list[dict[str, Any]]
    _music_generation_providers: list[dict[str, Any]]
    _web_fetch_providers: list[dict[str, Any]]
    _web_search_providers: list[dict[str, Any]]
    _migration_providers: list[dict[str, Any]]
    _speech_providers: list[dict[str, Any]]
    def register_service(
        self,
        service: dict[str, Any],
    ) -> None:
        """Register a long-running service owned by this plugin."""
        if not isinstance(service, dict):
            raise TypeError(
                f"service must be a dict; got {type(service).__name__}"
            )
        if "id" not in service or not service["id"]:
            raise ValueError("service must have a non-empty 'id'")
        if "start" not in service or not callable(service["start"]):
            raise ValueError(
                "service must have a callable 'start' "
                "(async function taking ctx)"
            )
        for existing in self._services:
            if existing["id"] == service["id"]:
                raise RuntimeError(
                    f"Plugin {self._ctx.plugin_id!r} tried to register "
                    f"service {service['id']!r} but it's already registered."
                )
        service["_owner_id"] = self._ctx.plugin_id
        self._services.append(service)

    def register_gateway_method(
        self,
        method: str,
        handler: Callable[..., Any],
        opts: dict[str, Any] | None = None,
    ) -> None:
        """Register a JSON-RPC method on the host gateway."""
        if not method or not isinstance(method, str):
            raise ValueError("gateway method name must be a non-empty string")
        if not callable(handler):
            raise TypeError(
                f"gateway method handler must be callable; got {type(handler).__name__}"
            )
        for existing in self._gateway_methods:
            if existing["method"] == method:
                raise RuntimeError(
                    f"Plugin {self._ctx.plugin_id!r} tried to register "
                    f"gateway method {method!r} but it's already registered."
                )
        self._gateway_methods.append(
            {
                "method": method,
                "handler": handler,
                "opts": dict(opts or {}),
                "_owner_id": self._ctx.plugin_id,
            }
        )

    def register_node_invoke_policy(
        self,
        policy: dict[str, Any],
    ) -> None:
        """Register a node-invoke policy for plugin commands."""
        if not isinstance(policy, dict):
            raise TypeError(
                f"node-invoke policy must be a dict; got {type(policy).__name__}"
            )
        commands = policy.get("commands")
        if not isinstance(commands, list) or not commands:
            raise ValueError(
                "node-invoke policy must have a non-empty 'commands' list"
            )
        handle = policy.get("handle")
        if not callable(handle):
            raise ValueError(
                "node-invoke policy must have a callable 'handle' "
                "(async function taking ctx)"
            )
        self._node_invoke_policies.append(
            {"policy": dict(policy), "_owner_id": self._ctx.plugin_id}
        )

    def register_hosted_media_resolver(self, resolver: dict[str, Any] | Any) -> None:
        """Register a hosted-media resolver for the gateway host surface."""
        if isinstance(resolver, dict):
            resolver_dict = cast(dict[str, Any], resolver)
            resolver_id = resolver_dict.get("id")
            if not resolver_id or not isinstance(resolver_id, str):
                raise ValueError("hosted media resolver requires a non-empty 'id'")
            if not callable(resolver_dict.get("resolve")):
                raise ValueError("hosted media resolver requires a callable 'resolve'")
            payload: dict[str, Any] = dict(resolver_dict)
        else:
            resolver_id = getattr(resolver, "id", None)
            if not resolver_id or not isinstance(resolver_id, str):
                raise ValueError("hosted media resolver requires a non-empty 'id'")
            resolver_fn = getattr(resolver, "resolve", None)
            if not callable(resolver_fn):
                raise ValueError("hosted media resolver requires a callable 'resolve'")
            payload: dict[str, Any] = {"id": resolver_id, "resolve": resolver_fn}
        payload["_owner_id"] = self._ctx.plugin_id
        self._hosted_media_resolvers.append(payload)

    def register_mcp_server_connection_resolver(
        self, resolver: dict[str, Any] | Any
    ) -> None:
        """Register an MCP server connection resolver through the API."""
        if isinstance(resolver, dict):
            resolver_dict = cast(dict[str, Any], resolver)
            resolver_id = resolver_dict.get("id")
            if not resolver_id or not isinstance(resolver_id, str):
                raise ValueError("MCP server connection resolver requires a non-empty 'id'")
            if not callable(resolver_dict.get("resolve")):
                raise ValueError(
                    "MCP server connection resolver requires a callable 'resolve'"
                )
            payload: dict[str, Any] = dict(resolver_dict)
        else:
            resolver_id = getattr(resolver, "id", None)
            if not resolver_id or not isinstance(resolver_id, str):
                raise ValueError("MCP server connection resolver requires a non-empty 'id'")
            resolver_fn = getattr(resolver, "resolve", None)
            if not callable(resolver_fn):
                raise ValueError(
                    "MCP server connection resolver requires a callable 'resolve'"
                )
            payload: dict[str, Any] = {"id": resolver_id, "resolve": resolver_fn}
        payload["_owner_id"] = self._ctx.plugin_id
        self._mcp_server_connection_resolvers.append(payload)

    def register_reload(self, handler: dict[str, Any] | Any) -> None:
        """Register a reload handler through the host API."""
        if isinstance(handler, dict):
            handler_dict = cast(dict[str, Any], handler)
            handler_id = handler_dict.get("id")
            if not handler_id or not isinstance(handler_id, str):
                raise ValueError("reload handler requires a non-empty 'id'")
            run = handler_dict.get("handler")
        else:
            handler_id = getattr(handler, "id", None)
            run = getattr(handler, "handler", None)
        if not callable(run):
            raise ValueError("reload handler requires a callable 'handler'")
        payload: dict[str, Any] = {"id": handler_id, "handler": run, "_owner_id": self._ctx.plugin_id}
        self._reload_handlers.append(payload)

    def register_node_host_command(self, command: dict[str, Any] | Any) -> None:
        """Register a node-host command through the host API."""
        if isinstance(command, dict):
            command_dict = cast(dict[str, Any], command)
            command_id = command_dict.get("id") or command_dict.get("command")
            handler = command_dict.get("handler")
        else:
            command_id = getattr(command, "id", None) or getattr(command, "command", None)
            handler = getattr(command, "handler", None)
        if not command_id or not isinstance(command_id, str):
            raise ValueError("node host command requires a non-empty 'id'")
        if not callable(handler):
            raise ValueError("node host command requires a callable 'handler'")
        payload: dict[str, Any] = {"id": command_id, "handler": handler, "_owner_id": self._ctx.plugin_id}
        self._node_host_commands.append(payload)

    def register_security_audit_collector(self, collector: dict[str, Any] | Any) -> None:
        """Register a security audit collector through the host API."""
        if isinstance(collector, dict):
            collector_dict = cast(dict[str, Any], collector)
            collector_id = collector_dict.get("id")
            if not collector_id or not isinstance(collector_id, str):
                raise ValueError("security audit collector requires a non-empty 'id'")
            collect = collector_dict.get("collect")
        else:
            collector_id = getattr(collector, "id", None)
            collect = getattr(collector, "collect", None)
        if not callable(collect):
            raise ValueError("security audit collector requires a callable 'collect'")
        payload: dict[str, Any] = {"id": collector_id, "collect": collect, "_owner_id": self._ctx.plugin_id}
        self._security_audit_collectors.append(payload)

    def register_worker_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register a worker-provider adapter for the host runtime."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("worker provider requires a non-empty 'id'")
            payload: dict[str, Any] = dict(provider_dict)
        else:
            provider_id = getattr(provider, "id", None)
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("worker provider requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": provider_id, "metadata": getattr(provider, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._worker_providers.append(payload)

    def register_embedding_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register an embedding-provider adapter at the API boundary."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("embedding provider requires a non-empty 'id'")
            payload: dict[str, Any] = dict(provider_dict)
        else:
            provider_id = getattr(provider, "id", None)
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("embedding provider requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": provider_id, "metadata": getattr(provider, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._embedding_providers.append(payload)

    def register_agent_harness(self, harness: dict[str, Any] | Any) -> None:
        """Register an agent-harness adapter for the host runtime."""
        if isinstance(harness, dict):
            harness_dict = cast(dict[str, Any], harness)
            harness_id = harness_dict.get("id")
            if not harness_id or not isinstance(harness_id, str):
                raise ValueError("agent harness requires a non-empty 'id'")
            payload: dict[str, Any] = dict(harness_dict)
        else:
            harness_id = getattr(harness, "id", None)
            if not harness_id or not isinstance(harness_id, str):
                raise ValueError("agent harness requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": harness_id, "metadata": getattr(harness, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._agent_harnesses.append(payload)

    def register_detached_task_runtime(self, runtime: dict[str, Any] | Any) -> None:
        """Register a detached-task runtime bridge through the OpenClaw API."""
        if isinstance(runtime, dict):
            runtime_dict = cast(dict[str, Any], runtime)
            runtime_id = runtime_dict.get("id")
            if not runtime_id or not isinstance(runtime_id, str):
                raise ValueError("detached task runtime requires a non-empty 'id'")
            payload: dict[str, Any] = dict(runtime_dict)
        else:
            runtime_id = getattr(runtime, "id", None)
            if not runtime_id or not isinstance(runtime_id, str):
                raise ValueError("detached task runtime requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": runtime_id, "metadata": getattr(runtime, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._detached_task_runtimes.append(payload)

    def register_realtime_transcription_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register a realtime transcription provider placeholder through the API."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("realtime transcription provider requires a non-empty 'id'")
            payload: dict[str, Any] = dict(provider_dict)
        else:
            provider_id = getattr(provider, "id", None)
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("realtime transcription provider requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": provider_id, "metadata": getattr(provider, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._realtime_transcription_providers.append(payload)

    def register_realtime_voice_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register a realtime voice provider placeholder through the API."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("realtime voice provider requires a non-empty 'id'")
            payload: dict[str, Any] = dict(provider_dict)
        else:
            provider_id = getattr(provider, "id", None)
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("realtime voice provider requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": provider_id, "metadata": getattr(provider, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._realtime_voice_providers.append(payload)

    def register_transcript_source_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register a transcript-source provider through the API."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("transcript source provider requires a non-empty 'id'")
            payload: dict[str, Any] = dict(provider_dict)
        else:
            provider_id = getattr(provider, "id", None)
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("transcript source provider requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": provider_id, "metadata": getattr(provider, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._transcript_source_providers.append(payload)

    def register_image_generation_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register an image-generation provider through the API."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("image generation provider requires a non-empty 'id'")
            payload: dict[str, Any] = dict(provider_dict)
        else:
            provider_id = getattr(provider, "id", None)
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("image generation provider requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": provider_id, "metadata": getattr(provider, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._image_generation_providers.append(payload)

    def register_video_generation_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register a video-generation provider through the API."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("video generation provider requires a non-empty 'id'")
            payload: dict[str, Any] = dict(provider_dict)
        else:
            provider_id = getattr(provider, "id", None)
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("video generation provider requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": provider_id, "metadata": getattr(provider, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._video_generation_providers.append(payload)

    def register_music_generation_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register a music-generation provider through the API."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("music generation provider requires a non-empty 'id'")
            payload: dict[str, Any] = dict(provider_dict)
        else:
            provider_id = getattr(provider, "id", None)
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("music generation provider requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": provider_id, "metadata": getattr(provider, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._music_generation_providers.append(payload)

    def register_web_fetch_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register a web-fetch provider through the API."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("web fetch provider requires a non-empty 'id'")
            payload: dict[str, Any] = dict(provider_dict)
        else:
            provider_id = getattr(provider, "id", None)
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("web fetch provider requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": provider_id, "metadata": getattr(provider, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._web_fetch_providers.append(payload)

    def register_web_search_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register a web-search provider through the API."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("web search provider requires a non-empty 'id'")
            payload = dict(provider_dict)
        else:
            provider_id = getattr(provider, "id", None)
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("web search provider requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": provider_id, "metadata": getattr(provider, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._web_search_providers.append(payload)

    def register_migration_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register a migration-provider adapter through the API."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("migration provider requires a non-empty 'id'")
            payload: dict[str, Any] = dict(provider_dict)
        else:
            provider_id = getattr(provider, "id", None)
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("migration provider requires a non-empty 'id'")
            payload = {"id": provider_id, "metadata": getattr(provider, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._migration_providers.append(payload)

    def register_speech_provider(
        self,
        provider: SpeechProvider | dict[str, Any],
    ) -> None:
        """Register a speech provider (TTS) the host can call."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_dict = cast(dict[str, Any], provider)
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            if not provider_id:
                raise ValueError("speech provider must have a non-empty 'id'")
            provider_obj: dict[str, Any] = {
                "id": provider_id,
                "label": provider_dict.get("label", ""),
                "description": provider_dict.get("description", ""),
                "defaultFormat": provider_dict.get("defaultFormat"),
                "defaultFor": provider_dict.get("defaultFor"),
                "synthesize": provider_dict.get("synthesize"),
                "synthesizeTelephony": provider_dict.get("synthesizeTelephony"),
                "listVoices": provider_dict.get("listVoices"),
                "metadata": dict(provider_dict.get("metadata") or {}),
            }
        else:
            provider_value = cast(Any, provider)
            provider_id = getattr(provider_value, "id", None) or getattr(provider_value, "get", lambda *_: None)("id")
            if not provider_id:
                raise ValueError("speech provider must have a non-empty 'id'")
            provider_obj = {
                "id": provider_id,
                "label": getattr(provider_value, "label", ""),
                "description": getattr(provider_value, "description", ""),
                "defaultFormat": getattr(provider_value, "defaultFormat", None),
                "defaultFor": getattr(provider_value, "defaultFor", None),
                "synthesize": getattr(provider_value, "synthesize", None),
                "synthesizeTelephony": getattr(provider_value, "synthesizeTelephony", None),
                "listVoices": getattr(provider_value, "listVoices", None),
                "metadata": dict(getattr(provider_value, "metadata", {}) or {}),
            }
        for existing in self._speech_providers:
            if existing["id"] == provider_id:
                raise RuntimeError(
                    f"Plugin {self._ctx.plugin_id!r} tried to register "
                    f"speech provider {provider_id!r} but it's already "
                    f"registered by {existing.get('_owner_id')!r}."
                )
        provider_obj["_owner_id"] = self._ctx.plugin_id
        self._speech_providers.append(provider_obj)
