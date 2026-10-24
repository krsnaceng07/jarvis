"""PluginApi — the registration surface the host gives each plugin.

Mirrors OpenClaw's ``OpenClawPluginApi`` from
``src/plugins/plugin-api.types.ts``. The host instantiates a
``PluginApi`` per plugin, calls ``register(api)`` (from the plugin's
``define_plugin_entry``), and then reads back the collected tools /
commands / CLI handlers / etc.

Grouped facades (``api.session``, ``api.agent``, ``api.run_context``,
``api.lifecycle``) mirror OpenClaw's namespace layout. Flat methods on
``api`` are kept for backwards compatibility with the Phase 1B SDK
shape — Phase 2 will deprecate them and migrate plugins to the grouped
form.

Adding a new registration point:
1. Add the accumulator + public property here.
2. Mirror the change in the host's loader
   (``apps/desktop/src/jarvis_desktop/app.py::_load_plugins``).
3. Wire the collected registration into the host subsystem that
   consumes it (e.g. command router, CLI parser, doctor runner).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, cast

from .cli import CliDescriptor  # used at runtime in register_cli()
from .manifest import ToolDecl

_log = logging.getLogger("jarvis_sdk.api")

#: Process-global host default for ``PluginAgentApi.resolve_thinking_policy``.
#: Installed once by host startup (e.g. ``src/plugins/runtime_entry.py``);
#: per-api ``resolve_thinking_policy_fn`` still wins when set. ``None``
#: keeps the historical empty-policy fallback (tests rely on this).
_host_thinking_policy_resolver: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None


def set_host_thinking_policy_resolver(
    resolver: Optional[Callable[[dict[str, Any]], dict[str, Any]]],
) -> None:
    """Install/clear the host-side thinking-policy resolver.

    The resolver receives the ``{"provider", "model", "agentRuntime",
    ...}`` call shape and returns a ``{"levels": [{"id", "label"}],
    "default"?}`` policy. Installed by host startup only — never by
    plugins.
    """
    global _host_thinking_policy_resolver
    _host_thinking_policy_resolver = resolver


#: Process-global host default for
#: ``PluginAgentApi.resolve_effective_agent_runtime``. Installed once by
#: host startup; per-api ``resolve_effective_agent_runtime_fn`` still wins.
_host_effective_agent_runtime_resolver: Optional[Callable[[dict[str, Any]], Optional[str]]] = None


def set_host_effective_agent_runtime_resolver(
    resolver: Optional[Callable[[dict[str, Any]], Optional[str]]],
) -> None:
    """Install/clear the host-side effective-runtime resolver.

    The resolver receives the ``{"cfg", "provider", "modelId", ...}`` call
    shape and returns the owning harness runtime id. Installed by host
    startup only — never by plugins.
    """
    global _host_effective_agent_runtime_resolver
    _host_effective_agent_runtime_resolver = resolver


def _normalize_plugin_tool_names(names: list[Any] | None) -> list[str]:
    """Mirror OpenClaw's ``normalizePluginToolNames``.

    Trims whitespace, drops empty strings, deduplicates while preserving order.
    Does not change case or convert kebab→snake.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in names or ():
        if not isinstance(raw, str):
            continue
        trimmed = raw.strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        out.append(trimmed)
    return out


def _find_undeclared_plugin_tool_names(declared: list[str], tool_names: list[str]) -> list[str]:
    """Mirror OpenClaw's ``findUndeclaredPluginToolNames``.

    Returns the tool names that are NOT in the ``declared`` set.
    """
    declared_set = set(declared or ())
    return [n for n in tool_names if n not in declared_set]


def _dict_from_any(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value)


# Common JSON-like mapping alias used for payloads
JSON = dict[str, Any]

# ── Command + CLI registration descriptors ──────────────────────────


