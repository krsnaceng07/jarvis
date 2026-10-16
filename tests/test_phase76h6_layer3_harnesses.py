"""Phase 7.6h-6 tests — compact.hooks.harness + run.overflow-compaction.harness ports."""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, List

import pytest

# Ensure src/ is on sys.path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.agents.embedded_agent_runner.compact_hooks_harness import (  # noqa: E402
    compact_hooks_test_api,
    load_compact_hooks_harness,
    reset_compact_hooks_harness_mocks,
    reset_compact_session_state_mocks,
    set_compact_hooks_harness_hook,
    set_compact_hooks_harness_mocks_hook,
    warm_compact_hooks_harness,
)
from src.agents.embedded_agent_runner.run_overflow_compaction_harness import (  # noqa: E402
    load_run_overflow_compaction_harness,
    overflow_base_run_params,
    reset_run_overflow_compaction_harness_mocks,
    run_overflow_compaction_test_api,
    set_run_overflow_compaction_harness_hook,
    set_run_overflow_compaction_harness_mocks_hook,
    use_openai_platform_auth_fixture,
    warm_run_overflow_compaction_harness,
)
from src.agents.embedded_agent_runner.run.run_overflow_compaction_fixture import (  # noqa: E402
    make_attempt_result,
    make_compaction_success,
    make_overflow_error,
    mock_overflow_retry_success,
    queue_overflow_attempt_with_oversized_tool_output,
)


# ============================================================================
# compact_hooks_harness
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_compact_hooks() -> None:
    set_compact_hooks_harness_hook(None)
    set_compact_hooks_harness_mocks_hook(None)
    reset_compact_hooks_harness_mocks()
    yield
    set_compact_hooks_harness_hook(None)
    set_compact_hooks_harness_mocks_hook(None)
    reset_compact_hooks_harness_mocks()


class TestCompactHooksHarness:
    def test_reset_compact_session_state_mocks(self) -> None:
        reset_compact_session_state_mocks()

    def test_reset_compact_hooks_harness_mocks(self) -> None:
        reset_compact_hooks_harness_mocks()

    def test_load_compact_hooks_harness(self) -> None:
        out = asyncio.run(load_compact_hooks_harness())
        assert isinstance(out, dict)
        # Should contain the mock keys
        assert "contextEngineCompactMock" in out
        assert "hookRunner" in out
        assert "buildAgentRuntimePlanMock" in out

    def test_load_with_hook(self) -> None:
        set_compact_hooks_harness_hook(lambda _p: {"hooked": True})
        out = asyncio.run(load_compact_hooks_harness())
        assert out == {"hooked": True}

    def test_load_with_async_hook(self) -> None:
        async def _hook(_p):
            return {"asyncHooked": True}
        set_compact_hooks_harness_hook(_hook)
        out = asyncio.run(load_compact_hooks_harness())
        assert out == {"asyncHooked": True}

    def test_warm_compact_hooks_harness(self) -> None:
        out = asyncio.run(warm_compact_hooks_harness())
        assert isinstance(out, dict)
        assert "buildAgentRuntimePlanMock" in out

    def test_warm_with_hook(self) -> None:
        set_compact_hooks_harness_hook(lambda _p: {"hooked": True})
        out = asyncio.run(warm_compact_hooks_harness())
        assert out == {"hooked": True}

    def test_test_api_exports(self) -> None:
        assert "resetCompactSessionStateMocks" in compact_hooks_test_api
        assert "resetCompactHooksHarnessMocks" in compact_hooks_test_api
        assert "loadCompactHooksHarness" in compact_hooks_test_api
        assert "warmCompactHooksHarness" in compact_hooks_test_api

    def test_set_mocks_hook_called(self) -> None:
        called = {}
        def _hook(p):
            called["op"] = p["op"]
        set_compact_hooks_harness_mocks_hook(_hook)
        reset_compact_session_state_mocks()
        assert called["op"] == "resetSessionState"
        reset_compact_hooks_harness_mocks()
        assert called["op"] == "resetSessionState"


# ============================================================================
# run_overflow_compaction_harness
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_run_overflow_hooks() -> None:
    set_run_overflow_compaction_harness_hook(None)
    set_run_overflow_compaction_harness_mocks_hook(None)
    reset_run_overflow_compaction_harness_mocks()
    yield
    set_run_overflow_compaction_harness_hook(None)
    set_run_overflow_compaction_harness_mocks_hook(None)
    reset_run_overflow_compaction_harness_mocks()


