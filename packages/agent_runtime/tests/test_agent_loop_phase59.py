"""Phase 5.9 tests for ``jarvis_agent.agent_loop``.

Ported from ``packages/agent-core/src/agent-loop.test.ts`` (1,847 lines) —
the non-``Agent``-class subset. Vectors that construct ``new Agent(...)``
(interruption-guidance replay, ``Agent.continue`` coded error, both
follow-up queue tests, "Agent next-turn preparation") are deferred to
Phase 5.11 with the Agent class itself.

Python adaptations, each marked at its site:

- ``queueMicrotask`` push scheduling is unnecessary: ``EventStream``
  queues events pushed before iteration begins, so producers push
  synchronously before returning the stream.
- TypeBox schemas become plain JSON Schema dicts.
- ``vi.fn`` call tracking becomes explicit counters/lists.
- TS ``config.reasoning`` lives at ``config.stream_options.reasoning``
  (AgentLoopConfig nests SimpleStreamOptions instead of extending it).
- The "preserves extra tool result fields" vector adapts: Python's
  ``AgentToolResult`` is a fixed dataclass, so there is no ad-hoc
  ``extra`` field to preserve; the test asserts the spread-preserving
  behaviour on the fields that exist (content kept, details patched,
  terminate set).
"""

from __future__ import annotations

import asyncio

import pytest

from jarvis_llm.abort import AbortController
from jarvis_llm.event_stream import EventStream, create_assistant_message_event_stream
from jarvis_llm.types import (
    AssistantMessage,
    Cost,
    Model,
    ModelCost,
    SimpleStreamOptions,
    StreamEventDone,
    StreamEventStart,
    StreamEventTextDelta,
    StreamEventTextEnd,
    StreamEventTextStart,
    StreamEventToolCallEnd,
    StreamEventToolCallStart,
    TextContent,
    ToolCall,
    Usage,
    UserMessage,
)

from jarvis_agent.agent_loop import (
    agent_loop,
    agent_loop_continue,
    run_agent_loop,
    run_agent_loop_continue,
)
from jarvis_agent.errors import (
    TRANSCRIPT_NOT_CONTINUABLE_ERROR_CODE,
    TranscriptNotContinuableError,
)
from jarvis_agent.types import (
    AfterToolCallResult,
    AgentContext,
    AgentLoopConfig,
    AgentToolResult,
    BeforeToolCallResult,
)

# ─────────────────────────────────────────────────────────────────────
# Shared fixtures (top of agent-loop.test.ts)
# ─────────────────────────────────────────────────────────────────────

MODEL = Model(
    id="test-model",
    name="Test Model",
    api="test-api",
    provider="test-provider",
    base_url="https://example.test",
    reasoning=False,
    input=("text",),
    cost=ModelCost(input=0, output=0, cache_read=0, cache_write=0),
    context_window=1000,
    max_tokens=1000,
)

EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def make_usage() -> Usage:
    return Usage(
        input=0,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=0,
        cost=Cost(input=0, output=0, cache_read=0, cache_write=0, total=0),
    )


def make_config(**overrides) -> AgentLoopConfig:
    base = dict(model=MODEL, convert_to_llm=lambda messages: list(messages))
    base.update(overrides)
    return AgentLoopConfig(**base)


async def failing_stream_fn(*_args, **_kwargs):
    raise RuntimeError("provider exploded")


def make_assistant_message(content, *, active_model: Model = MODEL) -> AssistantMessage:
    """Parity: the termination suite's ``makeAssistantMessage`` helper."""
    return AssistantMessage(
        api=active_model.api,
        provider=active_model.provider,
        model=active_model.id,
        content=list(content),
        usage=make_usage(),
        stop_reason=("toolUse" if any(item.type == "toolCall" for item in content) else "stop"),
        timestamp=1,
    )


class FakeTool:
    """Structural AgentTool (a Protocol — no inheritance needed)."""

    def __init__(
        self,
        name: str,
        executed: list | None = None,
        *,
        parameters: dict | None = None,
        execution_mode: str | None = None,
        hide_from_channel_progress: bool | None = None,
        execute=None,
    ) -> None:
        self.name = name
        self.label = name
        self.description = name
        self.parameters = parameters or EMPTY_SCHEMA
        self.output_schema = None
        self.hide_from_channel_progress = hide_from_channel_progress
        self.execution_mode = execution_mode
        self._executed = executed
        self._execute = execute

    async def execute(self, tool_call_id, params, signal=None, on_update=None):
        if self._execute is not None:
            return await self._execute(tool_call_id, params, signal, on_update)
        if self._executed is not None:
            self._executed.append(self.name)
        return AgentToolResult(
            content=[TextContent(text=f"{self.name} result")],
            details={"name": self.name},
        )


def push_done(stream, message: AssistantMessage, *, end: bool = True) -> None:
    reason = "toolUse" if message.stop_reason == "toolUse" else message.stop_reason
    stream.push(StreamEventDone(reason=reason, message=message))
    if end:
        stream.end()