@dataclass
class CommandDecl:
    """A slash command a plugin registers. Mirrors OpenClaw's CommandReg.

    Attributes
    ----------
    name : str
        The slash-command name (without leading ``/``).
    description : str
        User-facing help text.
    handler : Callable
        **Required.** Async function with signature
        ``async (ctx) -> PluginCommandResult``. The host invokes
        ``handler(ctx)`` and uses the result to drive the agent loop.
    accepts_args : bool
        Whether the command accepts trailing arguments. Default: True.
    expose_sender_is_owner : bool
        If True, the command works only when the sender is the operator
        (vs a paired remote user). Used for security-sensitive commands.
    """

    name: str
    description: str
    handler: Callable[..., Any]
    accepts_args: bool = True
    expose_sender_is_owner: bool = True

    def __post_init__(self) -> None:
        # Validate the handler is callable at construction time so
        # plugins can't ship a stub and the host only has to check
        # once.
        if not callable(self.handler):
            raise TypeError(
                f"CommandDecl({self.name!r}).handler must be callable; "
                f"got {type(self.handler).__name__}. Use an async function "
                f"returning PluginCommandResult."
            )


# `CliDescriptor` is defined in `cli.py` (single source of truth).
# It is re-exported from `__init__.py` for plugin convenience.


# ── Grouped facades (mirror OpenClaw's namespace layout) ────────────


@dataclass
class PluginRuntimeConfigApi:
    """``api.runtime.config`` — live config + mutator surface.

    Mirrors OpenClaw's ``api.runtime.config`` namespace. The
    host wires each method up; the default implementations
    are no-ops so plugins that only read config still work
    when the host hasn't wired the live mutator yet.
    """

    def current(self) -> Any:
        """Return the most recent config (any mapping) or ``None``."""
        return None

    def mutate_config_file(self, params: dict[str, Any]) -> Any:
        """Atomically rewrite the config file with a draft.

        Mirrors OpenClaw's ``api.runtime.config.mutateConfigFile``.
        ``params`` carries:
        - ``mutate``: callable ``(draft) -> None`` (mutates in place).
        - ``afterWrite``: optional ``{"mode": "auto"}``.

        Returns the new config or ``None`` if the host
        hasn't wired the mutator.
        """
        return None


@dataclass
class PluginRuntimeStateApi:
    """``api.runtime.state`` — host state dir + keyed store surface.

    Mirrors OpenClaw's ``api.runtime.state`` namespace. The
    host wires each method up; the default implementations
    are no-ops so plugins still work when the host hasn't
    wired the state surface yet.
    """

    def resolve_state_dir(self) -> str:
        """Return the host's state dir (e.g. ``~/.jarvis``)."""
        import os
        from pathlib import Path

        env = os.environ.get("JARVIS_DATA_DIR")
        if env:
            return env
        return str(Path.home() / ".jarvis")

    def open_keyed_store(self, params: dict[str, Any]) -> Any:
        """Open a per-namespace keyed store.

        Mirrors OpenClaw's ``api.runtime.state.openKeyedStore``.
        ``params`` carries ``namespace`` (str) and ``maxEntries``
        (int, optional). Returns ``None`` when the host hasn't
        wired a store implementation.
        """
        return None


