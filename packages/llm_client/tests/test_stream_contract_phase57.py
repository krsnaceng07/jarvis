"""Phase 5.7 gate: the ``StreamFn`` never-throw contract under fault injection.

This suite is the pass/fail gate for Phase 5.7 of
``docs/OPENCLAW_BRAIN_PORT_PLAN_V2.md``, quoting the plan:

    a test suite that injects timeout, 4xx, 5xx, malformed-payload, and
    mid-stream abort into the stub and asserts the function never raises
    and always terminates with an AssistantMessage carrying stop_reason in
    {"error", "aborted"} plus error_message.

Why this gate and not another
=============================
The never-throw contract is the highest-cost-if-wrong part of the whole
brain port. Every layer above (agent loop, session tree, compaction)
assumes a run terminates with a well-formed ``AssistantMessage``. A
provider that raises instead leaves a dangling ``toolUse`` message that
compaction later summarizes from — silent, persistent transcript
corruption that no later fix repairs. So the guard is tested against
deliberately hostile providers before any consumer exists.

``asyncio_mode = "auto"`` is set in the root ``pyproject.toml``, so async
tests need no marker.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

import pytest

from jarvis_llm import (
    AbortController,
    AssistantMessage,
    Context,
    Model,
    SimpleStreamOptions,
    StreamEventDone,
    StreamEventStart,
    StreamEventTextDelta,
    StreamEventTextStart,
    empty_usage,
    guard_stream_fn,
)
from jarvis_llm.stream import (
    DIAGNOSTIC_PROVIDER_THREW,
    DIAGNOSTIC_STREAM_UNTERMINATED,
)

FAILURE_REASONS = ("error", "aborted")

MODEL = Model(
    id="test-model",
    name="Test Model",
    api="anthropic-messages",
    provider="test",
    context_window=200_000,
    max_tokens=8_192,
)
CONTEXT = Context(system_prompt="You are a test.", messages=[], tools=[])


def _message(stop_reason: str = "stop") -> AssistantMessage:
    return AssistantMessage(
        api=MODEL.api,
        provider=MODEL.provider,
        model=MODEL.id,
        content=[],
        usage=empty_usage(),
        stop_reason=stop_reason,  # type: ignore[arg-type]
        timestamp=0,
    )


#: Reused snapshot for events whose ``partial`` is required. Its contents do
#: not matter to the guard, only that the event constructs.
PARTIAL = _message()


def _start() -> Any:
    return StreamEventStart(partial=PARTIAL)


def _text_start() -> Any:
    return StreamEventTextStart(content_index=0, partial=PARTIAL)


def _text_delta(delta: str) -> Any:
    return StreamEventTextDelta(content_index=0, delta=delta)


def _done(message: AssistantMessage) -> Any:
    return StreamEventDone(reason="stop", message=message)


class _IterableStream:
    """Minimal provider-side stream: async-iterable plus ``result()``.

    Deliberately *not* the real ``AssistantMessageEventStream`` — the guard
    must accept any structurally-conforming provider stream, exactly as
    OpenClaw accepts ``AssistantMessageEventStreamLike``.
    """

    def __init__(self, iterator: AsyncIterator[Any]) -> None:
        self._iterator = iterator

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterator

    async def result(self) -> AssistantMessage:
        raise AssertionError("the guard must not await the provider's own result()")


def _assert_is_failure(result: Any, expected_reason: str | None = None) -> None:
    """Every requirement the contract places on a failure terminal."""
    assert isinstance(result, AssistantMessage)
    assert result.stop_reason in FAILURE_REASONS, result.stop_reason
    assert result.is_failure is True
    assert result.error_message, "a failure must carry a non-empty error_message"
    if expected_reason is not None:
        assert result.stop_reason == expected_reason


# ── failure mode 1: provider raises before producing a stream ────────


@pytest.mark.parametrize(
    ("label", "error"),
    [
        ("timeout", TimeoutError("request timed out after 60s")),
        ("http_4xx", RuntimeError("HTTP 429 Too Many Requests")),
        ("http_5xx", RuntimeError("HTTP 503 Service Unavailable")),
        ("malformed_payload", ValueError("Expecting value: line 1 column 1 (char 0)")),
        ("connection_reset", ConnectionResetError("Connection reset by peer")),
        ("bare_exception", Exception()),
    ],
)
async def test_sync_raise_becomes_error_terminal(label: str, error: BaseException) -> None:
    """A provider raising synchronously must not propagate."""

    def provider(m: Model, c: Context, o: SimpleStreamOptions | None = None) -> Any:
        raise error

    stream = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
    result = await asyncio.wait_for(stream.result(), timeout=5)
    _assert_is_failure(result, "error")


async def test_async_raise_becomes_error_terminal() -> None:
    """A provider raising while awaited must not propagate either."""

    async def provider(m: Model, c: Context, o: SimpleStreamOptions | None = None) -> Any:
        await asyncio.sleep(0)
        raise RuntimeError("HTTP 500 Internal Server Error")

    stream = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
    result = await asyncio.wait_for(stream.result(), timeout=5)
    _assert_is_failure(result, "error")
    assert "500" in result.error_message


async def test_raise_records_provider_threw_diagnostic() -> None:
    """A contract violation is tagged so it is distinguishable in a transcript."""

    def provider(m: Model, c: Context, o: SimpleStreamOptions | None = None) -> Any:
        raise RuntimeError("boom")

    stream = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
    result = await asyncio.wait_for(stream.result(), timeout=5)
    assert result.diagnostics is not None
    assert result.diagnostics[0].type == DIAGNOSTIC_PROVIDER_THREW
    assert result.diagnostics[0].error is not None
    assert result.diagnostics[0].error.name == "RuntimeError"
    assert result.diagnostics[0].error.stack is not None


async def test_non_stream_return_becomes_error_terminal() -> None:
    """Returning the wrong type is a violation the loop must not see."""

    def provider(m: Model, c: Context, o: SimpleStreamOptions | None = None) -> Any:
        return {"not": "a stream"}

    stream = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
    result = await asyncio.wait_for(stream.result(), timeout=5)
    _assert_is_failure(result, "error")
    assert "event stream" in result.error_message


# ── failure mode 2: provider raises mid-stream ───────────────────────


async def test_mid_stream_raise_preserves_earlier_events() -> None:
    """A partial response is kept; only the terminal is synthesized."""

    def provider(m: Model, c: Context, o: SimpleStreamOptions | None = None) -> Any:
        async def broken() -> AsyncIterator[Any]:
            yield _start()
            yield _text_start()
            yield _text_delta("partial ")
            raise ConnectionResetError("stream died mid-flight")

        return _IterableStream(broken())

    guarded = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
    seen = [event async for event in guarded]
    result = await asyncio.wait_for(guarded.result(), timeout=5)

    types = [event.type for event in seen]
    assert types[:3] == ["start", "text_start", "text_delta"]
    assert types[-1] == "error", "the guard must append exactly one terminal"
    assert types.count("error") == 1
    _assert_is_failure(result, "error")


# ── failure mode 3: stream ends with no terminal event ───────────────


async def test_unterminated_stream_is_completed() -> None:
    """Without this, ``result()`` would hang the whole run forever."""

    def provider(m: Model, c: Context, o: SimpleStreamOptions | None = None) -> Any:
        async def truncated() -> AsyncIterator[Any]:
            yield _start()
            yield _text_delta("cut off")

        return _IterableStream(truncated())

    guarded = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
    result = await asyncio.wait_for(guarded.result(), timeout=5)
    _assert_is_failure(result, "error")
    assert result.diagnostics is not None
    assert result.diagnostics[0].type == DIAGNOSTIC_STREAM_UNTERMINATED


# ── abort: stop_reason must be "aborted", not "error" ────────────────


async def test_abort_before_call_yields_aborted() -> None:
    """An already-aborted signal must not be reported as a provider error."""
    controller = AbortController()
    controller.abort()

    def provider(m: Model, c: Context, o: SimpleStreamOptions | None = None) -> Any:
        raise RuntimeError("cancelled")

    options = SimpleStreamOptions(signal=controller.signal)
    stream = await guard_stream_fn(provider)(MODEL, CONTEXT, options)
    result = await asyncio.wait_for(stream.result(), timeout=5)
    _assert_is_failure(result, "aborted")


async def test_mid_stream_abort_yields_aborted() -> None:
    """The realistic case: the user interrupts while tokens are streaming."""
    controller = AbortController()

    def provider(m: Model, c: Context, o: SimpleStreamOptions | None = None) -> Any:
        async def interruptible() -> AsyncIterator[Any]:
            yield _start()
            for index in range(100):
                if controller.signal.aborted:
                    return  # cooperative: stop without a terminal event
                yield _text_delta(f"{index} ")
                await asyncio.sleep(0)

        return _IterableStream(interruptible())

    options = SimpleStreamOptions(signal=controller.signal)
    guarded = await guard_stream_fn(provider)(MODEL, CONTEXT, options)

    count = 0
    async for _event in guarded:
        count += 1
        if count == 3:
            controller.abort()

    result = await asyncio.wait_for(guarded.result(), timeout=5)
    _assert_is_failure(result, "aborted")


async def test_abort_reason_first_wins_and_reaches_error_message() -> None:
    """Idempotent abort: the first reason is the one an operator sees."""
    controller = AbortController()
    controller.abort(RuntimeError("user pressed escape"))
    controller.abort(RuntimeError("timeout also fired"))

    def provider(m: Model, c: Context, o: SimpleStreamOptions | None = None) -> Any:
        async def stopped() -> AsyncIterator[Any]:
            return
            yield  # pragma: no cover - makes this an async generator

        return _IterableStream(stopped())

    options = SimpleStreamOptions(signal=controller.signal)
    guarded = await guard_stream_fn(provider)(MODEL, CONTEXT, options)
    result = await asyncio.wait_for(guarded.result(), timeout=5)
    _assert_is_failure(result, "aborted")
    assert result.error_message == "user pressed escape"


# ── the happy path must survive the guard unchanged ──────────────────


async def test_well_behaved_provider_passes_through() -> None:
    """The guard must be transparent when nothing goes wrong.

    Without this, the suite above could pass with a guard that turns
    *every* call into a failure.
    """
    expected = _message()

    def provider(m: Model, c: Context, o: SimpleStreamOptions | None = None) -> Any:
        async def good() -> AsyncIterator[Any]:
            yield _start()
            yield _text_start()
            yield _text_delta("hello")
            yield _done(expected)

        return _IterableStream(good())

    guarded = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
    seen = [event async for event in guarded]
    result = await asyncio.wait_for(guarded.result(), timeout=5)

    assert [event.type for event in seen] == ["start", "text_start", "text_delta", "done"]
    assert result is expected
    assert result.stop_reason == "stop"
    assert result.is_failure is False
    assert result.diagnostics is None


async def test_result_resolves_without_iterating() -> None:
    """Non-streaming callers never iterate; the relay must still run.

    This is the regression test for a lazily-started relay, which would
    deadlock every ``complete``-style call site.
    """
    expected = _message()

    def provider(m: Model, c: Context, o: SimpleStreamOptions | None = None) -> Any:
        async def good() -> AsyncIterator[Any]:
            yield _start()
            yield _done(expected)

        return _IterableStream(good())

    guarded = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
    result = await asyncio.wait_for(guarded.result(), timeout=5)
    assert result is expected
