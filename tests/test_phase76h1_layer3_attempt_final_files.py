"""Phase 7.6h-1 tests — 7 final attempt.* files (after-turn, dispatch-preparation, prompt-submit, session-cleanup, session-lock-prepare, session, system-prompt)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.run.attempt_after_turn import (
    complete_embedded_attempt_after_turn,
    set_complete_embedded_attempt_after_turn_hook,
)
from src.agents.embedded_agent_runner.run.attempt_dispatch_preparation import (
    prepare_and_dispatch_embedded_run_attempt,
    set_prepare_and_dispatch_embedded_run_attempt_hook,
)
from src.agents.embedded_agent_runner.run.attempt_prompt_submit import (
    set_submit_embedded_attempt_prompt_hook,
    submit_embedded_attempt_prompt,
)
from src.agents.embedded_agent_runner.run.attempt_session_cleanup import (
    cleanup_embedded_attempt_session_phase,
    set_cleanup_embedded_attempt_session_phase_hook,
)
from src.agents.embedded_agent_runner.run.attempt_session_lock_prepare import (
    prepare_embedded_attempt_session_lock,
    set_prepare_embedded_attempt_session_lock_hook,
)
from src.agents.embedded_agent_runner.run.attempt_session import (
    prepare_embedded_attempt_agent_session,
    set_prepare_embedded_attempt_agent_session_hook,
)
from src.agents.embedded_agent_runner.run.attempt_system_prompt import (
    build_attempt_system_prompt,
    set_build_attempt_system_prompt_hook,
)


# ============================================================================
# attempt.after-turn
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_after_turn_hooks() -> None:
    set_complete_embedded_attempt_after_turn_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_complete_embedded_attempt_after_turn_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestCompleteEmbeddedAttemptAfterTurn:
    def test_basic(self) -> None:
        result = asyncio.run(
            complete_embedded_attempt_after_turn({})
        )
        assert result["completed"] is True
        assert result["result"] is None

    def test_with_hook(self) -> None:
        async def _complete(_p: Any) -> Any:
            return {"completed": True, "result": {"x": 1}}

        set_complete_embedded_attempt_after_turn_hook(_complete)
        result = asyncio.run(
            complete_embedded_attempt_after_turn({})
        )
        assert result["result"] == {"x": 1}


# ============================================================================
# attempt-dispatch-preparation
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_dispatch_preparation_hooks() -> None:
    set_prepare_and_dispatch_embedded_run_attempt_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_prepare_and_dispatch_embedded_run_attempt_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestPrepareAndDispatchEmbeddedRunAttempt:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_and_dispatch_embedded_run_attempt({})
        )
        assert result["prepared"] is True
        assert result["dispatched"] is False
        assert result["result"] is None

    def test_with_hook(self) -> None:
        async def _do(_p: Any) -> Any:
            return {
                "prepared": True,
                "dispatched": True,
                "result": {"runId": "r1"},
            }

        set_prepare_and_dispatch_embedded_run_attempt_hook(_do)
        result = asyncio.run(
            prepare_and_dispatch_embedded_run_attempt({})
        )
        assert result["dispatched"] is True
        assert result["result"]["runId"] == "r1"


# ============================================================================
# attempt-prompt-submit
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_submit_hooks() -> None:
    set_submit_embedded_attempt_prompt_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_submit_embedded_attempt_prompt_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestSubmitEmbeddedAttemptPrompt:
    def test_basic(self) -> None:
        result = asyncio.run(
            submit_embedded_attempt_prompt({})
        )
        assert result["submitted"] is True
        assert result["result"] is None

    def test_with_hook(self) -> None:
        async def _submit(_p: Any) -> Any:
            return {"submitted": True, "result": {"prompt": "hi"}}

        set_submit_embedded_attempt_prompt_hook(_submit)
        result = asyncio.run(
            submit_embedded_attempt_prompt({})
        )
        assert result["result"]["prompt"] == "hi"


# ============================================================================
# attempt-session-cleanup
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_session_cleanup_hooks() -> None:
    set_cleanup_embedded_attempt_session_phase_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_cleanup_embedded_attempt_session_phase_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestCleanupEmbeddedAttemptSessionPhase:
    def test_basic(self) -> None:
        result = asyncio.run(
            cleanup_embedded_attempt_session_phase({})
        )
        assert result["cleanedUp"] is True
        assert result["result"] is None

    def test_with_hook(self) -> None:
        async def _cleanup(_p: Any) -> Any:
            return {"cleanedUp": True, "result": {"cleaned": "yes"}}

        set_cleanup_embedded_attempt_session_phase_hook(_cleanup)
        result = asyncio.run(
            cleanup_embedded_attempt_session_phase({})
        )
        assert result["result"]["cleaned"] == "yes"


# ============================================================================
# attempt-session-lock-prepare
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_session_lock_prepare_hooks() -> None:
    set_prepare_embedded_attempt_session_lock_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_prepare_embedded_attempt_session_lock_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestPrepareEmbeddedAttemptSessionLock:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_embedded_attempt_session_lock({})
        )
        assert result["prepared"] is True
        assert result["sessionLockController"] is None

    def test_with_hook(self) -> None:
        async def _prepare(_p: Any) -> Any:
            return {
                "prepared": True,
                "sessionLockController": "lock-ctrl",
            }

        set_prepare_embedded_attempt_session_lock_hook(_prepare)
        result = asyncio.run(
            prepare_embedded_attempt_session_lock({})
        )
        assert result["sessionLockController"] == "lock-ctrl"


# ============================================================================
# attempt-session
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_session_hooks() -> None:
    set_prepare_embedded_attempt_agent_session_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_prepare_embedded_attempt_agent_session_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestPrepareEmbeddedAttemptAgentSession:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_embedded_attempt_agent_session({})
        )
        assert result["agentSession"] is None
        assert result["sessionId"] is None
        assert result["sessionFile"] is None

    def test_with_hook(self) -> None:
        async def _prepare(_p: Any) -> Any:
            return {
                "agentSession": {"sessionId": "s1"},
                "sessionId": "s1",
                "sessionFile": "/tmp/s.jsonl",
            }

        set_prepare_embedded_attempt_agent_session_hook(_prepare)
        result = asyncio.run(
            prepare_embedded_attempt_agent_session({})
        )
        assert result["agentSession"]["sessionId"] == "s1"
        assert result["sessionFile"] == "/tmp/s.jsonl"


# ============================================================================
# attempt-system-prompt
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_system_prompt_hooks() -> None:
    set_build_attempt_system_prompt_hook(
        lambda _p: {"text": "", "report": {}}
    )
    yield
    set_build_attempt_system_prompt_hook(
        lambda _p: {"text": "", "report": {}}
    )


class TestBuildAttemptSystemPrompt:
    def test_basic(self) -> None:
        result = build_attempt_system_prompt({})
        assert result["text"] == ""
        assert result["report"] == {}

    def test_with_hook(self) -> None:
        set_build_attempt_system_prompt_hook(
            lambda _p: {
                "text": "you are a helper",
                "report": {"tokens": 50},
            }
        )
        result = build_attempt_system_prompt({})
        assert result["text"] == "you are a helper"
        assert result["report"]["tokens"] == 50

    def test_non_dict(self) -> None:
        set_build_attempt_system_prompt_hook(lambda _p: None)
        result = build_attempt_system_prompt({})
        assert result["text"] is None
        assert result["report"] == {}