@dataclass
class PluginAgentSessionApi:
    """``api.runtime.agent.session`` — per-agent session registry.

    Mirrors OpenClaw's ``api.runtime.agent.session`` namespace.
    Phase 4.2 ships ``getSessionEntry`` (harness-skip), plus
    the registry helpers ``listSessionEntries`` and
    ``patchSessionEntry`` used by the recall-flow
    status-line persistence and canonical-session-key
    resolution.
    """

    def get_session_entry(self, params: dict[str, Any]) -> Any:
        """Return the session registry entry or ``None`` if missing.

        Mirrors OpenClaw's
        ``api.runtime.agent.session.getSessionEntry``.
        Recognized params: ``agentId``, ``sessionKey``,
        ``sessionId``, ``readConsistency`` (e.g. ``"latest"``).
        """
        return None

    def list_session_entries(self, params: dict[str, Any]) -> list[tuple[str, Any]]:
        """List the agent's session entries.

        Mirrors OpenClaw's
        ``api.runtime.agent.session.listSessionEntries``.
        Returns a list of ``(sessionKey, entry)`` pairs;
        empty list when the host hasn't wired the registry.
        Recognized params: ``agentId``, ``limit``,
        ``readConsistency`` (e.g. ``"latest"``).
        """
        return []

    def patch_session_entry(self, params: dict[str, Any]) -> Any:
        """Atomically patch a session entry.

        Mirrors OpenClaw's
        ``api.runtime.agent.session.patchSessionEntry``.
        The ``update`` callback receives the existing entry
        and returns the patch to apply. Returns the updated
        entry or ``None`` when the host hasn't wired the
        registry. Recognized params: ``agentId``,
        ``sessionKey``, ``update``, ``preserveActivity``,
        ``skipMaintenance``, ``replaceEntry``,
        ``fallbackEntry``, ``storePath``.
        """
        return None


