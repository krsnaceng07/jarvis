"""Stdlib-only driver mirroring tests/test_stream_contract_phase57.py.

Why this file exists: the dev sandbox used for this port has no pytest and
no network to install it, so the pytest suite (which is the committed,
authoritative gate) could not be executed there. This driver runs the same
assertions using only unittest + asyncio so the behaviour was actually
verified rather than assumed.

Run: python3 packages/llm_client/tools/verify_stream_contract.py
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any, AsyncIterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jarvis_llm import (  # noqa: E402
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
from jarvis_llm.stream import (  # noqa: E402
    DIAGNOSTIC_PROVIDER_THREW,
    DIAGNOSTIC_STREAM_UNTERMINATED,
)
from jarvis_llm.validation import (  # noqa: E402
    ToolValidationError,
    validate_tool_arguments,
    validate_tool_call,
)
from jarvis_llm.types import Tool, ToolCall  # noqa: E402

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


def success_message() -> AssistantMessage:
    return AssistantMessage(
        api=MODEL.api,
        provider=MODEL.provider,
        model=MODEL.id,
        content=[],
        usage=empty_usage(),
        stop_reason="stop",
        timestamp=0,
    )


PARTIAL = AssistantMessage(
    api=MODEL.api,
    provider=MODEL.provider,
    model=MODEL.id,
    content=[],
    usage=empty_usage(),
    stop_reason="stop",
    timestamp=0,
)


def ev_start() -> Any:
    return StreamEventStart(partial=PARTIAL)


def ev_text_start() -> Any:
    return StreamEventTextStart(content_index=0, partial=PARTIAL)


def ev_text_delta(delta: str) -> Any:
    return StreamEventTextDelta(content_index=0, delta=delta)


def ev_done(message: AssistantMessage) -> Any:
    return StreamEventDone(reason="stop", message=message)


class IterableStream:
    def __init__(self, iterator: AsyncIterator[Any]) -> None:
        self._iterator = iterator

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterator

    async def result(self) -> AssistantMessage:
        raise AssertionError("the guard must not await the provider's own result()")


class StreamContractTest(unittest.TestCase):
    def assert_failure(self, result: Any, expected: str | None = None) -> None:
        self.assertIsInstance(result, AssistantMessage)
        self.assertIn(result.stop_reason, FAILURE_REASONS)
        self.assertTrue(result.is_failure)
        self.assertTrue(result.error_message)
        if expected is not None:
            self.assertEqual(result.stop_reason, expected)

    def run_async(self, coro: Any) -> Any:
        return asyncio.run(asyncio.wait_for(coro, timeout=5))

    # mode 1
    def test_sync_raises(self) -> None:
        cases = [
            TimeoutError("request timed out after 60s"),
            RuntimeError("HTTP 429 Too Many Requests"),
            RuntimeError("HTTP 503 Service Unavailable"),
            ValueError("Expecting value: line 1 column 1 (char 0)"),
            ConnectionResetError("Connection reset by peer"),
            Exception(),
        ]
        for error in cases:
            with self.subTest(error=type(error).__name__):

                def provider(m, c, o=None, _error=error):
                    raise _error

                async def go():
                    stream = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
                    return await stream.result()

                self.assert_failure(self.run_async(go()), "error")

    def test_async_raise(self) -> None:
        async def provider(m, c, o=None):
            await asyncio.sleep(0)
            raise RuntimeError("HTTP 500 Internal Server Error")

        async def go():
            stream = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
            return await stream.result()

        result = self.run_async(go())
        self.assert_failure(result, "error")
        self.assertIn("500", result.error_message)

    def test_diagnostic_tag(self) -> None:
        def provider(m, c, o=None):
            raise RuntimeError("boom")

        async def go():
            stream = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
            return await stream.result()

        result = self.run_async(go())
        self.assertIsNotNone(result.diagnostics)
        self.assertEqual(result.diagnostics[0].type, DIAGNOSTIC_PROVIDER_THREW)
        self.assertEqual(result.diagnostics[0].error.name, "RuntimeError")

    def test_non_stream_return(self) -> None:
        def provider(m, c, o=None):
            return {"not": "a stream"}

        async def go():
            stream = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
            return await stream.result()

        result = self.run_async(go())
        self.assert_failure(result, "error")
        self.assertIn("event stream", result.error_message)

    # mode 2
    def test_mid_stream_raise(self) -> None:
        def provider(m, c, o=None):
            async def broken():
                yield ev_start()
                yield ev_text_start()
                yield ev_text_delta("partial ")
                raise ConnectionResetError("stream died mid-flight")

            return IterableStream(broken())

        async def go():
            guarded = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
            seen = [event async for event in guarded]
            return seen, await guarded.result()

        seen, result = self.run_async(go())
        types = [event.type for event in seen]
        self.assertEqual(types[:3], ["start", "text_start", "text_delta"])
        self.assertEqual(types[-1], "error")
        self.assertEqual(types.count("error"), 1)
        self.assert_failure(result, "error")

    # mode 3
    def test_unterminated(self) -> None:
        def provider(m, c, o=None):
            async def truncated():
                yield ev_start()
                yield ev_text_delta("cut off")

            return IterableStream(truncated())

        async def go():
            guarded = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
            return await guarded.result()

        result = self.run_async(go())
        self.assert_failure(result, "error")
        self.assertEqual(result.diagnostics[0].type, DIAGNOSTIC_STREAM_UNTERMINATED)

    # abort
    def test_abort_before_call(self) -> None:
        controller = AbortController()
        controller.abort()

        def provider(m, c, o=None):
            raise RuntimeError("cancelled")

        async def go():
            options = SimpleStreamOptions(signal=controller.signal)
            stream = await guard_stream_fn(provider)(MODEL, CONTEXT, options)
            return await stream.result()

        self.assert_failure(self.run_async(go()), "aborted")

    def test_mid_stream_abort(self) -> None:
        controller = AbortController()

        def provider(m, c, o=None):
            async def interruptible():
                yield ev_start()
                for index in range(100):
                    if controller.signal.aborted:
                        return
                    yield ev_text_delta(f"{index} ")
                    await asyncio.sleep(0)

            return IterableStream(interruptible())

        async def go():
            options = SimpleStreamOptions(signal=controller.signal)
            guarded = await guard_stream_fn(provider)(MODEL, CONTEXT, options)
            count = 0
            async for _event in guarded:
                count += 1
                if count == 3:
                    controller.abort()
            return await guarded.result()

        self.assert_failure(self.run_async(go()), "aborted")

    def test_abort_reason_first_wins(self) -> None:
        controller = AbortController()
        controller.abort(RuntimeError("user pressed escape"))
        controller.abort(RuntimeError("timeout also fired"))

        def provider(m, c, o=None):
            async def stopped():
                if False:
                    yield ev_start()

            return IterableStream(stopped())

        async def go():
            options = SimpleStreamOptions(signal=controller.signal)
            guarded = await guard_stream_fn(provider)(MODEL, CONTEXT, options)
            return await guarded.result()

        result = self.run_async(go())
        self.assert_failure(result, "aborted")
        self.assertEqual(result.error_message, "user pressed escape")

    # happy path
    def test_passthrough(self) -> None:
        expected = success_message()

        def provider(m, c, o=None):
            async def good():
                yield ev_start()
                yield ev_text_start()
                yield ev_text_delta("hello")
                yield ev_done(expected)

            return IterableStream(good())

        async def go():
            guarded = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
            seen = [event async for event in guarded]
            return seen, await guarded.result()

        seen, result = self.run_async(go())
        self.assertEqual(
            [event.type for event in seen],
            ["start", "text_start", "text_delta", "done"],
        )
        self.assertIs(result, expected)
        self.assertFalse(result.is_failure)
        self.assertIsNone(result.diagnostics)

    def test_result_without_iterating(self) -> None:
        expected = success_message()

        def provider(m, c, o=None):
            async def good():
                yield ev_start()
                yield ev_done(expected)

            return IterableStream(good())

        async def go():
            guarded = await guard_stream_fn(provider)(MODEL, CONTEXT, None)
            return await guarded.result()

        self.assertIs(self.run_async(go()), expected)


class ValidationTest(unittest.TestCase):
    def tool(self, parameters: dict) -> Tool:
        return Tool(name="t", description="d", parameters=parameters)

    def call(self, arguments: dict) -> ToolCall:
        return ToolCall(id="1", name="t", arguments=arguments)

    def test_string_number_coerced(self) -> None:
        tool = self.tool(
            {"type": "object", "properties": {"n": {"type": "number"}}, "required": ["n"]}
        )
        self.assertEqual(validate_tool_arguments(tool, self.call({"n": "3"})), {"n": 3})

    def test_string_bool_coerced(self) -> None:
        tool = self.tool({"type": "object", "properties": {"b": {"type": "boolean"}}})
        self.assertEqual(validate_tool_arguments(tool, self.call({"b": "true"})), {"b": True})

    def test_json_string_object_coerced(self) -> None:
        tool = self.tool(
            {
                "type": "object",
                "properties": {"o": {"type": "object", "properties": {"k": {"type": "string"}}}},
            }
        )
        self.assertEqual(
            validate_tool_arguments(tool, self.call({"o": '{"k":"v"}'})), {"o": {"k": "v"}}
        )

    def test_nullable_union_keeps_null(self) -> None:
        """The load-bearing null pre-pass: must stay None, not become ''."""
        tool = self.tool(
            {
                "type": "object",
                "properties": {"s": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
            }
        )
        self.assertEqual(validate_tool_arguments(tool, self.call({"s": None})), {"s": None})

    def test_required_missing_rejected(self) -> None:
        tool = self.tool(
            {"type": "object", "properties": {"n": {"type": "number"}}, "required": ["n"]}
        )
        with self.assertRaises(ToolValidationError) as ctx:
            validate_tool_arguments(tool, self.call({}))
        self.assertIn("n: Required property missing", str(ctx.exception))
        self.assertIn("Received arguments:", str(ctx.exception))

    def test_uncoercible_rejected(self) -> None:
        tool = self.tool({"type": "object", "properties": {"n": {"type": "number"}}})
        with self.assertRaises(ToolValidationError):
            validate_tool_arguments(tool, self.call({"n": "not a number"}))

    def test_enum_enforced(self) -> None:
        tool = self.tool({"type": "object", "properties": {"m": {"enum": ["a", "b"]}}})
        self.assertEqual(validate_tool_arguments(tool, self.call({"m": "a"})), {"m": "a"})
        with self.assertRaises(ToolValidationError):
            validate_tool_arguments(tool, self.call({"m": "c"}))

    def test_nested_array_items_coerced(self) -> None:
        tool = self.tool(
            {
                "type": "object",
                "properties": {"xs": {"type": "array", "items": {"type": "integer"}}},
            }
        )
        self.assertEqual(
            validate_tool_arguments(tool, self.call({"xs": ["1", "2"]})), {"xs": [1, 2]}
        )

    def test_bool_is_not_a_number(self) -> None:
        """Python's bool-is-int trap: True must not satisfy type: integer."""
        tool = self.tool({"type": "object", "properties": {"n": {"type": "integer"}}})
        # A bool coerces to 1/0 per coercePrimitiveByType, matching TS.
        self.assertEqual(validate_tool_arguments(tool, self.call({"n": True})), {"n": 1})

    def test_string_from_number_uses_js_formatting(self) -> None:
        tool = self.tool({"type": "object", "properties": {"s": {"type": "string"}}})
        self.assertEqual(validate_tool_arguments(tool, self.call({"s": 3.0})), {"s": "3"})

    def test_unknown_tool_rejected(self) -> None:
        with self.assertRaises(ToolValidationError) as ctx:
            validate_tool_call([], self.call({}))
        self.assertIn('Tool "t" not found', str(ctx.exception))

    def test_oversized_json_string_not_parsed(self) -> None:
        """DoS guard: past the length bound, no parse is attempted."""
        tool = self.tool({"type": "object", "properties": {"o": {"type": "object"}}})
        payload = '{"k":"' + "x" * 70_000 + '"}'
        with self.assertRaises(ToolValidationError):
            validate_tool_arguments(tool, self.call({"o": payload}))

    def test_additional_properties_false(self) -> None:
        tool = self.tool(
            {
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "additionalProperties": False,
            }
        )
        with self.assertRaises(ToolValidationError):
            validate_tool_arguments(tool, self.call({"a": "x", "b": "y"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
