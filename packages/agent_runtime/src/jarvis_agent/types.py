"""jarvis_agent.types — shared agent-core contracts.

OpenClaw parity: ``packages/agent-core/src/types.ts``.

Every module above this one imports from here and none of them redefine
these shapes. The file is deliberately data-only: no behaviour, no
provider imports beyond ``jarvis_llm``.

Four things a reader should know before using these types
=========================================================

``ThinkingLevel`` here includes ``"off"``
    This is *not* the same alias as ``jarvis_llm.types.ThinkingLevel``,
    which excludes it. The agent tracks a logical level that a user can set
    to off; the provider option is a narrower thing that
    :func:`jarvis_agent.reasoning.resolve_agent_reasoning_option` computes.
    Conflating the two is how "off" silently becomes "provider default".

``AfterToolCallResult`` replaces fields, never merges them
    A hook that returns ``content`` replaces the whole content list. There
    is no deep merge. A hook author expecting merge semantics would append
    and instead truncate.

``terminate`` needs unanimous consent
    The loop stops early only when *every* finalized tool result in the
    batch sets ``terminate=True``. One tool cannot end the run.

Hook contract: do not raise
    ``convert_to_llm``, ``transform_context``, ``get_api_key``,
    ``should_stop_after_turn``, ``prepare_next_turn``,
    ``get_steering_messages`` and ``get_follow_up_messages`` must return a
    safe fallback instead of raising. Raising interrupts the loop without
    producing a normal event sequence, so the caller sees a run that ended
    with no ``agent_end``. This mirrors the never-throw ``StreamFn``
    contract in :mod:`jarvis_llm.stream`.

    The two exceptions are ``resolve_deferred_tool`` and the tool's own
    ``execute``: those *should* raise on failure, and the loop converts the
    exception into an error tool result. ``execute`` must not encode errors
    in ``content``.

Sentinel for "field omitted"
============================
TypeScript distinguishes an absent optional field from one explicitly set
to ``undefined``; several hook results here depend on that distinction
(``AfterToolCallResult`` fields especially, where ``None`` would otherwise
be indistinguishable from "keep the original"). :data:`UNSET` provides it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence, Set
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Protocol, TypeAlias, Union

from jarvis_llm.abort import AbortSignal
from jarvis_llm.stream import StreamFn as LlmStreamFn
from jarvis_llm.types import (
    AssistantMessage,
    AssistantMessageEvent,
    ImageContent,
    Message,
    Model,
    SimpleStreamOptions,
    TextContent,
    Tool,
    ToolCall,
    ToolResultMessage,
)

# ─────────────────────────────────────────────────────────────────────
# Unset sentinel
# ─────────────────────────────────────────────────────────────────────


class _Unset(Enum):
    """Distinguishes "field omitted" from "field explicitly None".

    An ``Enum`` rather than ``object()`` so it is a singleton that survives
    pickling and reads clearly in a repr.
    """

    token = "UNSET"

    def __bool__(self) -> bool:  # pragma: no cover - defensive
        return False

    def __repr__(self) -> str:
        return "UNSET"


#: Marker meaning "this optional field was not provided".
#: Parity: TypeScript's absent-property state, which ``None`` cannot express
#: for fields whose valid values include null.
UNSET: Literal[_Unset.token] = _Unset.token


# ─────────────────────────────────────────────────────────────────────
# Stream function and execution modes
# ─────────────────────────────────────────────────────────────────────

#: Parity: ``StreamFn = LlmStreamFn``. Re-exported so agent-level code
#: never imports the provider layer directly.
#:
#: The contract is unchanged and non-negotiable: it must not raise for
#: request, model, or runtime failures. Failures are encoded in the returned
#: stream as protocol events plus a final ``AssistantMessage`` whose
#: ``stop_reason`` is ``"error"`` or ``"aborted"`` with ``error_message``
#: set. Wrap raw providers in ``jarvis_llm.guard_stream_fn``.
StreamFn: TypeAlias = LlmStreamFn

#: Parity: ``ToolExecutionMode``.
#:
#: ``"sequential"``: each call is prepared, executed and finalized before
#: the next starts. ``"parallel"``: all calls are prepared sequentially,
#: then allowed tools execute concurrently — ``tool_execution_end`` fires in
#: *completion* order while tool-result message artifacts are emitted later
#: in assistant *source* order. Those two orders differ, and code that
#: assumes they match will reorder a transcript.
ToolExecutionMode: TypeAlias = Literal["sequential", "parallel"]

#: Parity: ``QueueMode``. ``"all"`` drains every queued user message at a
#: drain point; ``"one-at-a-time"`` drains only the oldest and leaves the
#: rest for later drain points.
QueueMode: TypeAlias = Literal["all", "one-at-a-time"]

#: Parity: ``ThinkingLevel``. Includes ``"off"``, unlike the llm-core alias.
#:
#: ``"xhigh"`` is supported by only some model families; use the predicates
#: in :mod:`jarvis_llm.model_contracts` to check a concrete model rather
#: than assuming.
ThinkingLevel: TypeAlias = Literal["off", "minimal", "low", "medium", "high", "xhigh", "max"]

#: Parity: ``AgentToolCall = Extract<AssistantMessage["content"][number],
#: { type: "toolCall" }>``. Python has no ``Extract``, so the already-narrow
#: ``ToolCall`` type stands in; the alias is kept so call sites read the
#: same as the TypeScript.
AgentToolCall: TypeAlias = ToolCall


# ─────────────────────────────────────────────────────────────────────
# Harness message types
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BashExecutionMessage:
    """Shell command transcript. Parity: ``BashExecutionMessage``.

    ``exclude_from_context`` keeps the command in session history while
    hiding it from model context — used for noisy or sensitive commands.
    ``convert_to_llm`` honours it by dropping the message.
    """

    #: Parity: ``role: "bashExecution"``.
    role: Literal["bashExecution"] = "bashExecution"
    #: Command line that was executed.
    command: str = ""
    #: Captured output, usually already truncated for context.
    output: str = ""
    #: Millisecond timestamp for transcript ordering.
    timestamp: int = 0
    #: Exit code, or ``None`` when the process never reached exit.
    exit_code: int | None = None
    #: True when the command was interrupted before normal completion.
    cancelled: bool = False
    #: True when output was shortened for transcript/context storage.
    truncated: bool = False
    #: Path holding the complete output when truncation occurred.
    full_output_path: str | None = None
    #: Hide from model context but keep in session history.
    exclude_from_context: bool | None = None


@dataclass(frozen=True)
class CustomMessage:
    """Application-defined transcript content. Parity: ``CustomMessage<T>``.

    ``content`` may be a plain string or a content-block list, matching
    ``string | (TextContent | ImageContent)[]``.

    ``display`` controls whether UI surfaces render it; it does *not*
    control whether the model sees it. A message can be invisible to the
    user and still occupy context.
    """

    #: Parity: ``role: "custom"``.
    role: Literal["custom"] = "custom"
    #: Application-defined discriminator for rendering or handling.
    custom_type: str = ""
    #: Content replayed into model context when included.
    content: str | list[TextContent | ImageContent] = ""
    #: Whether UI surfaces should display this message.
    display: bool = True
    #: Millisecond timestamp for transcript ordering.
    timestamp: int = 0
    #: Application-specific metadata. Parity: the generic ``details?: T``.
    details: Any = None


@dataclass(frozen=True)
class BranchSummaryMessage:
    """Summary produced when returning from another branch.

    Parity: ``BranchSummaryMessage``.
    """

    #: Parity: ``role: "branchSummary"``.
    role: Literal["branchSummary"] = "branchSummary"
    #: Summary text inserted back into model context.
    summary: str = ""
    #: Entry id of the branch root or source leaf being summarized.
    from_id: str = ""
    #: Millisecond timestamp for transcript ordering.
    timestamp: int = 0


@dataclass(frozen=True)
class CompactionSummaryMessage:
    """Summary replacing compacted transcript history.

    Parity: ``CompactionSummaryMessage``.

    ``timestamp`` is typed ``int | str`` on purpose: older persisted rows
    stored it as a string. The union is the actual shape on disk, and
    normalizing it away here would break loading real sessions. See
    ``normalize_compaction_summary_timestamp`` in :mod:`jarvis_agent.messages`.
    """

    #: Parity: ``role: "compactionSummary"``.
    role: Literal["compactionSummary"] = "compactionSummary"
    #: Summary text inserted back into model context.
    summary: str = ""
    #: Estimated context tokens before compaction.
    tokens_before: int = 0
    #: Numeric in memory, string in older persisted rows.
    timestamp: int | str = 0
    #: Estimated context tokens after compaction.
    tokens_after: int | None = None
    #: First retained entry id from the compaction range.
    first_kept_entry_id: str | None = None
    #: Implementation-specific compaction metadata.
    details: Any = None


#: Parity: ``CustomAgentMessages`` — the extension point apps widen via
#: declaration merging. Python has no declaration merging, so the union is
#: written out; an app that adds a message type extends
#: :data:`AgentMessage` in its own module instead.
CustomAgentMessage: TypeAlias = Union[
    BashExecutionMessage,
    CustomMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
]

#: Parity: ``AgentMessage = Message | CustomAgentMessages[keyof ...]``.
#: The transcript type the agent works in; ``convert_to_llm`` narrows it to
#: provider-visible ``Message`` values before each request.
AgentMessage: TypeAlias = Union[Message, CustomAgentMessage]


# ─────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentToolProgress:
    """Channel-safe progress text from a running tool.

    Parity: ``AgentToolProgress``.

    The ``visibility``/``privacy`` fields are constants in the TS and are
    kept as literal defaults here rather than dropped: they document a hard
    rule that this text reaches user-facing surfaces, so it must not contain
    secrets, private arguments, or fetched content.
    """

    #: Public text suitable for user-facing progress surfaces.
    text: str
    #: Stable id for progress-line replacement.
    id: str | None = None
    #: Parity: ``visibility: "channel"``.
    visibility: Literal["channel"] = "channel"
    #: Parity: ``privacy: "public"``.
    privacy: Literal["public"] = "public"


@dataclass(frozen=True)
class AgentToolResult:
    """Final or partial result from a tool. Parity: ``AgentToolResult<T>``.

    ``terminate`` is a *hint*, not a command: early termination requires
    every finalized result in the batch to set it.
    """

    #: Text or image content returned to the model.
    content: list[TextContent | ImageContent] = field(default_factory=list)
    #: Arbitrary structured details for logs or UI. Parity: the generic ``T``.
    details: Any = None
    #: Public progress hint for partial updates; never model content.
    progress: AgentToolProgress | None = None
    #: Hint that the agent should stop after the current tool batch.
    terminate: bool | None = None


#: Parity: ``AgentToolUpdateCallback<T>``. Synchronous by design — a tool
#: reporting progress must not be able to block the loop on an await.
AgentToolUpdateCallback: TypeAlias = Callable[[AgentToolResult], None]


class AgentTool(Protocol):
    """Tool definition used by the agent runtime. Parity: ``AgentTool``.

    A Protocol rather than a dataclass because tools are implemented by
    host packages and extensions; requiring them to inherit a base class
    would couple every extension to this module's release cadence.

    Parity note on generics: the TS parameterizes on ``TSchema`` and
    ``TDetails`` via typebox. This port keeps the schema as a plain dict
    (JSON Schema) because the validation layer in
    :mod:`jarvis_llm.validation` already works on dicts.
    """

    #: Tool name the model calls. Inherited from ``Tool``.
    name: str
    #: Description shown to the model. Inherited from ``Tool``.
    description: str
    #: JSON Schema for the arguments. Inherited from ``Tool``.
    parameters: dict[str, Any]
    #: Human-readable label for UI display.
    label: str
    #: Schema for the structured ``AgentToolResult.details`` value.
    output_schema: dict[str, Any] | None
    #: Keep lifecycle telemetry without rendering transient progress.
    hide_from_channel_progress: bool | None
    #: Per-tool override of the default execution mode.
    execution_mode: ToolExecutionMode | None

    def prepare_arguments(self, args: Any) -> Any:
        """Compatibility shim for raw arguments before schema validation.

        Parity: ``prepareArguments``. Must return an object matching
        ``parameters``.
        """
        ...

    async def execute(
        self,
        tool_call_id: str,
        params: Any,
        signal: AbortSignal | None = None,
        on_update: AgentToolUpdateCallback | None = None,
    ) -> AgentToolResult:
        """Execute the call.

        Parity: ``execute``. **Raise on failure** — do not encode errors in
        ``content``. The loop turns the exception into an error tool result;
        an error hidden inside ``content`` looks like success to the loop
        and to every hook that inspects ``is_error``.
        """
        ...


# ─────────────────────────────────────────────────────────────────────
# Context and state
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentContext:
    """Context snapshot passed into the low-level loop. Parity: ``AgentContext``."""

    #: System prompt included with the request.
    system_prompt: str = ""
    #: Transcript visible to the model.
    messages: list[AgentMessage] = field(default_factory=list)
    #: Tools available for this run.
    tools: list[AgentTool] | None = None


class AgentState(Protocol):
    """Public agent state. Parity: ``AgentState``.

    A Protocol because the TS declares ``tools`` and ``messages`` as
    accessor pairs whose setters *copy* the assigned list. That copy is the
    point: without it a caller holding the original list could mutate agent
    state after assignment. The implementing class in Phase 5.11 provides
    the copying properties; this only states the surface.
    """

    #: System prompt sent with each model request.
    system_prompt: str
    #: Active model used for future turns.
    model: Model
    #: Requested reasoning level for future turns.
    thinking_level: ThinkingLevel

    @property
    def tools(self) -> list[AgentTool]:
        """Available tools. Assignment copies the top-level list."""
        ...

    @property
    def messages(self) -> list[AgentMessage]:
        """Conversation transcript. Assignment copies the top-level list."""
        ...

    @property
    def is_streaming(self) -> bool:
        """True while processing a prompt or continuation.

        Stays true until awaited ``agent_end`` listeners settle — the run is
        not finished when the last event is emitted, only when its listeners
        have returned.
        """
        ...

    @property
    def streaming_message(self) -> AgentMessage | None:
        """Partial assistant message for the current streamed response."""
        ...

    @property
    def pending_tool_calls(self) -> Set[str]:
        """Tool call ids currently executing. Parity: ``ReadonlySet<string>``."""
        ...

    @property
    def error_message(self) -> str | None:
        """Error from the most recent failed or aborted assistant turn."""
        ...


# ─────────────────────────────────────────────────────────────────────
# Hook payloads
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BeforeToolCallResult:
    """Parity: ``BeforeToolCallResult``.

    ``block=True`` prevents execution; the loop emits an error tool result
    whose text is ``reason``, or a default blocked message when omitted.
    """

    block: bool | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AfterToolCallResult:
    """Partial override of an executed tool result.

    Parity: ``AfterToolCallResult``.

    **Replacement, not merge.** Each provided field replaces the original
    value in full — ``content`` replaces the whole list, ``details``
    replaces the whole payload. Omitted fields keep their original values.
    There is no deep merge, so a hook that wants to append must read the
    original from :class:`AfterToolCallContext` and rebuild the list.

    This is why every field defaults to :data:`UNSET` rather than ``None``:
    ``is_error=None`` and "is_error omitted" would otherwise be
    indistinguishable, and the first would clear a genuine error flag.
    """

    content: list[TextContent | ImageContent] | Literal[_Unset.token] = UNSET
    details: Any = UNSET
    is_error: bool | Literal[_Unset.token] = UNSET
    #: Early termination happens only when every finalized result in the
    #: batch sets this to True.
    terminate: bool | Literal[_Unset.token] = UNSET


@dataclass(frozen=True)
class BeforeToolCallContext:
    """Parity: ``BeforeToolCallContext``."""

    #: The assistant message that requested the call.
    assistant_message: AssistantMessage
    #: The raw tool call block from ``assistant_message.content``.
    tool_call: AgentToolCall
    #: Validated arguments for the target tool schema.
    args: Any
    #: Agent context at the time the call is prepared.
    context: AgentContext


@dataclass(frozen=True)
class AfterToolCallContext:
    """Parity: ``AfterToolCallContext``."""

    #: The assistant message that requested the call.
    assistant_message: AssistantMessage
    #: The raw tool call block from ``assistant_message.content``.
    tool_call: AgentToolCall
    #: Validated arguments for the target tool schema.
    args: Any
    #: The executed result *before* any override is applied.
    result: AgentToolResult
    #: Whether the executed result is currently treated as an error.
    is_error: bool
    #: Agent context at the time the call is finalized.
    context: AgentContext


@dataclass(frozen=True)
class DeferredToolCallContext:
    """Parity: ``DeferredToolCallContext``."""

    #: The assistant message that requested the deferred call.
    assistant_message: AssistantMessage
    #: The raw call whose authorized tool definition is deferred.
    tool_call: AgentToolCall
    #: Agent context before the deferred tool is hydrated.
    context: AgentContext


@dataclass(frozen=True)
class ShouldStopAfterTurnContext:
    """Parity: ``ShouldStopAfterTurnContext``."""

    #: The assistant message that completed the turn.
    message: AssistantMessage
    #: Tool results passed to the preceding ``turn_end`` event.
    tool_results: list[ToolResultMessage]
    #: Context *after* the turn's message and results were appended.
    context: AgentContext
    #: Messages this loop invocation returns if it exits here. Prompt runs
    #: include the initial prompt messages; continuation runs do not include
    #: pre-existing context messages.
    new_messages: list[AgentMessage]


#: Parity: ``PrepareNextTurnContext extends ShouldStopAfterTurnContext`` —
#: an empty extension, so an alias rather than a subclass.
PrepareNextTurnContext: TypeAlias = ShouldStopAfterTurnContext


@dataclass(frozen=True)
class AgentLoopTurnUpdate:
    """Replacement runtime state for the next provider request.

    Parity: ``AgentLoopTurnUpdate``. Returning ``None`` from
    ``prepare_next_turn`` keeps the current state; returning this with only
    some fields set replaces only those.
    """

    context: AgentContext | None = None
    model: Model | None = None
    thinking_level: ThinkingLevel | None = None


# ─────────────────────────────────────────────────────────────────────
# Loop configuration
# ─────────────────────────────────────────────────────────────────────

#: Parity: ``convertToLlm``. Converts the agent transcript to
#: provider-visible messages before each call. May be sync or async.
#: Messages that cannot be converted (UI-only notifications, status lines)
#: must be filtered out rather than passed through. Must not raise.
ConvertToLlmFn: TypeAlias = Callable[
    [list[AgentMessage]], Union[list[Message], Awaitable[list[Message]]]
]

#: Parity: ``transformContext``. Applied *before* ``convert_to_llm``, at the
#: AgentMessage level — context pruning, injecting external context. Must
#: not raise; return the original list as the fallback.
TransformContextFn: TypeAlias = Callable[
    [list[AgentMessage], Union[AbortSignal, None]], Awaitable[list[AgentMessage]]
]

#: Parity: ``getApiKey``. Resolves a key per call so short-lived OAuth
#: tokens can be refreshed during long tool phases. Must not raise; return
#: ``None`` when no key is available.
GetApiKeyFn: TypeAlias = Callable[[str], Union[str, None, Awaitable[Union[str, None]]]]

#: Parity: ``shouldStopAfterTurn``. Must not raise.
ShouldStopAfterTurnFn: TypeAlias = Callable[
    [ShouldStopAfterTurnContext], Union[bool, Awaitable[bool]]
]

#: Parity: ``prepareNextTurn``. Must not raise.
PrepareNextTurnFn: TypeAlias = Callable[
    [PrepareNextTurnContext],
    Union[AgentLoopTurnUpdate, None, Awaitable[Union[AgentLoopTurnUpdate, None]]],
]

#: Parity: ``getSteeringMessages``. Must not raise; return ``[]``.
GetMessagesFn: TypeAlias = Callable[[], Awaitable[list[AgentMessage]]]

#: Parity: ``beforeToolCall``. Receives the abort signal and is responsible
#: for honouring it.
BeforeToolCallFn: TypeAlias = Callable[
    [BeforeToolCallContext, Union[AbortSignal, None]],
    Awaitable[Union[BeforeToolCallResult, None]],
]

#: Parity: ``resolveDeferredTool``. Unlike the other hooks this one *may*
#: raise: a thrown failure becomes an error tool result for the requested
#: call. Return ``None`` for names it does not handle so the loop keeps its
#: normal "Tool <name> not found" result.
ResolveDeferredToolFn: TypeAlias = Callable[
    [DeferredToolCallContext, Union[AbortSignal, None]],
    Union[AgentTool, None, Awaitable[Union[AgentTool, None]]],
]

#: Parity: ``afterToolCall``. Receives the abort signal and is responsible
#: for honouring it.
AfterToolCallFn: TypeAlias = Callable[
    [AfterToolCallContext, Union[AbortSignal, None]],
    Awaitable[Union[AfterToolCallResult, None]],
]


@dataclass(frozen=True)
class AgentLoopConfig:
    """Configuration for one run of the low-level loop.

    Parity: ``AgentLoopConfig extends SimpleStreamOptions``. Python
    dataclasses cannot cleanly inherit the optional-field ordering of
    ``SimpleStreamOptions``, so the stream options are held in a
    :attr:`stream_options` field instead of flattened. That is the one
    structural divergence in this file, and it is visible at every call
    site rather than silent.

    ``model`` and ``convert_to_llm`` are the only required fields, matching
    the TS.
    """

    #: Model for the request. Parity: ``model``.
    model: Model
    #: Parity: ``convertToLlm``. Required.
    convert_to_llm: ConvertToLlmFn

    #: Provider request options. Parity: the ``extends SimpleStreamOptions``
    #: base. See the class docstring for why this is nested.
    stream_options: SimpleStreamOptions | None = None

    #: Logical level retained across model changes, before provider mapping.
    #: Parity: ``thinkingLevel``.
    thinking_level: ThinkingLevel | None = None

    #: Parity: ``transformContext``.
    transform_context: TransformContextFn | None = None
    #: Parity: ``getApiKey``.
    get_api_key: GetApiKeyFn | None = None
    #: Parity: ``shouldStopAfterTurn``.
    should_stop_after_turn: ShouldStopAfterTurnFn | None = None
    #: Parity: ``prepareNextTurn``.
    prepare_next_turn: PrepareNextTurnFn | None = None
    #: Parity: ``getSteeringMessages`` — injected mid-run, after the current
    #: turn's tool calls finish. Does not skip pending tool calls.
    get_steering_messages: GetMessagesFn | None = None
    #: Parity: ``getFollowUpMessages`` — consulted only when there are no
    #: tool calls and no steering messages left.
    get_follow_up_messages: GetMessagesFn | None = None
    #: Parity: ``toolExecution``. Default is ``"parallel"``; ``None`` here
    #: means "unset", and the loop applies the default.
    tool_execution: ToolExecutionMode | None = None
    #: Parity: ``beforeToolCall``.
    before_tool_call: BeforeToolCallFn | None = None
    #: Parity: ``resolveDeferredTool``.
    resolve_deferred_tool: ResolveDeferredToolFn | None = None
    #: Parity: ``afterToolCall``.
    after_tool_call: AfterToolCallFn | None = None


#: Parity: the documented default for ``toolExecution``. Named rather than
#: inlined so the loop and the tests cannot disagree about it.
DEFAULT_TOOL_EXECUTION: ToolExecutionMode = "parallel"


# ─────────────────────────────────────────────────────────────────────
# Events
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentEventAgentStart:
    """Parity: ``{ type: "agent_start" }``."""

    type: Literal["agent_start"] = "agent_start"


@dataclass(frozen=True)
class AgentEventAgentEnd:
    """Parity: ``{ type: "agent_end"; messages }``.

    The last event of a run — but the run is not settled until awaited
    ``agent_end`` listeners finish. ``AgentState.is_streaming`` stays true
    until then.
    """

    messages: list[AgentMessage]
    type: Literal["agent_end"] = "agent_end"


@dataclass(frozen=True)
class AgentEventTurnStart:
    """Parity: ``{ type: "turn_start" }``."""

    type: Literal["turn_start"] = "turn_start"


@dataclass(frozen=True)
class AgentEventTurnEnd:
    """Parity: ``{ type: "turn_end"; message; toolResults }``.

    A turn is one assistant response plus any tool calls and results.
    """

    message: AgentMessage
    tool_results: list[ToolResultMessage]
    type: Literal["turn_end"] = "turn_end"


@dataclass(frozen=True)
class AgentEventMessageStart:
    """Parity: ``{ type: "message_start"; message }``.

    Emitted for user, assistant and toolResult messages.
    """

    message: AgentMessage
    type: Literal["message_start"] = "message_start"


@dataclass(frozen=True)
class AgentEventMessageUpdate:
    """Parity: ``{ type: "message_update"; message; assistantMessageEvent }``.

    Only emitted for assistant messages, during streaming.
    """

    message: AgentMessage
    assistant_message_event: AssistantMessageEvent
    type: Literal["message_update"] = "message_update"


@dataclass(frozen=True)
class AgentEventMessageEnd:
    """Parity: ``{ type: "message_end"; message }``."""

    message: AgentMessage
    type: Literal["message_end"] = "message_end"


@dataclass(frozen=True)
class AgentEventToolExecutionStart:
    """Parity: ``{ type: "tool_execution_start"; ... }``."""

    tool_call_id: str
    tool_name: str
    args: Any
    hide_from_channel_progress: bool | None = None
    type: Literal["tool_execution_start"] = "tool_execution_start"


@dataclass(frozen=True)
class AgentEventToolExecutionUpdate:
    """Parity: ``{ type: "tool_execution_update"; ... }``."""

    tool_call_id: str
    tool_name: str
    args: Any
    partial_result: Any
    hide_from_channel_progress: bool | None = None
    type: Literal["tool_execution_update"] = "tool_execution_update"


@dataclass(frozen=True)
class AgentEventToolExecutionEnd:
    """Parity: ``{ type: "tool_execution_end"; ... }``.

    In ``"parallel"`` mode these fire in tool *completion* order, while the
    tool-result message artifacts are emitted later in assistant *source*
    order.
    """

    tool_call_id: str
    tool_name: str
    result: Any
    is_error: bool
    #: False when resolution, argument preparation, validation, or policy
    #: blocked execution — i.e. the tool never ran.
    execution_started: bool | None = None
    #: Typed pre-execution failure provenance for safe diagnostics.
    error_kind: Literal["argument-validation"] | None = None
    hide_from_channel_progress: bool | None = None
    type: Literal["tool_execution_end"] = "tool_execution_end"


#: Parity: ``AgentEvent`` — the 11-variant discriminated union emitted for
#: UI updates.
AgentEvent: TypeAlias = Union[
    AgentEventAgentStart,
    AgentEventAgentEnd,
    AgentEventTurnStart,
    AgentEventTurnEnd,
    AgentEventMessageStart,
    AgentEventMessageUpdate,
    AgentEventMessageEnd,
    AgentEventToolExecutionStart,
    AgentEventToolExecutionUpdate,
    AgentEventToolExecutionEnd,
]

#: Every ``AgentEvent.type`` value, in the order the union declares them.
#: Not in the TS as a value; needed here so dispatchers and tests can
#: enumerate the variants without duplicating the list.
AGENT_EVENT_TYPES: tuple[str, ...] = (
    "agent_start",
    "agent_end",
    "turn_start",
    "turn_end",
    "message_start",
    "message_update",
    "message_end",
    "tool_execution_start",
    "tool_execution_update",
    "tool_execution_end",
)


def _unused_type_imports() -> tuple[object, ...]:
    """Keep re-exported type-only imports reachable for linters."""
    return (Tool, Sequence)


__all__ = [
    "AGENT_EVENT_TYPES",
    "DEFAULT_TOOL_EXECUTION",
    "UNSET",
    "AfterToolCallContext",
    "AfterToolCallFn",
    "AfterToolCallResult",
    "AgentContext",
    "AgentEvent",
    "AgentEventAgentEnd",
    "AgentEventAgentStart",
    "AgentEventMessageEnd",
    "AgentEventMessageStart",
    "AgentEventMessageUpdate",
    "AgentEventToolExecutionEnd",
    "AgentEventToolExecutionStart",
    "AgentEventToolExecutionUpdate",
    "AgentEventTurnEnd",
    "AgentEventTurnStart",
    "AgentLoopConfig",
    "AgentLoopTurnUpdate",
    "AgentMessage",
    "AgentState",
    "AgentTool",
    "AgentToolCall",
    "AgentToolProgress",
    "AgentToolResult",
    "AgentToolUpdateCallback",
    "BashExecutionMessage",
    "BeforeToolCallContext",
    "BeforeToolCallFn",
    "BeforeToolCallResult",
    "BranchSummaryMessage",
    "CompactionSummaryMessage",
    "ConvertToLlmFn",
    "CustomAgentMessage",
    "CustomMessage",
    "DeferredToolCallContext",
    "GetApiKeyFn",
    "GetMessagesFn",
    "PrepareNextTurnContext",
    "PrepareNextTurnFn",
    "QueueMode",
    "ResolveDeferredToolFn",
    "ShouldStopAfterTurnContext",
    "ShouldStopAfterTurnFn",
    "StreamFn",
    "ThinkingLevel",
    "ToolExecutionMode",
    "TransformContextFn",
]
