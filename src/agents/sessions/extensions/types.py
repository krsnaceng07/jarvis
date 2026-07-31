"""jarvis.agents.sessions.extensions.types — extension system types.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/extensions/types.ts``.

Extensions are Python modules that can:
- Subscribe to agent lifecycle events
- Register LLM-callable tools
- Register commands, keyboard shortcuts, and CLI flags
- Interact with the user via UI primitives

Phase 6.9a — extension system types (1:1 port).

Adaptations
-----------
- The OpenClaw source uses TS ``interface`` /
  ``type`` shapes. The Python port uses
  :class:`dataclass` for the structured
  objects (``Extension``, ``ExtensionRuntime``)
  + ``TypedDict`` for the data-only event /
  result shapes. The plain-``dict`` aliases
  preserve the dynamic shape (extensions can
  attach their own fields at runtime).
- The OpenClaw source's TypeBox parameter
  schemas (``ToolDefinition.parameters``) are
  represented as plain :class:`dict` (the
  Python port has no TypeBox equivalent; the
  LLM-side surface lands in Phase 6.10 with
  the tools/ port).
- The OpenClaw source's TUI ``Component`` /
  ``Theme`` / ``KeyId`` types come from
  ``@earendil-works/pi-tui``. The Python
  port uses opaque ``Any`` placeholders
  (the TUI lands in Phase 6.12+).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Optional,
    TypedDict,
    Union,
)


# ============================================================================
# OAuth Types
# ============================================================================


class OAuthCredentials(TypedDict, total=False):
    refresh: str
    access: str
    expires: int


class OAuthPrompt(TypedDict, total=False):
    message: str
    placeholder: str
    allowEmpty: bool


class OAuthAuthInfo(TypedDict, total=False):
    url: str
    instructions: str


class OAuthSelectOption(TypedDict, total=False):
    id: str
    label: str


class OAuthSelectPrompt(TypedDict, total=False):
    message: str
    options: list[OAuthSelectOption]


class OAuthLoginCallbacks(TypedDict, total=False):
    onAuth: Callable[[OAuthAuthInfo], None]
    onPrompt: Callable[[OAuthPrompt], Awaitable[str]]
    onProgress: Callable[[str], None]
    onManualCodeInput: Callable[[], Awaitable[str]]
    onSelect: Callable[[OAuthSelectPrompt], Awaitable[Optional[str]]]
    signal: Any  # AbortSignal


# ============================================================================
# UI Context Types
# ============================================================================


#: AbortSignal sentinels. The Python port
#: uses :class:`threading.Event` (see Phase 6.5
#: for the AbortSignal → Event conversion).
#: Type alias kept opaque for now.
AbortSignal = Any


class ExtensionUIDialogOptions(TypedDict, total=False):
    signal: AbortSignal
    timeout: int


WidgetPlacement = str  # "aboveEditor" | "belowEditor"


class ExtensionWidgetOptions(TypedDict, total=False):
    placement: WidgetPlacement


#: Raw terminal input listener. Mirrors
#: ``TerminalInputHandler``.
TerminalInputHandler = Callable[[str], Optional[dict]]


class WorkingIndicatorOptions(TypedDict, total=False):
    frames: list[str]
    intervalMs: int


#: Wrap the current autocomplete provider.
#: Mirrors ``AutocompleteProviderFactory``.
AutocompleteProviderFactory = Callable[[Any], Any]


#: TUI editor factory. Mirrors ``EditorFactory``.
EditorFactory = Callable[[Any, Any, Any], Any]


#: Component is opaque (TUI lands in Phase 6.12+).
Component = Any


#: Theme is opaque (TUI lands in Phase 6.12+).
Theme = Any


#: ``KeyId`` is opaque (TUI lands in Phase 6.12+).
KeyId = str


#: Autocomplete provider placeholder.
AutocompleteProvider = Any


#: Autocomplete item placeholder.
AutocompleteItem = Any


#: Footer data provider placeholder.
ReadonlyFooterDataProvider = Any


#: Custom message placeholder.
CustomMessage = Any


#: TUI opaque handle.
TUI = Any


class ExtensionUIContext(TypedDict, total=False):
    """UI context for extensions to request
    interactive UI. Mirrors ``ExtensionUIContext``
    (``extensions/types.ts:159-324``).

    Each mode (interactive, RPC, print) provides
    its own implementation.
    """

    select: Callable[..., Awaitable[Optional[str]]]
    confirm: Callable[..., Awaitable[bool]]
    input: Callable[..., Awaitable[Optional[str]]]
    notify: Callable[..., None]
    onTerminalInput: Callable[[TerminalInputHandler], Callable[[], None]]
    setStatus: Callable[[str, Optional[str]], None]
    setWorkingMessage: Callable[..., None]
    setWorkingVisible: Callable[[bool], None]
    setWorkingIndicator: Callable[..., None]
    setHiddenThinkingLabel: Callable[..., None]
    setWidget: Callable[..., None]
    setFooter: Callable[..., None]
    setHeader: Callable[..., None]
    setTitle: Callable[[str], None]
    custom: Callable[..., Awaitable[Any]]
    pasteToEditor: Callable[[str], None]
    setEditorText: Callable[[str], None]
    getEditorText: Callable[[], str]
    editor: Callable[..., Awaitable[Optional[str]]]
    addAutocompleteProvider: Callable[[AutocompleteProviderFactory], None]
    setEditorComponent: Callable[[Optional[EditorFactory]], None]
    getEditorComponent: Callable[[], Optional[EditorFactory]]
    theme: Theme
    getAllThemes: Callable[[], list[dict]]
    getTheme: Callable[[str], Optional[Theme]]
    setTheme: Callable[[Union[str, Theme]], dict]
    getToolsExpanded: Callable[[], bool]
    setToolsExpanded: Callable[[bool], None]


# ============================================================================
# Extension Context
# ============================================================================


class ContextUsage(TypedDict, total=False):
    tokens: Optional[int]
    contextWindow: int
    percent: Optional[float]


class CompactOptions(TypedDict, total=False):
    customInstructions: str
    onComplete: Callable[[Any], None]
    onError: Callable[[Exception], None]


#: Readonly session manager placeholder (Phase 6.5).
ReadonlySessionManager = Any


#: Session manager placeholder (Phase 6.5).
SessionManager = Any


#: Model placeholder (Phase 6.7).
Model = Any


#: Image content placeholder.
ImageContent = Any


#: Text content placeholder.
TextContent = Any


#: Tool result message placeholder.
ToolResultMessage = Any


#: Thinking level placeholder.
ThinkingLevel = Any


#: Tool execution mode placeholder.
ToolExecutionMode = str  # "sequential" | "parallel"


#: Agent message placeholder.
AgentMessage = Any


#: Agent tool result placeholder.
AgentToolResult = Any


#: Agent tool update callback placeholder.
AgentToolUpdateCallback = Callable[..., None]


#: System prompt build options placeholder.
BuildSystemPromptOptions = Any


class ExtensionContext(TypedDict, total=False):
    """Context passed to extension event
    handlers. Mirrors ``ExtensionContext``
    (``extensions/types.ts:347-376``)."""

    ui: ExtensionUIContext
    hasUI: bool
    cwd: str
    sessionManager: ReadonlySessionManager
    modelRegistry: Any  # ModelRegistry (Phase 6.7)
    model: Optional[Model]
    isIdle: Callable[[], bool]
    signal: Optional[AbortSignal]
    abort: Callable[[], None]
    hasPendingMessages: Callable[[], bool]
    shutdown: Callable[[], None]
    getContextUsage: Callable[[], Optional[ContextUsage]]
    compact: Callable[[Optional[CompactOptions]], None]
    getSystemPrompt: Callable[[], str]


class NewSessionOptions(TypedDict, total=False):
    parentSession: str
    setup: Callable[[SessionManager], Awaitable[None]]
    withSession: Callable[["ReplacedSessionContext"], Awaitable[None]]


class ExtensionCommandContext(ExtensionContext, total=False):
    """Extended context for command handlers.
    Mirrors ``ExtensionCommandContext``
    (``extensions/types.ts:382-421``)."""

    waitForIdle: Callable[[], Awaitable[None]]
    newSession: Callable[
        [Optional[NewSessionOptions]], Awaitable[dict]
    ]
    fork: Callable[[str, Optional[ForkOptions]], Awaitable[dict]]
    navigateTree: Callable[[str, Optional[NavigateTreeOptions]], Awaitable[dict]]
    switchSession: Callable[[str, Optional[SwitchSessionOptions]], Awaitable[dict]]
    reload: Callable[[], Awaitable[None]]


class ForkOptions(TypedDict, total=False):
    position: str  # "before" | "at"
    withSession: Callable[["ReplacedSessionContext"], Awaitable[None]]


class NavigateTreeOptions(TypedDict, total=False):
    summarize: bool
    customInstructions: str
    replaceInstructions: bool
    label: str


class SwitchSessionOptions(TypedDict, total=False):
    withSession: Callable[["ReplacedSessionContext"], Awaitable[None]]


class ReplacedSessionContext(TypedDict, total=False):
    """Fresh command-capable context bound to
    the replacement session after a session
    switch. Mirrors ``ReplacedSessionContext``
    (``extensions/types.ts:428-438``)."""

    sendMessage: Callable[..., Awaitable[None]]
    sendUserMessage: Callable[..., Awaitable[None]]


# ============================================================================
# Tool Types
# ============================================================================


class ToolRenderResultOptions(TypedDict, total=False):
    expanded: bool
    isPartial: bool


class ToolRenderContext(TypedDict, total=False):
    args: Any
    toolCallId: str
    invalidate: Callable[[], None]
    lastComponent: Optional[Component]
    state: Any
    cwd: str
    executionStarted: bool
    argsComplete: bool
    isPartial: bool
    expanded: bool
    showImages: bool
    isError: bool


class ToolDefinition(TypedDict, total=False):
    """Tool definition for ``registerTool()``.
    Mirrors ``ToolDefinition``
    (``extensions/types.ts:487-548``)."""

    name: str
    label: str
    hideFromChannelProgress: bool
    description: str
    promptSnippet: str
    promptGuidelines: list[str]
    parameters: dict  # TypeBox schema (Python: dict)
    outputSchema: dict
    renderShell: str  # "default" | "self"
    prepareArguments: Callable[[Any], dict]
    executionMode: ToolExecutionMode
    execute: Callable[..., Awaitable[AgentToolResult]]
    renderCall: Callable[..., Component]
    renderResult: Callable[..., Component]


# ============================================================================
# Resource Events
# ============================================================================


class ResourcesDiscoverEvent(TypedDict, total=False):
    type: str  # "resources_discover"
    cwd: str
    reason: str  # "startup" | "reload"


class ResourcesDiscoverResult(TypedDict, total=False):
    skillPaths: list[str]
    promptPaths: list[str]
    themePaths: list[str]


# ============================================================================
# Session Events
# ============================================================================


class SessionStartEvent(TypedDict, total=False):
    type: str  # "session_start"
    reason: str  # "startup" | "reload" | "new" | "resume" | "fork"
    previousSessionFile: str


class SessionBeforeSwitchEvent(TypedDict, total=False):
    type: str  # "session_before_switch"
    reason: str
    targetSessionFile: str


class SessionBeforeForkEvent(TypedDict, total=False):
    type: str  # "session_before_fork"
    entryId: str
    position: str  # "before" | "at"


class SessionBeforeCompactEvent(TypedDict, total=False):
    type: str  # "session_before_compact"
    preparation: Any  # CompactionPreparation (Phase 6.12)
    branchEntries: list[Any]  # SessionEntry[]
    customInstructions: str
    signal: AbortSignal


class SessionCompactEvent(TypedDict, total=False):
    type: str  # "session_compact"
    compactionEntry: Any  # CompactionEntry (Phase 6.12)
    fromExtension: bool


class SessionShutdownEvent(TypedDict, total=False):
    type: str  # "session_shutdown"
    reason: str
    targetSessionFile: str


class TreePreparation(TypedDict, total=False):
    targetId: str
    oldLeafId: Optional[str]
    commonAncestorId: Optional[str]
    entriesToSummarize: list[Any]  # SessionEntry[]
    userWantsSummary: bool
    customInstructions: str
    replaceInstructions: bool
    label: str


class SessionBeforeTreeEvent(TypedDict, total=False):
    type: str  # "session_before_tree"
    preparation: TreePreparation
    signal: AbortSignal


class SessionTreeEvent(TypedDict, total=False):
    type: str  # "session_tree"
    newLeafId: Optional[str]
    oldLeafId: Optional[str]
    summaryEntry: Any  # BranchSummaryEntry (Phase 6.12)
    fromExtension: bool


# ============================================================================
# Agent Events
# ============================================================================


class ContextEvent(TypedDict, total=False):
    type: str  # "context"
    messages: list[AgentMessage]


class BeforeProviderRequestEvent(TypedDict, total=False):
    type: str  # "before_provider_request"
    payload: Any


class AfterProviderResponseEvent(TypedDict, total=False):
    type: str  # "after_provider_response"
    status: int
    headers: dict


class BeforeAgentStartEvent(TypedDict, total=False):
    type: str  # "before_agent_start"
    prompt: str
    images: list[ImageContent]
    systemPrompt: str
    systemPromptOptions: BuildSystemPromptOptions


class AgentStartEvent(TypedDict, total=False):
    type: str  # "agent_start"


class AgentEndEvent(TypedDict, total=False):
    type: str  # "agent_end"
    messages: list[AgentMessage]


class AgentSettledEvent(TypedDict, total=False):
    type: str  # "agent_settled"


class TurnStartEvent(TypedDict, total=False):
    type: str  # "turn_start"
    turnIndex: int
    timestamp: int


class TurnEndEvent(TypedDict, total=False):
    type: str  # "turn_end"
    turnIndex: int
    message: AgentMessage
    toolResults: list[ToolResultMessage]


class MessageStartEvent(TypedDict, total=False):
    type: str  # "message_start"
    message: AgentMessage


class MessageUpdateEvent(TypedDict, total=False):
    type: str  # "message_update"
    message: AgentMessage
    assistantMessageEvent: Any  # AssistantMessageEvent


class MessageEndEvent(TypedDict, total=False):
    type: str  # "message_end"
    message: AgentMessage


class ToolExecutionStartEvent(TypedDict, total=False):
    type: str  # "tool_execution_start"
    toolCallId: str
    toolName: str
    args: Any


class ToolExecutionUpdateEvent(TypedDict, total=False):
    type: str  # "tool_execution_update"
    toolCallId: str
    toolName: str
    args: Any
    partialResult: Any


class ToolExecutionEndEvent(TypedDict, total=False):
    type: str  # "tool_execution_end"
    toolCallId: str
    toolName: str
    result: Any
    isError: bool


# ============================================================================
# Model Events
# ============================================================================


class ModelSelectEvent(TypedDict, total=False):
    type: str  # "model_select"
    model: Model
    previousModel: Optional[Model]
    source: str  # "set" | "cycle" | "restore"


class ThinkingLevelSelectEvent(TypedDict, total=False):
    type: str  # "thinking_level_select"
    level: ThinkingLevel
    previousLevel: ThinkingLevel


# ============================================================================
# User Bash Events
# ============================================================================


class UserBashEvent(TypedDict, total=False):
    type: str  # "user_bash"
    command: str
    excludeFromContext: bool
    cwd: str


# ============================================================================
# Input Events
# ============================================================================


InputSource = str  # "interactive" | "rpc" | "extension"


class InputEvent(TypedDict, total=False):
    type: str  # "input"
    text: str
    images: list[ImageContent]
    source: InputSource


class InputEventResult(TypedDict, total=False):
    action: str  # "continue" | "transform" | "handled"
    text: str
    images: list[ImageContent]


# ============================================================================
# Tool Events
# ============================================================================


class ToolCallEvent(TypedDict, total=False):
    type: str  # "tool_call"
    toolCallId: str
    toolName: str
    input: dict


class ToolResultEvent(TypedDict, total=False):
    type: str  # "tool_result"
    toolCallId: str
    input: dict
    content: list  # (TextContent | ImageContent)[]
    isError: bool
    toolName: str
    details: Any


# ============================================================================
# Event Results
# ============================================================================


class ContextEventResult(TypedDict, total=False):
    messages: list[AgentMessage]


class ToolCallEventResult(TypedDict, total=False):
    block: bool
    reason: str


class UserBashEventResult(TypedDict, total=False):
    operations: Any  # BashOperations (Phase 6.10)
    result: Any  # BashResult (Phase 6.10)


class ToolResultEventResult(TypedDict, total=False):
    content: list  # (TextContent | ImageContent)[]
    details: Any
    isError: bool


class MessageEndEventResult(TypedDict, total=False):
    message: AgentMessage


class BeforeAgentStartEventResult(TypedDict, total=False):
    message: Any  # Pick<CustomMessage, "customType" | "content" | "display" | "details">
    systemPrompt: str


class SessionBeforeSwitchResult(TypedDict, total=False):
    cancel: bool


class SessionBeforeForkResult(TypedDict, total=False):
    cancel: bool
    skipConversationRestore: bool


class SessionBeforeCompactResult(TypedDict, total=False):
    cancel: bool
    compaction: Any  # CompactionResult


class SessionBeforeTreeResult(TypedDict, total=False):
    cancel: bool
    summary: dict
    customInstructions: str
    replaceInstructions: bool
    label: str


# ============================================================================
# Message Rendering
# ============================================================================


class MessageRenderOptions(TypedDict, total=False):
    expanded: bool


#: Message renderer. Mirrors ``MessageRenderer``.
MessageRenderer = Callable[..., Optional[Component]]


# ============================================================================
# Command Registration
# ============================================================================


#: Source info placeholder (Phase 6.9+).
SourceInfo = Any


#: Autocomplete item placeholder.
AutocompleteItem = Any


class RegisteredCommand(TypedDict, total=False):
    name: str
    sourceInfo: SourceInfo
    description: str
    getArgumentCompletions: Callable[..., Any]
    handler: Callable[[str, "ExtensionCommandContext"], Awaitable[None]]


class ResolvedCommand(TypedDict, total=False):
    """Resolved command with an assigned
    ``invocationName``. Mirrors
    ``ResolvedCommand``
    (``extensions/types.ts:1170-1172``)."""

    name: str
    sourceInfo: SourceInfo
    description: str
    getArgumentCompletions: Callable[..., Any]
    handler: Callable[[str, "ExtensionCommandContext"], Awaitable[None]]
    invocationName: str


# ============================================================================
# Extension API
# ============================================================================


#: Handler function type for events.
ExtensionHandler = Callable[..., Any]


#: Event bus placeholder (Phase 6.9+).
EventBus = Any


#: Slash command info placeholder.
SlashCommandInfo = Any


#: Model provider config (mirrors ProviderConfig).
class ProviderConfig(TypedDict, total=False):
    name: str
    baseUrl: str
    apiKey: str
    api: str  # Api (Phase 6.7)
    streamSimple: Callable[..., Any]
    headers: dict
    authHeader: bool
    models: list[dict]  # ProviderModelConfig[]
    oauth: dict  # OAuthProviderConfig


class ExtensionAPI(TypedDict, total=False):
    """ExtensionAPI passed to extension
    factory functions. Mirrors ``ExtensionAPI``
    (``extensions/types.ts:1188-1426``).

    The Python port uses a flat ``dict`` for the
    runtime instance (the loader creates this
    per extension); the static type surface
    here is for documentation / type checking.
    """

    on: Callable[[str, ExtensionHandler], None]
    registerTool: Callable[[ToolDefinition], None]
    registerCommand: Callable[[str, dict], None]
    registerShortcut: Callable[[KeyId, dict], None]
    registerFlag: Callable[[str, dict], None]
    getFlag: Callable[[str], Optional[Union[bool, str]]]
    registerMessageRenderer: Callable[[str, MessageRenderer], None]
    sendMessage: Callable[..., None]
    sendUserMessage: Callable[..., None]
    appendEntry: Callable[[str, Optional[Any]], None]
    setSessionName: Callable[[str], None]
    getSessionName: Callable[[], Optional[str]]
    setLabel: Callable[[str, Optional[str]], None]
    exec: Callable[..., Awaitable[Any]]
    getActiveTools: Callable[[], list[str]]
    getAllTools: Callable[[], list[dict]]
    setActiveTools: Callable[[list[str]], None]
    getCommands: Callable[[], list[SlashCommandInfo]]
    setModel: Callable[[Model], Awaitable[bool]]
    getThinkingLevel: Callable[[], ThinkingLevel]
    setThinkingLevel: Callable[[ThinkingLevel], None]
    registerProvider: Callable[[str, ProviderConfig], None]
    unregisterProvider: Callable[[str], None]
    events: EventBus


# ============================================================================
# Extension Factory
# ============================================================================


#: Extension factory function type. Supports
#: both sync and async initialization.
ExtensionFactory = Callable[[ExtensionAPI], Union[None, Awaitable[None]]]


# ============================================================================
# Loaded Extension Types
# ============================================================================


class RegisteredTool(TypedDict, total=False):
    definition: ToolDefinition
    sourceInfo: SourceInfo


class ExtensionFlag(TypedDict, total=False):
    name: str
    description: str
    type: str  # "boolean" | "string"
    default: Optional[Union[bool, str]]
    extensionPath: str


class ExtensionShortcut(TypedDict, total=False):
    shortcut: KeyId
    description: str
    handler: Callable[[ExtensionContext], Union[None, Awaitable[None]]]
    extensionPath: str


#: Tool info. Mirrors ``ToolInfo``
#: (``extensions/types.ts:1544-1547``).
class ToolInfo(TypedDict, total=False):
    name: str
    description: str
    parameters: dict
    sourceInfo: SourceInfo


# ============================================================================
# Extension Runtime (state + actions)
# ============================================================================


def _not_initialized_factory() -> Callable[..., None]:
    """Build a fresh throwing action stub.
    The stub raises when invoked, mirroring
    the OpenClaw ``notInitialized`` shim
    (``loader.ts:247-251``)."""

    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(
            "Extension runtime not initialized. "
            "Action methods cannot be called during extension loading."
        )

    return _raise


def _not_initialized_async_factory() -> Callable[..., Awaitable[None]]:
    """Build a fresh throwing async action stub.
    Used for ``setModel`` (the OpenClaw source
    returns a rejected Promise;
    ``loader.ts:272``)."""

    async def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(
            "Extension runtime not initialized. "
            "Action methods cannot be called during extension loading."
        )

    return _raise


#: Backwards-compatible alias used by tests +
#: pre-bind Runtime callers. Calling the
#: alias directly raises.
def _not_initialized(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError(
        "Extension runtime not initialized. "
        "Action methods cannot be called during extension loading."
    )


#: Handler function type for events.
HandlerFn = Callable[..., Awaitable[Any]]


class PendingProviderRegistration(TypedDict, total=False):
    name: str
    config: ProviderConfig
    extensionPath: str


#: Default stale-instance message (mirrors
#: ``runner.ts:491-498``).
DEFAULT_STALE_MESSAGE = (
    "This extension ctx is stale after session replacement or reload. "
    "Do not use a captured api or command ctx after ctx.newSession(), "
    "ctx.fork(), ctx.switchSession(), or ctx.reload(). For newSession, "
    "fork, and switchSession, move post-replacement work into withSession "
    "and use the ctx passed to withSession. For reload, do not use the "
    "old ctx after await ctx.reload()."
)


@dataclass
class ExtensionRuntime:
    """Shared state created by loader, used
    during registration and runtime. Contains
    flag values (defaults set during
    registration, CLI values set after).

    Mirrors ``ExtensionRuntime``
    (``extensions/types.ts:1569-1666``)."""

    flagValues: dict[str, Union[bool, str]] = field(default_factory=dict)
    pendingProviderRegistrations: list[PendingProviderRegistration] = field(
        default_factory=list
    )
    _stale_message: Optional[str] = None
    # Action stubs (replaced by bindCore)
    sendMessage: Callable[..., None] = field(default_factory=_not_initialized_factory)
    sendUserMessage: Callable[..., None] = field(default_factory=_not_initialized_factory)
    appendEntry: Callable[..., None] = field(default_factory=_not_initialized_factory)
    setSessionName: Callable[..., None] = field(default_factory=_not_initialized_factory)
    getSessionName: Callable[..., None] = field(default_factory=_not_initialized_factory)
    setLabel: Callable[..., None] = field(default_factory=_not_initialized_factory)
    getActiveTools: Callable[..., list[str]] = field(
        default_factory=_not_initialized_factory
    )
    getAllTools: Callable[..., list[dict]] = field(
        default_factory=_not_initialized_factory
    )
    setActiveTools: Callable[..., None] = field(default_factory=_not_initialized_factory)
    refreshTools: Callable[..., None] = field(default=lambda: None)
    getCommands: Callable[..., list[SlashCommandInfo]] = field(
        default_factory=_not_initialized_factory
    )
    setModel: Callable[..., Awaitable[bool]] = field(
        default_factory=_not_initialized_async_factory
    )
    getThinkingLevel: Callable[..., ThinkingLevel] = field(
        default_factory=_not_initialized_factory
    )
    setThinkingLevel: Callable[..., None] = field(
        default_factory=_not_initialized_factory
    )
    registerProvider: Callable[..., None] = field(
        default_factory=_not_initialized_factory
    )
    unregisterProvider: Callable[..., None] = field(
        default_factory=_not_initialized_factory
    )

    def __post_init__(self) -> None:
        """Wire the pre-bind provider
        registration / unregistration methods
        so they queue into
        ``pendingProviderRegistrations`` until
        :meth:`bindCore` flushes them. Mirrors
        ``loader.ts:285-292`` (the OpenClaw
        source sets these on the runtime object
        inside ``createExtensionRuntime()``).
        """
        pending = self.pendingProviderRegistrations

        def _register_provider(
            name: str,
            config: ProviderConfig,
            extension_path: str = "<unknown>",
        ) -> None:
            self.assertActive()
            pending.append(
                {"name": name, "config": config, "extensionPath": extension_path}
            )

        def _unregister_provider(
            name: str,
            extension_path: str = "<unknown>",
        ) -> None:
            self.assertActive()
            # OpenClaw removes from queue pre-bind;
            # the type signature is unused here.
            del extension_path
            self.pendingProviderRegistrations[:] = [
                r for r in self.pendingProviderRegistrations if r["name"] != name
            ]

        self.registerProvider = _register_provider  # type: ignore[assignment]
        self.unregisterProvider = _unregister_provider  # type: ignore[assignment]

    def assertActive(self) -> None:
        if self._stale_message:
            raise RuntimeError(self._stale_message)

    def invalidate(self, message: Optional[str] = None) -> None:
        if not self._stale_message:
            self._stale_message = message or DEFAULT_STALE_MESSAGE


class ExtensionActions(TypedDict, total=False):
    """Action implementations for ExtensionAPI
    methods. Mirrors ``ExtensionActions``
    (``extensions/types.ts:1595-1610``)."""

    sendMessage: Callable[..., None]
    sendUserMessage: Callable[..., None]
    appendEntry: Callable[..., None]
    setSessionName: Callable[..., None]
    getSessionName: Callable[..., None]
    setLabel: Callable[..., None]
    getActiveTools: Callable[..., list[str]]
    getAllTools: Callable[..., list[dict]]
    setActiveTools: Callable[..., None]
    refreshTools: Callable[..., None]
    getCommands: Callable[..., list[SlashCommandInfo]]
    setModel: Callable[..., Awaitable[bool]]
    getThinkingLevel: Callable[..., ThinkingLevel]
    setThinkingLevel: Callable[..., None]


class ExtensionContextActions(TypedDict, total=False):
    """Actions for ExtensionContext (``ctx.*``
    in event handlers). Mirrors
    ``ExtensionContextActions``
    (``extensions/types.ts:1616-1626``)."""

    getModel: Callable[[], Optional[Model]]
    isIdle: Callable[[], bool]
    getSignal: Callable[[], Optional[AbortSignal]]
    abort: Callable[[], None]
    hasPendingMessages: Callable[[], bool]
    shutdown: Callable[[], None]
    getContextUsage: Callable[[], Optional[ContextUsage]]
    compact: Callable[[Optional[CompactOptions]], None]
    getSystemPrompt: Callable[[], str]


class ExtensionCommandContextActions(TypedDict, total=False):
    """Actions for ExtensionCommandContext
    (``ctx.*`` in command handlers). Mirrors
    ``ExtensionCommandContextActions``
    (``extensions/types.ts:1632-1660``)."""

    waitForIdle: Callable[[], Awaitable[None]]
    newSession: Callable[
        [Optional[NewSessionOptions]], Awaitable[dict]
    ]
    fork: Callable[[str, Optional[ForkOptions]], Awaitable[dict]]
    navigateTree: Callable[[str, Optional[NavigateTreeOptions]], Awaitable[dict]]
    switchSession: Callable[[str, Optional[SwitchSessionOptions]], Awaitable[dict]]
    reload: Callable[[], Awaitable[None]]


# ============================================================================
# Extension (loaded)
# ============================================================================


@dataclass
class Extension:
    """Loaded extension with all registered
    items. Mirrors ``Extension``
    (``extensions/types.ts:1669-1679``)."""

    path: str
    resolvedPath: str
    sourceInfo: SourceInfo
    handlers: dict[str, list[HandlerFn]]
    tools: dict[str, RegisteredTool]
    messageRenderers: dict[str, MessageRenderer]
    commands: dict[str, RegisteredCommand]
    flags: dict[str, ExtensionFlag]
    shortcuts: dict[KeyId, ExtensionShortcut]


# ============================================================================
# Load Result
# ============================================================================


class LoadExtensionsError(TypedDict, total=False):
    path: str
    error: str


@dataclass
class LoadExtensionsResult:
    """Result of loading extensions. Mirrors
    ``LoadExtensionsResult``
    (``extensions/types.ts:1682-1687``)."""

    extensions: list[Extension]
    errors: list[LoadExtensionsError]
    runtime: ExtensionRuntime


# ============================================================================
# Extension Error
# ============================================================================


class ExtensionError(TypedDict, total=False):
    extensionPath: str
    event: str
    error: str
    stack: str


#: Error listener type (the OpenClaw source
#: declares it in ``runner.ts:163``; the
#: Python port keeps the alias in the
#: ``runner`` module to match the
#: OpenClaw module split).
ExtensionErrorListener = Callable[["ExtensionError"], None]


#: Shutdown handler type (the OpenClaw source
#: declares it in ``runner.ts:196``; the
#: Python port keeps the alias in the
#: ``runner`` module to match the
#: OpenClaw module split).
ShutdownHandler = Callable[[], None]


# ============================================================================
# Type Guards
# ============================================================================


def is_bash_tool_result(event: ToolResultEvent) -> bool:
    """Type guard for narrowing ToolResultEvent
    by tool name. Mirrors
    ``extensions/types.ts:972-992``."""
    return event.get("toolName") == "bash"


def is_read_tool_result(event: ToolResultEvent) -> bool:
    return event.get("toolName") == "read"


def is_edit_tool_result(event: ToolResultEvent) -> bool:
    return event.get("toolName") == "edit"


def is_write_tool_result(event: ToolResultEvent) -> bool:
    return event.get("toolName") == "write"


def is_grep_tool_result(event: ToolResultEvent) -> bool:
    return event.get("toolName") == "grep"


def is_find_tool_result(event: ToolResultEvent) -> bool:
    return event.get("toolName") == "find"


def is_ls_tool_result(event: ToolResultEvent) -> bool:
    return event.get("toolName") == "ls"


def is_tool_call_event_type(
    tool_name: str,
    event: ToolCallEvent,
) -> bool:
    """Type guard for narrowing ToolCallEvent
    by tool name. Mirrors
    ``extensions/types.ts:1014-1045``."""
    return event.get("toolName") == tool_name


# ============================================================================
# defineTool (identity function for type compat)
# ============================================================================


def define_tool(
    tool: ToolDefinition,
) -> ToolDefinition:
    """Preserve parameter inference for
    standalone tool definitions. Mirrors
    ``extensions/types.ts:559-563`` (the
    Python port is a plain identity — there
    is no TS type-narrowing trick to preserve).
    """
    return tool


__all__ = [
    "AbortSignal",
    "AgentEndEvent",
    "AgentMessage",
    "AgentSettledEvent",
    "AgentStartEvent",
    "AgentToolResult",
    "AgentToolUpdateCallback",
    "AfterProviderResponseEvent",
    "AutocompleteItem",
    "AutocompleteProvider",
    "AutocompleteProviderFactory",
    "BeforeAgentStartEvent",
    "BeforeAgentStartEventResult",
    "BeforeProviderRequestEvent",
    "BuildSystemPromptOptions",
    "CompactOptions",
    "Component",
    "ContextEvent",
    "ContextEventResult",
    "ContextUsage",
    "DEFAULT_STALE_MESSAGE",
    "CustomMessage",
    "EditorFactory",
    "EventBus",
    "Extension",
    "ExtensionActions",
    "ExtensionAPI",
    "ExtensionCommandContext",
    "ExtensionCommandContextActions",
    "ExtensionContext",
    "ExtensionContextActions",
    "ExtensionError",
    "ExtensionFactory",
    "ExtensionFlag",
    "ExtensionHandler",
    "ExtensionRuntime",
    "ExtensionShortcut",
    "ExtensionUIDialogOptions",
    "ExtensionUIContext",
    "ExtensionWidgetOptions",
    "ForkOptions",
    "HandlerFn",
    "ImageContent",
    "InputEvent",
    "InputEventResult",
    "InputSource",
    "KeyId",
    "LoadExtensionsError",
    "LoadExtensionsResult",
    "MessageEndEvent",
    "MessageEndEventResult",
    "MessageRenderOptions",
    "MessageRenderer",
    "MessageStartEvent",
    "MessageUpdateEvent",
    "Model",
    "ModelSelectEvent",
    "NavigateTreeOptions",
    "NewSessionOptions",
    "OAuthAuthInfo",
    "OAuthCredentials",
    "OAuthLoginCallbacks",
    "OAuthPrompt",
    "OAuthSelectOption",
    "OAuthSelectPrompt",
    "PendingProviderRegistration",
    "ProviderConfig",
    "ReadonlyFooterDataProvider",
    "ReadonlySessionManager",
    "RegisteredCommand",
    "RegisteredTool",
    "ReplacedSessionContext",
    "ResolvedCommand",
    "ResourcesDiscoverEvent",
    "ResourcesDiscoverResult",
    "SessionBeforeCompactEvent",
    "SessionBeforeCompactResult",
    "SessionBeforeForkEvent",
    "SessionBeforeForkResult",
    "SessionBeforeSwitchEvent",
    "SessionBeforeSwitchResult",
    "SessionBeforeTreeEvent",
    "SessionBeforeTreeResult",
    "SessionCompactEvent",
    "SessionManager",
    "SessionShutdownEvent",
    "SessionStartEvent",
    "SessionTreeEvent",
    "SlashCommandInfo",
    "SourceInfo",
    "SwitchSessionOptions",
    "TerminalInputHandler",
    "TextContent",
    "Theme",
    "ThinkingLevel",
    "ThinkingLevelSelectEvent",
    "ToolCallEvent",
    "ToolCallEventResult",
    "ToolDefinition",
    "ToolExecutionEndEvent",
    "ToolExecutionMode",
    "ToolExecutionStartEvent",
    "ToolExecutionUpdateEvent",
    "ToolInfo",
    "ToolRenderContext",
    "ToolRenderResultOptions",
    "ToolResultEvent",
    "ToolResultEventResult",
    "ToolResultMessage",
    "TreePreparation",
    "TurnEndEvent",
    "TurnStartEvent",
    "TUI",
    "UserBashEvent",
    "UserBashEventResult",
    "WidgetPlacement",
    "WorkingIndicatorOptions",
    "_not_initialized",
    "_not_initialized_async_factory",
    "_not_initialized_factory",
    "define_tool",
    "is_bash_tool_result",
    "is_edit_tool_result",
    "is_find_tool_result",
    "is_grep_tool_result",
    "is_ls_tool_result",
    "is_read_tool_result",
    "is_tool_call_event_type",
    "is_write_tool_result",
]
