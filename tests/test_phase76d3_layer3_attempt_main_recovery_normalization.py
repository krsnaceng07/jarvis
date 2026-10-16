"""Phase 7.6d-3 tests — attempt.ts (main) + attempt-recovery + attempt-normalization."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.agents.embedded_agent_runner.run.attempt import (
    run_embedded_attempt,
    set_recover_embedded_run_attempt_attempt_hook,
    set_run_embedded_attempt_settled_phase_hook,
)
from src.agents.embedded_agent_runner.run.attempt_recovery import (
    recover_embedded_run_attempt,
    set_handle_embedded_assistant_failure_attempt_recovery_hook,
    set_handle_embedded_prompt_failure_attempt_recovery_hook,
    set_recover_embedded_run_overflow_attempt_recovery_hook,
    set_recover_embedded_run_timeout_attempt_recovery_hook,
)
from src.agents.embedded_agent_runner.run.attempt_normalization import (
    normalize_embedded_run_attempt,
    set_normalize_message_list_hook,
    set_normalize_prompt_hook,
    set_project_run_attempt_result_hook,
)


# ============================================================================
# attempt.ts (main)
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_attempt_main_hooks() -> None:
    set_recover_embedded_run_attempt_attempt_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_run_embedded_attempt_settled_phase_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_run_embedded_attempt_settled_phase_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestRunEmbeddedAttempt:
    def test_basic(self) -> None:
        async def _settle(_p: Any) -> Any:
            return {"aborted": False, "timedOut": False, "promptError": None}

        set_run_embedded_attempt_settled_phase_hook(_settle)
        result = asyncio.run(
            run_embedded_attempt(
                {"attempt": {"runId": "r1", "sessionId": "s1"}}
            )
        )
        assert result["aborted"] is False
        assert result["timedOut"] is False
        assert result["promptError"] is None

    def test_with_prompt_error(self) -> None:
        async def _settle(_p: Any) -> Any:
            return {"promptError": "boom"}

        async def _recover(_p: Any) -> Any:
            return {"action": "complete", "result": "recovered"}

        set_run_embedded_attempt_settled_phase_hook(_settle)
        set_recover_embedded_run_attempt_attempt_hook(_recover)
        result = asyncio.run(
            run_embedded_attempt({"attempt": {"runId": "r1"}})
        )
        assert result["action"] == "complete"
        assert result["result"] == "recovered"

    def test_with_timeout(self) -> None:
        async def _settle(_p: Any) -> Any:
            return {"timedOut": True}

        async def _recover(_p: Any) -> Any:
            return {"action": "complete", "result": "recovered-from-timeout"}

        set_run_embedded_attempt_settled_phase_hook(_settle)
        set_recover_embedded_run_attempt_attempt_hook(_recover)
        result = asyncio.run(
            run_embedded_attempt({"attempt": {"runId": "r1"}})
        )
        assert result["result"] == "recovered-from-timeout"

    def test_no_recovery_on_clean(self) -> None:
        called = {"n": 0}

        async def _settle(_p: Any) -> Any:
            return {"aborted": False, "timedOut": False, "promptError": None}

        async def _recover(_p: Any) -> Any:
            called["n"] += 1
            return {"action": "should-not-be-called"}

        set_run_embedded_attempt_settled_phase_hook(_settle)
        set_recover_embedded_run_attempt_attempt_hook(_recover)
        asyncio.run(
            run_embedded_attempt({"attempt": {"runId": "r1"}})
        )
        assert called["n"] == 0

    def test_non_dict_result(self) -> None:
        async def _settle(_p: Any) -> Any:
            return None

        set_run_embedded_attempt_settled_phase_hook(_settle)
        result = asyncio.run(
            run_embedded_attempt({"attempt": {"runId": "r1"}})
        )
        # Non-dict settled-phase result is treated as empty, no recovery.
        assert isinstance(result, dict)
        assert result.get("aborted") is None


# ============================================================================
# attempt-recovery
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_attempt_recovery_hooks() -> None:
    set_handle_embedded_assistant_failure_attempt_recovery_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_handle_embedded_prompt_failure_attempt_recovery_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_recover_embedded_run_overflow_attempt_recovery_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_recover_embedded_run_timeout_attempt_recovery_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_handle_embedded_prompt_failure_attempt_recovery_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestRecoverEmbeddedRunAttempt:
    def test_no_error(self) -> None:
        result = asyncio.run(
            recover_embedded_run_attempt(
                {
                    "attempt": {"runId": "r1"},
                    "result": {"aborted": False},
                }
            )
        )
        assert result["action"] == "none"
        assert result["attemptId"] == "r1"

    def test_prompt_error(self) -> None:
        async def _recover(_p: Any) -> Any:
            return {"action": "complete", "result": "from-prompt-failure"}

        set_handle_embedded_prompt_failure_attempt_recovery_hook(_recover)
        result = asyncio.run(
            recover_embedded_run_attempt(
                {
                    "attempt": {"runId": "r1"},
                    "result": {"promptError": "boom"},
                }
            )
        )
        assert result["action"] == "complete"
        assert result["result"] == "from-prompt-failure"

    def test_timeout(self) -> None:
        async def _recover(_p: Any) -> Any:
            return {"action": "complete", "result": "from-timeout"}

        set_recover_embedded_run_timeout_attempt_recovery_hook(_recover)
        result = asyncio.run(
            recover_embedded_run_attempt(
                {
                    "attempt": {"runId": "r1"},
                    "result": {"timedOut": True},
                }
            )
        )
        assert result["result"] == "from-timeout"

    def test_assistant_failure(self) -> None:
        async def _recover(_p: Any) -> Any:
            return {"action": "complete", "result": "from-assistant-failure"}

        set_handle_embedded_assistant_failure_attempt_recovery_hook(_recover)
        result = asyncio.run(
            recover_embedded_run_attempt(
                {
                    "attempt": {"runId": "r1"},
                    "result": {"aborted": True},
                }
            )
        )
        assert result["result"] == "from-assistant-failure"


# ============================================================================
# attempt-normalization
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_attempt_normalization_hooks() -> None:
    set_normalize_message_list_hook(lambda _p: None)
    set_normalize_prompt_hook(lambda _p: None)
    set_project_run_attempt_result_hook(lambda _p: None)
    yield
    set_normalize_prompt_hook(lambda _p: None)
    set_project_run_attempt_result_hook(lambda _p: None)


class TestNormalizeEmbeddedRunAttempt:
    def test_basic(self) -> None:
        result = asyncio.run(
            normalize_embedded_run_attempt(
                {"attempt": {"runId": "r1"}}
            )
        )
        assert result["attemptId"] == "r1"
        assert result["prompt"] is None
        assert result["messages"] is None
        assert result["projection"] == {}

    def test_with_hooks(self) -> None:
        set_normalize_prompt_hook(lambda _p: "normalized-prompt")
        set_normalize_message_list_hook(
            lambda _p: [{"role": "user", "content": "hi"}]
        )
        set_project_run_attempt_result_hook(
            lambda p: {"prompt": p.get("prompt"), "messages": p.get("messages")}
        )
        result = asyncio.run(
            normalize_embedded_run_attempt(
                {"attempt": {"runId": "r1"}}
            )
        )
        assert result["prompt"] == "normalized-prompt"
        assert len(result["messages"]) == 1
        assert result["projection"]["prompt"] == "normalized-prompt"

    def test_non_dict_projection(self) -> None:
        set_project_run_attempt_result_hook(lambda _p: "not-a-dict")
        result = asyncio.run(
            normalize_embedded_run_attempt(
                {"attempt": {"runId": "r1"}}
            )
        )
        assert result["projection"] == {}
