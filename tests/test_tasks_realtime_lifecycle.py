"""tests.test_tasks_realtime_lifecycle — Empirical verification of real-time background task tracking & completion events.

Validates OpenClaw parity for:
1. Real-time task registration in TaskRegistry (status: running / queued).
2. Live status visibility in task ledger and process tool (action='list').
3. Terminal status update formatting (done, failed, timed_out, cancelled).
4. Reactive system event delivery into SystemEventQueue on task exit.
5. Reactive agent wake-up via request_heartbeat.
6. Execution background process tracking and completion notification.
"""

import time
import pytest

from src.automation.task_registry import (
    get_task_by_id,
    list_task_records,
)
from src.infra.heartbeat_wake import (
    reset_heartbeat_wake_for_tests,
    set_heartbeat_wake_handler,
)
from src.sessions.system_event_queue import (
    dequeue_system_events,
)
from src.tasks import (
    create_running_task_run,
    finalize_task_run_by_run_id,
    format_task_terminal_message,
    record_task_run_progress_by_run_id,
)
from src.agents.sessions.process_registry import registry as proc_registry
from src.agents.sessions.tools.process_tool import create_process_tool_definition
from src.gateway.tasks_handlers import make_tasks_handlers


@pytest.fixture(autouse=True)
def cleanup():
    reset_heartbeat_wake_for_tests()
    yield
    reset_heartbeat_wake_for_tests()


def test_detached_task_realtime_lifecycle():
    session_key = "agent:main:realtime-test"
    run_id = "test-run-123"

    # Track wake requests
    wakes = []
    set_heartbeat_wake_handler(lambda opts: wakes.append(opts))

    # 1. Register running task
    task = create_running_task_run(
        runtime="cli",
        task_kind="background_exec",
        requester_session_key=session_key,
        owner_key=session_key,
        run_id=run_id,
        label="Test background build",
        task="python -m build",
        notify_policy="done_only",
    )
    assert task.status == "running"
    assert task.run_id == run_id

    # 2. Verify real-time visibility in TaskRegistry
    found = get_task_by_id(task.task_id)
    assert found is not None
    assert found.status == "running"
    assert found.label == "Test background build"

    # 3. Gateway tasks.list sees it in real time
    handlers = make_tasks_handlers()
    list_res = handlers["tasks.list"]({"status": "running"})
    assert any(t["task_id"] == task.task_id for t in list_res["tasks"])

    # 4. Record progress
    record_task_run_progress_by_run_id(run_id, "Compiling package...")
    found = get_task_by_id(task.task_id)
    assert found.progress_summary == "Compiling package..."

    # 5. Finalize task run as succeeded
    finalized = finalize_task_run_by_run_id(
        run_id=run_id,
        status="succeeded",
        terminal_summary="Build completed with 0 errors",
    )
    assert len(finalized) == 1
    assert finalized[0].status == "succeeded"

    # 6. Verify terminal delivery generated system event and wake-up
    events = dequeue_system_events(session_key)
    assert len(events) >= 1
    assert "Background task done: Test background build" in events[0]["message"]
    assert "Build completed with 0 errors" in events[0]["message"]

    # Verify heartbeat wake was triggered immediately
    assert len(wakes) >= 1
    assert wakes[-1]["source"] == "background-task"
    assert wakes[-1]["intent"] == "immediate"
    assert wakes[-1]["sessionKey"] == session_key


def test_format_task_terminal_message_variants():
    base = create_running_task_run(
        runtime="cli",
        label="DB Migration",
        task="alembic upgrade head",
        requester_session_key="agent:main:test",
    )

    import dataclasses

    # Succeeded
    succeeded = dataclasses.replace(base, status="succeeded", terminal_summary="12 migrations applied")
    msg = format_task_terminal_message(succeeded)
    assert "Background task done: DB Migration." in msg
    assert "12 migrations applied" in msg

    # Failed
    failed = dataclasses.replace(base, status="failed", error="Connection refused on port 5432")
    msg = format_task_terminal_message(failed)
    assert "Background task failed: DB Migration." in msg
    assert "Connection refused on port 5432" in msg

    # Timed out
    timed_out = dataclasses.replace(base, status="timed_out")
    msg = format_task_terminal_message(timed_out)
    assert "Background task timed out: DB Migration." in msg

    # Cancelled
    cancelled = dataclasses.replace(base, status="cancelled")
    msg = format_task_terminal_message(cancelled)
    assert "Background task cancelled: DB Migration." in msg


def test_process_tool_list_action():
    # Setup process registry with one active and one finished session
    from src.agents.sessions.process_registry import ProcessSession, FinishedSession
    
    session_id_1 = "proc-act-1"
    session_id_2 = "proc-fin-2"
    test_session_key = "agent:main:proc-test"

    proc_registry.register(
        ProcessSession(
            id=session_id_1,
            command="python -m http.server 8000",
            session_key=test_session_key,
            started_at=time.time() - 30,
            pid=12345,
            backgrounded=True,
        )
    )

    proc_registry.mark_finished(session_id_2, code=0)
    proc_registry._finished[session_id_2] = FinishedSession(
        id=session_id_2,
        command="git status",
        started_at=time.time() - 60,
        ended_at=time.time() - 58,
        session_key=test_session_key,
        exit_code=0,
        tail="On branch main\nnothing to commit",
    )

    tool_def = create_process_tool_definition(options={"session_key": test_session_key})

    import asyncio
    result = asyncio.run(
        tool_def["execute"]("call_1", {"action": "list"})
    )

    text = result["content"][0]["text"]
    assert "proc-act-1" in text
    assert "python -m http.server 8000" in text
    assert "proc-fin-2" in text
    assert "finished (code 0)" in text
    assert result["details"]["activeCount"] >= 1
    assert result["details"]["finishedCount"] >= 1

    # Cleanup
    proc_registry.remove(session_id_1)
    proc_registry.remove(session_id_2)


def test_background_command_execution_and_notification():
    from src.agents.sessions.exec import spawn_background_command

    wakes = []
    set_heartbeat_wake_handler(lambda opts: wakes.append(opts))
    session_key = "agent:main:exec-test"

    import sys
    if sys.platform == "win32":
        cmd = "powershell.exe"
        args = ["-NoProfile", "-Command", "Write-Output 'Hello from background task'"]
    else:
        cmd = "/bin/sh"
        args = ["-c", "echo 'Hello from background task'"]

    session_id = spawn_background_command(
        command=cmd,
        args=args,
        cwd=".",
        session_key=session_key,
    )
    assert session_id

    # Check that task was immediately registered in TaskRegistry as running
    run_id = f"exec:{session_id}"
    tasks = [t for t in list_task_records() if t.run_id == run_id]
    assert len(tasks) == 1
    assert tasks[0].status in ("running", "succeeded")

    # Wait for the background process to exit
    time.sleep(1.5)

    # Verify task in TaskRegistry transitioned to succeeded
    tasks_after = [t for t in list_task_records() if t.run_id == run_id]
    assert len(tasks_after) == 1
    assert tasks_after[0].status == "succeeded"

    # Verify session event queue has notification
    events = dequeue_system_events(session_key)
    assert len(events) >= 1
    assert any("Exec completed" in e["message"] or "Background task done" in e["message"] for e in events)

    # Verify agent wake-up was received
    assert len(wakes) >= 1
    assert any(w["sessionKey"] == session_key for w in wakes)

    # Cleanup
    proc_registry.remove(session_id)
