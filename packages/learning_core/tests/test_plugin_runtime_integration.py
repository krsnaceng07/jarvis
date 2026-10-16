"""Integration tests for Phase 2: Plugin Runtime Integration & HookBus Contract.

Verifies:
1. Extension discovery via jarvis_sdk.loader.load_all_plugins_from_workspace.
2. HookBus registration of all canonical events (tool_called, tool_completed, before_prompt_build, etc.).
3. Universal payload adaptation (nested, flat dispatcher-style, object-based).
4. Durable two-tier idempotency (L1 in-memory + L2 SQLite durable storage).
5. Observational safety (tool calls and prompts are never disrupted).
6. Exception containment (malformed payloads never crash the host agent loop).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from jarvis_hooks import HookBus
from jarvis_learning import LearningEngine
from jarvis_learning.events import EventIdempotencyStore
from jarvis_learning.strategies import Strategy, FailurePattern
from jarvis_sdk.loader import load_all_plugins_from_workspace

import extensions.learning.plugin as learning_plugin


@pytest.fixture
def clean_engine(tmp_path: Path) -> LearningEngine:
    """Create an isolated, temporary LearningEngine and wire to the plugin."""
    db_path = str(tmp_path / "test_learning.sqlite")
    engine = LearningEngine(db_path=db_path)
    engine.startup()

    # Point plugin to this isolated engine
    learning_plugin._engine = engine
    learning_plugin._idempotency_store = EventIdempotencyStore(db=engine.db)
    learning_plugin.hook_events_received = 0
    learning_plugin.strategy_retrieval_events = 0
    learning_plugin.experience_records_created = 0
    learning_plugin.routing_decisions_recorded = 0
    learning_plugin.duplicate_events_suppressed = 0
    return engine


def test_manifest_discovery_and_loader() -> None:
    """Verify load_all_plugins_from_workspace discovers the learning extension."""
    workspace_root = Path(__file__).resolve().parent.parent.parent.parent
    result = load_all_plugins_from_workspace(workspace_root)

    # Learning plugin must be discovered and registered
    assert result.plugin_count > 0
    hook_names = {h.name for h in result.hooks}
    assert "before_prompt_build" in hook_names
    assert "tool_called" in hook_names or "before_tool_call" in hook_names
    assert "tool_completed" in hook_names or "after_tool_call" in hook_names
    assert "agent_end" in hook_names
    assert "session_end" in hook_names


@pytest.mark.asyncio
async def test_hookbus_wire_and_tool_lifecycle(clean_engine: LearningEngine) -> None:
    """Verify HookBus registration, tool execution recording, and SQLite storage."""
    bus = HookBus()

    class MockPluginApi:
        def __init__(self) -> None:
            self.hooks: list[Any] = []

        def register_hook(self, name: str, handler: Any, **kwargs: Any) -> None:
            from jarvis_sdk.hook import HookRegistration

            reg = HookRegistration(name=name, handler=handler)
            self.hooks.append(reg)
            bus.register(reg)

    api = MockPluginApi()
    learning_plugin.register(api)
    assert len(api.hooks) >= 8

    # 1. Fire tool_called
    await bus.fire(
        "tool_called",
        {
            "tool": "file_search",
            "args": {"pattern": "*.py"},
            "call_id": "call_abc_1",
        },
    )
    assert learning_plugin.hook_events_received >= 1

    # 2. Fire tool_completed
    await bus.fire(
        "tool_completed",
        {
            "tool": "file_search",
            "call_id": "call_abc_1",
            "is_error": False,
            "duration_ms": 42.0,
            "result": {"files": ["main.py", "app.py"]},
        },
    )

    # Verify experience recorded in SQLite
    experiences = clean_engine.db.get_recent_experiences(limit=10)
    assert len(experiences) == 1
    assert experiences[0].selected_tool == "file_search"
    assert experiences[0].success is True


@pytest.mark.asyncio
async def test_two_tier_idempotency_deduplication(clean_engine: LearningEngine) -> None:
    """Verify repeated tool executions are caught by L1 cache and L2 SQLite store."""
    bus = HookBus()

    class MockPluginApi:
        def register_hook(self, name: str, handler: Any, **kwargs: Any) -> None:
            from jarvis_sdk.hook import HookRegistration

            bus.register(HookRegistration(name=name, handler=handler))

    learning_plugin.register(MockPluginApi())

    payload = {
        "tool": "calculator",
        "call_id": "calc_call_999",
        "attempt_id": 1,
        "result": {"value": 42},
    }

    # First dispatch -> recorded
    await bus.fire("tool_completed", payload)
    assert learning_plugin.experience_records_created == 1
    assert learning_plugin.duplicate_events_suppressed == 0

    # Second dispatch (immediate replay) -> caught by L1 memory cache
    await bus.fire("tool_completed", payload)
    assert learning_plugin.experience_records_created == 1
    assert learning_plugin.duplicate_events_suppressed == 1

    # Verify only 1 record exists in DB
    experiences = clean_engine.db.get_recent_experiences(limit=10)
    assert len(experiences) == 1

    # Reset L1 cache to simulate process restart / memory eviction
    learning_plugin._idempotency_store._l1_cache.clear()

    # Third dispatch -> caught by L2 SQLite durable store
    await bus.fire("tool_completed", payload)
    assert learning_plugin.experience_records_created == 1
    assert learning_plugin.duplicate_events_suppressed == 2


@pytest.mark.asyncio
async def test_universal_payload_adaptation(clean_engine: LearningEngine) -> None:
    """Verify plugin parses OpenClaw nested payloads, flat payloads, and object payloads."""
    # 1. Nested OpenClaw payload with hookCtx
    nested_payload = {
        "event": {
            "tool": "web_fetch",
            "params": {"url": "https://example.com"},
            "result": {"status": 200, "body": "OK"},
            "call_id": "fetch_1",
        },
        "hookCtx": {
            "agentId": "agent-alpha",
            "sessionId": "session-omega",
            "attemptId": 1,
            "lastUserInput": "Fetch example website",
        },
    }
    await learning_plugin.on_after_tool_call(nested_payload)
    experiences = clean_engine.db.get_recent_experiences(limit=10)
    assert len(experiences) == 1
    assert experiences[0].agent_id == "agent-alpha"
    assert experiences[0].session_id == "session-omega"
    assert experiences[0].user_input == "Fetch example website"

    # 2. Object-based payload
    class ToolCallEvent:
        tool = "system_status"
        args = {"scope": "cpu"}
        call_id = "obj_call_1"
        result = {"cpu": 15.0}
        is_error = False

    await learning_plugin.on_after_tool_call(
        ToolCallEvent(), {"agentId": "agent-beta", "sessionId": "sess-2"}
    )
    experiences = clean_engine.db.get_recent_experiences(limit=10)
    assert len(experiences) == 2
    assert any(
        e.selected_tool == "system_status" and e.agent_id == "agent-beta" for e in experiences
    )


@pytest.mark.asyncio
async def test_before_prompt_build_strategy_injection(clean_engine: LearningEngine) -> None:
    """Verify learned strategies are cleanly injected into prependContext."""
    now = 1700000000000
    # Seed a learned strategy
    strategy = Strategy(
        id="strat_test_1",
        created_at=now,
        updated_at=now,
        intent="weather_lookup",
        tool="get_weather",
        confidence=0.95,
        argument_pattern={"provider": "open_meteo"},
        preferred_action="use open_meteo for weather",
    )
    clean_engine.strategy_store.add_strategy(strategy)

    # 1. Prompt matching the strategy intent
    prompt_payload = {
        "messages": [
            {"role": "system", "content": "You are JARVIS."},
            {"role": "user", "content": "What is the weather_lookup for Paris?"},
        ],
        "hookCtx": {"agentId": "agent_1"},
    }
    res = await learning_plugin.on_before_prompt_build(prompt_payload)
    assert res is not None
    assert "prependContext" in res
    assert "<learning_context>" in res["prependContext"]
    assert "weather_lookup" in res["prependContext"]
    assert "get_weather" in res["prependContext"]

    # 2. Irrelevant prompt -> no injection
    irrelevant_payload = {
        "messages": [
            {"role": "user", "content": "Calculate the square root of 144."},
        ],
    }
    res_none = await learning_plugin.on_before_prompt_build(irrelevant_payload)
    assert res_none is None


@pytest.mark.asyncio
async def test_observational_failure_pattern_warning(clean_engine: LearningEngine) -> None:
    """Verify failure pattern detection logs advisory without modifying execution."""
    now = 1700000000000
    pattern = FailurePattern(
        id="fp_1",
        created_at=now,
        pattern_name="excessive_volume",
        tool_name="set_volume",
        bad_action="level > 100",
        preferred_action="cap volume at 100",
        condition={"level": 150},
        confidence=0.9,
    )
    clean_engine.strategy_store.add_failure_pattern(pattern)

    # Calling before_tool_call with matching bad action
    res = await learning_plugin.on_before_tool_call(
        {
            "tool": "set_volume",
            "params": {"level": 150},
        }
    )
    # Must return None (strictly observational, non-blocking)
    assert res is None
    assert learning_plugin.routing_decisions_recorded >= 1


@pytest.mark.asyncio
async def test_exception_containment() -> None:
    """Verify corrupted or malformed payloads never crash hook handlers."""
    # Malformed non-dict payload to handlers
    res1 = await learning_plugin.on_before_prompt_build(12345)
    assert res1 is None

    res2 = await learning_plugin.on_before_tool_call(None)
    assert res2 is None

    res3 = await learning_plugin.on_after_tool_call({"tool": None})
    assert res3 is None

    res4 = await learning_plugin.on_agent_end(object())
    assert res4 is None

    res5 = await learning_plugin.on_session_end(None)
    assert res5 is None


def test_desktop_host_hookbus_integration() -> None:
    """Verify that desktop host app discovers learning plugin and wires it into _PLUGIN_HOOK_BUS."""
    from jarvis_desktop.app import _PLUGIN_HOOK_BUS

    # Desktop HookBus must contain the canonical learning hooks
    names = _PLUGIN_HOOK_BUS.names()
    assert "before_prompt_build" in names
    assert "tool_called" in names
    assert "tool_completed" in names
    assert "after_tool_call" in names
    assert "agent_end" in names
    assert "session_end" in names

    # Handlers must be registered and non-empty
    assert len(_PLUGIN_HOOK_BUS.handlers_for("before_prompt_build")) >= 1
    assert len(_PLUGIN_HOOK_BUS.handlers_for("tool_completed")) >= 1
