"""jarvis_agent.agent_loop — the core agent loop.

OpenClaw parity: ``packages/agent-core/src/agent-loop.ts`` (1,130 lines).

Public surface matches the TS exports exactly: :data:`AgentEventSink`,
:func:`agent_loop`, :func:`agent_loop_continue`, :func:`run_agent_loop`,
:func:`run_agent_loop_continue`. Everything else is module-private, as in
the source.

Shape of the loop (same as the TS):

- **Outer loop** re-enters when ``get_follow_up_messages`` returns queued
  messages after the agent would otherwise stop.
- **Inner loop** runs while the last assistant turn requested tools or
  steering messages are pending; each iteration streams one assistant
  response and executes its tool calls.
- ``stop_if_aborted`` is checked at every await boundary and synthesizes a
  complete event sequence (failure assistant → ``turn_end`` → optional
  interruption guidance → ``agent_end``) instead of unwinding — see
  :mod:`jarvis_llm.abort` for why abort is polled, never raised.

Event-order contract worth restating: in ``"parallel"`` mode,
``tool_execution_end`` events fire in tool *completion* order, while the
``toolResult`` message artifacts are emitted afterwards in assistant
*source* order. Consumers that zip the two streams will misattribute
results.

Python-specific notes (each marked at its use site):

- ``agent_loop``/``agent_loop_continue`` background the runner with
  ``asyncio.ensure_future`` (TS: ``void run(...).then(...)``), so they must
  be called with an event loop running.
- The tool-resolution cache is keyed by ``id(tool_call)`` because the TS
  ``Map`` keys on object identity and ``ToolCall.arguments`` is an
  unhashable dict. The keying objects outlive the cache (they are held by
  the batch's ``tool_calls`` list), so ids cannot be recycled mid-batch.
- ``AgentContext`` is frozen; the TS ``currentContext.tools = [...]``
  hydration reassignment is performed with ``object.__setattr__`` so every
  holder of the context object observes it, exactly like the TS property
  write.
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
from typing import Any, Awaitable, Callable, TypeAlias, Union

from jarvis_llm.abort import AbortError, AbortSignal, is_aborted
from jarvis_llm.event_stream import EventStream
from jarvis_llm.types import (
    AssistantMessage,
    AssistantMessageEvent,
    Context,
    SimpleStreamOptions,
    TextContent,
    ToolResultMessage,
    now_ms,
)

from .errors import TranscriptNotContinuableError
from .reasoning import resolve_agent_reasoning_option
from .runtime_deps import AgentCoreStreamRuntimeDeps, resolve_agent_core_stream_fn
from .turn_interruption import (
    append_interrupted_turn_message,
    create_failure_message,
    create_interrupted_turn_message,
    is_turn_handoff_abort,
    normalize_core_context_messages,
)
from .types import (
    UNSET,
    AfterToolCallContext,
    AgentContext,
    AgentEvent,
    AgentEventAgentEnd,
    AgentEventAgentStart,
    AgentEventMessageEnd,
    AgentEventMessageStart,
    AgentEventMessageUpdate,
    AgentEventToolExecutionEnd,
    AgentEventToolExecutionStart,
    AgentEventToolExecutionUpdate,
    AgentEventTurnEnd,
    AgentEventTurnStart,
    AgentLoopConfig,
    AgentMessage,
    AgentTool,
    AgentToolCall,
    AgentToolResult,
    BeforeToolCallContext,
    DeferredToolCallContext,
    ShouldStopAfterTurnContext,
    StreamFn,
)
from .validation import validate_tool_arguments

#: Callback used by synchronous loop runners to publish agent lifecycle
#: events. Parity: ``AgentEventSink = (event) => Promise<void> | void``.
AgentEventSink: TypeAlias = Callable[[AgentEvent], Union[Awaitable[None], None]]

#: Parity: the ``AssistantMessageUpdateEvent`` Extract — the nine streaming
#: event types that update the in-flight assistant message.
_UPDATE_EVENT_TYPES = frozenset(
    (
        "text_start",
        "text_delta",
        "text_end",
        "thinking_start",
        "thinking_delta",
        "thinking_end",
        "toolcall_start",
        "toolcall_delta",
        "toolcall_end",
    )
)


async def _settle(value: object) -> Any:
    """Await a value that may or may not be awaitable.

    The hook aliases in :mod:`jarvis_agent.types` allow sync or async
    implementations (TS: ``T | Promise<T>``); this is the single place that
    normalizes them.
    """
    if inspect.isawaitable(value):
        return await value
    return value


async def _emit(emit: AgentEventSink, event: AgentEvent) -> None:
    """Deliver one event, settling ``Promise<void> | void`` sinks."""
    result = emit(event)
    if inspect.isawaitable(result):
        await result


def _append_text_delta_to_assistant_message(
    message: AssistantMessage,
    content_index: int,
    delta: str,
) -> AssistantMessage:
    """Parity: ``appendTextDeltaToAssistantMessage``."""
    content = list(message.content)
    current = content[content_index] if 0 <= content_index < len(content) else None
    if current is not None and current.type == "text":
        block = dataclasses.replace(current, text=current.text + delta)
    else:
        block = TextContent(text=delta)
    if content_index < len(content):
        content[content_index] = block
    else:
        # JS auto-extends sparse arrays on indexed write; deltas are emitted
        # contiguously in practice, so an append is the dense equivalent.
        content.append(block)
    return dataclasses.replace(message, content=content)


def _resolve_assistant_message_update(
    event: AssistantMessageEvent,
    current_message: AssistantMessage,
) -> AssistantMessage:
    """Parity: ``resolveAssistantMessageUpdate`` — prefer the provider's
    ``partial`` snapshot, else rebuild text deltas locally."""
    partial = getattr(event, "partial", None)
    if partial:
        return partial
    if event.type == "text_delta":
        return _append_text_delta_to_assistant_message(
            current_message, event.content_index, event.delta
        )
    return current_message


def _remove_non_executable_tool_calls(message: AssistantMessage) -> AssistantMessage:
    """Parity: ``removeNonExecutableToolCalls``.

    Only ``stop_reason == "toolUse"`` turns dispatch tools; ``length`` or
    ``stop`` responses can still carry partial toolCall blocks from an
    interrupted stream, and leaving them in would strand unanswered calls
    in the transcript.
    """
    if message.stop_reason == "toolUse":
        return message
    content = [item for item in message.content if item.type != "toolCall"]
    if len(content) == len(message.content):
        return message
    return dataclasses.replace(message, content=content)


def agent_loop(
    prompts: list[AgentMessage],
    context: AgentContext,
    config: AgentLoopConfig,
    signal: AbortSignal | None = None,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreStreamRuntimeDeps | None = None,
) -> EventStream[AgentEvent, list[AgentMessage]]:
    """Start an agent loop with a new prompt message.

    The prompt is added to the context and events are emitted for it.
    Parity: ``agentLoop``. Must be called with an event loop running: the
    runner is backgrounded (TS ``void runAgentLoop(...).then/catch``) as an
    asyncio task feeding the returned stream.
    """
    stream = _create_agent_stream()

    async def _drive() -> None:
        try:
            messages = await run_agent_loop(
                prompts, context, config, stream.push, signal, stream_fn, runtime
            )
        except Exception as error:  # noqa: BLE001 - parity: .catch(pushLoopFailure)
            _push_loop_failure(stream, config, error, signal)
        else:
            stream.end(messages)

    asyncio.ensure_future(_drive())
    return stream


def agent_loop_continue(
    context: AgentContext,
    config: AgentLoopConfig,
    signal: AbortSignal | None = None,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreStreamRuntimeDeps | None = None,
) -> EventStream[AgentEvent, list[AgentMessage]]:
    """Continue an agent loop from the current context without adding a new
    message. Used for retries — context already has user message or tool
    results. Parity: ``agentLoopContinue``.

    **Important:** the last message in context must convert to a ``user``
    or ``toolResult`` message via ``convert_to_llm``. If it doesn't, the
    LLM provider will reject the request. This cannot be validated here
    since ``convert_to_llm`` is only called once per turn.
    """
    last_message = context.messages[-1] if context.messages else None
    if last_message is None:
        raise RuntimeError("Cannot continue: no messages in context")

    if last_message.role == "assistant":
        raise TranscriptNotContinuableError(last_message.role)

    stream = _create_agent_stream()

    async def _drive() -> None:
        try:
            messages = await run_agent_loop_continue(
                context, config, stream.push, signal, stream_fn, runtime
            )
        except Exception as error:  # noqa: BLE001 - parity: .catch(pushLoopFailure)
            _push_loop_failure(stream, config, error, signal)
        else:
            stream.end(messages)

    asyncio.ensure_future(_drive())
    return stream


async def run_agent_loop(
    prompts: list[AgentMessage],
    context: AgentContext,
    config: AgentLoopConfig,
    emit: AgentEventSink,
    signal: AbortSignal | None = None,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreStreamRuntimeDeps | None = None,
) -> list[AgentMessage]:
    """Run a prompt-started loop and emit events through a caller-owned
    sink. Parity: ``runAgentLoop``."""
    new_messages: list[AgentMessage] = [*prompts]
    current_context = dataclasses.replace(
        context, messages=[*context.messages, *prompts]
    )

    await _emit(emit, AgentEventAgentStart())
    await _emit(emit, AgentEventTurnStart())
    for prompt in prompts:
        await _emit(emit, AgentEventMessageStart(message=prompt))
        await _emit(emit, AgentEventMessageEnd(message=prompt))

    await _run_loop(current_context, new_messages, config, signal, emit, stream_fn, runtime)
    return new_messages


async def run_agent_loop_continue(
    context: AgentContext,
    config: AgentLoopConfig,
    emit: AgentEventSink,
    signal: AbortSignal | None = None,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreStreamRuntimeDeps | None = None,
) -> list[AgentMessage]:
    """Continue an existing loop context and emit only newly produced
    messages. Parity: ``runAgentLoopContinue``."""
    last_message = context.messages[-1] if context.messages else None
    if last_message is None:
        raise RuntimeError("Cannot continue: no messages in context")

    if last_message.role == "assistant":
        raise TranscriptNotContinuableError(last_message.role)

    new_messages: list[AgentMessage] = []
    # TS `{ ...context }` — a shallow copy sharing the messages list, so
    # continuation pushes are visible to the caller's context object.
    current_context = dataclasses.replace(context)

    await _emit(emit, AgentEventAgentStart())
    await _emit(emit, AgentEventTurnStart())

    await _run_loop(current_context, new_messages, config, signal, emit, stream_fn, runtime)
    return new_messages


def _create_agent_stream() -> EventStream[AgentEvent, list[AgentMessage]]:
    """Parity: ``createAgentStream``."""
    return EventStream(
        lambda event: event.type == "agent_end",
        lambda event: event.messages if event.type == "agent_end" else [],
    )


def _push_loop_failure(
    stream: EventStream[AgentEvent, list[AgentMessage]],
    config: AgentLoopConfig,
    error: object,
    signal: AbortSignal | None,
) -> None:
    """Parity: ``pushLoopFailure`` — synthesize a full terminal event
    sequence when the backgrounded runner itself throws."""
    aborted = is_aborted(signal)
    failure_message = create_failure_message(config.model, error, aborted)
    stream.push(AgentEventMessageStart(message=failure_message))
    stream.push(AgentEventMessageEnd(message=failure_message))
    stream.push(AgentEventTurnEnd(message=failure_message, tool_results=[]))
    messages: list[AgentMessage] = [failure_message]
    if aborted and not is_turn_handoff_abort(signal):
        interruption = create_interrupted_turn_message()
        messages.append(interruption)
        stream.push(AgentEventMessageStart(message=interruption))
        stream.push(AgentEventMessageEnd(message=interruption))
    stream.push(AgentEventAgentEnd(messages=messages))


async def _run_loop(
    initial_context: AgentContext,
    new_messages: list[AgentMessage],
    initial_config: AgentLoopConfig,
    signal: AbortSignal | None,
    emit: AgentEventSink,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreStreamRuntimeDeps | None = None,
) -> None:
    """Main loop logic shared by agent_loop and agent_loop_continue.

    Parity: ``runLoop``.
    """
    current_context = initial_context
    config = initial_config
    first_turn = True
    turn_open = True
    # Check for steering messages at start (user may have typed while waiting)
    pending_messages: list[AgentMessage] = (
        await _settle(config.get_steering_messages())
        if config.get_steering_messages is not None
        else None
    ) or []

    async def stop_if_aborted() -> bool:
        nonlocal turn_open
        if not is_aborted(signal):
            return False
        # Persist an aborted assistant outcome so session post-processing
        # does not compact or continue from the preceding toolUse message.
        aborted_message = create_failure_message(
            config.model,
            signal.reason
            if signal is not None and signal.reason is not None
            else AbortError("Agent run aborted"),
            True,
        )
        new_messages.append(aborted_message)
        if not turn_open:
            await _emit(emit, AgentEventTurnStart())
            turn_open = True
        await _emit(emit, AgentEventMessageStart(message=aborted_message))
        await _emit(emit, AgentEventMessageEnd(message=aborted_message))
        await _emit(
            emit, AgentEventTurnEnd(message=aborted_message, tool_results=[])
        )
        turn_open = False
        if not is_turn_handoff_abort(signal):
            await append_interrupted_turn_message(new_messages, emit)
        await _emit(emit, AgentEventAgentEnd(messages=new_messages))
        return True

    # Outer loop: continues when queued follow-up messages arrive after the
    # agent would stop
    while True:
        has_more_tool_calls = True

        # Inner loop: process tool calls and steering messages
        while has_more_tool_calls or pending_messages:
            if await stop_if_aborted():
                return

            if not first_turn:
                await _emit(emit, AgentEventTurnStart())
                turn_open = True
            else:
                first_turn = False

            # Process pending messages (inject before next assistant response)
            if pending_messages:
                for message in pending_messages:
                    await _emit(emit, AgentEventMessageStart(message=message))
                    await _emit(emit, AgentEventMessageEnd(message=message))
                    current_context.messages.append(message)
                    new_messages.append(message)

            if await stop_if_aborted():
                return

            # Stream assistant response
            message = await _stream_assistant_response(
                current_context, config, signal, emit, stream_fn, runtime
            )
            new_messages.append(message)

            if message.stop_reason in ("error", "aborted"):
                await _emit(emit, AgentEventTurnEnd(message=message, tool_results=[]))
                if (
                    message.stop_reason == "aborted"
                    and is_aborted(signal)
                    and not is_turn_handoff_abort(signal)
                ):
                    await append_interrupted_turn_message(new_messages, emit)
                await _emit(emit, AgentEventAgentEnd(messages=new_messages))
                return

            # Only completed toolUse turns dispatch; length/stop can carry
            # partial stream blocks.
            tool_calls = [c for c in message.content if c.type == "toolCall"]

            tool_results: list[ToolResultMessage] = []
            has_more_tool_calls = False
            if message.stop_reason == "toolUse" and tool_calls:
                executed_tool_batch = await _execute_tool_calls(
                    current_context, message, config, signal, emit
                )
                tool_results.extend(executed_tool_batch.messages)
                has_more_tool_calls = not executed_tool_batch.terminate

                for result in tool_results:
                    current_context.messages.append(result)
                    new_messages.append(result)

            await _emit(
                emit, AgentEventTurnEnd(message=message, tool_results=tool_results)
            )
            turn_open = False
            if await stop_if_aborted():
                return

            next_turn_context = ShouldStopAfterTurnContext(
                message=message,
                tool_results=tool_results,
                context=current_context,
                new_messages=new_messages,
            )
            next_turn_snapshot = (
                await _settle(config.prepare_next_turn(next_turn_context))
                if config.prepare_next_turn is not None
                else None
            )
            if next_turn_snapshot:
                if next_turn_snapshot.context is not None:
                    current_context = next_turn_snapshot.context
                next_model = (
                    next_turn_snapshot.model
                    if next_turn_snapshot.model is not None
                    else config.model
                )
                next_thinking_level = (
                    next_turn_snapshot.thinking_level
                    if next_turn_snapshot.thinking_level is not None
                    else config.thinking_level
                )
                should_resolve_reasoning = next_turn_snapshot.thinking_level is not None or (
                    next_turn_snapshot.model is not None
                    and next_thinking_level is not None
                )
                current_options = config.stream_options or SimpleStreamOptions()
                next_reasoning = (
                    resolve_agent_reasoning_option(next_model, next_thinking_level)
                    if should_resolve_reasoning and next_thinking_level is not None
                    else current_options.reasoning
                )
                config = dataclasses.replace(
                    config,
                    model=next_model,
                    thinking_level=next_thinking_level,
                    stream_options=dataclasses.replace(
                        current_options, reasoning=next_reasoning
                    ),
                )
            if await stop_if_aborted():
                return

            if config.should_stop_after_turn is not None and await _settle(
                config.should_stop_after_turn(
                    ShouldStopAfterTurnContext(
                        message=message,
                        tool_results=tool_results,
                        context=current_context,
                        new_messages=new_messages,
                    )
                )
            ):
                await _emit(emit, AgentEventAgentEnd(messages=new_messages))
                return

            pending_messages = (
                await _settle(config.get_steering_messages())
                if config.get_steering_messages is not None
                else None
            ) or []
            if await stop_if_aborted():
                return

        follow_up_messages = (
            await _settle(config.get_follow_up_messages())
            if config.get_follow_up_messages is not None
            else None
        ) or []
        if follow_up_messages:
            # Follow-up messages arrive after a turn would otherwise end;
            # route them through the same pending-message path so event
            # ordering matches steering messages.
            pending_messages = follow_up_messages
            continue

        # No more messages, exit
        break

    await _emit(emit, AgentEventAgentEnd(messages=new_messages))


async def _stream_assistant_response(
    context: AgentContext,
    config: AgentLoopConfig,
    signal: AbortSignal | None,
    emit: AgentEventSink,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreStreamRuntimeDeps | None = None,
) -> AssistantMessage:
    """Stream an assistant response from the LLM.

    This is where ``AgentMessage[]`` gets transformed to ``Message[]`` for
    the LLM. Parity: ``streamAssistantResponse``.
    """
    # Apply context transform if configured (AgentMessage[] → AgentMessage[])
    messages = context.messages
    if config.transform_context is not None:
        messages = await _settle(config.transform_context(messages, signal))
    messages = normalize_core_context_messages(messages)

    # Convert to LLM-compatible messages (AgentMessage[] → Message[])
    llm_messages = await _settle(config.convert_to_llm(messages))

    # Build LLM context
    llm_context = Context(
        system_prompt=context.system_prompt,
        messages=llm_messages,
        tools=context.tools,
    )

    stream_function = resolve_agent_core_stream_fn(runtime, stream_fn)

    # Resolve API key (important for expiring tokens)
    base_options = config.stream_options or SimpleStreamOptions()
    resolved_api_key = (
        await _settle(config.get_api_key(config.model.provider))
        if config.get_api_key is not None
        else None
    ) or base_options.api_key

    response = await _settle(
        stream_function(
            config.model,
            llm_context,
            dataclasses.replace(base_options, api_key=resolved_api_key, signal=signal),
        )
    )

    partial_message: AssistantMessage | None = None
    added_partial = False

    async for event in response:
        if event.type == "start":
            message = event.partial
            partial_message = message
            context.messages.append(message)
            added_partial = True
            await _emit(
                emit, AgentEventMessageStart(message=dataclasses.replace(message))
            )
        elif event.type in _UPDATE_EVENT_TYPES:
            if partial_message is not None:
                message = _resolve_assistant_message_update(event, partial_message)
                partial_message = message
                context.messages[-1] = message
                await _emit(
                    emit,
                    AgentEventMessageUpdate(
                        message=dataclasses.replace(message),
                        assistant_message_event=event,
                    ),
                )
        elif event.type in ("done", "error"):
            final_message = _remove_non_executable_tool_calls(await response.result())
            if added_partial:
                context.messages[-1] = final_message
            else:
                context.messages.append(final_message)
            if not added_partial:
                await _emit(
                    emit,
                    AgentEventMessageStart(
                        message=dataclasses.replace(final_message)
                    ),
                )
            await _emit(emit, AgentEventMessageEnd(message=final_message))
            return final_message

    final_message = _remove_non_executable_tool_calls(await response.result())
    if added_partial:
        context.messages[-1] = final_message
    else:
        context.messages.append(final_message)
        await _emit(
            emit,
            AgentEventMessageStart(message=dataclasses.replace(final_message)),
        )
    await _emit(emit, AgentEventMessageEnd(message=final_message))
    return final_message


# ─────────────────────────────────────────────────────────────────────
# Tool execution
# ─────────────────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class _ExecutedToolCallBatch:
    """Parity: ``ExecutedToolCallBatch``."""

    messages: list[ToolResultMessage]
    terminate: bool


@dataclasses.dataclass(frozen=True)
class _ResolvedToolCallOutcome:
    """Parity: ``ResolvedToolCallOutcome`` — ``kind`` discriminates."""

    kind: str  # "resolved" | "error"
    tool: AgentTool | None = None
    error: object = None


@dataclasses.dataclass(frozen=True)
class _PreparedToolCall:
    """Parity: ``PreparedToolCall``."""

    kind: str  # always "prepared"
    tool_call: AgentToolCall
    tool: AgentTool
    args: Any


@dataclasses.dataclass(frozen=True)
class _ImmediateToolCallOutcome:
    """Parity: ``ImmediateToolCallOutcome``."""

    kind: str  # always "immediate"
    result: AgentToolResult
    is_error: bool
    error_kind: str | None = None


@dataclasses.dataclass(frozen=True)
class _ExecutedToolCallOutcome:
    """Parity: ``ExecutedToolCallOutcome``."""

    result: AgentToolResult
    is_error: bool
    execution_started: bool


@dataclasses.dataclass(frozen=True)
class _FinalizedToolCallOutcome:
    """Parity: ``FinalizedToolCallOutcome``."""

    tool_call: AgentToolCall
    result: AgentToolResult
    is_error: bool
    execution_started: bool
    error_kind: str | None = None
    hide_from_channel_progress: bool | None = None


async def _execute_tool_calls(
    current_context: AgentContext,
    assistant_message: AssistantMessage,
    config: AgentLoopConfig,
    signal: AbortSignal | None,
    emit: AgentEventSink,
) -> _ExecutedToolCallBatch:
    """Execute tool calls from an assistant message.

    Parity: ``executeToolCalls`` — pre-resolves the batch so one
    ``execution_mode == "sequential"`` tool promotes the whole batch to the
    sequential path.
    """
    tool_calls = [c for c in assistant_message.content if c.type == "toolCall"]
    resolved_tool_calls: dict[int, _ResolvedToolCallOutcome] = {}
    has_sequential_tool_call = False
    if config.tool_execution != "sequential":
        for tool_call in tool_calls:
            resolution = await _resolve_tool_call_tool(
                current_context,
                assistant_message,
                tool_call,
                config,
                signal,
                resolved_tool_calls,
            )
            if (
                resolution.kind == "resolved"
                and resolution.tool is not None
                and getattr(resolution.tool, "execution_mode", None) == "sequential"
            ):
                has_sequential_tool_call = True
                break
            if is_aborted(signal):
                break
    if config.tool_execution == "sequential" or has_sequential_tool_call:
        return await _execute_tool_calls_sequential(
            current_context,
            assistant_message,
            tool_calls,
            resolved_tool_calls,
            config,
            signal,
            emit,
        )
    return await _execute_tool_calls_parallel(
        current_context,
        assistant_message,
        tool_calls,
        resolved_tool_calls,
        config,
        signal,
        emit,
    )


def _hides_tool_call_from_channel_progress(
    context: AgentContext,
    tool_call: AgentToolCall,
    resolved_tool_calls: dict[int, _ResolvedToolCallOutcome],
) -> bool:
    """Parity: ``hidesToolCallFromChannelProgress``."""
    resolution = resolved_tool_calls.get(id(tool_call))
    if resolution is not None and resolution.kind == "resolved":
        tool = resolution.tool
    else:
        tool = next(
            (
                candidate
                for candidate in (context.tools or [])
                if candidate.name == tool_call.name
            ),
            None,
        )
    return tool is not None and getattr(tool, "hide_from_channel_progress", None) is True


async def _execute_tool_calls_sequential(
    current_context: AgentContext,
    assistant_message: AssistantMessage,
    tool_calls: list[AgentToolCall],
    resolved_tool_calls: dict[int, _ResolvedToolCallOutcome],
    config: AgentLoopConfig,
    signal: AbortSignal | None,
    emit: AgentEventSink,
) -> _ExecutedToolCallBatch:
    """Parity: ``executeToolCallsSequential`` — each call fully prepared,
    executed, finalized, and its artifacts emitted before the next starts."""
    finalized_calls: list[_FinalizedToolCallOutcome] = []
    messages: list[ToolResultMessage] = []

    for tool_call in tool_calls:
        hide_from_channel_progress = _hides_tool_call_from_channel_progress(
            current_context, tool_call, resolved_tool_calls
        )
        await _emit(
            emit,
            AgentEventToolExecutionStart(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                args=tool_call.arguments,
                hide_from_channel_progress=True if hide_from_channel_progress else None,
            ),
        )

        preparation = await _prepare_tool_call(
            current_context,
            assistant_message,
            tool_call,
            config,
            signal,
            resolved_tool_calls,
        )
        if isinstance(preparation, _ImmediateToolCallOutcome):
            finalized = _FinalizedToolCallOutcome(
                tool_call=tool_call,
                result=preparation.result,
                is_error=preparation.is_error,
                execution_started=False,
                error_kind=preparation.error_kind,
                hide_from_channel_progress=True if hide_from_channel_progress else None,
            )
        else:
            executed = await _execute_prepared_tool_call(preparation, signal, emit)
            finalized = await _finalize_executed_tool_call(
                current_context,
                assistant_message,
                preparation,
                executed,
                config,
                signal,
            )

        await _emit_tool_execution_end(finalized, emit)
        tool_result_message = _create_tool_result_message(finalized)
        await _emit_tool_result_message(tool_result_message, emit)
        finalized_calls.append(finalized)
        messages.append(tool_result_message)

        if is_aborted(signal):
            break

    return _ExecutedToolCallBatch(
        messages=messages,
        terminate=_should_terminate_tool_batch(finalized_calls),
    )


async def _execute_tool_calls_parallel(
    current_context: AgentContext,
    assistant_message: AssistantMessage,
    tool_calls: list[AgentToolCall],
    resolved_tool_calls: dict[int, _ResolvedToolCallOutcome],
    config: AgentLoopConfig,
    signal: AbortSignal | None,
    emit: AgentEventSink,
) -> _ExecutedToolCallBatch:
    """Parity: ``executeToolCallsParallel``.

    All ``tool_execution_start`` events fire first (preparation is
    sequential); immediate outcomes emit their end event inline; prepared
    calls become deferred closures gathered concurrently. Tool-result
    messages are then emitted in call order.
    """
    finalized_calls: list[
        _FinalizedToolCallOutcome | Callable[[], Awaitable[_FinalizedToolCallOutcome]]
    ] = []

    for tool_call in tool_calls:
        hide_from_channel_progress = _hides_tool_call_from_channel_progress(
            current_context, tool_call, resolved_tool_calls
        )
        await _emit(
            emit,
            AgentEventToolExecutionStart(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                args=tool_call.arguments,
                hide_from_channel_progress=True if hide_from_channel_progress else None,
            ),
        )

        preparation = await _prepare_tool_call(
            current_context,
            assistant_message,
            tool_call,
            config,
            signal,
            resolved_tool_calls,
        )
        if isinstance(preparation, _ImmediateToolCallOutcome):
            finalized = _FinalizedToolCallOutcome(
                tool_call=tool_call,
                result=preparation.result,
                is_error=preparation.is_error,
                execution_started=False,
                error_kind=preparation.error_kind,
                hide_from_channel_progress=True if hide_from_channel_progress else None,
            )
            await _emit_tool_execution_end(finalized, emit)
            finalized_calls.append(finalized)
            if is_aborted(signal):
                break
            continue

        def make_entry(
            prepared: _PreparedToolCall,
        ) -> Callable[[], Awaitable[_FinalizedToolCallOutcome]]:
            async def run() -> _FinalizedToolCallOutcome:
                executed = await _execute_prepared_tool_call(prepared, signal, emit)
                finalized = await _finalize_executed_tool_call(
                    current_context,
                    assistant_message,
                    prepared,
                    executed,
                    config,
                    signal,
                )
                await _emit_tool_execution_end(finalized, emit)
                return finalized

            return run

        finalized_calls.append(make_entry(preparation))
        if is_aborted(signal):
            break

    async def _ready(value: _FinalizedToolCallOutcome) -> _FinalizedToolCallOutcome:
        return value

    ordered_finalized_calls: list[_FinalizedToolCallOutcome] = list(
        await asyncio.gather(
            *(
                entry() if callable(entry) else _ready(entry)
                for entry in finalized_calls
            )
        )
    )
    messages: list[ToolResultMessage] = []
    for finalized in ordered_finalized_calls:
        tool_result_message = _create_tool_result_message(finalized)
        await _emit_tool_result_message(tool_result_message, emit)
        messages.append(tool_result_message)

    return _ExecutedToolCallBatch(
        messages=messages,
        terminate=_should_terminate_tool_batch(ordered_finalized_calls),
    )


def _should_terminate_tool_batch(
    finalized_calls: list[_FinalizedToolCallOutcome],
) -> bool:
    """Parity: ``shouldTerminateToolBatch`` — unanimous consent required."""
    return len(finalized_calls) > 0 and all(
        finalized.result.terminate is True for finalized in finalized_calls
    )


def _prepare_tool_call_arguments(
    tool: AgentTool, tool_call: AgentToolCall
) -> AgentToolCall:
    """Parity: ``prepareToolCallArguments``."""
    prepare = getattr(tool, "prepare_arguments", None)
    if not prepare:
        return tool_call
    prepared_arguments = prepare(tool_call.arguments)
    if prepared_arguments is tool_call.arguments:
        return tool_call
    return dataclasses.replace(tool_call, arguments=prepared_arguments)


async def _resolve_tool_call_tool(
    current_context: AgentContext,
    assistant_message: AssistantMessage,
    tool_call: AgentToolCall,
    config: AgentLoopConfig,
    signal: AbortSignal | None,
    resolved_tool_calls: dict[int, _ResolvedToolCallOutcome] | None = None,
) -> _ResolvedToolCallOutcome:
    """Parity: ``resolveToolCallTool``.

    Cached per tool call (by identity, see module docstring) so the
    sequential-mode pre-scan and the execution pass hydrate a deferred tool
    at most once.
    """
    if resolved_tool_calls is not None:
        cached = resolved_tool_calls.get(id(tool_call))
        if cached is not None:
            return cached
    resolution: _ResolvedToolCallOutcome
    try:
        tool = next(
            (t for t in (current_context.tools or []) if t.name == tool_call.name),
            None,
        )
        if tool is None and config.resolve_deferred_tool is not None:
            resolved_tool = await _settle(
                config.resolve_deferred_tool(
                    DeferredToolCallContext(
                        assistant_message=assistant_message,
                        tool_call=tool_call,
                        context=current_context,
                    ),
                    signal,
                )
            )
            # Keep execution and lifecycle/audit identity aligned with the
            # original model call.
            if resolved_tool is not None and resolved_tool.name != tool_call.name:
                raise RuntimeError(
                    f'Deferred tool resolver returned "{resolved_tool.name}" '
                    f'for requested "{tool_call.name}"'
                )
            tool = resolved_tool
            if tool is not None:
                # Make the recovered tool visible to later provider
                # continuations in this run. AgentContext is frozen; this is
                # the TS `currentContext.tools = [...]` property write, done
                # on the same object so every holder observes it.
                object.__setattr__(
                    current_context, "tools", [*(current_context.tools or []), tool]
                )
        resolution = _ResolvedToolCallOutcome(kind="resolved", tool=tool)
    except Exception as error:  # noqa: BLE001 - parity: catch → error outcome
        resolution = _ResolvedToolCallOutcome(kind="error", error=error)
    if resolved_tool_calls is not None:
        resolved_tool_calls[id(tool_call)] = resolution
    return resolution


async def _prepare_tool_call(
    current_context: AgentContext,
    assistant_message: AssistantMessage,
    tool_call: AgentToolCall,
    config: AgentLoopConfig,
    signal: AbortSignal | None,
    resolved_tool_calls: dict[int, _ResolvedToolCallOutcome],
) -> _PreparedToolCall | _ImmediateToolCallOutcome:
    """Parity: ``prepareToolCall`` — resolution, argument preparation,
    schema validation, and the ``before_tool_call`` policy gate."""
    resolution = await _resolve_tool_call_tool(
        current_context,
        assistant_message,
        tool_call,
        config,
        signal,
        resolved_tool_calls,
    )
    if resolution.kind == "error":
        return _ImmediateToolCallOutcome(
            kind="immediate",
            result=_create_error_tool_result(
                "Operation aborted" if is_aborted(signal) else str(resolution.error)
            ),
            is_error=True,
        )
    tool = resolution.tool
    if tool is None:
        return _ImmediateToolCallOutcome(
            kind="immediate",
            result=_create_error_tool_result(f"Tool {tool_call.name} not found"),
            is_error=True,
        )

    try:
        prepared_tool_call = _prepare_tool_call_arguments(tool, tool_call)
    except Exception as error:  # noqa: BLE001 - parity
        return _ImmediateToolCallOutcome(
            kind="immediate",
            result=_create_error_tool_result(str(error)),
            is_error=True,
        )

    try:
        validated_args = validate_tool_arguments(tool, prepared_tool_call)
    except Exception as error:  # noqa: BLE001 - parity
        return _ImmediateToolCallOutcome(
            kind="immediate",
            result=_create_error_tool_result(str(error)),
            is_error=True,
            error_kind="argument-validation",
        )

    try:
        if config.before_tool_call is not None:
            before_result = await _settle(
                config.before_tool_call(
                    BeforeToolCallContext(
                        assistant_message=assistant_message,
                        tool_call=tool_call,
                        args=validated_args,
                        context=current_context,
                    ),
                    signal,
                )
            )
            if is_aborted(signal):
                return _ImmediateToolCallOutcome(
                    kind="immediate",
                    result=_create_error_tool_result("Operation aborted"),
                    is_error=True,
                )
            if before_result is not None and before_result.block:
                return _ImmediateToolCallOutcome(
                    kind="immediate",
                    result=_create_error_tool_result(
                        before_result.reason or "Tool execution was blocked"
                    ),
                    is_error=True,
                )
        if is_aborted(signal):
            return _ImmediateToolCallOutcome(
                kind="immediate",
                result=_create_error_tool_result("Operation aborted"),
                is_error=True,
            )
        return _PreparedToolCall(
            kind="prepared",
            tool_call=tool_call,
            tool=tool,
            args=validated_args,
        )
    except Exception as error:  # noqa: BLE001 - parity
        return _ImmediateToolCallOutcome(
            kind="immediate",
            result=_create_error_tool_result(str(error)),
            is_error=True,
        )


async def _execute_prepared_tool_call(
    prepared: _PreparedToolCall,
    signal: AbortSignal | None,
    emit: AgentEventSink,
) -> _ExecutedToolCallOutcome:
    """Parity: ``executePreparedToolCall``."""
    # Parallel batches prepare every call first. A later preflight abort must
    # not let an earlier prepared, side-effectful tool start afterward.
    if is_aborted(signal):
        return _ExecutedToolCallOutcome(
            result=_create_error_tool_result("Operation aborted"),
            is_error=True,
            execution_started=False,
        )

    update_events: list[asyncio.Future[None]] = []
    accepting_updates = True

    def on_update(partial_result: AgentToolResult) -> None:
        if not accepting_updates:
            return
        # Parity with `Promise.resolve(emit(...))`: the sink runs now; an
        # async sink's completion is awaited after execute settles.
        emitted = emit(
            AgentEventToolExecutionUpdate(
                tool_call_id=prepared.tool_call.id,
                tool_name=prepared.tool_call.name,
                args=prepared.tool_call.arguments,
                partial_result=partial_result,
                hide_from_channel_progress=(
                    True
                    if getattr(prepared.tool, "hide_from_channel_progress", None) is True
                    else None
                ),
            )
        )
        if inspect.isawaitable(emitted):
            update_events.append(asyncio.ensure_future(emitted))

    try:
        result = await _settle(
            prepared.tool.execute(
                prepared.tool_call.id,
                prepared.args,
                signal,
                on_update,
            )
        )
        accepting_updates = False
        await asyncio.gather(*update_events)
        return _ExecutedToolCallOutcome(
            result=result, is_error=False, execution_started=True
        )
    except Exception as error:  # noqa: BLE001 - parity: tool errors → result
        accepting_updates = False
        await asyncio.gather(*update_events)
        return _ExecutedToolCallOutcome(
            result=_create_error_tool_result(str(error)),
            is_error=True,
            execution_started=True,
        )
    finally:
        accepting_updates = False


async def _finalize_executed_tool_call(
    current_context: AgentContext,
    assistant_message: AssistantMessage,
    prepared: _PreparedToolCall,
    executed: _ExecutedToolCallOutcome,
    config: AgentLoopConfig,
    signal: AbortSignal | None,
) -> _FinalizedToolCallOutcome:
    """Parity: ``finalizeExecutedToolCall`` — ``after_tool_call`` applies
    only when execution actually started, merging per-field with the
    UNSET-aware equivalent of ``??``."""
    result = executed.result
    is_error = executed.is_error

    if executed.execution_started and config.after_tool_call is not None:
        try:
            after_result = await _settle(
                config.after_tool_call(
                    AfterToolCallContext(
                        assistant_message=assistant_message,
                        tool_call=prepared.tool_call,
                        args=prepared.args,
                        result=result,
                        is_error=is_error,
                        context=current_context,
                    ),
                    signal,
                )
            )
            if after_result is not None:
                result = dataclasses.replace(
                    result,
                    content=_coalesce(after_result.content, result.content),
                    details=_coalesce(after_result.details, result.details),
                    terminate=_coalesce(after_result.terminate, result.terminate),
                )
                is_error = _coalesce(after_result.is_error, is_error)
        except Exception as error:  # noqa: BLE001 - parity: hook throw → error
            result = _create_error_tool_result(str(error))
            is_error = True

    return _FinalizedToolCallOutcome(
        tool_call=prepared.tool_call,
        result=result,
        is_error=is_error,
        execution_started=executed.execution_started,
        hide_from_channel_progress=(
            True
            if getattr(prepared.tool, "hide_from_channel_progress", None) is True
            else None
        ),
    )


def _coalesce(value: Any, fallback: Any) -> Any:
    """The TS ``??`` for hook-result fields: UNSET and None both mean
    "keep the original" (TS ``undefined`` and ``null`` respectively)."""
    if value is UNSET or value is None:
        return fallback
    return value


def _create_error_tool_result(message: str) -> AgentToolResult:
    """Parity: ``createErrorToolResult``."""
    return AgentToolResult(content=[TextContent(text=message)], details={})


async def _emit_tool_execution_end(
    finalized: _FinalizedToolCallOutcome,
    emit: AgentEventSink,
) -> None:
    """Parity: ``emitToolExecutionEnd``."""
    await _emit(
        emit,
        AgentEventToolExecutionEnd(
            tool_call_id=finalized.tool_call.id,
            tool_name=finalized.tool_call.name,
            result=finalized.result,
            is_error=finalized.is_error,
            execution_started=finalized.execution_started,
            error_kind=finalized.error_kind,
            hide_from_channel_progress=(
                True if finalized.hide_from_channel_progress is True else None
            ),
        ),
    )


def _create_tool_result_message(
    finalized: _FinalizedToolCallOutcome,
) -> ToolResultMessage:
    """Parity: ``createToolResultMessage``."""
    return ToolResultMessage(
        tool_call_id=finalized.tool_call.id,
        tool_name=finalized.tool_call.name,
        content=finalized.result.content if finalized.result.content is not None else [],
        details=finalized.result.details,
        is_error=finalized.is_error,
        timestamp=now_ms(),
    )


async def _emit_tool_result_message(
    tool_result_message: ToolResultMessage,
    emit: AgentEventSink,
) -> None:
    """Parity: ``emitToolResultMessage``."""
    await _emit(emit, AgentEventMessageStart(message=tool_result_message))
    await _emit(emit, AgentEventMessageEnd(message=tool_result_message))


# ─────────────────────────────────────────────────────────────────────

__all__ = [
    "AgentEventSink",
    "agent_loop",
    "agent_loop_continue",
    "run_agent_loop",
    "run_agent_loop_continue",
]
