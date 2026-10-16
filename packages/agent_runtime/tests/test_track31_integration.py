"""End-to-End integration scenarios validating Track 3.1 Orchestration Runtime.

Scenarios Covered:
  - Scenario A: Browser continuation workflow (YouTube search -> play -> pause).
  - Scenario B: File creation crash recovery across restart.
  - Scenario C: Channel route continuity (Telegram return route isolation).
  - Scenario D: Parallel multi-tasking (YouTube + Math).
  - Scenario E: Ambiguous continuation & clarification prompt.
  - Scenario F: Tool failure & replanning without fabricated completion.
  - Scenario G: User interruption & cancellation propagation.
  - Scenario H: Crash during node execution & journal reconciliation.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import pytest

from jarvis_agent.orchestration import OrchestrationRuntime
from jarvis_agent.orchestration.brain import BrainDecisionType
from jarvis_agent.orchestration.models import (
    NodeStatus,
    ObservationRecord,
    ResponseRoute,
    TaskStage,
    UserTurn,
    VerificationResult,
)
from jarvis_agent.orchestration.recovery import FailureClass


@pytest.fixture
def temp_runtime():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_orchestration.sqlite"
        runtime = OrchestrationRuntime(db_path)
        yield runtime, db_path
        runtime.close()


def test_scenario_a_browser_youtube_workflow(temp_runtime) -> None:
    """Scenario A: YouTube browse, search, and pause state tracking."""
    runtime, _ = temp_runtime
    route = ResponseRoute(channel="desktop", conversation_id="conv_hud", user_id="user_1")

    # Turn 1: User says "Play lofi beats on YouTube"
    turn1 = UserTurn(
        turn_id="turn_1",
        request_id="r1",
        session_id="s1",
        conversation_id="conv_hud",
        user_id="user_1",
        timestamp_utc="2026-09-20T00:00:00Z",
        raw_text="Play lofi beats on YouTube",
        clean_text="Play lofi beats on YouTube",
        response_route=route,
    )
    state, decision, command = runtime.process_turn(turn1)

    assert state.task is not None
    assert state.task.current_stage == TaskStage.WAITING_FOR_TOOL
    assert state.plan is not None
    assert "n_open" in state.plan.nodes
    assert command is not None
    assert command.capability_target == "browser.navigate"

    # Tool returns observation & verification for n_open
    obs = ObservationRecord(
        "obs_1", "n_open", "2026-09-20T00:00:01Z", True, {"url": "https://youtube.com"}
    )
    ver = VerificationResult("ver_1", "v1", "n_open", True, 1, 1)
    state = runtime.handle_observation(state.task.task_id, "n_open", obs, ver)
    assert state.plan.nodes["n_open"].status == NodeStatus.COMPLETED

    # Turn 2: User says "Pause it" -> Antecedent resolves to YouTube task
    turn2 = UserTurn(
        turn_id="turn_2",
        request_id="r2",
        session_id="s1",
        conversation_id="conv_hud",
        user_id="user_1",
        timestamp_utc="2026-09-20T00:00:05Z",
        raw_text="Pause it",
        clean_text="Pause it",
        response_route=route,
    )
    state2, dec2, _ = runtime.process_turn(turn2)
    assert state2.task.task_id == state.task.task_id
    assert state2.task.current_stage == TaskStage.PAUSED


def test_scenario_b_file_creation_crash_recovery(temp_runtime) -> None:
    """Scenario B: State recovery across crash/restart preserves file task integrity."""
    runtime, db_path = temp_runtime
    route = ResponseRoute(channel="desktop", conversation_id="c1", user_id="u1")

    turn = UserTurn(
        turn_id="turn_b1",
        request_id="rb1",
        session_id="s1",
        conversation_id="c1",
        user_id="u1",
        timestamp_utc="2026-09-20T00:00:00Z",
        raw_text="Create report.md file",
        clean_text="Create report.md file",
        response_route=route,
    )
    state, _, command = runtime.process_turn(turn)
    task_id = state.task.task_id
    assert command is not None

    # Simulate crash by closing runtime abruptly
    runtime.close()

    # Reopen fresh runtime pointing at same SQLite database
    reopened = OrchestrationRuntime(db_path)
    recovered_state, suspect_ids = reopened._recovery_mgr.recover_task(task_id)

    # In-flight node was running during crash -> marked AMBIGUOUS_CRASH_SUSPECT
    assert command.node_id in suspect_ids
    assert recovered_state.plan.nodes[command.node_id].status == NodeStatus.AMBIGUOUS_CRASH_SUSPECT
    reopened.close()


def test_scenario_c_channel_route_continuity(temp_runtime) -> None:
    """Scenario C: Telegram return route remains strictly bound and isolated from Desktop HUD."""
    runtime, _ = temp_runtime
    tg_route = ResponseRoute(
        channel="telegram",
        conversation_id="tg_chat_88",
        user_id="tg_user_9",
        thread_id="topic_12",
        reply_to_message_id="msg_555",
    )
    turn = UserTurn(
        turn_id="turn_tg",
        request_id="rtg",
        session_id="s_tg",
        conversation_id="tg_chat_88",
        user_id="tg_user_9",
        timestamp_utc="2026-09-20T00:00:00Z",
        raw_text="Summarize latest release",
        clean_text="Summarize latest release",
        response_route=tg_route,
    )
    state, _, _ = runtime.process_turn(turn)

    # ResponseRoute in state must match Telegram origin
    assert state.task.response_route.channel == "telegram"
    assert state.task.response_route.conversation_id == "tg_chat_88"
    assert state.task.response_route.reply_to_message_id == "msg_555"


def test_scenario_d_parallel_multi_tasking(temp_runtime) -> None:
    """Scenario D: User initiates second task while first is in-flight."""
    runtime, _ = temp_runtime
    route = ResponseRoute(channel="desktop", conversation_id="c_multi", user_id="u1")

    # Task 1: Play YouTube video
    turn1 = UserTurn(
        turn_id="t1",
        request_id="r1",
        session_id="s1",
        conversation_id="c_multi",
        user_id="u1",
        timestamp_utc="2026-09-20T00:00:00Z",
        raw_text="Play video on YouTube",
        clean_text="Play video on YouTube",
        response_route=route,
    )
    state1, _, _ = runtime.process_turn(turn1)
    tid1 = state1.task.task_id

    # Task 2: Explicit new task for Math
    turn2 = UserTurn(
        turn_id="t2",
        request_id="r2",
        session_id="s1",
        conversation_id="c_multi",
        user_id="u1",
        timestamp_utc="2026-09-20T00:00:02Z",
        raw_text="New task: compute prime factors of 1024",
        clean_text="New task: compute prime factors of 1024",
        response_route=route,
    )
    state2, _, _ = runtime.process_turn(turn2)
    tid2 = state2.task.task_id

    assert tid1 != tid2
    assert runtime._focus.current_focus() == tid2
    assert runtime._focus.list_focus_stack() == [tid1, tid2]


def test_scenario_e_ambiguous_continuation_and_clarification(temp_runtime) -> None:
    """Scenario E: Multiple active tasks with ambiguous pronoun trigger clarification."""
    runtime, _ = temp_runtime
    route = ResponseRoute(channel="desktop", conversation_id="c_amb", user_id="u1")

    # Start Task 1
    t1 = UserTurn(
        "t1",
        "r1",
        "s1",
        "c_amb",
        "u1",
        "2026-09-20T00:00:00Z",
        "Inspect logs",
        "Inspect logs",
        route,
    )
    s1, _, _ = runtime.process_turn(t1)

    # Start Task 2
    t2 = UserTurn(
        "t2",
        "r2",
        "s1",
        "c_amb",
        "u1",
        "2026-09-20T00:00:01Z",
        "New task: run benchmark",
        "New task: run benchmark",
        route,
    )
    s2, _, _ = runtime.process_turn(t2)

    # Ambiguous command: "cancel it" across 2 active tasks with no entity match
    t3 = UserTurn(
        "t3", "r3", "s1", "c_amb", "u1", "2026-09-20T00:00:02Z", "Cancel it", "Cancel it", route
    )
    s3, dec3, cmd3 = runtime.process_turn(t3)

    assert dec3.decision_type == BrainDecisionType.REQUEST_CLARIFICATION
    assert cmd3 is None


def test_scenario_f_tool_failure_and_replanning(temp_runtime) -> None:
    """Scenario F: Tool failure triggers replanning; verified nodes are not refabricated or rerun."""
    runtime, _ = temp_runtime
    route = ResponseRoute(channel="desktop", conversation_id="c_fail", user_id="u1")

    turn = UserTurn(
        "t1",
        "r1",
        "s1",
        "c_fail",
        "u1",
        "2026-09-20T00:00:00Z",
        "Play song on YouTube",
        "Play song on YouTube",
        route,
    )
    state, _, command = runtime.process_turn(turn)
    tid = state.task.task_id

    # Node n_open completes
    obs = ObservationRecord("obs_1", "n_open", "2026-09-20T00:00:01Z", True, {})
    ver = VerificationResult("ver_1", "v1", "n_open", True, 1, 1)
    state = runtime.handle_observation(tid, "n_open", obs, ver)

    # Node n_search fails due to network timeout
    state, dec = runtime.handle_failure(
        tid, "n_search", FailureClass.TIMEOUT, "HTTP 504 Gateway Timeout"
    )

    assert state.plan.revision == 2
    # n_open completed in v1 remains completed in v2
    assert state.plan.nodes["n_open"].status == NodeStatus.COMPLETED
    assert len(state.revisions) == 1
    assert state.revisions[0].diff.reason == "HTTP 504 Gateway Timeout"


def test_scenario_g_user_interruption_cancellation(temp_runtime) -> None:
    """Scenario G: User says 'stop' -> transitions to CANCELLED and cancels in-flight work."""
    runtime, _ = temp_runtime
    route = ResponseRoute(channel="desktop", conversation_id="c_cancel", user_id="u1")

    turn = UserTurn(
        "t1",
        "r1",
        "s1",
        "c_cancel",
        "u1",
        "2026-09-20T00:00:00Z",
        "Download large file",
        "Download large file",
        route,
    )
    state, _, _ = runtime.process_turn(turn)

    # User interrupts
    turn_stop = UserTurn(
        "t2", "r2", "s1", "c_cancel", "u1", "2026-09-20T00:00:02Z", "Stop now!", "Stop now!", route
    )
    state_cancel, dec_cancel, _ = runtime.process_turn(turn_stop)

    assert state_cancel.task.current_stage == TaskStage.CANCELLED
    assert dec_cancel.decision_type == BrainDecisionType.FAIL_TASK


def test_scenario_h_crash_during_node_execution_journal_reconciliation(temp_runtime) -> None:
    """Scenario H: Crash during node execution; journal records AMBIGUOUS_CRASH_SUSPECTED."""
    runtime, db_path = temp_runtime
    route = ResponseRoute(channel="desktop", conversation_id="c_h", user_id="u1")

    turn = UserTurn(
        "t1",
        "r1",
        "s1",
        "c_h",
        "u1",
        "2026-09-20T00:00:00Z",
        "Backup database",
        "Backup database",
        route,
    )
    state, _, cmd = runtime.process_turn(turn)
    tid = state.task.task_id
    assert cmd is not None

    runtime.close()

    reopened = OrchestrationRuntime(db_path)
    recovered, suspects = (
        reopened.recover_after_crash(tid)
        if hasattr(reopened, "recover_after_crash")
        else reopened._recovery_mgr.recover_task(tid)
    )

    assert cmd.node_id in suspects
    assert recovered.plan.nodes[cmd.node_id].status == NodeStatus.AMBIGUOUS_CRASH_SUSPECT

    events = reopened._event_store.get_events_for_task(tid)
    assert any(e.event_type.value == "AMBIGUOUS_CRASH_SUSPECTED" for e in events)
    reopened.close()