async def collect_events(stream) -> list:
    events = []
    async for event in stream:
        events.append(event)
    return events


def expect_terminal_failure(events, result) -> None:
    assert "agent_end" in [event.type for event in events]
    assert len(result) == 1
    failure = result[0]
    assert failure.role == "assistant"
    assert failure.stop_reason == "error"
    assert failure.error_message == "provider exploded"


# ─────────────────────────────────────────────────────────────────────
# describe("agentLoop EventStream failures")
# ─────────────────────────────────────────────────────────────────────


class TestEventStreamFailures:
    async def test_ends_the_public_stream_when_a_new_prompt_run_rejects(self) -> None:
        stream = agent_loop(
            [UserMessage(content="hello", timestamp=1)],
            AgentContext(system_prompt="", messages=[]),
            make_config(),
            None,
            failing_stream_fn,
        )
        assert isinstance(stream, EventStream)

        events = await collect_events(stream)
        result = await stream.result()

        expect_terminal_failure(events, result)

    async def test_ends_the_public_stream_when_a_continue_run_rejects(self) -> None:
        context = AgentContext(
            system_prompt="",
            messages=[UserMessage(content="hello", timestamp=1)],
        )
        stream = agent_loop_continue(context, make_config(), None, failing_stream_fn)

        events = await collect_events(stream)
        result = await stream.result()

        expect_terminal_failure(events, result)


# ─────────────────────────────────────────────────────────────────────
# describe("agentLoop continuation guards")
# ─────────────────────────────────────────────────────────────────────


def make_assistant_tail_context() -> AgentContext:
    return AgentContext(
        system_prompt="",
        messages=[
            AssistantMessage(
                api=MODEL.api,
                provider=MODEL.provider,
                model=MODEL.id,
                content=[TextContent(text="done")],
                usage=make_usage(),
                stop_reason="stop",
                timestamp=1,
            )
        ],
    )


class TestContinuationGuards:
    async def test_throws_a_coded_error_from_the_public_continue_stream_guard(
        self,
    ) -> None:
        # TS asserts synchronously; agent_loop_continue guards before
        # backgrounding the runner, so the raise is synchronous here too.
        try:
            agent_loop_continue(make_assistant_tail_context(), make_config())
        except TranscriptNotContinuableError as error:
            assert error.code == TRANSCRIPT_NOT_CONTINUABLE_ERROR_CODE
            assert error.role == "assistant"
        else:  # pragma: no cover - parity guard
            raise AssertionError("expected TranscriptNotContinuableError")

    async def test_throws_a_coded_error_from_the_async_continue_runner_guard(
        self,
    ) -> None:
        async def emit(_event) -> None:
            return None

        try:
            await run_agent_loop_continue(make_assistant_tail_context(), make_config(), emit)
        except TranscriptNotContinuableError as error:
            assert error.code == TRANSCRIPT_NOT_CONTINUABLE_ERROR_CODE
            assert error.role == "assistant"
        else:  # pragma: no cover - parity guard
            raise AssertionError("expected TranscriptNotContinuableError")

    async def test_continue_with_empty_context_raises(self) -> None:
        # Source-derived guard (TS: `throw new Error("Cannot continue: no
        # messages in context")`); no dedicated upstream vector.
        with pytest.raises(RuntimeError, match="Cannot continue: no messages"):
            agent_loop_continue(AgentContext(system_prompt="", messages=[]), make_config())


# ─────────────────────────────────────────────────────────────────────
# describe("agentLoop streaming updates")
# ─────────────────────────────────────────────────────────────────────


