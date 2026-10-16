"""Phase 7.6d-4 tests — 6 attempt-prompt/history files (preflight, system-prompt-prepare, assembly, phase, context, history-prepare)."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.agents.embedded_agent_runner.run.attempt_prompt_preflight import (
    handle_embedded_attempt_mid_turn_precheck,
    prepare_embedded_attempt_prompt_preflight,
    set_build_pre_prompt_context_budget_status_preflight_hook,
    set_format_pre_prompt_precheck_log_preflight_hook,
    set_run_mid_turn_precheck_hook,
)
from src.agents.embedded_agent_runner.run.attempt_system_prompt_prepare import (
    prepare_embedded_attempt_system_prompt,
    set_build_runtime_info_hook,
    set_build_system_prompt_hook,
    set_resolve_identity_context_hook,
)
from src.agents.embedded_agent_runner.run.attempt_prompt_assembly import (
    prepare_embedded_attempt_prompt_assembly,
    set_assemble_prompt_hook,
)
from src.agents.embedded_agent_runner.run.attempt_prompt_context import (
    prepare_embedded_attempt_prompt_context,
    set_build_tool_result_prompt_projection_hook,
    set_resolve_boundary_timestamp_hook,
    set_resolve_user_message_boundary_hook,
)
from src.agents.embedded_agent_runner.run.attempt_history_prepare import (
    prepare_embedded_attempt_history,
    set_load_context_engine_history_hook,
    set_prepare_history_replay_hook,
    set_prune_history_images_hook,
)
from src.agents.embedded_agent_runner.run.attempt_prompt_phase import (
    run_embedded_attempt_prompt_phase,
    set_prepare_attempt_stream_runtime_phase_hook,
    set_run_prompt_dispatch_hook,
    set_run_prompt_submit_hook,
)


# ============================================================================
# attempt-prompt-preflight
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_preflight_hooks() -> None:
    set_build_pre_prompt_context_budget_status_preflight_hook(lambda _p: {})
    set_format_pre_prompt_precheck_log_preflight_hook(lambda _p: "")
    set_run_mid_turn_precheck_hook(lambda _p: asyncio.sleep(0))
    yield
    set_build_pre_prompt_context_budget_status_preflight_hook(lambda _p: {})
    set_format_pre_prompt_precheck_log_preflight_hook(lambda _p: "")


class TestHandleEmbeddedAttemptMidTurnPrecheck:
    def test_basic(self) -> None:
        result = handle_embedded_attempt_mid_turn_precheck({})
        assert result["outcome"] == "continue"
        assert result["contextBudgetStatus"] == {}

    def test_with_status(self) -> None:
        set_build_pre_prompt_context_budget_status_preflight_hook(
            lambda _p: {"route": "compact", "overflowTokens": 100}
        )
        result = handle_embedded_attempt_mid_turn_precheck({})
        assert result["contextBudgetStatus"]["route"] == "compact"


class TestPrepareEmbeddedAttemptPromptPreflight:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_embedded_attempt_prompt_preflight(
                {"decision": {"route": "compact"}}
            )
        )
        assert result["decision"]["route"] == "compact"
        assert result["logLine"] == ""
        assert result["contextBudgetStatus"] == {}

    def test_with_log_line(self) -> None:
        set_format_pre_prompt_precheck_log_preflight_hook(
            lambda p: f"route={p.get('decision', {}).get('route', 'none')}"
        )
        result = asyncio.run(
            prepare_embedded_attempt_prompt_preflight(
                {"decision": {"route": "compact"}}
            )
        )
        assert result["logLine"] == "route=compact"


# ============================================================================
# attempt-system-prompt-prepare
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_system_prompt_hooks() -> None:
    set_build_runtime_info_hook(lambda _p: {})
    set_build_system_prompt_hook(lambda _p: asyncio.sleep(0))
    set_resolve_identity_context_hook(lambda _p: {})
    yield
    set_build_runtime_info_hook(lambda _p: {})
    set_build_system_prompt_hook(lambda _p: asyncio.sleep(0))


class TestPrepareEmbeddedAttemptSystemPrompt:
    def test_basic(self) -> None:
        async def _build(_p: Any) -> Any:
            return {"text": "you are a helper", "report": {"tokens": 50}}

        set_build_system_prompt_hook(_build)
        result = asyncio.run(
            prepare_embedded_attempt_system_prompt({})
        )
        assert result["systemPromptText"] == "you are a helper"
        assert result["systemPromptReport"]["tokens"] == 50

    def test_default_build_system_prompt(self) -> None:
        async def _default_build(_p: Any) -> Any:
            from src.agents.embedded_agent_runner.run.attempt_system_prompt import build_attempt_system_prompt

            return build_attempt_system_prompt(_p)

        set_build_system_prompt_hook(_default_build)
        result = asyncio.run(
            prepare_embedded_attempt_system_prompt(
                {
                    "runtimeInfo": {"model": "m1", "provider": "openai"},
                    "workspaceDir": "/tmp",
                    "tools": [{"name": "read"}],
                }
            )
        )
        assert isinstance(result["systemPromptText"], str)
        assert "Current date:" in result["systemPromptText"]
        assert "read" in result["systemPromptText"] or "Available tools" in result["systemPromptText"]

    def test_default_build_system_prompt_with_wrapped_params(self) -> None:
        async def _default_build(_p: Any) -> Any:
            from src.agents.embedded_agent_runner.run.attempt_system_prompt import (
                build_attempt_system_prompt,
            )

            return build_attempt_system_prompt(_p)

        set_build_system_prompt_hook(_default_build)
        result = asyncio.run(
            prepare_embedded_attempt_system_prompt(
                {
                    "workspaceDir": "/tmp",
                    "tools": [{"name": "read"}],
                    "runtimeInfo": {"model": "m1", "provider": "openai"},
                }
            )
        )
        assert isinstance(result["systemPromptText"], str)
        assert "/tmp" in result["systemPromptText"]
        assert "Current date:" in result["systemPromptText"]
        assert "read" in result["systemPromptText"] or "Available tools" in result["systemPromptText"]

    def test_with_runtime_info_and_identity(self) -> None:
        async def _build(_p: Any) -> Any:
            return {"text": "x"}

        set_build_system_prompt_hook(_build)
        set_build_runtime_info_hook(lambda _p: {"model": "m1"})
        set_resolve_identity_context_hook(lambda _p: {"agentId": "a1"})
        result = asyncio.run(
            prepare_embedded_attempt_system_prompt({})
        )
        assert result["runtimeInfo"]["model"] == "m1"
        assert result["identity"]["agentId"] == "a1"

    def test_non_dict_build_result(self) -> None:
        async def _build(_p: Any) -> Any:
            return None

        set_build_system_prompt_hook(_build)
        result = asyncio.run(
            prepare_embedded_attempt_system_prompt({})
        )
        assert result["systemPromptText"] is None
        assert result["systemPromptReport"] is None


# ============================================================================
# attempt-prompt-assembly
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_assembly_hooks() -> None:
    set_assemble_prompt_hook(lambda _p: asyncio.sleep(0))
    yield
    set_assemble_prompt_hook(lambda _p: asyncio.sleep(0))


class TestPrepareEmbeddedAttemptPromptAssembly:
    def test_basic(self) -> None:
        async def _assemble(_p: Any) -> Any:
            return {
                "systemPromptText": "sp",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [{"name": "read"}],
                "prompt": "full-prompt",
                "report": {"tokens": 100},
            }

        set_assemble_prompt_hook(_assemble)
        result = asyncio.run(
            prepare_embedded_attempt_prompt_assembly({})
        )
        assert result["systemPromptText"] == "sp"
        assert len(result["messages"]) == 1
        assert len(result["tools"]) == 1
        assert result["prompt"] == "full-prompt"
        assert result["report"]["tokens"] == 100

    def test_default_assembly_pass_through(self) -> None:
        async def _build(_p: Any) -> Any:
            return {
                "systemPromptText": "sp",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [{"name": "read"}],
                "prompt": "full-prompt",
                "report": {"tokens": 100},
            }

        set_assemble_prompt_hook(_build)
        result = asyncio.run(
            prepare_embedded_attempt_prompt_assembly({})
        )
        assert result["systemPromptText"] == "sp"
        assert len(result["messages"]) == 1
        assert len(result["tools"]) == 1
        assert result["prompt"] == "full-prompt"
        assert result["report"]["tokens"] == 100

    def test_non_dict(self) -> None:
        async def _assemble(_p: Any) -> Any:
            return None

        set_assemble_prompt_hook(_assemble)
        result = asyncio.run(
            prepare_embedded_attempt_prompt_assembly({})
        )
        assert result["messages"] == []
        assert result["tools"] == []
        assert result["prompt"] is None


# ============================================================================
# attempt-prompt-context
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_context_hooks() -> None:
    set_build_tool_result_prompt_projection_hook(lambda _p: {})
    set_resolve_boundary_timestamp_hook(lambda _p: None)
    set_resolve_user_message_boundary_hook(lambda _p: {})
    yield
    set_resolve_boundary_timestamp_hook(lambda _p: None)
    set_resolve_user_message_boundary_hook(lambda _p: {})


class TestPrepareEmbeddedAttemptPromptContext:
    def test_basic(self) -> None:
        result = prepare_embedded_attempt_prompt_context({})
        assert result["boundary"] is None
        assert result["userBoundary"] == {}
        assert result["projection"] == {}

    def test_with_hooks(self) -> None:
        set_resolve_boundary_timestamp_hook(lambda _p: "2024-01-01T00:00:00Z")
        set_resolve_user_message_boundary_hook(
            lambda _p: {"timezone": "UTC"}
        )
        set_build_tool_result_prompt_projection_hook(
            lambda _p: {"truncated": True}
        )
        result = prepare_embedded_attempt_prompt_context({})
        assert result["boundary"] == "2024-01-01T00:00:00Z"
        assert result["userBoundary"]["timezone"] == "UTC"
        assert result["projection"]["truncated"] is True


# ============================================================================
# attempt-history-prepare
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_history_hooks() -> None:
    set_load_context_engine_history_hook(lambda _p: asyncio.sleep(0))
    set_prepare_history_replay_hook(lambda _p: None)
    set_prune_history_images_hook(lambda _p: None)
    yield
    set_load_context_engine_history_hook(lambda _p: asyncio.sleep(0))
    set_prune_history_images_hook(lambda _p: None)


class TestPrepareEmbeddedAttemptHistory:
    def test_basic(self) -> None:
        async def _load(_p: Any) -> Any:
            return {"messages": [{"role": "user", "content": "hi"}]}

        set_load_context_engine_history_hook(_load)
        result = asyncio.run(
            prepare_embedded_attempt_history({})
        )
        assert len(result["messages"]) == 1
        assert result["replay"] is None

    def test_with_prune(self) -> None:
        async def _load(_p: Any) -> Any:
            return {"messages": [{"role": "user", "content": "hi"}]}

        set_load_context_engine_history_hook(_load)
        set_prune_history_images_hook(
            lambda p: {"messages": [], "summary": "pruned"}
        )
        result = asyncio.run(
            prepare_embedded_attempt_history({})
        )
        assert result["messages"] == []
        assert result["summary"] == "pruned"

    def test_with_replay(self) -> None:
        async def _load(_p: Any) -> Any:
            return {"messages": []}

        async def _load_sync(_p: Any) -> Any:
            return {"messages": []}

        set_load_context_engine_history_hook(_load_sync)
        set_prepare_history_replay_hook(
            lambda p: {"replaySafe": True, "messages": p["history"]["messages"]}
        )
        result = asyncio.run(
            prepare_embedded_attempt_history({})
        )
        assert result["replay"]["replaySafe"] is True

    def test_non_dict_history(self) -> None:
        async def _load(_p: Any) -> Any:
            return None

        set_load_context_engine_history_hook(_load)
        result = asyncio.run(
            prepare_embedded_attempt_history({})
        )
        assert result["messages"] == []


# ============================================================================
# attempt-prompt-phase
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_phase_hooks() -> None:
    set_prepare_attempt_stream_runtime_phase_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_run_prompt_dispatch_hook(lambda _p: asyncio.sleep(0))
    set_run_prompt_submit_hook(lambda _p: asyncio.sleep(0))
    yield
    set_run_prompt_submit_hook(lambda _p: asyncio.sleep(0))
    set_run_prompt_dispatch_hook(lambda _p: asyncio.sleep(0))
    set_prepare_attempt_stream_runtime_phase_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestRunEmbeddedAttemptPromptPhase:
    def test_basic(self) -> None:
        result = asyncio.run(
            run_embedded_attempt_prompt_phase({})
        )
        assert result["preflight"] == {}
        assert result["streamRuntime"] == {}
        assert result["dispatch"] == {}

    def test_with_hooks(self) -> None:
        async def _submit(_p: Any) -> Any:
            return {"submitted": True}

        async def _prepare(_p: Any) -> Any:
            return {"ready": True}

        async def _dispatch(_p: Any) -> Any:
            return {"dispatched": True}

        set_run_prompt_submit_hook(_submit)
        set_prepare_attempt_stream_runtime_phase_hook(_prepare)
        set_run_prompt_dispatch_hook(_dispatch)
        result = asyncio.run(
            run_embedded_attempt_prompt_phase({})
        )
        assert result["preflight"]["submitted"] is True
        assert result["streamRuntime"]["ready"] is True
        assert result["dispatch"]["dispatched"] is True
