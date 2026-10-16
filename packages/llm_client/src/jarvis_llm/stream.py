"""jarvis_llm.stream — the ``StreamFn`` contract and its enforcement.

OpenClaw parity: the ``StreamFn`` / ``CompleteSimpleFn`` contracts in
``packages/llm-core/src/types.ts`` plus the facade in ``src/llm/stream.ts``
(``stream``, ``complete``, ``streamSimple``, ``completeSimple``,
``resolveRuntime``).

The contract this module exists to guarantee
============================================
Quoting ``types.ts`` verbatim:

    Contract:
    - Must return an AssistantMessageEventStream.
    - Once invoked, request/model/runtime failures should be encoded in the
      returned stream, not thrown.
    - Error termination must produce an AssistantMessage with stopReason
      "error" or "aborted" and errorMessage, emitted via the stream protocol.

And from ``packages/agent-core/src/types.ts``:

    Contract: Must not throw or return a rejected promise for request/model/
    runtime failures.

Why this is the critical point of the brain port
================================================
Every layer above — the agent loop, the session tree, compaction — assumes
a run always terminates with a well-formed ``AssistantMessage``. If a
provider raises instead, the loop unwinds without emitting ``turn_end`` /
``agent_end``, and the session is left with a dangling ``toolUse`` message
that compaction will later try to summarize from. The damage is silent and
persistent, and no amount of later work repairs a transcript already
written that way.

So provider authors are not trusted to honour the contract by discipline.
:func:`guard_stream_fn` wraps any provider and *enforces* it: a raise
becomes an ``error``-terminated stream, an abort becomes an
``aborted``-terminated stream, and a stream that ends without a terminal
event is completed with a synthesized failure message.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Protocol

from .abort import AbortSignal, is_aborted
from .diagnostics import (
    append_assistant_message_diagnostic,
    create_assistant_message_diagnostic,
    extract_diagnostic_error,
    format_thrown_value,
    now_ms,
)
from .event_stream import AssistantMessageEventStream, create_assistant_message_event_stream
from .types import (
    AssistantMessage,
    Context,
    Model,
    SimpleStreamOptions,
    StreamEventError,
    empty_usage,
)

#: Diagnostic type recorded when a provider raised instead of encoding the
#: failure in its stream. Its presence in a transcript is a provider bug
#: report, not a normal error, so it gets a distinct type.
DIAGNOSTIC_PROVIDER_THREW = "provider_threw"

#: Diagnostic type recorded when a provider's stream ended with no terminal
#: event and the guard had to synthesize one.
DIAGNOSTIC_STREAM_UNTERMINATED = "stream_unterminated"

#: Message used when a run is aborted with no more specific reason.
#: Parity: ``new Error("Agent run aborted")`` in ``agent-loop.ts``.
ABORTED_MESSAGE = "Agent run aborted"

#: Message used when a provider stream ends without ``done`` or ``error``.
UNTERMINATED_MESSAGE = "Provider stream ended without a terminal event"


class StreamFn(Protocol):
    """A text-streaming provider. Parity: ``StreamFn`` in ``types.ts``.

    May be sync or async — OpenClaw's type is
    ``AssistantMessageEventStreamLike | Promise<AssistantMessageEventStreamLike>``,
    and :func:`guard_stream_fn` normalizes both.
    """

    def __call__(
        self,
        model: Model,
        context: Context,
        options: SimpleStreamOptions | None = None,
    ) -> Any: ...


class CompleteSimpleFn(Protocol):
    """Non-streaming completion. Parity: ``CompleteSimpleFn`` in ``types.ts``.

    Note the context is narrowed to ``Pick<Context, "systemPrompt" | "messages">``
    in TS — tools are not part of a simple completion.
    """

    async def __call__(
        self,
        model: Model,
        context: Context,
        options: SimpleStreamOptions | None = None,
    ) -> AssistantMessage: ...


def create_failure_message(
    model: Model,
    error: object,
    aborted: bool = False,
    *,
    diagnostic_type: str | None = None,
    details: dict[str, Any] | None = None,
) -> AssistantMessage:
    """Build the terminal ``AssistantMessage`` for a failed run.

    Parity: ``createFailureMessage(model, error, aborted)`` in
    ``packages/agent-core/src/agent-loop.ts``. Lives here rather than in the
    agent package because both the provider guard and the loop synthesize
    the same shape, and two copies would drift.

    ``stop_reason`` is ``"aborted"`` when *aborted* else ``"error"`` — these
    are the only two values the contract permits for a failure, and the
    caller must not pass anything else.
    """
    message = format_thrown_value(error)
    info = extract_diagnostic_error(error)
    diagnostics = None
    if diagnostic_type is not None:
        diagnostics = append_assistant_message_diagnostic(
            None, create_assistant_message_diagnostic(diagnostic_type, error, details)
        )

    return AssistantMessage(
        api=model.api,
        provider=model.provider,
        model=model.id,
        content=[],
        usage=empty_usage(),
        stop_reason="aborted" if aborted else "error",
        error_message=message,
        error_code=str(info.code) if info.code is not None else None,
        error_type=info.name,
        diagnostics=diagnostics,
        timestamp=now_ms(),
    )


def guard_stream_fn(provider: StreamFn) -> StreamFn:
    """Wrap a provider so it cannot violate the never-throw contract.

    Returns an async callable producing an
    :class:`~jarvis_llm.event_stream.AssistantMessageEventStream` that is
    guaranteed to terminate with exactly one ``done`` or ``error`` event.

    Three failure modes are converted, all into stream data:

    1. **The provider raises synchronously or while awaited** — before any
       stream exists. The guard creates one and terminates it with an
       ``error`` event, tagged ``provider_threw``.
    2. **The provider raises mid-stream** — some events already delivered.
       The guard appends an ``error`` terminal event; earlier events stay
       valid, so a partial response is preserved rather than discarded.
    3. **The provider's stream ends with no terminal event.** The guard
       synthesizes an ``error`` terminal, tagged ``stream_unterminated``.
       Without this, ``result()`` would await forever and hang the run.

    An abort observed on ``options.signal`` yields ``stop_reason="aborted"``
    rather than ``"error"``, since the loop treats the two differently:
    abort is expected, error is not.

    ``BaseException`` is caught deliberately, not just ``Exception``. A
    ``KeyboardInterrupt`` or ``asyncio.CancelledError`` escaping a provider
    would corrupt the transcript exactly as any other raise does. The
    exception is recorded and then **re-raised** after the stream is
    terminated, so interpreter-level control flow still works while the
    transcript stays consistent.
    """

    async def guarded(
        model: Model,
        context: Context,
        options: SimpleStreamOptions | None = None,
    ) -> AssistantMessageEventStream:
        signal: AbortSignal | None = getattr(options, "signal", None)

        try:
            produced = provider(model, context, options)
            if inspect.isawaitable(produced):
                produced = await produced
        except BaseException as exc:  # noqa: BLE001 - contract enforcement
            stream = create_assistant_message_event_stream()
            _terminate_with_failure(
                stream,
                model,
                exc,
                aborted=is_aborted(signal),
                diagnostic_type=DIAGNOSTIC_PROVIDER_THREW,
            )
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            return stream

        # The provider returned something. It must be a stream; if it is not,
        # that is a contract violation the loop cannot recover from silently.
        if not _looks_like_stream(produced):
            stream = create_assistant_message_event_stream()
            _terminate_with_failure(
                stream,
                model,
                TypeError(
                    "Provider did not return an assistant-message event stream "
                    f"(got {type(produced).__name__})"
                ),
                aborted=False,
                diagnostic_type=DIAGNOSTIC_PROVIDER_THREW,
            )
            return stream

        return _wrap_produced_stream(produced, model, signal)

    return guarded


def _wrap_produced_stream(
    produced: Any,
    model: Model,
    signal: AbortSignal | None,
) -> AssistantMessageEventStream:
    """Relay a provider stream into a guarded one.

    Relaying rather than returning the provider's own object is what allows
    failure modes 2 and 3 to be caught: the guard sits between producer and
    consumer and can always append a terminal event.

    The relay runs as a background task. It is started here rather than
    lazily on first iteration so that ``result()`` resolves even for a
    caller that never iterates — the agent loop's ``complete``-style paths
    do exactly that, and a lazily-started relay would deadlock them.
    """
    guarded_stream = create_assistant_message_event_stream()
    saw_terminal = False

    async def relay() -> None:
        nonlocal saw_terminal
        try:
            async for event in produced:
                guarded_stream.push(event)
                if getattr(event, "type", None) in ("done", "error"):
                    saw_terminal = True
        except BaseException as exc:  # noqa: BLE001 - contract enforcement
            if not saw_terminal:
                _terminate_with_failure(
                    guarded_stream,
                    model,
                    exc,
                    aborted=is_aborted(signal),
                    diagnostic_type=DIAGNOSTIC_PROVIDER_THREW,
                )
                saw_terminal = True
            else:
                guarded_stream.end()
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            return

        if not saw_terminal:
            # Mode 3: the provider simply stopped. Synthesize a terminal so
            # `result()` resolves instead of hanging the whole run.
            aborted = is_aborted(signal)
            explicit = signal.reason if signal is not None else None
            reason: BaseException = explicit or RuntimeError(
                ABORTED_MESSAGE if aborted else UNTERMINATED_MESSAGE
            )
            _terminate_with_failure(
                guarded_stream,
                model,
                reason,
                aborted=aborted,
                diagnostic_type=DIAGNOSTIC_STREAM_UNTERMINATED,
            )
            saw_terminal = True

        guarded_stream.end()

    # Keep a reference on the stream: a bare `create_task` may be garbage
    # collected mid-flight, which would stall the relay and hang `result()`.
    guarded_stream.relay_task = asyncio.ensure_future(relay())  # type: ignore[attr-defined]
    return guarded_stream


def _terminate_with_failure(
    stream: AssistantMessageEventStream,
    model: Model,
    error: object,
    *,
    aborted: bool,
    diagnostic_type: str,
) -> None:
    """Push the single ``error`` terminal event and close the stream."""
    failure = create_failure_message(model, error, aborted=aborted, diagnostic_type=diagnostic_type)
    stream.push(StreamEventError(reason="aborted" if aborted else "error", error=failure))
    stream.end()


def _looks_like_stream(value: Any) -> bool:
    """Duck-type check for the read-only stream contract.

    Requires ``__aiter__`` and ``result``, matching
    ``AssistantMessageEventStreamLike``. A structural check keeps provider
    extensions free to supply their own stream implementation, as they can
    in OpenClaw.
    """
    return hasattr(value, "__aiter__") and callable(getattr(value, "result", None))


__all__ = [
    "ABORTED_MESSAGE",
    "DIAGNOSTIC_PROVIDER_THREW",
    "DIAGNOSTIC_STREAM_UNTERMINATED",
    "UNTERMINATED_MESSAGE",
    "CompleteSimpleFn",
    "StreamFn",
    "create_failure_message",
    "guard_stream_fn",
]
