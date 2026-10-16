"""Phase 7.6d-6 tests — 11 attempt.* files (startup, finalize, session-boundary, trajectory-status, prompt-dispatch, tool-search-run-plan, before-agent-run, orphan-repair, stage-timing, execution-phase, timeout-prepare)."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.agents.embedded_agent_runner.run.attempt_startup import (
    prepare_embedded_attempt_skills,
    set_prepare_skills_hook,
    set_start_diagnostics_hook,
    start_embedded_attempt_diagnostics,
)
from src.agents.embedded_agent_runner.run.attempt_finalize import (
    finalize_embedded_attempt,
    set_finalize_attempt_hook,
)
from src.agents.embedded_agent_runner.run.attempt_session_boundary import (
    prepare_embedded_attempt_session_boundary,
    set_prepare_session_boundary_hook,
)
from src.agents.embedded_agent_runner.run.attempt_trajectory_status import (
    resolve_attempt_trajectory_terminal,
    resolve_terminal_assistant_texts,
    set_resolve_terminal_assistant_texts_hook,
    set_resolve_trajectory_terminal_hook,
)
from src.agents.embedded_agent_runner.run.attempt_prompt_dispatch import (
    dispatch_embedded_attempt_prompt,
    set_dispatch_prompt_hook,
)
from src.agents.embedded_agent_runner.run.attempt_tool_search_run_plan import (
    resolve_attempt_tool_search_run_plan,
    set_resolve_tool_search_run_plan_hook,
)
from src.agents.embedded_agent_runner.run.attempt_before_agent_run import (
    run_embedded_attempt_before_agent_run,
    set_run_before_agent_run_hook,
)
from src.agents.embedded_agent_runner.run.attempt_orphan_repair import (
    replay_trailing_entries_for_orphan_repair,
    resolve_orphan_repair_plan,
    set_replay_trailing_entries_hook,
    set_resolve_orphan_repair_plan_hook,
)
from src.agents.embedded_agent_runner.run.attempt_stage_timing import (
    EMBEDDED_RUN_ATTEMPT_DISPATCH_STAGE,
    EMBEDDED_RUN_STAGE_SUMMARY_EMIT_MS,
    EMBEDDED_RUN_STAGE_SUMMARY_WARN_MS,
    create_embedded_run_stage_summary_emitter,
    create_embedded_run_stage_tracker,
    format_embedded_run_stage_summary,
    should_warn_embedded_run_stage_summary,
)
from src.agents.embedded_agent_runner.run.attempt_execution_phase import (
    run_embedded_attempt_execution_phase,
    set_run_execution_phase_hook,
)
from src.agents.embedded_agent_runner.run.attempt_timeout_prepare import (
    prepare_embedded_attempt_timeout,
    set_prepare_timeout_hook,
)


# ============================================================================
# attempt-startup
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_startup_hooks() -> None:
    set_prepare_skills_hook(lambda _p: None)
    set_start_diagnostics_hook(lambda _p: {})
    yield
    set_prepare_skills_hook(lambda _p: None)
    set_start_diagnostics_hook(lambda _p: {})


class TestPrepareEmbeddedAttemptSkills:
    def test_basic(self) -> None:
        result = prepare_embedded_attempt_skills({})
        assert result["skills"] == {}
        assert result["skillNames"] == []

    def test_with_skills(self) -> None:
        set_prepare_skills_hook(
            lambda _p: {"skillNames": ["search", "browse"]}
        )
        result = prepare_embedded_attempt_skills({})
        assert result["skillNames"] == ["search", "browse"]


class TestStartEmbeddedAttemptDiagnostics:
    def test_basic(self) -> None:
        result = start_embedded_attempt_diagnostics({})
        assert result["runTrace"] is None
        assert result["diagnosticTrace"] is None

    def test_with_traces(self) -> None:
        set_start_diagnostics_hook(
            lambda _p: {
                "runTrace": "rt",
                "diagnosticTrace": "dt",
            }
        )
        result = start_embedded_attempt_diagnostics({})
        assert result["runTrace"] == "rt"
        assert result["diagnosticTrace"] == "dt"


# ============================================================================
# attempt-finalize
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_finalize_hooks() -> None:
    set_finalize_attempt_hook(lambda _p: {})
    yield
    set_finalize_attempt_hook(lambda _p: {})


class TestFinalizeEmbeddedAttempt:
    def test_basic(self) -> None:
        attempt = {
            "runId": "r1",
            "sessionId": "s1",
            "aborted": True,
            "messagesSnapshot": [{"role": "user"}],
        }
        result = finalize_embedded_attempt({"attempt": attempt})
        assert result["runId"] == "r1"
        assert result["aborted"] is True
        assert len(result["messagesSnapshot"]) == 1

    def test_with_hook(self) -> None:
        set_finalize_attempt_hook(lambda _p: {"finalized": True})
        result = finalize_embedded_attempt(
            {"attempt": {"runId": "r1"}}
        )
        assert result["extra"] == {"finalized": True}


# ============================================================================
# attempt-session-boundary
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_session_boundary_hooks() -> None:
    set_prepare_session_boundary_hook(lambda _p: {})
    yield
    set_prepare_session_boundary_hook(lambda _p: {})


class TestPrepareEmbeddedAttemptSessionBoundary:
    def test_basic(self) -> None:
        result = prepare_embedded_attempt_session_boundary({})
        assert result["boundaryTimezone"] is None
        assert result["includeBoundaryTimestamp"] is False
        assert result["orphanRepair"] is None

    def test_with_hook(self) -> None:
        set_prepare_session_boundary_hook(
            lambda _p: {
                "boundaryTimezone": "UTC",
                "includeBoundaryTimestamp": True,
                "orphanRepair": {"needsRepair": True},
            }
        )
        result = prepare_embedded_attempt_session_boundary({})
        assert result["boundaryTimezone"] == "UTC"
        assert result["includeBoundaryTimestamp"] is True
        assert result["orphanRepair"]["needsRepair"] is True


# ============================================================================
# attempt-trajectory-status
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_trajectory_status_hooks() -> None:
    set_resolve_terminal_assistant_texts_hook(lambda _p: [])
    set_resolve_trajectory_terminal_hook(lambda _p: {})
    yield
    set_resolve_terminal_assistant_texts_hook(lambda _p: [])


class TestResolveTerminalAssistantTexts:
    def test_basic(self) -> None:
        assert resolve_terminal_assistant_texts({}) == []

    def test_with_hook(self) -> None:
        set_resolve_terminal_assistant_texts_hook(
            lambda _p: ["hello", "world"]
        )
        assert resolve_terminal_assistant_texts({}) == ["hello", "world"]


class TestResolveAttemptTrajectoryTerminal:
    def test_basic(self) -> None:
        assert resolve_attempt_trajectory_terminal({}) == {}

    def test_with_hook(self) -> None:
        set_resolve_trajectory_terminal_hook(
            lambda _p: {"terminal": True, "reason": "completed"}
        )
        result = resolve_attempt_trajectory_terminal({})
        assert result["terminal"] is True
        assert result["reason"] == "completed"


# ============================================================================
# attempt-prompt-dispatch
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_dispatch_hooks() -> None:
    set_dispatch_prompt_hook(lambda _p: asyncio.sleep(0))
    yield
    set_dispatch_prompt_hook(lambda _p: asyncio.sleep(0))


class TestDispatchEmbeddedAttemptPrompt:
    def test_basic(self) -> None:
        result = asyncio.run(
            dispatch_embedded_attempt_prompt({})
        )
        assert result["promptActiveSession"] is None

    def test_with_hook(self) -> None:
        async def _dispatch(_p: Any) -> Any:
            return {
                "promptActiveSession": "pas",
                "sessionPromptState": {"sent": 1},
                "trajectoryRecorder": "tr",
            }

        set_dispatch_prompt_hook(_dispatch)
        result = asyncio.run(
            dispatch_embedded_attempt_prompt({})
        )
        assert result["promptActiveSession"] == "pas"
        assert result["sessionPromptState"]["sent"] == 1
        assert result["trajectoryRecorder"] == "tr"


# ============================================================================
# attempt-tool-search-run-plan
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_tool_search_run_plan_hooks() -> None:
    set_resolve_tool_search_run_plan_hook(lambda _p: {})
    yield
    set_resolve_tool_search_run_plan_hook(lambda _p: {})


class TestResolveAttemptToolSearchRunPlan:
    def test_basic(self) -> None:
        result = resolve_attempt_tool_search_run_plan({})
        assert result["shouldRunToolSearch"] is False
        assert result["compacted"] is None

    def test_with_hook(self) -> None:
        set_resolve_tool_search_run_plan_hook(
            lambda _p: {"shouldRunToolSearch": True, "compacted": {"a": 1}}
        )
        result = resolve_attempt_tool_search_run_plan({})
        assert result["shouldRunToolSearch"] is True
        assert result["compacted"]["a"] == 1


# ============================================================================
# attempt-before-agent-run
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_before_agent_run_hooks() -> None:
    set_run_before_agent_run_hook(lambda _p: asyncio.sleep(0))
    yield
    set_run_before_agent_run_hook(lambda _p: asyncio.sleep(0))


class TestRunEmbeddedAttemptBeforeAgentRun:
    def test_basic(self) -> None:
        result = asyncio.run(
            run_embedded_attempt_before_agent_run({})
        )
        assert result["beforeAgentRunResult"] is None
        assert result["blocked"] is False
        assert result["blockedBy"] is None

    def test_with_hook_blocked(self) -> None:
        async def _run(_p: Any) -> Any:
            return {"blocked": True, "blockedBy": "policy"}

        set_run_before_agent_run_hook(_run)
        result = asyncio.run(
            run_embedded_attempt_before_agent_run({})
        )
        assert result["blocked"] is True
        assert result["blockedBy"] == "policy"


# ============================================================================
# attempt-orphan-repair
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_orphan_repair_hooks() -> None:
    set_replay_trailing_entries_hook(lambda _p: [])
    set_resolve_orphan_repair_plan_hook(lambda _p: {})
    yield
    set_replay_trailing_entries_hook(lambda _p: [])


class TestReplayTrailingEntriesForOrphanRepair:
    def test_basic(self) -> None:
        assert (
            replay_trailing_entries_for_orphan_repair({}) == []
        )

    def test_with_hook(self) -> None:
        set_replay_trailing_entries_hook(
            lambda _p: [{"id": "1"}, {"id": "2"}]
        )
        result = replay_trailing_entries_for_orphan_repair({})
        assert len(result) == 2


class TestResolveOrphanRepairPlan:
    def test_basic(self) -> None:
        assert resolve_orphan_repair_plan({}) == {}

    def test_with_hook(self) -> None:
        set_resolve_orphan_repair_plan_hook(
            lambda _p: {"needsRepair": True, "toReplay": 2}
        )
        result = resolve_orphan_repair_plan({})
        assert result["needsRepair"] is True
        assert result["toReplay"] == 2


# ============================================================================
# attempt-stage-timing
# ============================================================================


class TestAttemptStageTimingConstants:
    def test_dispatch_stage_keys(self) -> None:
        assert "auth_plan" in EMBEDDED_RUN_ATTEMPT_DISPATCH_STAGE
        assert "auth" in EMBEDDED_RUN_ATTEMPT_DISPATCH_STAGE
        assert "scope" in EMBEDDED_RUN_ATTEMPT_DISPATCH_STAGE
        assert "stream_dispatch" in EMBEDDED_RUN_ATTEMPT_DISPATCH_STAGE

    def test_thresholds(self) -> None:
        assert EMBEDDED_RUN_STAGE_SUMMARY_WARN_MS == 5_000
        assert EMBEDDED_RUN_STAGE_SUMMARY_EMIT_MS == 30_000


class TestCreateEmbeddedRunStageTracker:
    def test_basic(self) -> None:
        tracker = create_embedded_run_stage_tracker()
        assert isinstance(tracker["startedAtMs"], int)
        assert tracker["stages"] == []
        assert tracker["current"] is None

    def test_with_options(self) -> None:
        tracker = create_embedded_run_stage_tracker(
            {"warnMs": 1000, "emitMs": 2000}
        )
        assert tracker["warnMs"] == 1000
        assert tracker["emitMs"] == 2000


class TestShouldWarnEmbeddedRunStageSummary:
    def test_no_tracker(self) -> None:
        assert should_warn_embedded_run_stage_summary(None) is False

    def test_non_dict(self) -> None:
        assert should_warn_embedded_run_stage_summary("not-a-dict") is False  # type: ignore[arg-type]

    def test_incomplete(self) -> None:
        assert should_warn_embedded_run_stage_summary({}) is False


class TestCreateEmbeddedRunStageSummaryEmitter:
    def test_basic(self) -> None:
        tracker = create_embedded_run_stage_tracker()
        emitter = create_embedded_run_stage_summary_emitter(
            {"tracker": tracker}
        )
        assert emitter["tracker"] is tracker
        assert emitter["startedAtMs"] == tracker["startedAtMs"]


class TestFormatEmbeddedRunStageSummary:
    def test_no_tracker(self) -> None:
        assert format_embedded_run_stage_summary(None) == ""

    def test_empty_stages(self) -> None:
        tracker = create_embedded_run_stage_tracker()
        assert format_embedded_run_stage_summary(tracker) == "no-stages"

    def test_with_stages(self) -> None:
        tracker = create_embedded_run_stage_tracker()
        tracker["stages"] = ["a", "b", "c"]
        assert format_embedded_run_stage_summary(tracker) == "a,b,c"


# ============================================================================
# attempt-execution-phase
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_execution_phase_hooks() -> None:
    set_run_execution_phase_hook(lambda _p: asyncio.sleep(0))
    yield
    set_run_execution_phase_hook(lambda _p: asyncio.sleep(0))


class TestRunEmbeddedAttemptExecutionPhase:
    def test_basic(self) -> None:
        result = asyncio.run(
            run_embedded_attempt_execution_phase({})
        )
        assert result["outcome"] == "completed"
        assert result["attemptResult"] is None
        assert result["execution"] == {}

    def test_with_hook(self) -> None:
        async def _run(_p: Any) -> Any:
            return {
                "outcome": "failed",
                "attemptResult": {"aborted": True},
                "execution": {"phase": "tool-call"},
            }

        set_run_execution_phase_hook(_run)
        result = asyncio.run(
            run_embedded_attempt_execution_phase({})
        )
        assert result["outcome"] == "failed"
        assert result["attemptResult"]["aborted"] is True


# ============================================================================
# attempt-timeout-prepare
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_timeout_prepare_hooks() -> None:
    set_prepare_timeout_hook(lambda _p: {})
    yield
    set_prepare_timeout_hook(lambda _p: {})


class TestPrepareEmbeddedAttemptTimeout:
    def test_basic(self) -> None:
        result = prepare_embedded_attempt_timeout({})
        assert result["getRunAbortDeadlineAtMs"] is None
        assert result["clearTimers"] is None

    def test_with_hook(self) -> None:
        def _clear() -> None:
            pass

        set_prepare_timeout_hook(
            lambda _p: {
                "getRunAbortDeadlineAtMs": lambda: 12345,
                "clearTimers": _clear,
                "removeAbortSignalListener": "remove",
            }
        )
        result = prepare_embedded_attempt_timeout({})
        assert result["getRunAbortDeadlineAtMs"]() == 12345
        assert result["clearTimers"] is _clear
        assert result["removeAbortSignalListener"] == "remove"