class TestStreamingUpdates:
    async def test_rebuilds_assistant_snapshots_for_text_deltas_without_partials(
        self,
    ) -> None:
        async def stream_fn(*_args, **_kwargs):
            stream = create_assistant_message_event_stream()
            start_message = AssistantMessage(
                api=MODEL.api,
                provider=MODEL.provider,
                model=MODEL.id,
                content=[],
                usage=make_usage(),
                stop_reason="stop",
                timestamp=1,
            )
            final_message = AssistantMessage(
                api=MODEL.api,
                provider=MODEL.provider,
                model=MODEL.id,
                content=[TextContent(text="Hello world")],
                usage=make_usage(),
                stop_reason="stop",
                timestamp=1,
            )
            stream.push(StreamEventStart(partial=start_message))
            stream.push(StreamEventTextStart(content_index=0, partial=start_message))
            # Parity point: the deltas deliberately omit `partial`.
            stream.push(StreamEventTextDelta(content_index=0, delta="Hello"))
            stream.push(StreamEventTextDelta(content_index=0, delta=" world"))
            stream.push(
                StreamEventTextEnd(content_index=0, content="Hello world", partial=final_message)
            )
            stream.push(StreamEventDone(reason="stop", message=final_message))
            return stream

        stream = agent_loop(
            [UserMessage(content="hello", timestamp=1)],
            AgentContext(system_prompt="", messages=[]),
            make_config(),
            None,
            stream_fn,
        )
        events = await collect_events(stream)

        delta_updates = [
            event
            for event in events
            if event.type == "message_update" and event.assistant_message_event.type == "text_delta"
        ]
        assert len(delta_updates) == 2
        snapshots = [
            [(item.type, item.text) for item in event.message.content] for event in delta_updates
        ]
        assert snapshots == [[("text", "Hello")], [("text", "Hello world")]]
        for update in delta_updates:
            assert update.assistant_message_event.partial is None

    async def test_does_not_execute_tool_calls_from_a_max_token_truncated_turn(
        self,
    ) -> None:
        execute_calls: list = []

        async def execute(tool_call_id, params, signal=None, on_update=None):
            execute_calls.append(tool_call_id)
            return AgentToolResult(content=[TextContent(text="should not run")], details={})

        contexts: list = []
        stream_calls = 0

        async def stream_fn(_model, context, _options):
            nonlocal stream_calls
            contexts.append(context)
            stream_calls += 1
            stream = create_assistant_message_event_stream()
            if stream_calls > 1:
                message = AssistantMessage(
                    api=MODEL.api,
                    provider=MODEL.provider,
                    model=MODEL.id,
                    content=[TextContent(text="continued")],
                    usage=make_usage(),
                    stop_reason="stop",
                    timestamp=2,
                )
                stream.push(StreamEventDone(reason="stop", message=message))
                return stream
            tool_call = ToolCall(id="call-truncated-spawn", name="sessions_spawn", arguments={})
            message = AssistantMessage(
                api=MODEL.api,
                provider=MODEL.provider,
                model=MODEL.id,
                content=[TextContent(text="spawning"), tool_call],
                usage=make_usage(),
                stop_reason="length",
                timestamp=1,
            )
            import dataclasses as _dc

            stream.push(StreamEventStart(partial=_dc.replace(message, content=[])))
            stream.push(StreamEventToolCallStart(content_index=1, partial=message))
            stream.push(
                StreamEventToolCallEnd(content_index=1, tool_call=tool_call, partial=message)
            )
            stream.push(StreamEventDone(reason="length", message=message))
            return stream

        async def get_follow_up_messages(*_args, **_kwargs):
            if stream_calls == 1:
                return [UserMessage(content="continue", timestamp=2)]
            return []

        stream = agent_loop(
            [UserMessage(content="spawn specialists", timestamp=1)],
            AgentContext(
                system_prompt="",
                messages=[],
                tools=[FakeTool("sessions_spawn", execute=execute)],
            ),
            make_config(get_follow_up_messages=get_follow_up_messages),
            None,
            stream_fn,
        )

        events = await collect_events(stream)
        messages = await stream.result()

        truncated_message_end = next(
            (
                event
                for event in events
                if event.type == "message_end"
                and getattr(event.message, "role", None) == "assistant"
                and event.message.stop_reason == "length"
            ),
            None,
        )
        replayed_truncated = contexts[1].messages[1]

        assert truncated_message_end is not None
        assert execute_calls == []
        assert not any(event.type == "tool_execution_start" for event in events)
        assert [message.role for message in messages] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert messages[1].role == "assistant"
        assert messages[1].stop_reason == "length"
        assert not any(item.type == "toolCall" for item in messages[1].content)
        assert not any(item.type == "toolCall" for item in truncated_message_end.message.content)
        assert replayed_truncated.role == "assistant"
        assert replayed_truncated.stop_reason == "length"
        assert not any(item.type == "toolCall" for item in replayed_truncated.content)


# ─────────────────────────────────────────────────────────────────────
# describe("runAgentLoop deferred tool hydration")
# ─────────────────────────────────────────────────────────────────────


def deferred_stream_fn_factory(first_content, contexts=None):
    """One toolUse turn then a plain stop turn, capturing request contexts."""
    state = {"calls": 0}

    async def stream_fn(_model, context, _options):
        if contexts is not None:
            # TS snapshots `context.tools?.slice()` at call time.
            contexts.append(list(context.tools or []))
        stream = create_assistant_message_event_stream()
        state["calls"] += 1
        if state["calls"] == 1:
            message = AssistantMessage(
                api="faux",
                provider="faux",
                model="faux-1",
                content=list(first_content),
                usage=make_usage(),
                stop_reason="toolUse",
                timestamp=1,
            )
        else:
            message = AssistantMessage(
                api="faux",
                provider="faux",
                model="faux-1",
                content=[TextContent(text="done")],
                usage=make_usage(),
                stop_reason="stop",
                timestamp=2,
            )
        push_done(stream, message, end=False)
        return stream

    return stream_fn


async def noop_emit(_event) -> None:
    return None


