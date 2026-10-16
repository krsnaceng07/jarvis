"""tests.test_task_continuity — Tests for multi-step task state and SQLite transcripts.

Validates:
1. Task state machine lifecycle (CREATED -> PLANNING -> RUNNING -> COMPLETED).
2. Step tracking and execution history recording.
3. Model-visible prompt formatting for task context.
4. SQLite persistence for turns, tool calls, and execution records.
"""

from src.agents.task.task_state import TaskStateManager
from src.agents.task.session_transcript_store import SessionTranscriptStore
from src.agents.verification.execution_verifier import VerificationOutcome


def test_task_state_manager_lifecycle():
    manager = TaskStateManager()
    task = manager.create_task(
        goal="Implement secure drive discovery",
        steps=["Step 1: Check Win32 API", "Step 2: Update ls tool", "Step 3: Run tests"],
    )

    assert task.goal == "Implement secure drive discovery"
    assert task.status == "RUNNING"
    assert task.current_step_index == 1
    assert len(task.steps) == 3
    assert task.steps[0].description == "Step 1: Check Win32 API"

    # Record execution on step 1
    verif = VerificationOutcome(
        status="verified",
        verified=True,
        tool_name="write",
        target_resource="path_utils.py",
    )
    manager.record_execution(
        tool_name="write",
        arguments={"path": "path_utils.py", "content": "..."},
        raw_output="Wrote 500 bytes",
        status="success",
        verification=verif,
        affected_files=["path_utils.py"],
    )

    assert task.steps[0].status == "completed"
    assert "path_utils.py" in task.modified_files
    assert len(task.execution_history) == 1

    # Advance to step 2
    manager.advance_step()
    assert task.current_step_index == 2
    assert task.steps[1].status == "running"

    # Advance to step 3
    manager.record_execution("write", {}, "written", verification=verif)
    manager.advance_step()
    assert task.current_step_index == 3

    # Advance past last step -> COMPLETED
    manager.record_execution("write", {}, "written", verification=verif)
    manager.advance_step()
    assert task.status == "COMPLETED"


def test_unverified_work_cannot_complete_or_skip_steps():
    manager = TaskStateManager()
    task = manager.create_task("Create and verify document", ["Create document", "Verify content"])
    manager.record_execution("write", {}, "I will write it", status="success")
    manager.advance_step()
    assert task.current_step_index == 1
    assert task.steps[0].status == "running"
    assert task.status != "COMPLETED"


def test_cancelled_task_does_not_advance():
    manager = TaskStateManager()
    task = manager.create_task("Task", ["Step"])
    task.steps[0].status = "completed"
    task.status = "CANCELLED"
    manager.advance_step()
    assert task.status == "CANCELLED"
    assert task.current_step_index == 1


def test_task_context_formatting():
    manager = TaskStateManager()
    manager.create_task(
        goal="Refactor authentication",
        steps=["Step 1: Add tokens", "Step 2: Verify tokens"],
    )
    verif = VerificationOutcome(status="verified", verified=True, tool_name="exec")
    manager.record_execution(
        tool_name="exec",
        arguments={"command": "pytest"},
        raw_output="2 passed in 0.1s",
        status="success",
        verification=verif,
    )

    context = manager.format_task_context_for_prompt()
    assert "[CONTINUOUS TASK CONTEXT]" in context
    assert "Active Goal: Refactor authentication" in context
    assert "Current Step: Step 1 of 2" in context
    assert "Most Recent Action: [exec]" in context
    assert "[Verified]" in context
    assert "2 passed in 0.1s" in context
    assert "Continuity Directive:" in context


def test_session_transcript_store_sqlite(tmp_path):
    db_file = tmp_path / "test_transcripts.sqlite"
    store = SessionTranscriptStore(db_path=str(db_file))

    seq1 = store.append_entry("sess_1", "user_turn", {"text": "Hello JARVIS"})
    assert seq1 == 1

    seq2 = store.append_entry(
        "sess_1",
        "tool_call",
        {"name": "ls", "args": {"path": "drives"}},
    )
    assert seq2 == 2

    seq3 = store.append_entry(
        "sess_1",
        "execution_record",
        {"tool_name": "ls", "status": "success"},
        verified=True,
    )
    assert seq3 == 3

    seq4 = store.append_entry(
        "sess_1",
        "assistant_speech",
        {"text": "Drives available: C:, E:"},
    )
    assert seq4 == 4

    # Verify retrieval
    recent = store.get_recent_entries("sess_1")
    assert len(recent) == 4
    assert recent[0]["entry_type"] == "user_turn"
    assert recent[0]["data"]["text"] == "Hello JARVIS"
    assert recent[2]["entry_type"] == "execution_record"
    assert recent[2]["verified"] is True

    # Verify latest execution record lookup
    last_exec = store.get_last_execution_record("sess_1")
    assert last_exec is not None
    assert last_exec["entry_type"] == "execution_record"
    assert last_exec["data"]["tool_name"] == "ls"
    assert last_exec["verified"] is True