class TestRunOverflowCompactionHarness:
    def test_overflow_base_run_params(self) -> None:
        assert overflow_base_run_params["prompt"] == "test prompt"
        assert overflow_base_run_params["sessionKey"] == "test-session"
        assert overflow_base_run_params["workspaceDir"] == "/tmp/workspace"
        assert overflow_base_run_params["agentId"] == "main"
        assert overflow_base_run_params["provider"] == "openai"
        assert overflow_base_run_params["modelId"] == "gpt-5"

    def test_use_openai_platform_auth_fixture(self) -> None:
        # Should not throw
        use_openai_platform_auth_fixture()

    def test_use_openai_with_mocks_hook(self) -> None:
        called = {}
        def _hook(p):
            called["op"] = p["op"]
        set_run_overflow_compaction_harness_mocks_hook(_hook)
        use_openai_platform_auth_fixture()
        assert called["op"] == "useOpenAIPlatformAuthFixture"

    def test_reset_harness_mocks(self) -> None:
        reset_run_overflow_compaction_harness_mocks()

    def test_reset_with_mocks_hook(self) -> None:
        called = {}
        def _hook(p):
            called["op"] = p["op"]
        set_run_overflow_compaction_harness_mocks_hook(_hook)
        reset_run_overflow_compaction_harness_mocks()
        assert called["op"] == "resetAll"

    def test_load_harness(self) -> None:
        out = asyncio.run(load_run_overflow_compaction_harness())
        assert isinstance(out, dict)
        assert "mockedGlobalHookRunner" in out
        assert "mockedContextEngine" in out
        assert "mockedBuildAgentRuntimePlan" in out

    def test_load_with_hook(self) -> None:
        set_run_overflow_compaction_harness_hook(lambda _p: {"hooked": True})
        out = asyncio.run(load_run_overflow_compaction_harness())
        assert out == {"hooked": True}

    def test_load_with_async_hook(self) -> None:
        async def _hook(_p):
            return {"asyncHooked": True}
        set_run_overflow_compaction_harness_hook(_hook)
        out = asyncio.run(load_run_overflow_compaction_harness())
        assert out == {"asyncHooked": True}

    def test_warm_harness(self) -> None:
        out = asyncio.run(warm_run_overflow_compaction_harness())
        assert isinstance(out, dict)
        assert "mockedBuildAgentRuntimePlan" in out

    def test_warm_with_hook(self) -> None:
        set_run_overflow_compaction_harness_hook(lambda _p: {"hooked": True})
        out = asyncio.run(warm_run_overflow_compaction_harness())
        assert out == {"hooked": True}

    def test_test_api_exports(self) -> None:
        assert "useOpenAIPlatformAuthFixture" in run_overflow_compaction_test_api
        assert "resetRunOverflowCompactionHarnessMocks" in run_overflow_compaction_test_api
        assert "loadRunOverflowCompactionHarness" in run_overflow_compaction_test_api
        assert "warmRunOverflowCompactionHarness" in run_overflow_compaction_test_api
        assert "overflowBaseRunParams" in run_overflow_compaction_test_api
        assert run_overflow_compaction_test_api["overflowBaseRunParams"] is overflow_base_run_params


class _MockResolvedValueOnce:
    def __init__(self) -> None:
        self.values: List[Any] = []

    def mock_resolved_value_once(self, value: Any) -> None:
        self.values.append(value)


class TestRunOverflowCompactionFixture:
    def test_make_overflow_error(self) -> None:
        err = make_overflow_error("boom")
        assert isinstance(err, Exception)
        assert str(err) == "boom"

    def test_make_compaction_success(self) -> None:
        result = make_compaction_success(
            {
                "summary": "Compacted",
                "tokensBefore": 100,
                "tokensAfter": 50,
            }
        )
        assert result["ok"] is True
        assert result["compacted"] is True
        assert result["result"]["summary"] == "Compacted"
        assert result["result"]["tokensBefore"] == 100
        assert result["result"]["tokensAfter"] == 50

    def test_make_attempt_result(self) -> None:
        attempt = make_attempt_result({"promptError": None})
        assert attempt["aborted"] is False
        assert attempt["promptError"] is None
        assert attempt["replayMetadata"]["replaySafe"] is True
        assert attempt["toolMetas"] == []

    def test_mock_overflow_retry_success(self) -> None:
        run_attempt = _MockResolvedValueOnce()
        compact_direct = _MockResolvedValueOnce()
        err = mock_overflow_retry_success(run_attempt, compact_direct)
        assert isinstance(err, Exception)
        assert len(run_attempt.values) == 2
        assert len(compact_direct.values) == 1
        assert compact_direct.values[0]["ok"] is True

    def test_queue_overflow_attempt_with_oversized_tool_output(self) -> None:
        run_attempt = _MockResolvedValueOnce()
        err = queue_overflow_attempt_with_oversized_tool_output(run_attempt)
        assert isinstance(err, Exception)
        assert len(run_attempt.values) == 1
        assert run_attempt.values[0]["messagesSnapshot"][0]["content"][0]["text"].startswith("x")
