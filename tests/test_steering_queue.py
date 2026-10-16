"""Tests for src/agents/steering_queue.py.

Mirrors tests of agent-steering-queue in OpenClaw.
"""

from __future__ import annotations


from src.agents.steering_queue import (
    SYNTHETIC_SKIPPED_TOOL_RESULT,
    AgentSteeringQueue,
    generate_synthetic_skipped_tool_result,
)


def test_generate_synthetic_skipped_tool_result():
    res = generate_synthetic_skipped_tool_result("call_123", "exec")
    assert res["role"] == "tool"
    assert res["tool_call_id"] == "call_123"
    assert res["name"] == "exec"
    assert res["content"] == SYNTHETIC_SKIPPED_TOOL_RESULT
    assert res["error"] is True
    assert res["skipped_by_steering"] is True


def test_steering_queue_enqueue_peek_lease():
    q = AgentSteeringQueue(session_key="session:main:1")
    assert q.size() == 0

    q.enqueue(run_id="r1", message="Please stop reading files and run tests.")
    assert q.size() == 1

    item = q.peek()
    assert item is not None
    assert item.message == "Please stop reading files and run tests."

    leased = q.lease_batch(lease_id="lease_1", max_items=10)
    assert len(leased) == 1
    assert leased[0].lease_id == "lease_1"

    # Subsequent peek finds no unleased items
    assert q.peek() is None

    # Commit lease removes items
    q.commit_lease("lease_1")
    assert q.size() == 0


def test_steering_queue_rollback():
    q = AgentSteeringQueue(session_key="session:main:2")
    q.enqueue(run_id="r2", message="Fix tests")

    leased = q.lease_batch(lease_id="lease_2")
    assert len(leased) == 1

    q.rollback_lease("lease_2")
    assert q.size() == 1
    assert q.peek() is not None
