"""tests.test_task_classifier — Unit tests for TaskClassifier and continuity detection."""

from src.agents.task.task_classifier import TaskClassifier, TaskIntent
from src.agents.task.task_state import TaskState, TaskStep


def test_classify_new_task_empty():
    res = TaskClassifier.classify("")
    assert res.intent == TaskIntent.NEW_TASK


def test_classify_status_query():
    for phrase in [
        "what are you doing?",
        "task status",
        "show progress",
        "k gardai chhau",
        "status k chha?",
    ]:
        res = TaskClassifier.classify(phrase)
        assert res.intent == TaskIntent.ANSWER_QUESTION_ABOUT_CURRENT_TASK, f"Failed on: {phrase}"


def test_classify_cancellation():
    for phrase in [
        "cancel",
        "stop this",
        "nevermind",
        "chhodideu",
        "banda gara yo",
    ]:
        res = TaskClassifier.classify(phrase)
        assert res.intent == TaskIntent.CANCEL_ACTIVE_TASK, f"Failed on: {phrase}"


def test_classify_continuation_with_active_task():
    task = TaskState(
        task_id="t-1",
        goal="Organize files",
        status="RUNNING",
        steps=[
            TaskStep(step_index=1, description="Create folder", status="completed"),
            TaskStep(step_index=2, description="Move files", status="pending"),
        ],
        current_step_index=1,
    )

    for phrase in [
        "continue",
        "proceed",
        "next step",
        "aagadi badha",
        "arko gara",
        "continue gardeu",
    ]:
        res = TaskClassifier.classify(phrase, active_task=task)
        assert res.intent == TaskIntent.CONTINUE_ACTIVE_TASK, f"Failed on: {phrase}"
        assert res.target_step_index == 2


def test_classify_retry_with_failed_action():
    task = TaskState(
        task_id="t-1",
        goal="Delete temp files",
        status="RUNNING",
        steps=[TaskStep(step_index=1, description="Delete file", status="failed")],
        current_step_index=1,
    )

    for phrase in [
        "retry",
        "try again",
        "bhayena feri gara",
        "chaina feri",
        "feri prayas gara",
    ]:
        res = TaskClassifier.classify(phrase, active_task=task, last_action_status="failed")
        assert res.intent == TaskIntent.RETRY_FAILED_STEP, f"Failed on: {phrase}"
        assert res.target_step_index == 1
