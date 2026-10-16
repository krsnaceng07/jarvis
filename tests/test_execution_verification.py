"""tests.test_execution_verification — Tests for ExecutionVerifier real-world OS verification.

Guarantees:
1. File write operations are confirmed by inspecting disk.
2. File edit operations are confirmed by inspecting file content on disk.
3. Path/drive checks truthful reporting when missing or invalid.
4. Process execution checks verify exit codes and error outputs.
"""

import sys
import pytest
from src.agents.verification.execution_verifier import ExecutionVerifier


def test_verify_filesystem_write_success(tmp_path):
    target = tmp_path / "created.txt"
    content = "Hello, JARVIS and OpenClaw parity!"
    target.write_text(content, encoding="utf-8")

    outcome = ExecutionVerifier.verify_filesystem_write(
        target, expected_bytes=len(content.encode("utf-8"))
    )
    assert outcome.verified is True
    assert outcome.status == "verified"
    assert outcome.tool_name == "write"
    assert outcome.details["size_bytes"] == len(content.encode("utf-8"))
    assert outcome.error is None


def test_verify_filesystem_write_nonexistent(tmp_path):
    target = tmp_path / "never_created.txt"
    outcome = ExecutionVerifier.verify_filesystem_write(target)
    assert outcome.verified is False
    assert outcome.status == "failed"
    assert outcome.error is not None
    assert "does not exist on disk" in outcome.error


def test_verify_filesystem_write_missing_drive():
    if sys.platform != "win32":
        pytest.skip("Windows-only drive test")

    outcome = ExecutionVerifier.verify_filesystem_write("D:\\nonexistent_dir\\file.txt")
    assert outcome.verified is False
    assert outcome.status == "failed"
    assert outcome.error is not None
    assert "Target drive does not exist" in outcome.error
    assert "Available drives:" in outcome.error


def test_verify_filesystem_write_size_mismatch(tmp_path):
    target = tmp_path / "undersized.txt"
    target.write_text("short", encoding="utf-8")

    outcome = ExecutionVerifier.verify_filesystem_write(target, expected_bytes=100)
    assert outcome.verified is False
    assert outcome.status == "failed"
    assert outcome.error is not None
    assert "smaller than expected" in outcome.error


def test_verify_filesystem_edit_success(tmp_path):
    target = tmp_path / "code.py"
    target.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    outcome = ExecutionVerifier.verify_filesystem_edit(
        target, expected_content_fragments=["return 'world'"]
    )
    assert outcome.verified is True
    assert outcome.status == "verified"


def test_verify_filesystem_edit_missing_fragment(tmp_path):
    target = tmp_path / "code.py"
    target.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    outcome = ExecutionVerifier.verify_filesystem_edit(
        target, expected_content_fragments=["return 'universe'"]
    )
    assert outcome.verified is False
    assert outcome.status == "failed"
    assert outcome.error is not None
    assert "Expected edits not found" in outcome.error


def test_verify_filesystem_path_checks(tmp_path):
    file_path = tmp_path / "item.txt"
    file_path.write_text("test", encoding="utf-8")

    # Existing file
    v_file = ExecutionVerifier.verify_filesystem_path(file_path)
    assert v_file.verified is True

    # must_be_dir on file fails
    v_not_dir = ExecutionVerifier.verify_filesystem_path(file_path, must_be_dir=True)
    assert v_not_dir.verified is False
    assert v_not_dir.error is not None
    assert "is not a directory" in v_not_dir.error

    # Directory succeeds
    v_dir = ExecutionVerifier.verify_filesystem_path(tmp_path, must_be_dir=True)
    assert v_dir.verified is True


def test_verify_process_execution():
    ok_outcome = ExecutionVerifier.verify_process_execution(0, stdout="Success output")
    assert ok_outcome.verified is True
    assert ok_outcome.status == "verified"

    err_outcome = ExecutionVerifier.verify_process_execution(
        1, stderr="Fatal error: module not found"
    )
    assert err_outcome.verified is False
    assert err_outcome.status == "failed"
    assert err_outcome.error is not None
    assert "exited with non-zero code 1" in err_outcome.error


def test_verify_desktop_action():
    ok = ExecutionVerifier.verify_desktop_action("click", "calc", "Clicked on calculator button")
    assert ok.verified is True
    assert ok.status == "verified"

    err = ExecutionVerifier.verify_desktop_action("focus", "unknown_app", "Application or window 'unknown_app' not found.")
    assert err.verified is False
    assert err.status == "failed"

    pending = ExecutionVerifier.verify_desktop_action("kill", "notepad", "CONFIRMATION REQUIRED: Are you sure?")
    assert pending.verified is False
    assert pending.status == "pending"


def test_verify_messaging_action():
    ok = ExecutionVerifier.verify_messaging_action("whatsapp", "Alice", "SUCCESS: WhatsApp message sent to 'Alice'. [TASK FULFILLED]")
    assert ok.verified is True
    assert ok.status == "verified"

    err = ExecutionVerifier.verify_messaging_action("whatsapp", "Bob", "WhatsApp error: contact not found")
    assert err.verified is False
    assert err.status == "failed"


def test_verify_subagent_and_generic():
    ok_sub = ExecutionVerifier.verify_subagent_action("sessions_spawn", "task-1", "Spawned subagent session child-123")
    assert ok_sub.verified is True

    err_sub = ExecutionVerifier.verify_subagent_action("sessions_spawn", "task-1", "Error: failed to spawn session")
    assert err_sub.verified is False
    assert err_sub.status == "failed"

    ok_gen = ExecutionVerifier.verify_generic_tool("custom_tool", "Done successfully")
    assert ok_gen.verified is True

    err_gen = ExecutionVerifier.verify_generic_tool("custom_tool", "Error: division by zero")
    assert err_gen.verified is False
    assert err_gen.status == "failed"