class TestDeferredToolHydration:
    async def test_hydrates_an_authorized_deferred_tool(self) -> None:
        execute_calls: list = []

        async def execute(tool_call_id, params, signal=None, on_update=None):
            execute_calls.append((tool_call_id, params, signal, on_update))
            return AgentToolResult(content=[TextContent(text="hidden ok")], details={"ok": True})

        hidden_tool = FakeTool(
            "hidden_search",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execute=execute,
        )
        contexts: list = []
        resolver_calls = []

        def resolve_deferred_tool(_ctx, _signal):
            resolver_calls.append(1)
            return hidden_tool

        messages = await run_agent_loop(
            [UserMessage(content="search penguin", timestamp=1)],
            AgentContext(system_prompt="test", messages=[], tools=[]),
            make_config(resolve_deferred_tool=resolve_deferred_tool),
            noop_emit,
            None,
            deferred_stream_fn_factory(
                [
                    ToolCall(
                        id="call-hidden",
                        name="hidden_search",
                        arguments={"query": "penguin"},
                    )
                ],
                contexts,
            ),
        )

        assert len(resolver_calls) == 1
        assert len(execute_calls) == 1
        call_id, params, signal, on_update = execute_calls[0]
        assert call_id == "call-hidden"
        assert params == {"query": "penguin"}
        assert signal is None
        assert callable(on_update)
        assert [[tool.name for tool in tools] for tools in contexts] == [
            [],
            ["hidden_search"],
        ]
        assert any(message.role == "toolResult" for message in messages)

    async def test_resolves_a_missing_deferred_tool_once(self) -> None:
        resolver_calls = []

        def resolve_deferred_tool(_ctx, _signal):
            resolver_calls.append(1)
            return None

        messages = await run_agent_loop(
            [UserMessage(content="call missing tool", timestamp=1)],
            AgentContext(system_prompt="test", messages=[], tools=[]),
            make_config(resolve_deferred_tool=resolve_deferred_tool),
            noop_emit,
            None,
            deferred_stream_fn_factory(
                [ToolCall(id="call-missing", name="missing_deferred", arguments={})]
            ),
        )

        assert len(resolver_calls) == 1
        assert any(
            message.role == "toolResult"
            and message.tool_name == "missing_deferred"
            and message.is_error
            for message in messages
        )

    async def test_converts_deferred_resolver_failures_into_one_error_result(
        self,
    ) -> None:
        resolver_calls = []

        async def resolve_deferred_tool(_ctx, _signal):
            resolver_calls.append(1)
            raise RuntimeError("deferred hydration failed")

        messages = await run_agent_loop(
            [UserMessage(content="call failing tool", timestamp=1)],
            AgentContext(system_prompt="test", messages=[], tools=[]),
            make_config(resolve_deferred_tool=resolve_deferred_tool),
            noop_emit,
            None,
            deferred_stream_fn_factory(
                [
                    ToolCall(
                        id="call-failing-deferred",
                        name="failing_deferred",
                        arguments={},
                    )
                ]
            ),
        )

        assert len(resolver_calls) == 1
        matching = [
            message
            for message in messages
            if message.role == "toolResult" and message.tool_name == "failing_deferred"
        ]
        assert len(matching) == 1
        assert matching[0].is_error
        assert [(item.type, item.text) for item in matching[0].content] == [
            ("text", "deferred hydration failed")
        ]

    async def test_rejects_deferred_tools_whose_names_differ(self) -> None:
        execute_calls: list = []

        async def execute(tool_call_id, params, signal=None, on_update=None):
            execute_calls.append(tool_call_id)
            return AgentToolResult(
                content=[TextContent(text="wrong tool ran")], details={"ok": True}
            )

        mismatched_tool = FakeTool("other_deferred", execute=execute)
        contexts: list = []

        messages = await run_agent_loop(
            [UserMessage(content="call requested tool", timestamp=1)],
            AgentContext(system_prompt="test", messages=[], tools=[]),
            make_config(resolve_deferred_tool=lambda _ctx, _signal: mismatched_tool),
            noop_emit,
            None,
            deferred_stream_fn_factory(
                [
                    ToolCall(
                        id="call-requested-deferred",
                        name="requested_deferred",
                        arguments={},
                    )
                ],
                contexts,
            ),
        )

        assert execute_calls == []
        assert [[tool.name for tool in tools] for tools in contexts] == [[], []]
        matching = [
            message
            for message in messages
            if message.role == "toolResult" and message.tool_name == "requested_deferred"
        ]
        assert len(matching) == 1
        assert matching[0].is_error
        assert [(item.type, item.text) for item in matching[0].content] == [
            (
                "text",
                'Deferred tool resolver returned "other_deferred" '
                'for requested "requested_deferred"',
            )
        ]

    async def test_hydrates_sequential_deferred_tools_before_choosing_executor(
        self,
    ) -> None:
        active = {"count": 0, "max": 0, "calls": 0}

        async def execute(_tool_call_id, _params, signal=None, on_update=None):
            active["calls"] += 1
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
            await asyncio.sleep(0.005)
            active["count"] -= 1
            return AgentToolResult(content=[TextContent(text="hidden ok")], details={"ok": True})

        hidden_tool = FakeTool(
            "hidden_serial",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execution_mode="sequential",
            execute=execute,
        )
        resolver_calls = []

        def resolve_deferred_tool(_ctx, _signal):
            resolver_calls.append(1)
            return hidden_tool

        await run_agent_loop(
            [UserMessage(content="search twice", timestamp=1)],
            AgentContext(system_prompt="test", messages=[], tools=[]),
            make_config(resolve_deferred_tool=resolve_deferred_tool),
            noop_emit,
            None,
            deferred_stream_fn_factory(
                [
                    ToolCall(
                        id="call-hidden-1",
                        name="hidden_serial",
                        arguments={"query": "one"},
                    ),
                    ToolCall(
                        id="call-hidden-2",
                        name="hidden_serial",
                        arguments={"query": "two"},
                    ),
                ]
            ),
        )

        assert len(resolver_calls) == 1
        assert active["calls"] == 2
        assert active["max"] == 1


