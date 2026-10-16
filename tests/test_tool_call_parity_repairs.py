from __future__ import annotations

import asyncio

from jarvis_sdk.memory_host_concurrency import run_with_concurrency

from src.agents.embedded_agent_runner.model_static_catalog import (
    DEFAULT_CONTEXT_TOKENS,
    _model_from_static_catalog_row,
)
from src.hooks.dispatcher import InternalHookDispatcher
from src.hooks.types import InternalHookEvent
from src.utils.run_with_concurrency import run_tasks_with_concurrency


def test_memory_concurrency_preserves_none_results() -> None:
    async def none_result() -> None:
        return None

    async def value_result() -> str:
        return "value"

    assert asyncio.run(run_with_concurrency([none_result, value_result], 2)) == [None, "value"]


def test_bounded_runner_preserves_none_results() -> None:
    async def none_result() -> None:
        return None

    async def value_result() -> str:
        return "value"

    outcome = asyncio.run(
        run_tasks_with_concurrency({"tasks": [none_result, value_result], "limit": 2})
    )
    assert outcome["results"] == [None, "value"]


def test_internal_hooks_run_family_before_specific_sequentially() -> None:
    order: list[str] = []

    async def family(event: InternalHookEvent) -> None:
        order.append("family-start")
        await asyncio.sleep(0)
        order.append("family-end")

    async def specific(event: InternalHookEvent) -> None:
        order.append("specific")

    dispatcher = InternalHookDispatcher({})
    dispatcher._handlers_by_event["command"] = [family]
    dispatcher._handlers_by_event["command:new"] = [specific]
    event = InternalHookEvent("command", "new", "session", {}, 0.0)

    asyncio.run(dispatcher.fire_and_wait(event))

    assert order == ["family-start", "family-end", "specific"]


def test_static_catalog_preserves_context_selection_and_zero_costs() -> None:
    model = _model_from_static_catalog_row(
        {
            "id": "model",
            "contextWindow": 0,
            "maxTokens": 0,
            "contextWindows": [{"id": "small", "contextWindow": 1}],
            "contextWindowDefault": "small",
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        }
    )

    assert model["contextWindow"] == 0
    assert model["maxTokens"] == 0
    assert model["contextWindows"] == [{"id": "small", "contextWindow": 1}]
    assert model["contextWindowDefault"] == "small"
    assert model["cost"] == {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}


def test_static_catalog_uses_defaults_only_for_missing_values() -> None:
    model = _model_from_static_catalog_row({"id": "model"})

    assert model["contextWindow"] == DEFAULT_CONTEXT_TOKENS
    assert model["maxTokens"] == DEFAULT_CONTEXT_TOKENS
