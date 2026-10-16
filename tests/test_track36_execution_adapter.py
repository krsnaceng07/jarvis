"""Track 3.6 Phase C — PluginExecutionAdapter Acceptance Tests.

Validates that:
1. PluginExecutionAdapter conforms to the ExecutionAdapter contract.
2. Synchronous and asynchronous plugin tools execute properly.
3. Errors raised within plugin tools are contained (fail-closed, no unhandled exceptions).
4. HookBus observers receive before_tool_call and after_tool_call events.
5. CommandDispatcher (Track 3.2 frozen runtime) correctly locates and dispatches
   commands to PluginExecutionAdapter.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from jarvis_sdk.execution_adapter import (
    ExecutionAdapterOutput,
    PluginExecutionAdapter,
)


@dataclass
class DummyCommand:
    command_id: str
    capability_target: str
    parameters: dict[str, Any]
    session_id: str | None = None


class MockHookBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def emit(self, event_name: str, payload: dict[str, Any]) -> None:
        self.events.append((event_name, payload))


class TestPluginExecutionAdapter:
    def test_adapter_name(self) -> None:
        adapter = PluginExecutionAdapter()
        assert adapter.adapter_name == "plugin_adapter"

    def test_can_handle_registered_tool(self) -> None:
        adapter = PluginExecutionAdapter()
        adapter.register_tool("plugin.weather.get_temp", lambda location: f"20C in {location}")

        assert adapter.can_handle("plugin.weather.get_temp")
        assert not adapter.can_handle("plugin.other.tool")
        assert not adapter.can_handle("core.filesystem.read")

    def test_sync_tool_execution(self) -> None:
        adapter = PluginExecutionAdapter()
        adapter.register_tool("plugin.calc.add", lambda a, b: a + b)

        cmd = DummyCommand(
            command_id="cmd-1",
            capability_target="plugin.calc.add",
            parameters={"a": 10, "b": 32},
        )
        result = adapter.execute(cmd)

        assert isinstance(result, ExecutionAdapterOutput)
        assert result.success is True
        assert result.output_data == 42
        assert result.exit_code == 0
        assert result.error_message is None

    def test_async_tool_execution(self) -> None:
        adapter = PluginExecutionAdapter()

        async def async_fetch(url: str) -> str:
            await asyncio.sleep(0.01)
            return f"content of {url}"

        adapter.register_tool("plugin.net.fetch", async_fetch)

        cmd = DummyCommand(
            command_id="cmd-2",
            capability_target="plugin.net.fetch",
            parameters={"url": "https://example.com"},
        )
        result = adapter.execute(cmd)

        assert result.success is True
        assert result.output_data == "content of https://example.com"

    def test_tool_exception_containment(self) -> None:
        adapter = PluginExecutionAdapter()

        def faulty_tool() -> None:
            raise ValueError("Invalid operation performed")

        adapter.register_tool("plugin.faulty.run", faulty_tool)

        cmd = DummyCommand(
            command_id="cmd-3",
            capability_target="plugin.faulty.run",
            parameters={},
        )
        result = adapter.execute(cmd)

        assert result.success is False
        assert result.exit_code == 1
        assert "Invalid operation performed" in (result.error_message or "")

    def test_hook_bus_observability(self) -> None:
        bus = MockHookBus()
        adapter = PluginExecutionAdapter(hook_bus=bus)
        adapter.register_tool("plugin.test.echo", lambda msg: f"echo: {msg}")

        cmd = DummyCommand(
            command_id="cmd-4",
            capability_target="plugin.test.echo",
            parameters={"msg": "hello"},
        )
        result = adapter.execute(cmd)

        assert result.success is True
        assert len(bus.events) == 2
        assert bus.events[0][0] == "before_tool_call"
        assert bus.events[0][1]["tool"] == "plugin.test.echo"
        assert bus.events[1][0] == "after_tool_call"
        assert bus.events[1][1]["tool"] == "plugin.test.echo"
        assert bus.events[1][1]["success"] is True
        assert "duration_seconds" in bus.events[1][1]

    def test_command_dispatcher_integration(self) -> None:
        """Verify seamless integration with the frozen CommandDispatcher from agent_runtime."""
        from jarvis_agent.execution.dispatcher.dispatcher import CommandDispatcher
        from jarvis_agent.orchestration.models.command import ExecutionCommand
        from jarvis_agent.orchestration.models.risk import RiskAssessment, RiskClass

        adapter = PluginExecutionAdapter()
        adapter.register_tool("plugin.system.query", lambda key: f"value_for_{key}")

        dispatcher = CommandDispatcher([adapter])  # type: ignore[list-item]

        risk = RiskAssessment(
            risk_class=RiskClass.LOW,
            blast_radius="LOCAL_TEMP",
            reversibility="FULLY_REVERSIBLE",
            data_sensitivity="PUBLIC",
            external_effect="NONE",
            requires_operator_approval=False,
            justification="Query system state",
        )

        cmd = ExecutionCommand(
            command_id="cmd-disp-1",
            task_id="task-1",
            plan_id="plan-1",
            node_id="node-1",
            execution_id="exec-1",
            attempt_id=1,
            plan_revision=1,
            capability_target="plugin.system.query",
            arguments={"key": "cpu_load"},
            arguments_hash="hash-123",
            idempotency_key="idem-123",
            issued_at_utc="2026-09-29T12:00:00Z",
            deadline_utc="2026-09-29T12:05:00Z",
            risk_assessment=risk,
        )

        output = dispatcher.dispatch(cmd)

        assert output.success is True
        assert output.output_data == "value_for_cpu_load"

