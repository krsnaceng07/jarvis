"""The stateful ``Agent`` wrapper over the low-level agent loop.

Port of ``packages/agent-core/src/agent.ts``.

``Agent`` owns the current transcript, emits lifecycle events, executes
tools, and exposes queueing APIs for steering and follow-up messages.

Python adaptations, all mechanical:

- ``Agent.continue()`` becomes :meth:`Agent.continue_` — ``continue`` is a
  Python keyword.
- ``AgentOptions`` is a frozen dataclass rather than a structural
  interface; the constructor takes it as a single argument, matching the
  TS call shape ``new Agent({...})``.
- ``initialState`` (a ``Partial<AgentState>`` in TS) is the
  :class:`AgentInitialState` dataclass, every field optional.
- The active run's settlement promise is an :class:`asyncio.Future`;
  ``AbortController``/``AbortSignal`` come from :mod:`jarvis_llm.abort`.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from jarvis_llm import (
    ImageContent,
    Message,
    Model,
    ModelCost,
    TextContent,
    UserMessage,
)
from jarvis_llm.abort import AbortController, AbortSignal
from jarvis_llm.stream import SimpleStreamOptions
from jarvis_llm.types import ThinkingBudgets, Transport, now_ms

from .agent_loop import run_agent_loop, run_agent_loop_continue
from .errors import TranscriptNotContinuableError
from .reasoning import resolve_agent_reasoning_option
from .runtime_deps import AgentCoreStreamRuntimeDeps, resolve_agent_core_stream_fn
from .turn_interruption import (
    append_interrupted_turn_message,
    create_failure_message,
    is_turn_handoff_abort,
)
from .types import (
    AfterToolCallFn,
    AgentContext,
    AgentEvent,
    AgentEventAgentEnd,
    AgentEventMessageEnd,
    AgentEventMessageStart,
    AgentEventTurnEnd,
    AgentLoopConfig,
    AgentLoopTurnUpdate,
    AgentMessage,
    AgentTool,
    BeforeToolCallFn,
    PrepareNextTurnContext,
    QueueMode,
    ResolveDeferredToolFn,
    StreamFn,
    ThinkingLevel,
    ToolExecutionMode,
)

__all__ = [
    "Agent",
    "AgentInitialState",
    "AgentOptions",
    "QueueMode",
]


async def _settle(value: object) -> Any:
    """Await ``value`` when awaitable, else return it — ``T | Promise<T>``."""
    if inspect.isawaitable(value):
        return await value
    return value


def default_convert_to_llm(messages: list[AgentMessage]) -> list[Message]:
    """Parity: ``defaultConvertToLlm`` — keep only provider-facing roles."""
    return [
        message
        for message in messages
        if message.role in ("user", "assistant", "toolResult")
    ]


#: Parity: ``DEFAULT_MODEL`` — placeholder until the host assigns a model.
DEFAULT_MODEL = Model(
    id="unknown",
    name="unknown",
    api="unknown",
    provider="unknown",
    base_url="",
    reasoning=False,
    input=(),
    cost=ModelCost(input=0, output=0, cache_read=0, cache_write=0),
    context_window=0,
    max_tokens=0,
)


@dataclass(frozen=True)
class AgentInitialState:
    """Initial transcript, tools, model, and prompt state.

    Parity: the ``Partial<Omit<AgentState, ...runtime fields>>`` accepted
    as ``AgentOptions.initialState``.
    """

    system_prompt: str | None = None
    model: Model | None = None
    thinking_level: ThinkingLevel | None = None
    tools: list[AgentTool] | None = None
    messages: list[AgentMessage] | None = None


class _MutableAgentState:
    """Parity: ``MutableAgentState`` from ``createMutableAgentState``.

    ``tools`` and ``messages`` are accessor pairs whose setters *copy* the
    assigned top-level list; the getters return the live internal list, so
    in-place event reduction (``messages.push``) is visible through
    ``agent.state`` exactly as in the TS.
    """

    def __init__(self, initial_state: AgentInitialState | None = None) -> None:
        initial = initial_state or AgentInitialState()
        self.system_prompt: str = initial.system_prompt or ""
        self.model: Model = initial.model or DEFAULT_MODEL
        self.thinking_level: ThinkingLevel = initial.thinking_level or "off"
        self._tools: list[AgentTool] = list(initial.tools or [])
        self._messages: list[AgentMessage] = list(initial.messages or [])
        self.is_streaming: bool = False
        self.streaming_message: AgentMessage | None = None
        self.pending_tool_calls: set[str] = set()
        self.error_message: str | None = None

    @property
    def tools(self) -> list[AgentTool]:
        return self._tools

    @tools.setter
    def tools(self, next_tools: list[AgentTool]) -> None:
        self._tools = list(next_tools)

    @property
    def messages(self) -> list[AgentMessage]:
        return self._messages

    @messages.setter
    def messages(self, next_messages: list[AgentMessage]) -> None:
        self._messages = list(next_messages)


@dataclass(frozen=True)
class AgentOptions:
    """Options for constructing an :class:`Agent`. Parity: ``AgentOptions``."""

    #: Initial transcript, tools, model, and prompt state.
    initial_state: AgentInitialState | None = None
    #: Convert agent-owned transcript messages into provider-facing messages.
    convert_to_llm: Callable[[list[AgentMessage]], Any] | None = None
    #: Optionally rewrite context before each provider request.
    transform_context: Callable[..., Any] | None = None
    #: Injected stream runtime used when ``stream_fn`` is not supplied.
    runtime: AgentCoreStreamRuntimeDeps | None = None
    #: Explicit stream implementation, preferred over ``runtime.stream_simple``.
    stream_fn: StreamFn | None = None
    #: Resolve provider API keys at request time.
    get_api_key: Callable[[str], Any] | None = None
    #: Inspect the provider payload before it is sent.
    on_payload: Any | None = None
    #: Inspect the provider response after it returns.
    on_response: Any | None = None
    #: Hook that may short-circuit or alter a tool call before execution.
    before_tool_call: BeforeToolCallFn | None = None
    #: Hook that may hydrate a deferred authorized tool call.
    resolve_deferred_tool: ResolveDeferredToolFn | None = None
    #: Hook that may alter a tool result after execution.
    after_tool_call: AfterToolCallFn | None = None
    #: Hook that may update model, reasoning, or context after a turn.
    prepare_next_turn: Callable[..., Any] | None = None
    #: Context-aware turn hook. Takes precedence over ``prepare_next_turn``.
    prepare_next_turn_with_context: Callable[..., Any] | None = None
    #: Queue drain mode for steering messages.
    steering_mode: QueueMode | None = None
    #: Queue drain mode for follow-up messages.
    follow_up_mode: QueueMode | None = None
    #: Session identifier forwarded to cache-aware providers.
    session_id: str | None = None
    #: Optional per-thinking-level token budgets forwarded to providers.
    thinking_budgets: ThinkingBudgets | None = None
    #: Preferred provider transport.
    transport: Transport | None = None
    #: Optional cap for provider-requested retry delays.
    max_retry_delay_ms: int | None = None
    #: Default strategy for executing multiple tool calls in one message.
    tool_execution: ToolExecutionMode | None = None


class _PendingMessageQueue:
    """Parity: ``PendingMessageQueue``."""

    def __init__(self, mode: QueueMode) -> None:
        self._messages: list[AgentMessage] = []
        self.mode: QueueMode = mode

    def enqueue(self, message: AgentMessage) -> None:
        self._messages.append(message)

    def has_items(self) -> bool:
        return len(self._messages) > 0

    def drain(self) -> list[AgentMessage]:
        if self.mode == "all":
            drained = self._messages[:]
            self._messages = []
            return drained

        # one-at-a-time preserves later queued messages for subsequent
        # loop turns.
        if not self._messages:
            return []
        first = self._messages[0]
        self._messages = self._messages[1:]
        return [first]

    def clear(self) -> None:
        self._messages = []


class _ActiveRun:
    """Parity: ``ActiveRun`` — settlement future plus abort controller."""

    def __init__(self) -> None:
        self.future: asyncio.Future[None] = (
            asyncio.get_running_loop().create_future()
        )
        self.abort_controller = AbortController()

    def resolve(self) -> None:
        if not self.future.done():
            self.future.set_result(None)


class Agent:
    """Stateful wrapper around the low-level agent loop.

    Parity: ``class Agent``. ``Agent`` owns the current transcript, emits
    lifecycle events, executes tools, and exposes queueing APIs for
    steering and follow-up messages.
    """

    def __init__(self, options: AgentOptions | None = None) -> None:
        options = options or AgentOptions()
        self._mutable_state = _MutableAgentState(options.initial_state)
        self._listeners: list[
            Callable[[AgentEvent, AbortSignal], Any]
        ] = []
        self.convert_to_llm = options.convert_to_llm or default_convert_to_llm
        self.transform_context = options.transform_context
        self.runtime = options.runtime
        self.stream_fn: StreamFn = resolve_agent_core_stream_fn(
            options.runtime, options.stream_fn
        )
        self.get_api_key = options.get_api_key
        self.on_payload = options.on_payload
        self.on_response = options.on_response
        self.before_tool_call = options.before_tool_call
        self.resolve_deferred_tool = options.resolve_deferred_tool
        self.after_tool_call = options.after_tool_call
        self.prepare_next_turn = options.prepare_next_turn
        self.prepare_next_turn_with_context = options.prepare_next_turn_with_context
        self._steering_queue = _PendingMessageQueue(
            options.steering_mode or "one-at-a-time"
        )
        self._follow_up_queue = _PendingMessageQueue(
            options.follow_up_mode or "one-at-a-time"
        )
        self._active_run: _ActiveRun | None = None
        #: Session identifier forwarded to providers for cache-aware backends.
        self.session_id = options.session_id
        #: Optional per-level thinking token budgets forwarded to providers.
        self.thinking_budgets = options.thinking_budgets
        #: Preferred transport forwarded to the stream function.
        self.transport: Transport = options.transport or "auto"
        #: Optional cap for provider-requested retry delays.
        self.max_retry_delay_ms = options.max_retry_delay_ms
        #: Tool execution strategy for multi-tool-call assistant messages.
        self.tool_execution: ToolExecutionMode = options.tool_execution or "parallel"

    def subscribe(
        self, listener: Callable[[AgentEvent, AbortSignal], Any]
    ) -> Callable[[], None]:
        """Subscribe to agent lifecycle events.

        Listener return values are awaited in subscription order and are
        included in the current run's settlement. Listeners also receive
        the active abort signal for the current run.

        ``agent_end`` is the final emitted event for a run, but the agent
        does not become idle until all awaited listeners for that event
        have settled.
        """
        if listener not in self._listeners:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    @property
    def state(self) -> _MutableAgentState:
        """Current agent state.

        Assigning ``state.tools`` or ``state.messages`` copies the
        provided top-level list.
        """
        return self._mutable_state

    @property
    def steering_mode(self) -> QueueMode:
        """Controls how queued steering messages are drained."""
        return self._steering_queue.mode

    @steering_mode.setter
    def steering_mode(self, mode: QueueMode) -> None:
        self._steering_queue.mode = mode

    @property
    def follow_up_mode(self) -> QueueMode:
        """Controls how queued follow-up messages are drained."""
        return self._follow_up_queue.mode

    @follow_up_mode.setter
    def follow_up_mode(self, mode: QueueMode) -> None:
        self._follow_up_queue.mode = mode

    def steer(self, message: AgentMessage) -> None:
        """Queue a message injected after the current assistant turn."""
        self._steering_queue.enqueue(message)

    def follow_up(self, message: AgentMessage) -> None:
        """Queue a message to run only after the agent would otherwise stop."""
        self._follow_up_queue.enqueue(message)

    def clear_steering_queue(self) -> None:
        """Remove all queued steering messages."""
        self._steering_queue.clear()

    def clear_follow_up_queue(self) -> None:
        """Remove all queued follow-up messages."""
        self._follow_up_queue.clear()

    def clear_all_queues(self) -> None:
        """Remove all queued steering and follow-up messages."""
        self.clear_steering_queue()
        self.clear_follow_up_queue()

    def has_queued_messages(self) -> bool:
        """True when either queue still contains pending messages."""
        return self._steering_queue.has_items() or self._follow_up_queue.has_items()

    @property
    def signal(self) -> AbortSignal | None:
        """Active abort signal for the current run, if any."""
        if self._active_run is None:
            return None
        return self._active_run.abort_controller.signal

    def abort(self, reason: object = None) -> None:
        """Abort the current run, if one is active."""
        if self._active_run is not None:
            self._active_run.abort_controller.abort(reason)  # type: ignore[arg-type]

    async def wait_for_idle(self) -> None:
        """Resolve when the run and all awaited event listeners finish.

        Parity: ``waitForIdle`` — resolves after ``agent_end`` listeners
        settle.
        """
        if self._active_run is not None:
            await asyncio.shield(self._active_run.future)

    def reset(self) -> None:
        """Clear transcript state, runtime state, and queued messages."""
        self._mutable_state.messages = []
        self._mutable_state.is_streaming = False
        self._mutable_state.streaming_message = None
        self._mutable_state.pending_tool_calls = set()
        self._mutable_state.error_message = None
        self.clear_follow_up_queue()
        self.clear_steering_queue()

    async def prompt(
        self,
        input: Union[str, AgentMessage, list[AgentMessage]],
        images: Optional[list[ImageContent]] = None,
    ) -> None:
        """Start a new prompt from text, one message, or a message batch."""
        if self._active_run is not None:
            raise RuntimeError(
                "Agent is already processing a prompt. Use steer() or "
                "followUp() to queue messages, or wait for completion."
            )
        messages = self._normalize_prompt_input(input, images)
        await self._run_prompt_messages(messages)

    async def continue_(self) -> None:
        """Continue from the current transcript.

        Parity: ``Agent.continue`` (renamed — ``continue`` is a Python
        keyword). The last message must be a user or tool-result message.
        """
        if self._active_run is not None:
            raise RuntimeError(
                "Agent is already processing. Wait for completion before continuing."
            )

        messages = self._mutable_state.messages
        last_message = messages[-1] if messages else None
        if last_message is None:
            raise RuntimeError("No messages to continue from")

        if last_message.role in ("assistant", "toolResult"):
            queued_steering = self._steering_queue.drain()
            if queued_steering:
                await self._run_prompt_messages(
                    queued_steering, skip_initial_steering_poll=True
                )
                return

            queued_follow_ups = self._follow_up_queue.drain()
            if queued_follow_ups:
                await self._run_prompt_messages(queued_follow_ups)
                return

        if last_message.role == "assistant":
            raise TranscriptNotContinuableError(last_message.role)

        await self._run_continuation()

    def _normalize_prompt_input(
        self,
        input: Union[str, AgentMessage, list[AgentMessage]],
        images: Optional[list[ImageContent]],
    ) -> list[AgentMessage]:
        """Parity: ``normalizePromptInput``."""
        if isinstance(input, list):
            return input

        if not isinstance(input, str):
            return [input]

        content: list[Union[TextContent, ImageContent]] = [TextContent(text=input)]
        if images:
            content.extend(images)
        return [UserMessage(content=content, timestamp=now_ms())]

    async def _run_prompt_messages(
        self,
        messages: list[AgentMessage],
        *,
        skip_initial_steering_poll: bool = False,
    ) -> None:
        """Parity: ``runPromptMessages``."""

        async def executor(signal: AbortSignal) -> None:
            await run_agent_loop(
                messages,
                self._create_context_snapshot(),
                self._create_loop_config(
                    skip_initial_steering_poll=skip_initial_steering_poll
                ),
                self._process_events,
                signal,
                self.stream_fn,
            )

        await self._run_with_lifecycle(executor)

    async def _run_continuation(self) -> None:
        """Parity: ``runContinuation``."""

        async def executor(signal: AbortSignal) -> None:
            await run_agent_loop_continue(
                self._create_context_snapshot(),
                self._create_loop_config(),
                self._process_events,
                signal,
                self.stream_fn,
            )

        await self._run_with_lifecycle(executor)

    def _create_context_snapshot(self) -> AgentContext:
        """Parity: ``createContextSnapshot``."""
        return AgentContext(
            system_prompt=self._mutable_state.system_prompt,
            messages=self._mutable_state.messages[:],
            tools=self._mutable_state.tools[:],
        )

    def _create_loop_config(
        self, *, skip_initial_steering_poll: bool = False
    ) -> AgentLoopConfig:
        """Parity: ``createLoopConfig``.

        The TS spreads ``sessionId``/``onPayload``/``onResponse``/
        ``transport``/``thinkingBudgets``/``maxRetryDelayMs``/``reasoning``
        onto the config because ``AgentLoopConfig extends
        SimpleStreamOptions``; the Python config nests them in
        ``stream_options`` instead (see :class:`AgentLoopConfig`).
        """
        skip_poll = {"value": skip_initial_steering_poll}

        prepare_next_turn: Optional[
            Callable[[PrepareNextTurnContext], Any]
        ] = None
        if self.prepare_next_turn_with_context or self.prepare_next_turn:

            async def prepare_next_turn(
                context: PrepareNextTurnContext,
            ) -> AgentLoopTurnUpdate | None:
                if self.prepare_next_turn_with_context is not None:
                    return await _settle(
                        self.prepare_next_turn_with_context(context, self.signal)
                    )
                if self.prepare_next_turn is not None:
                    return await _settle(self.prepare_next_turn(self.signal))
                return None

        async def get_steering_messages() -> list[AgentMessage]:
            if skip_poll["value"]:
                skip_poll["value"] = False
                return []
            return self._steering_queue.drain()

        async def get_follow_up_messages() -> list[AgentMessage]:
            return self._follow_up_queue.drain()

        return AgentLoopConfig(
            model=self._mutable_state.model,
            convert_to_llm=self.convert_to_llm,
            thinking_level=self._mutable_state.thinking_level,
            stream_options=SimpleStreamOptions(
                reasoning=resolve_agent_reasoning_option(
                    self._mutable_state.model,
                    self._mutable_state.thinking_level,
                ),
                session_id=self.session_id,
                on_payload=self.on_payload,
                on_response=self.on_response,
                transport=self.transport,
                thinking_budgets=self.thinking_budgets,
                max_retry_delay_ms=self.max_retry_delay_ms,
            ),
            tool_execution=self.tool_execution,
            before_tool_call=self.before_tool_call,
            resolve_deferred_tool=self.resolve_deferred_tool,
            after_tool_call=self.after_tool_call,
            prepare_next_turn=prepare_next_turn,
            transform_context=self.transform_context,
            get_api_key=self.get_api_key,
            get_steering_messages=get_steering_messages,
            get_follow_up_messages=get_follow_up_messages,
        )

    async def _run_with_lifecycle(
        self, executor: Callable[[AbortSignal], Any]
    ) -> None:
        """Parity: ``runWithLifecycle``."""
        if self._active_run is not None:
            raise RuntimeError("Agent is already processing.")

        active_run = _ActiveRun()
        self._active_run = active_run

        self._mutable_state.is_streaming = True
        self._mutable_state.streaming_message = None
        self._mutable_state.error_message = None

        try:
            await executor(active_run.abort_controller.signal)
        except Exception as error:  # noqa: BLE001 - parity: catch (error)
            await self._handle_run_failure(
                error, active_run.abort_controller.signal.aborted
            )
        finally:
            self._finish_run()

    async def _handle_run_failure(self, error: object, aborted: bool) -> None:
        """Parity: ``handleRunFailure``."""
        failure_message = create_failure_message(
            self._mutable_state.model, error, aborted
        )
        await self._process_events(
            AgentEventMessageStart(message=failure_message)
        )
        await self._process_events(AgentEventMessageEnd(message=failure_message))
        await self._process_events(
            AgentEventTurnEnd(message=failure_message, tool_results=[])
        )
        messages: list[AgentMessage] = [failure_message]
        if aborted and not is_turn_handoff_abort(self.signal):
            await append_interrupted_turn_message(messages, self._process_events)
        await self._process_events(AgentEventAgentEnd(messages=messages))

    def _finish_run(self) -> None:
        """Parity: ``finishRun``."""
        self._mutable_state.is_streaming = False
        self._mutable_state.streaming_message = None
        self._mutable_state.pending_tool_calls = set()
        active_run = self._active_run
        if active_run is not None:
            active_run.resolve()
        self._active_run = None

    async def _process_events(self, event: AgentEvent) -> None:
        """Reduce internal state for a loop event, then await listeners.

        Parity: ``processEvents``. ``agent_end`` only means no further
        loop events will be emitted. The run is considered idle later,
        after all awaited listeners for ``agent_end`` finish and
        :meth:`_finish_run` clears runtime-owned state.
        """
        event_type = event.type
        if event_type in ("agent_start", "turn_start", "tool_execution_update"):
            pass
        elif event_type == "message_start":
            self._mutable_state.streaming_message = event.message
        elif event_type == "message_update":
            self._mutable_state.streaming_message = event.message
        elif event_type == "message_end":
            self._mutable_state.streaming_message = None
            self._mutable_state.messages.append(event.message)
        elif event_type == "tool_execution_start":
            pending_tool_calls = set(self._mutable_state.pending_tool_calls)
            pending_tool_calls.add(event.tool_call_id)
            self._mutable_state.pending_tool_calls = pending_tool_calls
        elif event_type == "tool_execution_end":
            pending_tool_calls = set(self._mutable_state.pending_tool_calls)
            pending_tool_calls.discard(event.tool_call_id)
            self._mutable_state.pending_tool_calls = pending_tool_calls
        elif event_type == "turn_end":
            if (
                event.message.role == "assistant"
                and event.message.error_message
            ):
                self._mutable_state.error_message = event.message.error_message
        elif event_type == "agent_end":
            self._mutable_state.streaming_message = None

        if self._active_run is None:
            raise RuntimeError("Agent listener invoked outside active run")
        signal = self._active_run.abort_controller.signal
        for listener in list(self._listeners):
            await _settle(listener(event, signal))