# ─────────────────────────────────────────────────────────────────────
# describe("agentLoop tool termination")
# ─────────────────────────────────────────────────────────────────────


def turn_stream_fn_factory(turn_contents):
    """Emit one assistant message per model turn from ``turn_contents``;
    turns beyond the list get a plain "done" text message."""
    state = {"turn": 0}

    async def stream_fn(*_args, **_kwargs):
        stream = create_assistant_message_event_stream()
        index = state["turn"]
        state["turn"] += 1
        if index < len(turn_contents):
            message = make_assistant_message(turn_contents[index])
        else:
            message = make_assistant_message([TextContent(text="done")])
        push_done(stream, message)
        return stream

    stream_fn.state = state
    return stream_fn


ABORT_EVENT_SEQUENCE = [
    "agent_start",
    "turn_start",
    "message_start",
    "message_end",
    "message_start",
    "message_end",
    "tool_execution_start",
    "tool_execution_end",
    "message_start",
    "message_end",
    "turn_end",
    "turn_start",
    "message_start",
    "message_end",
    "turn_end",
    "message_start",
    "message_end",
    "agent_end",
]


class TestToolTermination:
    async def test_marks_lifecycle_events_from_the_concrete_hidden_tool(self) -> None:
        async def execute(_tool_call_id, _args, _signal=None, on_update=None):
            if on_update is not None:
                on_update(
                    AgentToolResult(
                        content=[TextContent(text="still waiting")],
                        details={"status": "waiting"},
                    )
                )
            return AgentToolResult(
                content=[TextContent(text="resumed")],
                details={"status": "completed"},
            )

        hidden_tool = FakeTool("wait", hide_from_channel_progress=True, execute=execute)
        stream_fn = turn_stream_fn_factory([[ToolCall(id="call-wait", name="wait", arguments={})]])

        events = await collect_events(
            agent_loop(
                [UserMessage(content="resume", timestamp=1)],
                AgentContext(system_prompt="", messages=[], tools=[hidden_tool]),
                make_config(tool_execution="sequential"),
                None,
                stream_fn,
            )
        )
        lifecycle = [event for event in events if event.type.startswith("tool_execution_")]

        assert [event.type for event in lifecycle] == [
            "tool_execution_start",
            "tool_execution_update",
            "tool_execution_end",
        ]
        assert all(event.hide_from_channel_progress is True for event in lifecycle)

    async def test_ignores_progress_updates_after_a_tool_execution_settles(
        self,
    ) -> None:
        captured = {}

        async def execute(_tool_call_id, _args, _signal=None, on_update=None):
            captured["on_update"] = on_update
            if on_update is not None:
                on_update(
                    AgentToolResult(
                        content=[TextContent(text="running")],
                        details={"status": "running"},
                    )
                )
            return AgentToolResult(
                content=[TextContent(text="done")],
                details={"status": "done"},
                terminate=True,
            )

        tool = FakeTool("delayed_tool", execute=execute)
        stream_fn = turn_stream_fn_factory(
            [[ToolCall(id="call-delayed", name="delayed_tool", arguments={})]]
        )

        events = await collect_events(
            agent_loop(
                [UserMessage(content="run", timestamp=1)],
                AgentContext(system_prompt="", messages=[], tools=[tool]),
                make_config(tool_execution="sequential"),
                None,
                stream_fn,
            )
        )
        count_after_run = len(events)
        captured["on_update"](
            AgentToolResult(content=[TextContent(text="late")], details={"status": "late"})
        )
        await asyncio.sleep(0)

        assert len(events) == count_after_run
        assert len([event for event in events if event.type == "tool_execution_update"]) == 1

    async def test_continues_after_side_effect_result_without_terminate(self) -> None:
        executed: list = []
        recorded = {"side_effect": False}

        async def after_tool_call(ctx, _signal):
            if ctx.tool_call.name == "message":
                recorded["side_effect"] = True
            return None

        stream_fn = turn_stream_fn_factory(
            [
                [ToolCall(id="call-message", name="message", arguments={})],
                [ToolCall(id="call-exec", name="exec", arguments={})],
            ]
        )

        events = await collect_events(
            agent_loop(
                [UserMessage(content="hello", timestamp=1)],
                AgentContext(
                    system_prompt="",
                    messages=[],
                    tools=[FakeTool("message", executed), FakeTool("exec", executed)],
                ),
                make_config(after_tool_call=after_tool_call),
                None,
                stream_fn,
            )
        )

        assert recorded["side_effect"] is True
        assert stream_fn.state["turn"] == 3
        assert executed == ["message", "exec"]
        starts = [event for event in events if event.type == "tool_execution_start"]
        assert len(starts) == 2
        ends = [event for event in events if event.type == "tool_execution_end"]
        assert [event.execution_started for event in ends] == [True, True]
        assert events[-1].type == "agent_end"

    async def test_normalizes_a_tool_result_with_missing_content(self) -> None:
        contexts: list = []
        state = {"turn": 0}

        async def stream_fn(_model, context, _options):
            contexts.append(context)
            state["turn"] += 1
            stream = create_assistant_message_event_stream()
            if state["turn"] == 1:
                message = make_assistant_message(
                    [ToolCall(id="call-empty", name="empty", arguments={})]
                )
            else:
                message = make_assistant_message([TextContent(text="done")])
            push_done(stream, message)
            return stream

        async def execute(_tool_call_id, _args, _signal=None, _on_update=None):
            # TS returns `{ details: { ok: true } }` with no content field.
            return AgentToolResult(details={"ok": True})

        tool = FakeTool("empty", execute=execute)

        await collect_events(
            agent_loop(
                [UserMessage(content="run", timestamp=1)],
                AgentContext(system_prompt="", messages=[], tools=[tool]),
                make_config(),
                None,
                stream_fn,
            )
        )

        assert len(contexts) == 2
        assert any(
            getattr(message, "role", None) == "toolResult"
            and message.tool_name == "empty"
            and message.content == []
            for message in contexts[1].messages
        )

    async def test_preserves_result_fields_when_an_after_hook_patches(self) -> None:
        # Adapted vector — see module docstring: no ad-hoc `extra` field on
        # the Python dataclass, so assert the preserved/patched split on the
        # fields that exist.
        original_content = [TextContent(text="sent")]

        async def execute(_tool_call_id, _args, _signal=None, _on_update=None):
            return AgentToolResult(content=list(original_content), details={"phase": "original"})

        tool = FakeTool("patched", execute=execute)
        stream_fn = turn_stream_fn_factory(
            [[ToolCall(id="call-patched", name="patched", arguments={})]]
        )

        async def after_tool_call(_ctx, _signal):
            return AfterToolCallResult(details={"phase": "patched"}, terminate=True)

        events = await collect_events(
            agent_loop(
                [UserMessage(content="run", timestamp=1)],
                AgentContext(system_prompt="", messages=[], tools=[tool]),
                make_config(after_tool_call=after_tool_call),
                None,
                stream_fn,
            )
        )
        end_event = next(event for event in events if event.type == "tool_execution_end")

        assert end_event.result.content == original_content
        assert end_event.result.details == {"phase": "patched"}
        assert end_event.result.terminate is True

    async def test_marks_policy_blocked_tool_calls_as_not_executed(self) -> None:
        executed: list = []
        stream_fn = turn_stream_fn_factory([[ToolCall(id="call-cron", name="cron", arguments={})]])

        async def before_tool_call(_ctx, _signal):
            return BeforeToolCallResult(block=True, reason="blocked")

        events = await collect_events(
            agent_loop(
                [UserMessage(content="hello", timestamp=1)],
                AgentContext(system_prompt="", messages=[], tools=[FakeTool("cron", executed)]),
                make_config(before_tool_call=before_tool_call),
                None,
                stream_fn,
            )
        )
        end_event = next(event for event in events if event.type == "tool_execution_end")

        assert executed == []
        assert end_event.execution_started is False

    async def test_marks_argument_validation_failures_with_typed_provenance(
        self,
    ) -> None:
        executed: list = []
        tool = FakeTool(
            "edit",
            executed,
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        )
        stream_fn = turn_stream_fn_factory([[ToolCall(id="call-edit", name="edit", arguments={})]])

        events = await collect_events(
            agent_loop(
                [UserMessage(content="hello", timestamp=1)],
                AgentContext(system_prompt="", messages=[], tools=[tool]),
                make_config(),
                None,
                stream_fn,
            )
        )
        end_event = next(event for event in events if event.type == "tool_execution_end")

        assert executed == []
        assert end_event.execution_started is False
        assert end_event.error_kind == "argument-validation"

    async def test_stops_only_when_the_finalized_result_explicitly_terminates(
        self,
    ) -> None:
        executed: list = []
        stream_fn = turn_stream_fn_factory(
            [
                [ToolCall(id="call-message", name="message", arguments={})],
                [ToolCall(id="call-exec", name="exec", arguments={})],
            ]
        )

        async def after_tool_call(ctx, _signal):
            if ctx.tool_call.name == "message":
                return AfterToolCallResult(terminate=True)
            return None

        events = await collect_events(
            agent_loop(
                [UserMessage(content="hello", timestamp=1)],
                AgentContext(
                    system_prompt="",
                    messages=[],
                    tools=[FakeTool("message", executed), FakeTool("exec", executed)],
                ),
                make_config(after_tool_call=after_tool_call),
                None,
                stream_fn,
            )
        )

        assert stream_fn.state["turn"] == 1
        assert executed == ["message"]
        assert len([event for event in events if event.type == "tool_execution_start"]) == 1
        assert events[-1].type == "agent_end"

    async def test_does_not_request_another_model_turn_after_a_tool_aborts(
        self,
    ) -> None:
        controller = AbortController()
        state = {"stream_calls": 0}

        async def stream_fn(*_args, **_kwargs):
            state["stream_calls"] += 1
            if state["stream_calls"] > 1:
                raise RuntimeError("model was called after abort")
            stream = create_assistant_message_event_stream()
            push_done(
                stream,
                make_assistant_message(
                    [ToolCall(id="call-abort", name="abort_tool", arguments={})]
                ),
            )
            return stream

        async def execute(_tool_call_id, _args, _signal=None, _on_update=None):
            controller.abort(RuntimeError("user aborted"))
            return AgentToolResult(content=[TextContent(text="aborted")], details={"aborted": True})

        abort_tool = FakeTool("abort_tool", execute=execute)
        events: list = []

        def emit(event) -> None:
            events.append(event)

        messages = await run_agent_loop(
            [UserMessage(content="abort during tool", timestamp=1)],
            AgentContext(system_prompt="", messages=[], tools=[abort_tool]),
            make_config(),
            emit,
            controller.signal,
            stream_fn,
        )

        assert state["stream_calls"] == 1
        assert [message.role for message in messages] == [
            "user",
            "assistant",
            "toolResult",
            "assistant",
            "custom",
        ]
        assert messages[-2].role == "assistant"
        assert messages[-2].stop_reason == "aborted"
        assert messages[-1].role == "custom"
        assert messages[-1].custom_type == "openclaw:turn-aborted"
        assert messages[-1].display is False
        assert "may have partially executed" in messages[-1].content
        assert [event.type for event in events] == ABORT_EVENT_SEQUENCE
        assert events[-1].type == "agent_end"

    async def test_skips_guidance_when_the_abort_reason_marks_a_turn_handoff(
        self,
    ) -> None:
        controller = AbortController()
        state = {"stream_calls": 0}

        async def stream_fn(*_args, **_kwargs):
            state["stream_calls"] += 1
            if state["stream_calls"] > 1:
                raise RuntimeError("model was called after abort")
            stream = create_assistant_message_event_stream()
            push_done(
                stream,
                make_assistant_message(
                    [ToolCall(id="call-yield", name="yield_tool", arguments={})]
                ),
            )
            return stream

        class _YieldReason(Exception):
            # Parity with the TS `{ code: "sessions_yield", turnHandoff: true }`
            # plain-object reason. Python abort reasons are exceptions
            # (AbortController wraps anything else in AbortError, which would
            # drop these attributes); the `turn_handoff` attribute — not the
            # TurnHandoffAbort type — is what exercises the duck-check.
            code = "sessions_yield"
            turn_handoff = True

        async def execute(_tool_call_id, _args, _signal=None, _on_update=None):
            controller.abort(_YieldReason())
            return AgentToolResult(content=[TextContent(text="yielded")], details={"yielded": True})

        yield_tool = FakeTool("yield_tool", execute=execute)

        messages = await run_agent_loop(
            [UserMessage(content="yield during tool", timestamp=1)],
            AgentContext(system_prompt="", messages=[], tools=[yield_tool]),
            make_config(),
            noop_emit,
            controller.signal,
            stream_fn,
        )

        assert state["stream_calls"] == 1
        assert messages[-1].role == "assistant"
        assert messages[-1].stop_reason == "aborted"
        assert not any(message.role == "custom" for message in messages)

    async def test_does_not_start_prepared_parallel_tools_after_mid_batch_abort(
        self,
    ) -> None:
        controller = AbortController()
        executed: list = []
        after_calls: list = []

        async def after_tool_call(_ctx, _signal):
            after_calls.append(1)
            return None

        async def stream_fn(*_args, **_kwargs):
            stream = create_assistant_message_event_stream()
            push_done(
                stream,
                make_assistant_message(
                    [
                        ToolCall(id="call-paid", name="paid", arguments={}),
                        ToolCall(id="call-gated", name="gated", arguments={}),
                    ]
                ),
            )
            return stream

        async def before_tool_call(ctx, _signal):
            if ctx.tool_call.name == "gated":
                await asyncio.sleep(0)
                controller.abort(RuntimeError("user aborted"))
            return None

        events: list = []

        def emit(event) -> None:
            events.append(event)

        await run_agent_loop(
            [UserMessage(content="abort during parallel tool preparation", timestamp=1)],
            AgentContext(
                system_prompt="",
                messages=[],
                tools=[FakeTool("paid", executed), FakeTool("gated", executed)],
            ),
            make_config(
                tool_execution="parallel",
                before_tool_call=before_tool_call,
                after_tool_call=after_tool_call,
            ),
            emit,
            controller.signal,
            stream_fn,
        )

        end_events = [event for event in events if event.type == "tool_execution_end"]

        assert executed == []
        assert after_calls == []
        assert len(end_events) == 2
        by_name = {event.tool_name: event for event in end_events}
        for name in ("paid", "gated"):
            assert by_name[name].is_error is True
            assert by_name[name].execution_started is False
            assert [(item.type, item.text) for item in by_name[name].result.content] == [
                ("text", "Operation aborted")
            ]

    async def test_does_not_request_another_turn_when_async_hook_aborts(self) -> None:
        controller = AbortController()
        state = {"stream_calls": 0}

        async def stream_fn(*_args, **_kwargs):
            state["stream_calls"] += 1
            if state["stream_calls"] > 1:
                raise RuntimeError("model was called after abort")
            stream = create_assistant_message_event_stream()
            push_done(
                stream,
                make_assistant_message(
                    [ToolCall(id="call-hook-abort", name="hook_abort", arguments={})]
                ),
            )
            return stream

        async def prepare_next_turn(_ctx, _signal=None):
            await asyncio.sleep(0)
            controller.abort(RuntimeError("user aborted"))
            return None

        events: list = []

        def emit(event) -> None:
            events.append(event)

        messages = await run_agent_loop(
            [UserMessage(content="abort from hook", timestamp=1)],
            AgentContext(system_prompt="", messages=[], tools=[FakeTool("hook_abort", [])]),
            make_config(prepare_next_turn=prepare_next_turn),
            emit,
            controller.signal,
            stream_fn,
        )

        assert state["stream_calls"] == 1
        assert [message.role for message in messages] == [
            "user",
            "assistant",
            "toolResult",
            "assistant",
            "custom",
        ]
        assert messages[-2].role == "assistant"
        assert messages[-2].stop_reason == "aborted"
        assert messages[-1].role == "custom"
        assert messages[-1].custom_type == "openclaw:turn-aborted"
        assert [event.type for event in events] == ABORT_EVENT_SEQUENCE
        assert events[-1].type == "agent_end"


