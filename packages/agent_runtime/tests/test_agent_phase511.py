"""Phase 5.11 tests for ``jarvis_agent.agent`` — the ``Agent`` class.

Ports the ``new Agent(...)`` vectors from
``packages/agent-core/src/agent-loop.test.ts`` that Phase 5.9 deferred:

- "persists and replays interruption guidance after Agent aborts a
  rejected run" (EventStream failures suite)
- "throws a coded error from Agent.continue" (continuation guards)
- "delivers a queued follow-up before continuing from a tool result"
- "keeps a queued follow-up behind a trailing user continuation"
- "Agent next-turn preparation" (forwards completed-turn context and
  applies its update to the following request)

Python adaptations, marked at their sites:

- ``Agent.continue`` is :meth:`Agent.continue_`.
- ``const interrupted = agent.prompt(...)`` (an unawaited promise)
  becomes an :func:`asyncio.ensure_future` task.
- ``vi.fn`` call tracking becomes explicit lists.
- ``queueMicrotask`` push scheduling is unnecessary: ``EventStream``
  queues events pushed before iteration begins.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from jarvis_llm.event_stream import create_assistant_message_event_stream
from jarvis_llm.types import (
    AssistantMessage,
    Cost,
    Model,
    ModelCost,
    StreamEventDone,
    TextContent,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
)

from jarvis_agent import (
    Agent,
    AgentInitialState,
    AgentLoopTurnUpdate,
    AgentOptions,
    TRANSCRIPT_NOT_CONTINUABLE_ERROR_CODE,
    TranscriptNotContinuableError,
)
from jarvis_agent.types import AgentToolResult

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


def make_assistant(content, *, active_model: Model = MODEL, stop_reason="stop", timestamp=1) -> AssistantMessage:
    return AssistantMessage(
        api=active_model.api,
        provider=active_model.provider,
        model=active_model.id,
        content=list(content),
        usage=make_usage(),
        stop_reason=stop_reason,
        timestamp=timestamp,
    )


def convert_passthrough(messages):
    """Parity: the tests' ``(messages) => messages as Message[]``."""
    return list(messages)


def filtering_convert(messages):
    """Parity: the explicit role-filtering convertToLlm in the replay test."""
    return [
        message
        for message in messages
        if message.role in ("user", "assistant", "toolResult")
    ]


async def failing_stream_fn(*_args, **_kwargs):
    raise RuntimeError("provider exploded")


# ─────────────────────────────────────────────────────────────────────
# describe("agentLoop EventStream failures") — the Agent vector
# ─────────────────────────────────────────────────────────────────────


class TestInterruptionReplay:
    async def test_persists_and_replays_interruption_guidance_after_abort(
        self,
    ) -> None:
        started = asyncio.Event()

        async def aborting_stream_fn(_model, _context, options=None):
            started.set()
            future = asyncio.get_running_loop().create_future()

            def on_abort() -> None:
                if not future.done():
                    future.set_exception(RuntimeError("provider aborted"))

            options.signal.add_listener(on_abort)
            await future
            raise RuntimeError("unreachable")

        agent = Agent(
            AgentOptions(
                initial_state=AgentInitialState(model=MODEL),
                convert_to_llm=filtering_convert,
                stream_fn=aborting_stream_fn,
            )
        )

        interrupted = asyncio.ensure_future(agent.prompt("perform side effect"))
        await started.wait()
        agent.abort()
        await interrupted

        last = agent.state.messages[-1]
        assert last.role == "custom"
        assert last.custom_type == "openclaw:turn-aborted"

        replayed_messages: list = []
        transformed_messages: list = []

        async def transform_context(messages, _signal=None):
            transformed_messages.extend(messages)
            return messages

        async def replay_stream_fn(_model, context, _options=None):
            replayed_messages.extend(context.messages)
            stream = create_assistant_message_event_stream()
            stream.push(
                StreamEventDone(
                    reason="stop",
                    message=make_assistant(
                        [TextContent(text="continued safely")], timestamp=2
                    ),
                )
            )
            stream.end()
            return stream

        agent.transform_context = transform_context
        agent.stream_fn = replay_stream_fn
        await agent.prompt("continue")

        assert any(
            getattr(message, "role", None) == "custom"
            and getattr(message, "custom_type", None) == "openclaw:turn-aborted"
            for message in transformed_messages
        )
        assert any(
            message.role == "user"
            and any(
                getattr(block, "type", None) == "text"
                and "may have partially executed" in block.text
                for block in (
                    message.content
                    if isinstance(message.content, list)
                    else [TextContent(text=message.content)]
                )
            )
            for message in replayed_messages
        )


# ─────────────────────────────────────────────────────────────────────
# describe("agentLoop continuation guards") — the Agent vectors
# ─────────────────────────────────────────────────────────────────────


def make_assistant_tail_messages() -> list:
    return [make_assistant([TextContent(text="done")])]


