"""jarvis_llm.event_stream — async-iterable event stream with a final result.

OpenClaw parity: ``packages/llm-core/src/utils/event-stream.ts``
(``EventStream``, ``AssistantMessageEventStream``,
``createAssistantMessageEventStream``).

The shape being reproduced
==========================
A stream that is *both* an async iterable of incremental events *and* a
holder of one separately-awaitable final result. Two consumers with
different needs read the same producer: the UI iterates deltas, while the
agent loop awaits ``result()`` for the terminal ``AssistantMessage``.

Behaviours preserved exactly from the TS original, because the loop
depends on each of them:

1. ``push`` after completion is a **silent no-op** (TS: ``if (this.done)
   return``). Providers routinely emit trailing chunks after a terminal
   event; dropping them silently is the contract.
2. The terminal event is still delivered to iterators *as well as*
   resolving ``result()``. TS resolves the result first, then dispatches
   to a waiter or queues — so consumers see ``done``/``error`` in the
   iteration too.
3. ``end(result)`` only resolves when ``result is not None`` (TS checks
   ``result !== undefined``); ``end()`` with no argument closes iteration
   and leaves an already-resolved result untouched.
4. FIFO across the queue/waiter split: a waiting consumer is handed the
   event directly, otherwise it queues.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Callable, Generic, TypeVar

from .types import AssistantMessage, AssistantMessageEvent

T = TypeVar("T")
R = TypeVar("R")


class EventStream(Generic[T, R]):
    """Generic async-iterable event stream with a separately awaited result.

    Parity: ``EventStream<T, R>``.

    ``is_complete`` decides which event is terminal; ``extract_result``
    pulls the final value out of it. Injecting both keeps this class free
    of assistant-message specifics, exactly as in OpenClaw.
    """

    def __init__(
        self,
        is_complete: Callable[[T], bool],
        extract_result: Callable[[T], R],
    ) -> None:
        self._queue: list[T] = []
        self._waiting: list[asyncio.Future[tuple[T, bool]]] = []
        self._done = False
        self._is_complete = is_complete
        self._extract_result = extract_result
        # Created lazily: the stream may be constructed off-loop (e.g. by a
        # sync provider factory) while it is awaited on the loop. Binding the
        # future at construction would attach it to the wrong event loop.
        self._final: asyncio.Future[R] | None = None
        self._final_value: R | None = None
        self._final_set = False

    # ── producer side ────────────────────────────────────────────────

    def push(self, event: T) -> None:
        """Queue one event. No-op once the stream has completed.

        Parity: ``push``. The post-completion no-op is intentional — see
        module docstring note 1.
        """
        if self._done:
            return

        if self._is_complete(event):
            self._done = True
            self._resolve_final(self._extract_result(event))

        # Terminal events are still delivered to iterators, matching TS:
        # resolution happens above, dispatch happens here unconditionally.
        if self._waiting:
            waiter = self._waiting.pop(0)
            if not waiter.done():
                waiter.set_result((event, False))
        else:
            self._queue.append(event)

    def end(self, result: R | None = None) -> None:
        """Complete the stream, optionally resolving the final result.

        Parity: ``end``. A ``None`` argument leaves the result alone (TS
        checks ``result !== undefined``) so ``end()`` can close a stream
        whose terminal event already resolved it.
        """
        self._done = True
        if result is not None:
            self._resolve_final(result)

        while self._waiting:
            waiter = self._waiting.pop(0)
            if not waiter.done():
                # The sentinel here is the "done" flag; the value is ignored.
                waiter.set_result((None, True))  # type: ignore[arg-type]

    # ── consumer side ────────────────────────────────────────────────

    async def __aiter__(self) -> AsyncIterator[T]:
        """Iterate events until the stream ends. Parity: ``[Symbol.asyncIterator]``."""
        while True:
            if self._queue:
                yield self._queue.pop(0)
                continue
            if self._done:
                return
            waiter: asyncio.Future[tuple[T, bool]] = asyncio.get_running_loop().create_future()
            self._waiting.append(waiter)
            value, finished = await waiter
            if finished:
                return
            yield value

    async def result(self) -> R:
        """Await the final result. Parity: ``result()``."""
        if self._final_set:
            # Already resolved — return without touching a future, so this
            # works even when awaited after the producing loop has closed.
            return self._final_value  # type: ignore[return-value]
        return await self._ensure_future()

    # ── internals ────────────────────────────────────────────────────

    def _ensure_future(self) -> asyncio.Future[R]:
        if self._final is None:
            self._final = asyncio.get_running_loop().create_future()
            if self._final_set:
                self._final.set_result(self._final_value)  # type: ignore[arg-type]
        return self._final

    def _resolve_final(self, value: R) -> None:
        if self._final_set:
            return
        self._final_set = True
        self._final_value = value
        if self._final is not None and not self._final.done():
            self._final.set_result(value)


def _is_terminal(event: AssistantMessageEvent) -> bool:
    """Terminal when ``type`` is ``done`` or ``error``.

    Parity: ``(event) => event.type === "done" || event.type === "error"``.
    """
    return getattr(event, "type", None) in ("done", "error")


def _extract_assistant_message(event: AssistantMessageEvent) -> AssistantMessage:
    """Pull the final message out of a terminal event.

    Parity: ``done`` -> ``event.message``, ``error`` -> ``event.error``.
    Anything else is a producer bug; OpenClaw throws here and so do we —
    this path is unreachable given ``_is_terminal`` gates it.
    """
    event_type = getattr(event, "type", None)
    if event_type == "done":
        return event.message  # type: ignore[union-attr]
    if event_type == "error":
        return event.error  # type: ignore[union-attr]
    raise RuntimeError("Unexpected event type for final result")


class AssistantMessageEventStream(EventStream["AssistantMessageEvent", AssistantMessage]):
    """Assistant-message stream resolving on ``done``/``error``.

    Parity: ``AssistantMessageEventStream``. Satisfies the
    ``AssistantMessageEventStreamContract`` protocol in ``types.py``.
    """

    def __init__(self) -> None:
        super().__init__(_is_terminal, _extract_assistant_message)


def create_assistant_message_event_stream() -> AssistantMessageEventStream:
    """Create a stream for provider and plugin adapters.

    Parity: ``createAssistantMessageEventStream``.
    """
    return AssistantMessageEventStream()


__all__ = [
    "AssistantMessageEventStream",
    "EventStream",
    "create_assistant_message_event_stream",
]
