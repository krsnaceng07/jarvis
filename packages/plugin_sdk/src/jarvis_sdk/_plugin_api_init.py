"""PluginApi initializer and core runtime state for the internal PluginApi implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from .context import PluginContext

#: Valid registration modes — mirrors OpenClaw's ``api.registrationMode`` literal union.
#: ``"full"``           — normal startup: register everything.
#: ``"cli-metadata"``   — CLI scan: register only CLI metadata, no tools/channels.
#: ``"discovery"``      — capability enumeration: register channels + providers only.
#: ``"tool-discovery"`` — tool-name enumeration: register tool names only.
RegistrationMode = Literal["full", "cli-metadata", "discovery", "tool-discovery"]


class PluginApiInit:
    def __init__(
        self, ctx: "PluginContext", logger: Any = None, registration_mode: RegistrationMode = "full"
    ) -> None:
        self._ctx = ctx
        self._logger = logger or ctx.logger
        # Mirrors OpenClaw's ``api.registrationMode``. The loader sets this
        # before calling ``entry.register(api)``; channel plugins gate what
        # they register based on this value.
        self._registration_mode: RegistrationMode = registration_mode

        # ── Accumulators (private) ────────────────────────────────────
        self._tools: list[tuple[Any, list[str] | None]] = []
        self._commands: list[Any] = []
        self._cli_handlers: list[tuple[Any, list[Any], list[str], list[str]]] = []
        self._memory_capability: dict[str, Any] | None = None
        self._provider: dict[str, Any] | None = None
        self._channel: dict[str, Any] | None = None
        self._context_engines: list[dict[str, Any]] = []
        self._compaction_providers: list[dict[str, Any]] = []
        self._session_catalogs: list[dict[str, Any]] = []
        self._cli_backends: list[dict[str, Any]] = []
        self._text_transforms: list[dict[str, Any]] = []
        self._session_extensions: list[dict[str, Any]] = []
        self._codex_app_server_extension_factories: list[dict[str, Any]] = []
        self._interactive_handlers: list[dict[str, Any]] = []
        self._runtime_lifecycles: list[dict[str, Any]] = []
        self._control_ui_descriptors: list[dict[str, Any]] = []
        self._tool_metadata: list[dict[str, Any]] = []
        self._trusted_tool_policies: list[dict[str, Any]] = []
        self._session_scheduler_jobs: list[dict[str, Any]] = []
        self._session_actions: list[dict[str, Any]] = []
        self._agent_event_subscriptions: list[dict[str, Any]] = []
        self._memory_embedding_providers: list[dict[str, Any]] = []
        self._memory_prompt_sections: list[dict[str, Any]] = []
        self._memory_prompt_supplements: list[dict[str, Any]] = []
        self._memory_prompt_preparations: list[dict[str, Any]] = []
        self._memory_corpus_supplements: list[dict[str, Any]] = []
        self._memory_flush_plans: list[dict[str, Any]] = []
        self._memory_runtimes: list[dict[str, Any]] = []
        self._conversation_binding_resolved_handlers: list[dict[str, Any]] = []
        self._doctor_contracts: list[dict[str, Any]] = []
        self._http_handlers: list[dict[str, Any]] = []
        self._agent_tool_result_middlewares: list[dict[str, Any]] = []
        self._model_catalog_providers: list[dict[str, Any]] = []
        self._skills: list[Any] = []
        self._hooks: list[Any] = []
        self._cron_jobs: list[Any] = []
        self._gateway_discovery_service: dict[str, Any] | None = None
        self._media_understanding_providers: list[dict[str, Any]] = []
        self._embedding_providers: list[dict[str, Any]] = []
        self._worker_providers: list[dict[str, Any]] = []
        self._agent_harnesses: list[dict[str, Any]] = []
        self._detached_task_runtimes: list[dict[str, Any]] = []
        self._realtime_transcription_providers: list[dict[str, Any]] = []
        self._realtime_voice_providers: list[dict[str, Any]] = []
        self._transcript_source_providers: list[dict[str, Any]] = []
        self._image_generation_providers: list[dict[str, Any]] = []
        self._video_generation_providers: list[dict[str, Any]] = []
        self._music_generation_providers: list[dict[str, Any]] = []
        self._web_fetch_providers: list[dict[str, Any]] = []
        self._web_search_providers: list[dict[str, Any]] = []
        self._migration_providers: list[dict[str, Any]] = []
        self._hosted_media_resolvers: list[dict[str, Any]] = []
        self._mcp_server_connection_resolvers: list[dict[str, Any]] = []
        self._reload_handlers: list[dict[str, Any]] = []
        self._node_host_commands: list[dict[str, Any]] = []
        self._security_audit_collectors: list[dict[str, Any]] = []
        self._services: list[dict[str, Any]] = []
        self._gateway_methods: list[dict[str, Any]] = []
        self._node_invoke_policies: list[dict[str, Any]] = []
        self._speech_providers: list[dict[str, Any]] = []
        self._manifest: dict[str, Any] = {}
        self._plugin_config: Any = None
        self._config: Any = None

        # Import here to break the api.py ↔ _plugin_api_init.py circular import.
        # These classes are defined early in api.py (before the _plugin_api_impl
        # import at line 469), but the module isn't fully initialised when the
        # mixin chain is first resolved, so a top-level import would silently
        # fall back to PluginApiInit = object in the try/except blocks.
        from .api import (  # noqa: PLC0415
            PluginAgentApi,
            PluginLifecycleApi,
            PluginRunContextApi,
            PluginSessionApi,
            _PluginRuntimeNamespace,
        )

        self.session = PluginSessionApi()
        self.agent = PluginAgentApi()
        self.run_context = PluginRunContextApi()
        self.lifecycle = PluginLifecycleApi()
        self.runtime: Any = _PluginRuntimeNamespace(self)

    def set_manifest(self, manifest: dict[str, Any]) -> None:
        """Provide the plugin manifest (used for ``contracts.tools`` validation)."""
        self._manifest = manifest or {}

    def _declared_tool_names(self) -> list[str]:
        """Return the tool names declared in ``contracts.tools`` (manifest)."""
        try:
            contracts: dict[str, Any] = self._manifest.get("contracts") or {}
            tools = contracts.get("tools")
            if not isinstance(tools, list):
                return []
            return [cast(str, tool).strip() for tool in tools if isinstance(tool, str)]
        except Exception:
            return []

    def _declared_str_list(self, key: str) -> list[str]:
        """Return a trimmed string list for a top-level manifest ``key``.

        Generic passthrough for OpenClaw manifest metadata (``channels``,
        ``providers``, ``cliCommands``) so the host reads ownership facts
        without per-extension branches. Unknown shapes yield ``[]``.
        """
        try:
            raw = self._manifest.get(key)
            if not isinstance(raw, list):
                return []
            return [cast(str, item).strip() for item in raw if isinstance(item, str)]
        except Exception:
            return []

    @property
    def ctx(self) -> "PluginContext":
        return self._ctx

    @property
    def logger(self) -> Any:
        return self._logger

    @property
    def config(self) -> Any:
        """The host config (the full ``OpenClawConfig`` / ``JarvisConfig``)."""
        return self._config if self._config is not None else {}

    def set_config(self, config: Any) -> None:
        """Provide the host config to the plugin API."""
        self._config = config

    @property
    def registration_mode(self) -> RegistrationMode:
        """Current registration scope — mirrors OpenClaw's ``api.registrationMode``.

        Channel plugins should check this before registering capabilities:

        .. code-block:: python

            if api.registration_mode == "full":
                api.register_channel(my_channel)
            else:
                api.register_cli(cli_descriptor)  # always safe

        Values:
            ``"full"``           — startup: register everything.
            ``"cli-metadata"``   — CLI scan only.
            ``"discovery"``      — channels + providers only.
            ``"tool-discovery"`` — tool names only.
        """
        return self._registration_mode
