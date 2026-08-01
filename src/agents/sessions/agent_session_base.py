"""jarvis.agents.sessions.agent_session_base — AgentSession base class.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/agent-session-base.ts``.

This is the **foundational** base class for
the AgentSession family. It holds the
shared state (the agent, session manager,
settings manager, model registry, etc.),
the event subscription machinery, the
compaction / retry / bash state, and the
write-lock helper.

The full 29K OpenClaw source includes a
lot of integration logic (tool hooks,
event translation, extension bindings,
compaction triggers, branch
summarization, etc.) that is split
across the other AgentSession files. The
Python port preserves the public surface
+ the state shape + the small helpers
(``emit``, ``subscribe``, ``emitQueueUpdate``,
``runWithSessionWriteLock``) so the
subclasses (:class:`AgentSessionPrompting`,
:class:`AgentSessionModels`, ...) can
build on top of it.

Phase 6.12b — focused port of the base
class. The subclasses land in 6.12c-g.

Adaptations
-----------
- The OpenClaw source's
  ``cleanupSessionResources`` is a no-op
  in the Python port (the cleanup
  responsibilities are owned by the
  Python equivalent of the agent runtime).
- The OpenClaw source's
  ``getModelRegistryRuntime`` is replaced
  with a direct call to the registry's
  ``getApiKeyAndHeaders`` method.
- The OpenClaw source's
  ``formatNoApiKeyFoundMessage`` lives
  in :mod:`jarvis.agents.sessions.auth_guidance`
  (Phase 6.13+). The Python port accepts
  a raw provider name for now; the
  guidance message is deferred.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Optional,
    Union,
)

from .agent_session_types import (
    AgentSessionConfig,
    AgentSessionEvent,
    AgentSessionEventListener,
    AgentSessionWriteLockRunner,
)
from .extensions.runner import ExtensionRunner
from .extensions.types import (
    ExtensionCommandContextActions,
    ExtensionErrorListener,
    ExtensionUIContext,
    SessionStartEvent,
    ShutdownHandler,
    ToolDefinition,
)
from .model_registry import ModelRegistry
from .resource_loader import ResourceLoader
from .session_manager import SessionManager
from .settings_manager import SettingsManager


if TYPE_CHECKING:
    from packages.jarvis_agent_runtime.src.jarvis_agent.types import (  # type: ignore[import-not-found]
        Agent,
        AgentEvent,
        AgentMessage,
        AgentState,
        AgentTool,
        AssistantMessage,
        ThinkingLevel,
    )
    from packages.jarvis_llm_client.src.jarvis_llm.types import (  # type: ignore[import-not-found]
        Model,
    )
else:
    # Runtime fallback aliases — see
    # ``agent_session_types.py`` for the
    # full explanation.
    Agent = Any
    AgentEvent = Any
    AgentMessage = Any
    AgentState = Any
    AgentTool = Any
    AssistantMessage = Any
    ThinkingLevel = str
    Model = Any


#: A custom message entry — mirrors
#: ``CustomMessage`` in
#: ``messages.ts``. The Python port
#: uses a plain ``dict`` (the OpenClaw
#: source uses an interface; the
#: runtime contract is the same).
CustomMessage = dict

#: A bash-execution message entry.
BashExecutionMessage = dict


@dataclass
class ToolDefinitionEntry:
    """A registered tool definition + the
    source info that produced it. Mirrors
    the inline
    ``{ definition, sourceInfo }`` shape
    in
    ``agent-session-base.ts:47-50``."""

    definition: ToolDefinition
    sourceInfo: dict  # SourceInfo (Phase 6.13+)


@dataclass
class ActiveToolPromptMetadata:
    """Metadata for the tool-prompt section
    of the system prompt. Mirrors
    ``ActiveToolPromptMetadata``
    (``agent-session-base.ts:52-56``)."""

    valid_tool_names: list[str] = field(default_factory=list)
    tool_snippets: dict[str, str] = field(default_factory=dict)
    prompt_guidelines: list[str] = field(default_factory=list)


@dataclass
class BuildSystemPromptOptions:
    """Options for the system-prompt
    builder. Mirrors
    ``BuildSystemPromptOptions`` from
    ``system-prompt.ts`` (the port's
    minimal shape — the full options
    land in Phase 6.13)."""

    cwd: str = ""
    agent_dir: str = ""
    has_append_system_prompt: bool = False
    include_skills: bool = True
    include_agents_files: bool = True
    include_project_context: bool = True


class AgentSessionBase:
    """Foundational base class for the
    :class:`AgentSession` family. Mirrors
    :class:`AgentSessionBase`
    (``agent-session-base.ts:58-150``).

    Subclasses (added in 6.12c-g):

    - :class:`AgentSessionPrompting` —
      adds ``prompt`` / ``steer`` /
      ``followUp`` (Phase 6.12c).
    - :class:`AgentSessionModels` — adds
      model selection + thinking-level
      cycling (Phase 6.12d).
    - :class:`AgentSessionExtensions` —
      binds extension runners (Phase 6.12e).
    - :class:`AgentSessionTree` — adds
      session-tree branching (Phase 6.12e).
    - :class:`AgentSessionCompaction` —
      adds the compaction loop (Phase 6.12f).
    - :class:`AgentSessionExecution` —
      adds the execution loop (Phase 6.12d).
    - :class:`AgentSessionInspection` —
      adds inspection helpers (Phase 6.12d).

    Phase 6.12b port — foundational state
    + event subscription + write-lock.
    """

    # -- State (mirrors
    #    agent-session-base.ts:59-128) ---------
    readonly_slots = (
        "agent",
        "session_manager",
        "settings_manager",
        "scoped_model_entries",
    )

    agent: Agent
    session_manager: SessionManager
    settings_manager: SettingsManager
    scoped_model_entries: list[dict]  # [{"model", "thinkingLevel"}]
    session_resource_loader: ResourceLoader
    custom_tools: list[ToolDefinition]
    cwd: str
    session_model_registry: ModelRegistry
    extension_runner_ref: Optional[dict]
    initial_active_tool_names: Optional[list[str]]
    allowed_tool_names: Optional[set[str]]
    disable_built_in_tools: bool
    base_tools_override: Optional[dict[str, AgentTool]]
    session_start_event: SessionStartEvent
    with_external_session_write_lock: Optional[AgentSessionWriteLockRunner]
    extension_ui_context: Optional[ExtensionUIContext]
    extension_command_context_actions: Optional[ExtensionCommandContextActions]
    extension_abort_handler: Optional[Callable[[], None]]
    extension_shutdown_handler: Optional[ShutdownHandler]
    extension_error_listener: Optional[ExtensionErrorListener]
    extension_error_unsubscriber: Optional[Callable[[], None]]
    base_tool_definitions: dict[str, ToolDefinition]
    tool_registry: dict[str, AgentTool]
    tool_definitions: dict[str, ToolDefinitionEntry]
    tool_prompt_snippets: dict[str, str]
    tool_prompt_guidelines: dict[str, list[str]]
    base_system_prompt: str
    base_system_prompt_options: BuildSystemPromptOptions
    exact_base_system_prompt: Optional[str]
    system_prompt_override: Optional[str]
    # Extension system
    current_extension_runner: ExtensionRunner
    turn_index: int
    # Compaction state
    compaction_abort_controller: Optional[Any]
    auto_compaction_abort_controller: Optional[Any]
    overflow_recovery_attempted: bool
    # Branch summarization state
    branch_summary_abort_controller: Optional[Any]
    extension_modified_tool_result_ids: set[str]
    # Retry state
    retry_abort_controller: Optional[Any]
    retry_count: int
    # Bash execution state
    bash_abort_controller: Optional[Any]
    pending_bash_messages: list[BashExecutionMessage]
    # Event subscription
    event_listeners: list[AgentSessionEventListener]
    unsubscribe_agent: Optional[Callable[[], None]]
    # Steering / follow-up queues
    steering_messages: list[str]
    follow_up_messages: list[str]
    pending_next_turn_messages: list[CustomMessage]
    # Last assistant message tracking
    last_assistant_message: Optional[AssistantMessage]
    last_run_ended_for_turn_handoff: bool

    def __init__(self, config: AgentSessionConfig) -> None:
        """Bind the session to the agent +
        persistence layers. Mirrors
        ``constructor``
        (``agent-session-base.ts:130-149``)."""
        self.agent = config.agent
        self.session_manager = config.session_manager
        self.settings_manager = config.settings_manager
        self.scoped_model_entries = [
            {"model": e.model, "thinkingLevel": e.thinking_level}
            for e in (config.scoped_models or [])
        ]
        self.session_resource_loader = config.resource_loader
        self.custom_tools = list(config.custom_tools or [])
        self.cwd = config.cwd
        self.session_model_registry = config.model_registry
        self.extension_runner_ref = config.extension_runner_ref
        self.initial_active_tool_names = config.initial_active_tool_names
        self.allowed_tool_names = (
            set(config.allowed_tool_names)
            if config.allowed_tool_names is not None
            else None
        )
        self.disable_built_in_tools = config.disable_built_in_tools
        self.base_tools_override = config.base_tools_override
        self.session_start_event = config.session_start_event or {
            "type": "session_start",
            "reason": "startup",
        }
        self.with_external_session_write_lock = config.with_session_write_lock

        # Initialise mutable state.
        self.extension_ui_context = None
        self.extension_command_context_actions = None
        self.extension_abort_handler = None
        self.extension_shutdown_handler = None
        self.extension_error_listener = None
        self.extension_error_unsubscriber = None
        self.base_tool_definitions = {}
        self.tool_registry = {}
        self.tool_definitions = {}
        self.tool_prompt_snippets = {}
        self.tool_prompt_guidelines = {}
        self.base_system_prompt = ""
        self.base_system_prompt_options = BuildSystemPromptOptions(cwd=self.cwd)
        self.exact_base_system_prompt = None
        self.system_prompt_override = None
        # ``currentExtensionRunner`` is set
        # by the extensions subclass
        # (Phase 6.12e).
        self.current_extension_runner = None  # type: ignore[assignment]
        self.turn_index = 0
        self.compaction_abort_controller = None
        self.auto_compaction_abort_controller = None
        self.overflow_recovery_attempted = False
        self.branch_summary_abort_controller = None
        self.extension_modified_tool_result_ids = set()
        self.retry_abort_controller = None
        self.retry_count = 0
        self.bash_abort_controller = None
        self.pending_bash_messages = []
        self.event_listeners = []
        self.unsubscribe_agent = None
        self.steering_messages = []
        self.follow_up_messages = []
        self.pending_next_turn_messages = []
        self.last_assistant_message = None
        self.last_run_ended_for_turn_handoff = False

    # ------------------------------------------------------------------
    # Model registry accessors
    # ------------------------------------------------------------------

    @property
    def model_registry(self) -> ModelRegistry:
        """Model registry for API key
        resolution + model discovery. Mirrors
        the ``modelRegistry`` getter
        (``agent-session-base.ts:151-154``)."""
        return self.session_model_registry

    # ------------------------------------------------------------------
    # Auth helpers (used by the prompting
    # + execution + compaction subclasses)
    # ------------------------------------------------------------------

    async def get_required_request_auth(
        self, model: Model
    ) -> dict:
        """Resolve the API key + custom
        headers for a model, or raise an
        Error if the model has no
        configured auth. Mirrors
        ``getRequiredRequestAuth``
        (``agent-session-base.ts:156-180``).

        Returns
        -------
        dict
            ``{"apiKey": str, "headers"?: dict}``
        """
        result = await self.session_model_registry.get_api_key_and_headers(model)
        if not result.get("ok"):
            error = result.get("error", "")
            if error.startswith("No API key found"):
                raise RuntimeError(self._format_no_api_key_message(model))
            raise RuntimeError(error)
        if result.get("apiKey"):
            return {
                "apiKey": result["apiKey"],
                "headers": result.get("headers"),
            }
        is_oauth = self.session_model_registry.is_using_oauth(model)
        if is_oauth:
            raise RuntimeError(
                f'Authentication failed for "{self._provider_name(model)}". '
                f"Credentials may have expired or network is unavailable. "
                f"Run '/login {self._provider_name(model)}' to re-authenticate."
            )
        raise RuntimeError(self._format_no_api_key_message(model))

    async def get_compaction_request_auth(
        self, model: Model
    ) -> dict:
        """Resolve auth for a compaction
        request — only the API key +
        headers (not the full auth
        handshake). Mirrors
        ``getCompactionRequestAuth``
        (``agent-session-base.ts:182-195``)."""
        result = await self.session_model_registry.get_api_key_and_headers(model)
        if result.get("ok"):
            return {
                "apiKey": result.get("apiKey"),
                "headers": result.get("headers"),
            }
        return {}

    # ------------------------------------------------------------------
    # Write-lock helper
    # ------------------------------------------------------------------

    async def run_with_session_write_lock(
        self, run: Callable[[], Union[Awaitable[Any], Any]]
    ) -> Any:
        """Serialise session-file writes
        behind the configured
        ``withSessionWriteLock`` (or run
        the task without a lock if the
        session didn't configure one).
        Mirrors ``runWithSessionWriteLock``
        (``agent-session-base.ts:197-201``)."""
        if self.with_external_session_write_lock is not None:
            return await self.with_external_session_write_lock(run)
        result = run()
        if hasattr(result, "__await__"):
            return await result
        return result

    # ------------------------------------------------------------------
    # Event subscription
    # ------------------------------------------------------------------

    def emit(self, event: AgentSessionEvent) -> None:
        """Fan out an event to every
        registered listener. Mirrors
        ``emit``
        (``agent-session-base.ts:276-280``).

        Handler exceptions are NOT isolated
        by this method — they propagate.
        The runner-level ``emit_error``
        path is the proper isolation point.
        """
        for listener in self.event_listeners:
            listener(event)

    def emit_queue_update(self) -> None:
        """Emit a ``queue_update`` event
        carrying the current steering +
        follow-up message lists. Mirrors
        ``emitQueueUpdate``
        (``agent-session-base.ts:282-288``)."""
        self.emit({
            "type": "queue_update",
            "steering": list(self.steering_messages),
            "followUp": list(self.follow_up_messages),
        })

    def subscribe(
        self, listener: AgentSessionEventListener
    ) -> Callable[[], None]:
        """Register an event listener;
        returns an unsubscribe callable.
        Mirrors ``subscribe``
        (``agent-session-base.ts:`` —
        the full method lands in 6.12e)."""
        self.event_listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self.event_listeners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    # ------------------------------------------------------------------
    # Tool hooks (skeleton — the full
    # implementation lands in the
    # extensions subclass)
    # ------------------------------------------------------------------

    def install_agent_tool_hooks(self) -> None:
        """Install the before-/after-tool
        hooks on the agent so the
        extension runner can intercept
        tool calls + tool results.
        Mirrors ``installAgentToolHooks``
        (``agent-session-base.ts:215-269``).

        Phase 6.12b — STUB. The full
        implementation lands with the
        extensions subclass in 6.12e.
        """
        # No-op stub. Subclass overrides.
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _provider_name(self, model: Model) -> str:
        """Extract the provider name from a
        model. Mirrors the
        ``model.provider`` access pattern
        in OpenClaw."""
        if isinstance(model, dict):
            return model.get("provider", "unknown")
        return getattr(model, "provider", "unknown")

    def _format_no_api_key_message(self, model: Model) -> str:
        """Fallback message for a missing
        API key. The OpenClaw source
        delegates to
        :func:`formatNoApiKeyFoundMessage`
        in :mod:`auth-guidance` (Phase
        6.13+); the Python port uses a
        simple string for now."""
        return f"No API key found for {self._provider_name(model)}"


__all__ = [
    "ActiveToolPromptMetadata",
    "AgentSessionBase",
    "BuildSystemPromptOptions",
    "ToolDefinitionEntry",
]
