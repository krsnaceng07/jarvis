"""Unit tests for Track 3.1 Task Continuity, Focus, Ambiguity, and Lifecycle Management."""

from __future__ import annotations

import datetime
from jarvis_agent.orchestration.models import ResponseRoute, TaskIdentity, UserTurn
from jarvis_agent.orchestration.task import (
    AmbiguityScorer,
    TaskFocusManager,
    TaskLifecycleManager,
    TaskLineageTracker,
    TaskResolver,
)


def test_task_lineage_hierarchy() -> None:
    tracker = TaskLineageTracker()
    root_id = TaskIdentity(
        task_id="t_root",
        conversation_id="c1",
        session_id="s1",
        root_task_id="t_root",
        turn_id="turn_1",
        creation_event_id="e1",
    )
    child_id = TaskIdentity(
        task_id="t_child",
        conversation_id="c1",
        session_id="s1",
        root_task_id="t_root",
        turn_id="turn_2",
        creation_event_id="e2",
        parent_task_id="t_root",
        generation=2,
    )
    grandchild_id = TaskIdentity(
        task_id="t_grandchild",
        conversation_id="c1",
        session_id="s1",
        root_task_id="t_root",
        turn_id="turn_3",
        creation_event_id="e3",
        parent_task_id="t_child",
        generation=3,
    )

    tracker.register_task(root_id)
    tracker.register_task(child_id)
    tracker.register_task(grandchild_id)

    assert tracker.get_children("t_root") == ["t_child"]
    assert tracker.get_children("t_child") == ["t_grandchild"]
    assert tracker.is_ancestor("t_root", "t_grandchild") is True
    assert tracker.is_ancestor("t_child", "t_root") is False
    assert tracker.get_generation("t_grandchild") == 3


def test_focus_manager_stack_and_antecedent_resolution() -> None:
    focus = TaskFocusManager()

    # Push task 1 (YouTube video)
    focus.push_focus("task_youtube", {"url": "https://youtube.com/watch?v=123", "type": "video"})
    assert focus.current_focus() == "task_youtube"

    # Push task 2 (Writing report)
    focus.push_focus("task_report", {"file": "summary.md", "type": "document"})
    assert focus.current_focus() == "task_report"
    assert focus.list_focus_stack() == ["task_youtube", "task_report"]

    # Pronoun referring to video should resolve to task_youtube despite task_report being on top
    tid_video, ent_video = focus.resolve_antecedent("Pause the video")
    assert tid_video == "task_youtube"
    assert ent_video == "https://youtube.com/watch?v=123"

    # Reference to file resolves to task_report
    tid_file, ent_file = focus.resolve_antecedent("Format the document")
    assert tid_file == "task_report"
    assert ent_file == "summary.md"

    # Generic pronoun "pause it" resolves to top of stack (task_report)
    tid_it, _ = focus.resolve_antecedent("Pause it")
    assert tid_it == "task_report"

    # Pop focus
    popped = focus.pop_focus()
    assert popped == "task_report"
    assert focus.current_focus() == "task_youtube"


def test_ambiguity_scoring_and_resolver() -> None:
    focus = TaskFocusManager()
    focus.push_focus("t_video", {"media": "youtube"})
    focus.push_focus("t_code", {"file": "main.py"})

    scorer = AmbiguityScorer()
    resolver = TaskResolver(focus, scorer)
    route = ResponseRoute(channel="desktop", conversation_id="c1", user_id="u1")

    # Case A: Ambiguous command with multiple active tasks ("stop it")
    turn_ambiguous = UserTurn(
        turn_id="turn_1",
        request_id="r1",
        session_id="s1",
        conversation_id="c1",
        user_id="u1",
        timestamp_utc="2026-09-20T00:00:00Z",
        raw_text="Stop it",
        clean_text="Stop it",
        response_route=route,
    )
    res_ambiguous = resolver.resolve(turn_ambiguous, active_task_ids=["t_video", "t_code"])
    assert res_ambiguous.action == "CLARIFY"
    assert len(res_ambiguous.candidate_task_ids) == 2

    # Case B: Unambiguous entity target ("Stop the video")
    turn_specific = UserTurn(
        turn_id="turn_2",
        request_id="r2",
        session_id="s1",
        conversation_id="c1",
        user_id="u1",
        timestamp_utc="2026-09-20T00:00:00Z",
        raw_text="Stop the video",
        clean_text="Stop the video",
        response_route=route,
    )
    res_specific = resolver.resolve(turn_specific, active_task_ids=["t_video", "t_code"])
    assert res_specific.action == "CONTINUE"
    assert res_specific.target_task_id == "t_video"

    # Case C: Explicit new task ("New task: calculate prime numbers")
    turn_new = UserTurn(
        turn_id="turn_3",
        request_id="r3",
        session_id="s1",
        conversation_id="c1",
        user_id="u1",
        timestamp_utc="2026-09-20T00:00:00Z",
        raw_text="New task: calculate prime numbers",
        clean_text="New task: calculate prime numbers",
        response_route=route,
    )
    res_new = resolver.resolve(turn_new, active_task_ids=["t_video", "t_code"])
    assert res_new.action == "NEW"
    assert res_new.new_goal == "calculate prime numbers"


def test_task_lifecycle_reaping() -> None:
    lifecycle = TaskLifecycleManager(default_inactivity_seconds=60.0)
    now = datetime.datetime.now(datetime.timezone.utc)
    one_hour_ago = now - datetime.timedelta(seconds=3600)

    lifecycle.register_task("t_stale", created_at=one_hour_ago)
    lifecycle.register_task("t_fresh", created_at=now)

    reaped = lifecycle.reap_stale_tasks(["t_stale", "t_fresh"], current_time=now)
    assert "t_stale" in reaped
    assert "t_fresh" not in reaped