@dataclass
class PluginAgentApi:
    """``api.runtime.agent`` — per-agent capability surface.

    Mirrors OpenClaw's ``api.runtime.agent`` namespace. The
    default implementations are no-ops so plugins that only
    need a subset still work when the host hasn't wired the
    rest yet.
    """

    resolve_agent_dir: Any = None  # set by host on init
    resolve_agent_workspace_dir: Any = None  # set by host on init
    resolve_cli_backend_dispatch_eligibility: Any = None
    session: PluginAgentSessionApi = field(default_factory=PluginAgentSessionApi)
    # The host wires the following DI callables. They are
    # ``None`` until the host sets them, so plugins can
    # test the no-op fallback paths without a real host.
    resolve_thinking_policy_fn: Any = None
    normalize_thinking_level_fn: Any = None
    run_embedded_agent_fn: Any = None
    build_model_alias_index_fn: Any = None
    resolve_model_ref_from_string_fn: Any = None
    resolve_effective_agent_runtime_fn: Any = None

    def __getattr__(self, item: str) -> Any:
        # Tolerate attribute lookups for properties the host
        # hasn't wired yet.
        return None

    def resolve_thinking_policy(self, params: dict[str, Any]) -> dict[str, Any]:
        """Resolve the thinking-policy for a (provider, model) pair.

        Mirrors ``api.runtime.agent.resolveThinkingPolicy``.
        Precedence: per-api ``resolve_thinking_policy_fn`` (most
        specific), then the process-global host default installed via
        :func:`set_host_thinking_policy_resolver`, then the empty
        ``"none"`` fallback policy.
        """
        if self.resolve_thinking_policy_fn is not None:
            return self.resolve_thinking_policy_fn(params)
        if _host_thinking_policy_resolver is not None:
            return _host_thinking_policy_resolver(params)
        return {
            "levels": [{"id": "none", "label": "None"}],
            "default": "none",
        }

    def normalize_thinking_level(self, value: object) -> Optional[str]:
        """Normalize a thinking-level id, or ``None`` for invalid input.

        Mirrors ``api.runtime.agent.normalizeThinkingLevel``.
        """
        if self.normalize_thinking_level_fn is not None:
            return self.normalize_thinking_level_fn(value)
        if not isinstance(value, str):
            return None
        lowered = value.strip().lower()
        return lowered or None

    async def run_embedded_agent(
        self,
        prompt: str | dict[str, Any],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        tools: list[Any] | None = None,
        tool_handlers: dict[str, Callable] | None = None,
        max_turns: int = 4,
        timeout_seconds: float = 30.0,
        context: dict[str, Any] | None = None,
        custom_runner: Callable | None = None,
    ) -> dict[str, Any]:
        """Run an embedded agent turn (provider/model/prompt).

        Mirrors ``api.runtime.agent.runEmbeddedAgent``.
        Executes lightweight in-memory async micro-tasks without process-spawning overhead.
        """
        from .embedded_runner import run_embedded_agent as _run_embedded

        runner = custom_runner or self.run_embedded_agent_fn
        return await _run_embedded(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            tools=tools,
            tool_handlers=tool_handlers,
            max_turns=max_turns,
            timeout_seconds=timeout_seconds,
            context=context,
            custom_runner=runner,
        )

    def build_model_alias_index(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build a model-alias index for the host config.

        Mirrors ``api.runtime.agent.buildModelAliasIndex``.
        """
        if self.build_model_alias_index_fn is None:
            return {}
        return self.build_model_alias_index_fn(params)

    def resolve_model_ref_from_string(self, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Resolve a model-ref string to ``{provider, model}`` or ``None``.

        Mirrors ``api.runtime.agent.resolveModelRefFromString``.
        """
        if self.resolve_model_ref_from_string_fn is None:
            return None
        return self.resolve_model_ref_from_string_fn(params)

    def resolve_effective_agent_runtime(self, params: dict[str, Any]) -> Optional[str]:
        """Resolve the effective agent runtime for a (provider, model) pair.

        Mirrors ``api.runtime.agent.resolveEffectiveAgentRuntime``.
        Precedence: per-api ``resolve_effective_agent_runtime_fn``, then
        the process-global host default installed via
        :func:`set_host_effective_agent_runtime_resolver`, then ``None``.
        """
        if self.resolve_effective_agent_runtime_fn is not None:
            return self.resolve_effective_agent_runtime_fn(params)
        if _host_effective_agent_runtime_resolver is not None:
            return _host_effective_agent_runtime_resolver(params)
        return None


@dataclass
class PluginControlUiDescriptor:
    """A dashboard tab/section descriptor a plugin registers.

    Mirrors the shape consumed by OpenClaw's
    ``api.session.controls.registerControlUiDescriptor``. The
    host renders the descriptor only while the plugin is
    active, so no core code references the plugin id.
    """

    surface: str = "tab"  # "tab" | "section" | "panel"
    id: str = ""
    label: str = ""
    description: str = ""
    icon: str = ""
    group: str = "control"
    required_scopes: list[str] = field(default_factory=list[str])


@dataclass
class _PluginControlsApi:
    """Grouped facade for session control-UI registrations.

    Mirrors OpenClaw's ``api.session.controls``. The host
    reads back the registered descriptors via the
    ``descriptors`` property and renders them in the
    dashboard.
    """

    def __init__(self) -> None:
        self._descriptors: list[PluginControlUiDescriptor] = []

    def register_control_ui_descriptor(
        self,
        descriptor: PluginControlUiDescriptor | dict[str, Any],
    ) -> None:
        if isinstance(descriptor, dict):
            descriptor_dict = cast(dict[str, Any], descriptor)
            # Translate camelCase keys to snake_case for the
            # dataclass. Mirrors the OpenClaw dict-shape
            # (camelCase keys per the TS source) and the
            # Python dataclass field shape (snake_case).
            # Coerce and validate types so static checkers understand the shape.
            raw_required: list[object] = cast(
                list[object],
                descriptor_dict.get("requiredScopes")
                or descriptor_dict.get("required_scopes")
                or [],
            )
            if not isinstance(raw_required, list):
                raw_required = []
            required_scopes: list[str] = [x for x in raw_required if isinstance(x, str)]
            descriptor = PluginControlUiDescriptor(
                surface=str(descriptor_dict.get("surface", "tab")),
                id=str(descriptor_dict.get("id", "")),
                label=str(descriptor_dict.get("label", "")),
                description=str(descriptor_dict.get("description", "")),
                icon=str(descriptor_dict.get("icon", "")),
                group=str(descriptor_dict.get("group", "control")),
                required_scopes=required_scopes,
            )
        if not descriptor.id:
            raise ValueError("control-ui descriptor must have a non-empty 'id'")
        self._descriptors.append(descriptor)


@dataclass
class PluginSessionApi:
    """Grouped facade for session-state registrations. Stubs in 1C."""

    state: Any = None  # registerSessionExtension (Phase 2)
    workflow: Any = None  # enqueueNextTurnInjection (Phase 2)
    controls: Any = None  # _PluginControlsApi (populated below)

    def __post_init__(self) -> None:
        if self.controls is None:
            self.controls = _PluginControlsApi()


@dataclass
class PluginRunContextApi:
    """Grouped facade for run-scoped scratch state. Stubs in 1C."""

    def set_run_context(self, patch: dict[str, object]) -> bool:
        return False

    def get_run_context(self, params: dict[str, object]) -> Any:
        return None

    def clear_run_context(self, params: dict[str, object]) -> None:
        return None


@dataclass
class PluginLifecycleApi:
    """Grouped facade for runtime cleanup hooks. Stubs in 1C."""

    def register_runtime_lifecycle(self, lifecycle: dict[str, object]) -> None:
        return None


# ── Main PluginApi ───────────────────────────────────────────────────


@dataclass
class _PluginRuntimeNamespace:
    """Mirror of OpenClaw's ``api.runtime`` nested namespace.

    Holds the three runtime sub-namespaces (config, state,
    agent) and forwards attribute access to the
    ``PluginApi`` instance. The host wires each sub-namespace
    by setting ``self.runtime._config`` etc. after
    construction.
    """

    config: PluginRuntimeConfigApi
    state: PluginRuntimeStateApi
    agent: PluginAgentApi

    def __init__(self, owner: object) -> None:
        self.config = PluginRuntimeConfigApi()
        self.state = PluginRuntimeStateApi()
        self.agent = PluginAgentApi()
        self._owner = owner

    def __getattr__(self, item: str) -> Any:
        # Tolerate attribute lookups for runtime sub-namespaces
        # the host hasn't wired yet (returns None for forward
        # compatibility — plugins must check for None before
        # calling).
        return None


# Mid-file import (not top): the impl mixins themselves do
# `from .api import ...` at their top, so importing them before this
# module finishes its own re-exports would be circular. E402 accepted
# intentionally — do not move.
from ._plugin_api_impl import PluginApi as _PluginApiImpl  # noqa: E402


class PluginApi(_PluginApiImpl):
    """PluginApi surface with explicit registrar aliases.

    This subclass preserves the public API method names in
    ``packages/plugin_sdk/src/jarvis_sdk/api.py`` so the SDK
    surface matches the OpenClaw registrar vocabulary.
    """

    @property
    def registration_mode(self) -> "RegistrationMode":
        """Read-only registration scope. Mirrors OpenClaw's ``api.registrationMode``."""
        return super().registration_mode

    def register_tool(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_tool(*args, **kwargs)

    def register_command(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_command(*args, **kwargs)

    def register_cli(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_cli(*args, **kwargs)

    def register_memory_capability(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_memory_capability(*args, **kwargs)

    def register_memory_prompt_section(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_memory_prompt_section(*args, **kwargs)

    def register_memory_prompt_supplement(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_memory_prompt_supplement(*args, **kwargs)

    def register_memory_prompt_preparation(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_memory_prompt_preparation(*args, **kwargs)

    def register_memory_corpus_supplement(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_memory_corpus_supplement(*args, **kwargs)

    def register_memory_flush_plan(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_memory_flush_plan(*args, **kwargs)

    def register_memory_runtime(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_memory_runtime(*args, **kwargs)

    def register_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_provider(*args, **kwargs)

    def register_channel(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_channel(*args, **kwargs)

    def register_context_engine(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_context_engine(*args, **kwargs)

    def register_compaction_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_compaction_provider(*args, **kwargs)

    def register_session_catalog(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_session_catalog(*args, **kwargs)

    def register_cli_backend(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_cli_backend(*args, **kwargs)

    def register_text_transform(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_text_transform(*args, **kwargs)

    def register_session_extension(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_session_extension(*args, **kwargs)

    def register_codex_app_server_extension_factory(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_codex_app_server_extension_factory(*args, **kwargs)

    def register_interactive_handler(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_interactive_handler(*args, **kwargs)

    def register_runtime_lifecycle(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_runtime_lifecycle(*args, **kwargs)

    def register_control_ui_descriptor(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_control_ui_descriptor(*args, **kwargs)

    def register_tool_metadata(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_tool_metadata(*args, **kwargs)

    def register_trusted_tool_policy(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_trusted_tool_policy(*args, **kwargs)

    def register_session_scheduler_job(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_session_scheduler_job(*args, **kwargs)

    def register_session_action(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_session_action(*args, **kwargs)

    def register_agent_event_subscription(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_agent_event_subscription(*args, **kwargs)

    def register_memory_embedding_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_memory_embedding_provider(*args, **kwargs)

    def register_conversation_binding_resolved_handler(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_conversation_binding_resolved_handler(*args, **kwargs)

    def register_doctor_contract(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_doctor_contract(*args, **kwargs)

    def register_http_handler(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_http_handler(*args, **kwargs)

    def register_http_route(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_http_route(*args, **kwargs)

    def register_text_transforms(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_text_transforms(*args, **kwargs)

    def register_typed_hook(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_typed_hook(*args, **kwargs)

    def register_model_catalog_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_model_catalog_provider(*args, **kwargs)

    def register_agent_tool_result_middleware(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_agent_tool_result_middleware(*args, **kwargs)

    def register_skill(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_skill(*args, **kwargs)

    def register_hook(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_hook(*args, **kwargs)

    def register_cron(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_cron(*args, **kwargs)

    def register_gateway_discovery_service(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_gateway_discovery_service(*args, **kwargs)

    def register_media_understanding_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_media_understanding_provider(*args, **kwargs)

    def register_service(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_service(*args, **kwargs)

    def register_gateway_method(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_gateway_method(*args, **kwargs)

    def register_node_invoke_policy(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_node_invoke_policy(*args, **kwargs)

    def register_hosted_media_resolver(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_hosted_media_resolver(*args, **kwargs)

    def register_mcp_server_connection_resolver(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_mcp_server_connection_resolver(*args, **kwargs)

    def register_reload(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_reload(*args, **kwargs)

    def register_node_host_command(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_node_host_command(*args, **kwargs)

    def register_security_audit_collector(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_security_audit_collector(*args, **kwargs)

    def register_worker_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_worker_provider(*args, **kwargs)

    def register_embedding_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_embedding_provider(*args, **kwargs)

    def register_agent_harness(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_agent_harness(*args, **kwargs)

    def register_detached_task_runtime(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_detached_task_runtime(*args, **kwargs)

    def register_realtime_transcription_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_realtime_transcription_provider(*args, **kwargs)

    def register_realtime_voice_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_realtime_voice_provider(*args, **kwargs)

    def register_transcript_source_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_transcript_source_provider(*args, **kwargs)

    def register_image_generation_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_image_generation_provider(*args, **kwargs)

    def register_video_generation_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_video_generation_provider(*args, **kwargs)

    def register_music_generation_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_music_generation_provider(*args, **kwargs)

    def register_web_fetch_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_web_fetch_provider(*args, **kwargs)

    def register_web_search_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_web_search_provider(*args, **kwargs)

    def register_migration_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_migration_provider(*args, **kwargs)

    def register_speech_provider(self, *args: Any, **kwargs: Any) -> Any:
        return super().register_speech_provider(*args, **kwargs)


# Re-export RegistrationMode so plugins can reference the type without
# importing from the private _plugin_api_init module.
from ._plugin_api_init import RegistrationMode  # noqa: E402

__all__ = [
    "CliDescriptor",
    "CommandDecl",
    "PluginAgentApi",
    "PluginApi",
    "PluginControlUiDescriptor",
    "PluginLifecycleApi",
    "PluginRunContextApi",
    "PluginSessionApi",
    "RegistrationMode",
    "ToolDecl",
]
