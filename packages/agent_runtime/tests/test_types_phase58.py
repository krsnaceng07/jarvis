"""Tests for ``jarvis_agent.types``.

OpenClaw source: ``packages/agent-core/src/types.ts`` (547 lines). Upstream
has no ``types.test.ts`` — the file is types only — so cases here verify the
structural contracts Python must actively maintain: event discriminants and
field sets (TS gets these for free from the compiler), literal-union values,
the ``UNSET`` sentinel semantics, and the frozen defaults.
"""

from __future__ import annotations

import dataclasses
import typing

import pytest

from jarvis_agent.types import (
    AGENT_EVENT_TYPES,
    DEFAULT_TOOL_EXECUTION,
    UNSET,
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
    AgentToolResult,
    QueueMode,
    ThinkingLevel,
    ToolExecutionMode,
)


class TestLiteralUnions:
    def test_thinking_level_values_and_order(self) -> None:
        # TS: "off" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max"
        assert typing.get_args(ThinkingLevel) == (
            "off",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        )

    def test_queue_mode_values(self) -> None:
        assert typing.get_args(QueueMode) == ("all", "one-at-a-time")

    def test_tool_execution_mode_values_and_default(self) -> None:
        assert typing.get_args(ToolExecutionMode) == ("sequential", "parallel")
        assert DEFAULT_TOOL_EXECUTION == "parallel"


class TestUnsetSentinel:
    def test_singleton_and_distinct_from_none(self) -> None:
        # UNSET exists because None is a *valid* hook-result value; the two
        # must never compare equal or be interchangeable.
        assert UNSET is not None
        assert UNSET != None  # noqa: E711 - the inequality itself is the contract

    def test_falsy(self) -> None:
        assert not UNSET

    def test_identity_check_is_the_idiom(self) -> None:
        value: object = UNSET
        assert value is UNSET


class TestAgentEvents:
    # (class, type literal, required field names in declaration order)
    _VARIANTS = [
        (AgentEventAgentStart, "agent_start", []),
        (AgentEventAgentEnd, "agent_end", ["messages"]),
        (AgentEventTurnStart, "turn_start", []),
        (AgentEventTurnEnd, "turn_end", ["message", "tool_results"]),
        (AgentEventMessageStart, "message_start", ["message"]),
        (
            AgentEventMessageUpdate,
            "message_update",
            ["message", "assistant_message_event"],
        ),
        (AgentEventMessageEnd, "message_end", ["message"]),
        (
            AgentEventToolExecutionStart,
            "tool_execution_start",
            ["tool_call_id", "tool_name", "args"],
        ),
        (
            AgentEventToolExecutionUpdate,
            "tool_execution_update",
            ["tool_call_id", "tool_name", "args", "partial_result"],
        ),
        (
            AgentEventToolExecutionEnd,
            "tool_execution_end",
            ["tool_call_id", "tool_name", "result", "is_error"],
        ),
    ]

    @pytest.mark.parametrize(("cls", "literal", "required"), _VARIANTS)
    def test_discriminant_and_required_fields(
        self, cls: type, literal: str, required: list[str]
    ) -> None:
        fields = dataclasses.fields(cls)
        required_names = [
            f.name
            for f in fields
            if f.default is dataclasses.MISSING
            and f.default_factory is dataclasses.MISSING
        ]
        assert required_names == required
        # type literal has a default equal to the discriminant value.
        type_field = next(f for f in fields if f.name == "type")
        assert type_field.default == literal

    def test_event_types_tuple_matches_union_declaration_order(self) -> None:
        assert AGENT_EVENT_TYPES == tuple(literal for _, literal, _ in self._VARIANTS)
        assert len(typing.get_args(AgentEvent)) == 10

    def test_tool_execution_start_optional_hide_flag(self) -> None:
        # TS: hideFromChannelProgress?: boolean — absent by default.
        event = AgentEventToolExecutionStart(
            tool_call_id="t1", tool_name="read", args={"path": "x"}
        )
        assert event.hide_from_channel_progress is None

    def test_tool_execution_end_optional_provenance_fields(self) -> None:
        # TS: executionStarted?: boolean; errorKind?: "argument-validation".
        event = AgentEventToolExecutionEnd(
            tool_call_id="t1", tool_name="read", result="out", is_error=False
        )
        assert event.execution_started is None
        assert event.error_kind is None
        blocked = AgentEventToolExecutionEnd(
            tool_call_id="t2",
            tool_name="read",
            result="bad args",
            is_error=True,
            execution_started=False,
            error_kind="argument-validation",
        )
        assert blocked.execution_started is False
        assert blocked.error_kind == "argument-validation"

    def test_events_frozen(self) -> None:
        event = AgentEventAgentStart()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.type = "agent_end"  # type: ignore[misc]


class TestAgentContext:
    def test_fields_in_ts_order(self) -> None:
        assert [f.name for f in dataclasses.fields(AgentContext)] == [
            "system_prompt",
            "messages",
            "tools",
        ]


class TestAgentToolResult:
    def test_fields(self) -> None:
        assert [f.name for f in dataclasses.fields(AgentToolResult)] == [
            "content",
            "details",
            "progress",
            "terminate",
        ]
