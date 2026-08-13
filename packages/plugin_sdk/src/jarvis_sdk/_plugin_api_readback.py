"""PluginApi readback accessors for the internal SDK implementation."""
from __future__ import annotations

from typing import Any, Callable

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api import CommandDecl, CronDecl, HookRegistration, SkillDecl


class PluginApiReadback:
    def set_plugin_config(self, plugin_config: Any) -> None:
        """Provide the ``plugins.<id>`` block from the host config."""
        self._plugin_config = plugin_config

    @property
    def plugin_config(self) -> Any:
        """The ``plugins.<id>`` block from the host config (or ``None``)."""
        return self._plugin_config

    @property
    def tools(self) -> list[tuple[Any, list[str] | None]]:
        return list(self._tools)

    @property
    def tool_instances(self) -> list[Any]:
        return [t for t, _ in self._tools]

    @property
    def commands(self) -> list[CommandDecl]:
        return list(self._commands)

    @property
    def cli_handlers(
        self,
    ) -> list[tuple[Callable[..., Any], list[object], list[str], list[str]]]:
        return list(self._cli_handlers)

    @property
    def memory_capability(self) -> dict[str, Any] | None:
        return self._memory_capability

    @property
    def provider(self) -> dict[str, Any] | None:
        return self._provider

    @property
    def channel(self) -> dict[str, Any] | None:
        return self._channel

    @property
    def context_engines(self) -> list[dict[str, Any]]:
        return list(self._context_engines)

    @property
    def context_engine(self) -> list[dict[str, Any]]:
        return list(self._context_engines)

    @property
    def compaction_providers(self) -> list[dict[str, Any]]:
        return list(self._compaction_providers)

    @property
    def session_catalogs(self) -> list[dict[str, Any]]:
        return list(self._session_catalogs)

    @property
    def cli_backends(self) -> list[dict[str, Any]]:
        return list(self._cli_backends)

    @property
    def text_transforms(self) -> list[dict[str, Any]]:
        return list(self._text_transforms)

    @property
    def session_extensions(self) -> list[dict[str, Any]]:
        return list(self._session_extensions)

    @property
    def codex_app_server_extension_factories(self) -> list[dict[str, Any]]:
        return list(self._codex_app_server_extension_factories)

    @property
    def interactive_handlers(self) -> list[dict[str, Any]]:
        return list(self._interactive_handlers)

    @property
    def runtime_lifecycles(self) -> list[dict[str, Any]]:
        return list(self._runtime_lifecycles)

    @property
    def control_ui_descriptors(self) -> list[dict[str, Any]]:
        return list(self._control_ui_descriptors)

    @property
    def tool_metadata(self) -> list[dict[str, Any]]:
        return list(self._tool_metadata)

    @property
    def trusted_tool_policies(self) -> list[dict[str, Any]]:
        return list(self._trusted_tool_policies)

    @property
    def session_scheduler_jobs(self) -> list[dict[str, Any]]:
        return list(self._session_scheduler_jobs)

    @property
    def session_actions(self) -> list[dict[str, Any]]:
        return list(self._session_actions)

    @property
    def agent_event_subscriptions(self) -> list[dict[str, Any]]:
        return list(self._agent_event_subscriptions)

    @property
    def memory_embedding_providers(self) -> list[dict[str, Any]]:
        return list(self._memory_embedding_providers)

    @property
    def memory_prompt_sections(self) -> list[dict[str, Any]]:
        return list(self._memory_prompt_sections)

    @property
    def memory_prompt_supplements(self) -> list[dict[str, Any]]:
        return list(self._memory_prompt_supplements)

    @property
    def memory_prompt_preparations(self) -> list[dict[str, Any]]:
        return list(self._memory_prompt_preparations)

    @property
    def memory_corpus_supplements(self) -> list[dict[str, Any]]:
        return list(self._memory_corpus_supplements)

    @property
    def memory_flush_plans(self) -> list[dict[str, Any]]:
        return list(self._memory_flush_plans)

    @property
    def memory_runtimes(self) -> list[dict[str, Any]]:
        return list(self._memory_runtimes)

    @property
    def conversation_binding_resolved_handlers(self) -> list[dict[str, Any]]:
        return list(self._conversation_binding_resolved_handlers)

    @property
    def doctor_contracts(self) -> list[dict[str, Any]]:
        return list(self._doctor_contracts)

    @property
    def http_handlers(self) -> list[dict[str, Any]]:
        return list(self._http_handlers)

    @property
    def agent_tool_result_middlewares(self) -> list[dict[str, Any]]:
        return list(self._agent_tool_result_middlewares)

    @property
    def model_catalog_providers(self) -> list[dict[str, Any]]:
        return list(self._model_catalog_providers)

    @property
    def skills(self) -> list[SkillDecl]:
        return list(self._skills)

    @property
    def hooks(self) -> list[HookRegistration]:
        return list(self._hooks)

    @property
    def cron_jobs(self) -> list[CronDecl]:
        return list(self._cron_jobs)

    @property
    def gateway_discovery_service(self) -> dict[str, Any] | None:
        return self._gateway_discovery_service

    @property
    def media_understanding_providers(self) -> list[dict[str, Any]]:
        return list(self._media_understanding_providers)

    @property
    def embedding_providers(self) -> list[dict[str, Any]]:
        return list(self._embedding_providers)

    @property
    def worker_providers(self) -> list[dict[str, Any]]:
        return list(self._worker_providers)

    @property
    def agent_harnesses(self) -> list[dict[str, Any]]:
        return list(self._agent_harnesses)

    @property
    def detached_task_runtimes(self) -> list[dict[str, Any]]:
        return list(self._detached_task_runtimes)

    @property
    def realtime_transcription_providers(self) -> list[dict[str, Any]]:
        return list(self._realtime_transcription_providers)

    @property
    def realtime_voice_providers(self) -> list[dict[str, Any]]:
        return list(self._realtime_voice_providers)

    @property
    def transcript_source_providers(self) -> list[dict[str, Any]]:
        return list(self._transcript_source_providers)

    @property
    def image_generation_providers(self) -> list[dict[str, Any]]:
        return list(self._image_generation_providers)

    @property
    def video_generation_providers(self) -> list[dict[str, Any]]:
        return list(self._video_generation_providers)

    @property
    def music_generation_providers(self) -> list[dict[str, Any]]:
        return list(self._music_generation_providers)

    @property
    def web_fetch_providers(self) -> list[dict[str, Any]]:
        return list(self._web_fetch_providers)

    @property
    def web_search_providers(self) -> list[dict[str, Any]]:
        return list(self._web_search_providers)

    @property
    def migration_providers(self) -> list[dict[str, Any]]:
        return list(self._migration_providers)

    @property
    def services(self) -> list[dict[str, Any]]:
        return list(self._services)

    @property
    def gateway_methods(self) -> list[dict[str, Any]]:
        return list(self._gateway_methods)

    @property
    def node_invoke_policies(self) -> list[dict[str, Any]]:
        return list(self._node_invoke_policies)

    @property
    def hosted_media_resolvers(self) -> list[dict[str, Any]]:
        return list(self._hosted_media_resolvers)

    @property
    def mcp_server_connection_resolvers(self) -> list[dict[str, Any]]:
        return list(self._mcp_server_connection_resolvers)

    @property
    def reload_handlers(self) -> list[dict[str, Any]]:
        return list(self._reload_handlers)

    @property
    def node_host_commands(self) -> list[dict[str, Any]]:
        return list(self._node_host_commands)

    @property
    def security_audit_collectors(self) -> list[dict[str, Any]]:
        return list(self._security_audit_collectors)

    @property
    def speech_providers(self) -> list[dict[str, Any]]:
        return list(self._speech_providers)
