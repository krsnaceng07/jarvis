"""jarvis.agents.sessions.agent_session_types — AgentSession type definitions.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/agent-session-types.ts``.

Defines the public contract for the
:class:`AgentSession` family:

- :data:`AgentSessionEvent` — the
  discriminated union of every event the
  session emits.
- :data:`AgentSessionEventListener` — the
  callback type for session subscribers.
- :data:`AgentSessionWriteLockRunner` — the
  helper for serialising session-file writes.
- :class:`AgentSessionConfig` — the
  constructor config for an agent session.
- :class:`ExtensionBindings` — extension
  handles the session binds.
- :class:`PromptOptions` — the
  per-:meth:`AgentSession.prompt` overrides.
- :class:`ModelCycleResult` — the result of
  cycling the active model.
- :class:`SessionStats` — the per-session
  statistics.

Phase 6.12a — focused port.

Adaptations
-----------
- ``ImageContent`` / ``Model`` come from
  the JARVIS llm-client module (the
  OpenClaw source uses ``llm/types``).
- ``Agent`` / ``AgentEvent`` / ``AgentMessage``
  / ``AgentTool`` / ``CompactionResult`` /
  ``ThinkingLevel`` come from the JARVIS
  agent-runtime module
  (``packages/agent_runtime``).
- The remaining types come from the
  already-ported Layer 2 modules
  (``extensions``, ``model-registry``,
  ``resource-loader``, ``session-manager``,
  ``settings-manager``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Optional,
    TypedDict,
    Union,
)

from .extensions.types import (
    ContextUsage,
    ExtensionCommandContextActions,
    ExtensionErrorListener,
    ExtensionUIContext,
    InputSource,
    SessionStartEvent,
    ShutdownHandler,
    ToolDefinition,
)
from .model_registry import ModelRegistry
from .resource_loader import ResourceLoader
from .session_manager import SessionManager
from .settings_manager import SettingsManager


if TYPE_CHECKING:
    # Image content + Model from the
    # llm-client package (forward ref —
    # the runtime type lives in a
    # workspace member).
    from packages.jarvis_llm_client.src.jarvis_llm.types import (  # type: ignore[import-not-found]
        ImageContent,
        Model,
    )
    # Agent runtime types (forward ref).
    from packages.jarvis_agent_runtime.src.jarvis_agent.types import (  # type: ignore[import-not-found]
        Agent,
        AgentEvent,
        AgentMessage,
        AgentTool,
        CompactionResult,
        ThinkingLevel,
    )
else:
    # Runtime fallback aliases — the
    # workspace packages may not be
    # installed in every test env. The
    # real types are imported under
    # ``TYPE_CHECKING`` for pyright.
    ThinkingLevel = str
    Model = Any
    ImageContent = Any
    Agent = Any
    AgentEvent = Any
    AgentMessage = Any
    AgentTool = Any
    CompactionResult = Any


#: The compaction reason. Mirrors
#: ``compaction_start`` / ``compaction_end``
#: events in
#: ``agent-session-types.ts:30-40``.
CompactionReason = str  # "manual" | "threshold" | "overflow"

#: The agent-end event carries the full
#: final message list + a retry hint.
AgentEndEvent = TypedDict(
    "AgentEndEvent",
    {
        "type": str,
        "messages": list,  # list[AgentMessage]
        "willRetry": bool,
    },
    total=False,
)

#: Queue update event when the steering /
#: follow-up queues change.
QueueUpdateEvent = TypedDict(
    "QueueUpdateEvent",
    {
        "type": str,
        "steering": list,  # list[str]
        "followUp": list,  # list[str]
    },
    total=False,
)

#: Compaction lifecycle events.
CompactionStartEvent = TypedDict(
    "CompactionStartEvent",
    {
        "type": str,
        "reason": str,
    },
    total=False,
)

CompactionEndEvent = TypedDict(
    "CompactionEndEvent",
    {
        "type": str,
        "reason": str,
        "result": Optional[Any],  # CompactionResult | None
        "aborted": bool,
        "willRetry": bool,
        "errorMessage": Optional[str],
    },
    total=False,
)

#: Session metadata change events.
SessionInfoChangedEvent = TypedDict(
    "SessionInfoChangedEvent",
    {"type": str, "name": Optional[str]},
    total=False,
)

ThinkingLevelChangedEvent = TypedDict(
    "ThinkingLevelChangedEvent",
    {"type": str, "level": ThinkingLevel},
    total=False,
)

#: Auto-retry lifecycle events.
AutoRetryStartEvent = TypedDict(
    "AutoRetryStartEvent",
    {
        "type": str,
        "attempt": int,
        "maxAttempts": int,
        "delayMs": int,
        "errorMessage": str,
    },
    total=False,
)

AutoRetryEndEvent = TypedDict(
    "AutoRetryEndEvent",
    {
        "type": str,
        "success": bool,
        "attempt": int,
        "finalError": Optional[str],
    },
    total=False,
)


#: A single event emitted by the agent
#: session. Mirrors ``AgentSessionEvent``
#: (``agent-session-types.ts:26-48``). The
#: Python port uses a TypedDict-style
#: ``"type"`` discriminator rather than a
#: TypeScript-style union (the runtime
#: check is via ``event["type"] == "..."``).
AgentSessionEvent = dict  # discriminated by "type"


#: Listener callback shape. Mirrors
#: ``AgentSessionEventListener``
#: (``agent-session-types.ts:50``).
AgentSessionEventListener = Callable[[AgentSessionEvent], None]


#: Helper for serialising session-file
#: writes + write-capable hooks. Mirrors
#: ``AgentSessionWriteLockRunner``
#: (``agent-session-types.ts:51``).
AgentSessionWriteLockRunner = Callable[
    [Callable[[], Union[Awaitable[Any], Any]]],
    Awaitable[Any],
]


@dataclass
class ScopedModelEntry:
    """A model the user can cycle to with
    ``Ctrl+P``. Mirrors the ``scopedModels``
    array in
    :class:`AgentSessionConfig`
    (``agent-session-types.ts:59``)."""

    model: Model
    thinking_level: Optional[ThinkingLevel] = None


@dataclass
class AgentSessionConfig:
    """Constructor config for
    :class:`AgentSession`. Mirrors
    :class:`AgentSessionConfig`
    (``agent-session-types.ts:53-80``).

    Attributes
    ----------
    agent : Agent
        The Layer-1 agent instance.
    session_manager : SessionManager
        Session persistence (Phase 6.5).
    settings_manager : SettingsManager
        Settings persistence (Phase 6.8).
    cwd : str
        Project working directory.
    resource_loader : ResourceLoader
        Resource loader (Phase 6.11b).
    model_registry : ModelRegistry
        Model registry (Phase 6.7).
    scoped_models : list[ScopedModelEntry]
        Optional cycle models (from ``--models``).
    custom_tools : list[ToolDefinition]
        Optional SDK custom tools.
    initial_active_tool_names : list[str]
        Optional initial active tool list
        (defaults to ``read``, ``bash``,
        ``edit``, ``write``).
    allowed_tool_names : list[str]
        Optional allowlist.
    disable_built_in_tools : bool
        Exclude the built-in shell + filesystem
        tools from the registry.
    base_tools_override : dict[str, AgentTool]
        Override the base tools for custom
        runtimes.
    extension_runner_ref : dict
        Mutable reference to the current
        extension runner (set by the session
        after construction).
    session_start_event : SessionStartEvent
        Session-start metadata emitted when
        extensions bind.
    with_session_write_lock : AgentSessionWriteLockRunner
        Lock used before session-file writes
        or write-capable hooks.
    """

    agent: Agent
    session_manager: SessionManager
    settings_manager: SettingsManager
    cwd: str
    resource_loader: ResourceLoader
    model_registry: ModelRegistry
    scoped_models: list[ScopedModelEntry] = field(default_factory=list)
    custom_tools: list[ToolDefinition] = field(default_factory=list)
    initial_active_tool_names: Optional[list[str]] = None
    allowed_tool_names: Optional[list[str]] = None
    disable_built_in_tools: bool = False
    base_tools_override: Optional[dict[str, AgentTool]] = None
    extension_runner_ref: Optional[dict] = None
    session_start_event: Optional[SessionStartEvent] = None
    with_session_write_lock: Optional[AgentSessionWriteLockRunner] = None


@dataclass
class ExtensionBindings:
    """Extension handles the session binds.
    Mirrors ``ExtensionBindings``
    (``agent-session-types.ts:82-88``)."""

    ui_context: Optional[ExtensionUIContext] = None
    command_context_actions: Optional[ExtensionCommandContextActions] = None
    abort_handler: Optional[Callable[[], None]] = None
    shutdown_handler: Optional[ShutdownHandler] = None
    on_error: Optional[ExtensionErrorListener] = None


@dataclass
class PromptOptions:
    """Per-:meth:`AgentSession.prompt`
    overrides. Mirrors ``PromptOptions``
    (``agent-session-types.ts:90-101``)."""

    expand_prompt_templates: bool = True
    images: Optional[list[ImageContent]] = None
    streaming_behavior: Optional[str] = None  # "steer" | "followUp"
    source: Optional[InputSource] = None
    preflight_result: Optional[Callable[[bool], None]] = None


@dataclass
class ModelCycleResult:
    """Result of cycling the active model.
    Mirrors ``ModelCycleResult``
    (``agent-session-types.ts:103-109``)."""

    model: Model
    thinking_level: ThinkingLevel
    is_scoped: bool = False


@dataclass
class SessionTokenUsage:
    """Per-session token usage. Mirrors the
    ``tokens`` field in :class:`SessionStats`
    (``agent-session-types.ts:120``)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0


@dataclass
class SessionStats:
    """Per-session statistics exposed to
    session commands. Mirrors
    :class:`SessionStats`
    (``agent-session-types.ts:111-122``)."""

    session_file: Optional[str] = None
    session_id: str = ""
    user_messages: int = 0
    assistant_messages: int = 0
    tool_calls: int = 0
    tool_results: int = 0
    total_messages: int = 0
    tokens: SessionTokenUsage = field(default_factory=SessionTokenUsage)
    cost: float = 0.0
    context_usage: Optional[ContextUsage] = None


__all__ = [
    "AgentEndEvent",
    "AgentSessionConfig",
    "AgentSessionEvent",
    "AgentSessionEventListener",
    "AgentSessionWriteLockRunner",
    "AutoRetryEndEvent",
    "AutoRetryStartEvent",
    "CompactionEndEvent",
    "CompactionReason",
    "CompactionStartEvent",
    "ExtensionBindings",
    "ModelCycleResult",
    "PromptOptions",
    "QueueUpdateEvent",
    "ScopedModelEntry",
    "SessionInfoChangedEvent",
    "SessionStats",
    "SessionTokenUsage",
    "ThinkingLevelChangedEvent",
]