class TestAgentContinuationGuards:
    async def test_throws_a_coded_error_from_agent_continue(self) -> None:
        agent = Agent(
            AgentOptions(
                initial_state=AgentInitialState(
                    messages=make_assistant_tail_messages()
                ),
                stream_fn=failing_stream_fn,
            )
        )

        with pytest.raises(TranscriptNotContinuableError) as exc_info:
            await agent.continue_()
        assert exc_info.value.code == TRANSCRIPT_NOT_CONTINUABLE_ERROR_CODE
        assert exc_info.value.role == "assistant"

    async def test_delivers_a_queued_follow_up_before_continuing_from_a_tool_result(
        self,
    ) -> None:
        request_contexts: list = []

        async def stream_fn(active_model, context, _options=None):
            request_contexts.append(context)
            stream = create_assistant_message_event_stream()
            stream.push(
                StreamEventDone(
                    reason="stop",
                    message=make_assistant(
                        [TextContent(text="done")],
                        active_model=active_model,
                        timestamp=3,
                    ),
                )
            )
            stream.end()
            return stream

        agent = Agent(
            AgentOptions(
                initial_state=AgentInitialState(
                    model=MODEL,
                    system_prompt="",
                    tools=[],
                    messages=[
                        ToolResultMessage(
                            tool_call_id="call-finish",
                            tool_name="finish",
                            content=[TextContent(text="finished")],
                            details={},
                            is_error=False,
                            timestamp=1,
                        )
                    ],
                ),
                convert_to_llm=convert_passthrough,
                stream_fn=stream_fn,
            )
        )
        agent.follow_up(UserMessage(content="queued after end", timestamp=2))

        await agent.continue_()

        assert request_contexts, "no provider request captured"
        last = request_contexts[0].messages[-1]
        assert last.role == "user"
        assert last.content == "queued after end"

    async def test_keeps_a_queued_follow_up_behind_a_trailing_user_continuation(
        self,
    ) -> None:
        request_contexts: list = []

        async def stream_fn(active_model, context, _options=None):
            request_contexts.append(context)
            stream = create_assistant_message_event_stream()
            stream.push(
                StreamEventDone(
                    reason="stop",
                    message=make_assistant(
                        [TextContent(text=f"answer {len(request_contexts)}")],
                        active_model=active_model,
                        timestamp=len(request_contexts) + 1,
                    ),
                )
            )
            stream.end()
            return stream

        agent = Agent(
            AgentOptions(
                initial_state=AgentInitialState(
                    model=MODEL,
                    system_prompt="",
                    tools=[],
                    messages=[UserMessage(content="retry this turn", timestamp=1)],
                ),
                convert_to_llm=convert_passthrough,
                stream_fn=stream_fn,
            )
        )
        agent.follow_up(UserMessage(content="queued after retry", timestamp=2))

        await agent.continue_()

        assert len(request_contexts) == 2
        first_last = request_contexts[0].messages[-1]
        assert first_last.role == "user"
        assert first_last.content == "retry this turn"
        second_last = request_contexts[1].messages[-1]
        assert second_last.role == "user"
        assert second_last.content == "queued after retry"


# ─────────────────────────────────────────────────────────────────────
# describe("Agent next-turn preparation")
# ─────────────────────────────────────────────────────────────────────


class RefreshTool:
    """Structural AgentTool for the next-turn preparation vector."""

    name = "refresh"
    label = "refresh"
    description = "refresh turn state"
    parameters = EMPTY_SCHEMA
    output_schema = None
    hide_from_channel_progress = None
    execution_mode = None

    async def execute(self, _tool_call_id, _params, signal=None, on_update=None):
        return AgentToolResult(
            content=[TextContent(text="refreshed")], details={}
        )


class TestAgentNextTurnPreparation:
    async def test_forwards_completed_turn_context_and_applies_update(
        self,
    ) -> None:
        next_model = dataclasses.replace(MODEL, id="next-model")
        requests: list[dict] = []
        turn = {"count": 0}

        async def stream_fn(active_model, context, _options=None):
            requests.append(
                {
                    "model": active_model.id,
                    "system_prompt": context.system_prompt or "",
                    "tools": [tool.name for tool in (context.tools or [])],
                }
            )
            turn["count"] += 1
            stream = create_assistant_message_event_stream()
            if turn["count"] == 1:
                content = [
                    ToolCall(id="call-refresh", name="refresh", arguments={})
                ]
                reason = "toolUse"
            else:
                content = [TextContent(text="done")]
                reason = "stop"
            stream.push(
                StreamEventDone(
                    reason=reason,
                    message=make_assistant(
                        content,
                        active_model=active_model,
                        stop_reason=reason,
                        timestamp=turn["count"],
                    ),
                )
            )
            stream.end()
            return stream

        tool = RefreshTool()
        with_context_calls: list = []
        legacy_calls: list = []

        def prepare_next_turn_with_context(context, _signal=None):
            with_context_calls.append(context)
            return AgentLoopTurnUpdate(
                context=dataclasses.replace(
                    context.context, system_prompt="refreshed prompt", tools=[]
                ),
                model=next_model,
            )

        def prepare_next_turn(_signal=None):
            legacy_calls.append(True)
            return AgentLoopTurnUpdate()

        agent = Agent(
            AgentOptions(
                initial_state=AgentInitialState(
                    model=MODEL, system_prompt="initial prompt", tools=[tool]
                ),
                convert_to_llm=convert_passthrough,
                stream_fn=stream_fn,
                prepare_next_turn=prepare_next_turn,
                prepare_next_turn_with_context=prepare_next_turn_with_context,
            )
        )

        await agent.prompt("start")

        assert with_context_calls, "prepareNextTurnWithContext was not called"
        assert not legacy_calls, "legacy prepareNextTurn must not be called"
        first_context = with_context_calls[0]
        assert first_context.message.role == "assistant"
        assert first_context.message.stop_reason == "toolUse"
        assert [
            (result.role, result.tool_name) for result in first_context.tool_results
        ] == [("toolResult", "refresh")]
        assert requests == [
            {
                "model": MODEL.id,
                "system_prompt": "initial prompt",
                "tools": ["refresh"],
            },
            {
                "model": next_model.id,
                "system_prompt": "refreshed prompt",
                "tools": [],
            },
        ]