# ─────────────────────────────────────────────────────────────────────
# describe("agentLoop thinking state")
# ─────────────────────────────────────────────────────────────────────


FABLE_MODEL = Model(
    id="claude-fable-5",
    name="Test Model",
    api="test-api",
    provider="test-provider",
    base_url="https://example.test",
    reasoning=False,
    input=("text",),
    cost=ModelCost(input=0, output=0, cache_read=0, cache_write=0),
    context_window=1000,
    max_tokens=1000,
    thinking_level_map={"off": "low"},
)


class TestThinkingState:
    @pytest.mark.parametrize(
        ("initial_model", "next_model", "expected"),
        [
            # disables reasoning after leaving Fable
            (FABLE_MODEL, MODEL, ["low", None]),
            # uses Fable's low fallback after entering Fable
            (MODEL, FABLE_MODEL, [None, "low"]),
        ],
    )
    async def test_thinking_transitions(self, initial_model, next_model, expected) -> None:
        observed_reasoning: list = []
        state = {"calls": 0, "prepared": False}

        async def stream_fn(active_model, _context, options):
            observed_reasoning.append(options.reasoning if options else None)
            state["calls"] += 1
            stream = create_assistant_message_event_stream()
            if state["calls"] == 1:
                content = [ToolCall(id="tool-1", name="missing_tool", arguments={})]
            else:
                content = [TextContent(text="done")]
            push_done(stream, make_assistant_message(content, active_model=active_model))
            return stream

        def prepare_next_turn(_ctx, _signal=None):
            if state["prepared"]:
                return None
            state["prepared"] = True
            from jarvis_agent.types import AgentLoopTurnUpdate

            return AgentLoopTurnUpdate(model=next_model)

        initial_reasoning = (
            "low" if (initial_model.thinking_level_map or {}).get("off") == "low" else None
        )
        stream = agent_loop(
            [UserMessage(content="hello", timestamp=1)],
            AgentContext(system_prompt="", messages=[]),
            make_config(
                model=initial_model,
                thinking_level="off",
                # TS `config.reasoning` — nested in Python, see module docstring.
                stream_options=SimpleStreamOptions(reasoning=initial_reasoning),
                prepare_next_turn=prepare_next_turn,
            ),
            None,
            stream_fn,
        )

        await collect_events(stream)

        assert observed_reasoning == expected
