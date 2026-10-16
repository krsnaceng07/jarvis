"""Unit tests for TaskFlow action validation, execution, and doctor checks."""

import json
from unittest.mock import MagicMock

import pytest
from extensions.webhooks.src.doctor import run_webhooks_doctor_checks
from extensions.webhooks.src.http import TaskFlowWebhookHandler
from extensions.webhooks.src.http_request_schema import validate_webhook_action
from extensions.webhooks.src.types import TaskFlowWebhookTarget


def test_validate_action_create_flow() -> None:
    """Test validation of create_flow action."""
    # Valid
    payload = {
        "action": "create_flow",
        "goal": "Build deployment pipeline",
        "status": "running",
        "notifyPolicy": "state_changes",
    }
    validated = validate_webhook_action(payload)
    assert validated["action"] == "create_flow"
    assert validated["goal"] == "Build deployment pipeline"
    assert validated["status"] == "running"

    # Missing goal
    with pytest.raises(ValueError, match="'goal' is required"):
        validate_webhook_action({"action": "create_flow"})


def test_validate_action_run_task() -> None:
    """Test validation of run_task action constraints."""
    # Valid running task with progress
    payload1 = {
        "action": "run_task",
        "flowId": "flow-123",
        "runtime": "subagent",
        "task": "Execute migration script",
        "status": "running",
        "progressSummary": "50% completed",
    }
    validated1 = validate_webhook_action(payload1)
    assert validated1["runtime"] == "subagent"
    assert validated1["status"] == "running"

    # Invalid: queued status with progressSummary
    payload2 = {
        "action": "run_task",
        "flowId": "flow-123",
        "runtime": "acp",
        "task": "Execute migration script",
        "status": "queued",
        "progressSummary": "started",
    }
    with pytest.raises(
        ValueError, match="status must be 'running' when startedAt, lastEventAt, or progressSummary"
    ):
        validate_webhook_action(payload2)

    # Invalid runtime
    with pytest.raises(ValueError, match="'runtime' must be 'subagent' or 'acp'"):
        validate_webhook_action(
            {
                "action": "run_task",
                "flowId": "flow-123",
                "runtime": "invalid",
                "task": "Do something",
            }
        )


def test_validate_lifecycle_actions() -> None:
    """Test validation of set_waiting, resume_flow, finish_flow, fail_flow, request_cancel."""
    # set_waiting
    w = validate_webhook_action(
        {
            "action": "set_waiting",
            "flowId": "flow-1",
            "expectedRevision": 2,
            "blockedSummary": "Waiting for user input",
        }
    )
    assert w["expectedRevision"] == 2

    # resume_flow
    r = validate_webhook_action(
        {
            "action": "resume_flow",
            "flowId": "flow-1",
            "expectedRevision": 3,
        }
    )
    assert r["status"] == "running"

    # finish_flow
    f = validate_webhook_action(
        {
            "action": "finish_flow",
            "flowId": "flow-1",
            "expectedRevision": 4,
        }
    )
    assert f["expectedRevision"] == 4

    # fail_flow
    fa = validate_webhook_action(
        {
            "action": "fail_flow",
            "flowId": "flow-1",
            "expectedRevision": 4,
            "blockedSummary": "Database unreachable",
        }
    )
    assert fa["blockedSummary"] == "Database unreachable"

    # request_cancel
    rc = validate_webhook_action(
        {
            "action": "request_cancel",
            "flowId": "flow-1",
            "expectedRevision": 4,
        }
    )
    assert rc["expectedRevision"] == 4


@pytest.mark.asyncio
async def test_dispatch_all_actions(mock_task_flow: MagicMock) -> None:
    """Test full dispatch pipeline for all actions through HTTP handler."""
    target = TaskFlowWebhookTarget(
        route_id="main",
        path="/plugins/webhooks/main",
        secret_input="secret123",
        default_controller_id="webhooks/main",
        task_flow=mock_task_flow,
    )
    handler = TaskFlowWebhookHandler(targets_by_path={"/plugins/webhooks/main": [target]})
    headers = {"Authorization": "Bearer secret123"}

    # 1. create_flow
    s, b = await handler.handle_request(
        path="/plugins/webhooks/main",
        method="POST",
        headers=headers,
        body_bytes=json.dumps({"action": "create_flow", "goal": "Deploy app"}).encode("utf-8"),
    )
    assert s == 200
    assert b["ok"] is True
    assert b["flow"]["goal"] == "Test Goal"

    # 2. get_flow
    s, b = await handler.handle_request(
        path="/plugins/webhooks/main",
        method="POST",
        headers=headers,
        body_bytes=json.dumps({"action": "get_flow", "flowId": "flow-123"}).encode("utf-8"),
    )
    assert s == 200
    assert b["flow"]["status"] == "running"

    # 3. set_waiting
    s, b = await handler.handle_request(
        path="/plugins/webhooks/main",
        method="POST",
        headers=headers,
        body_bytes=json.dumps(
            {"action": "set_waiting", "flowId": "flow-123", "expectedRevision": 1}
        ).encode("utf-8"),
    )
    assert s == 200
    assert b["flow"]["status"] == "waiting"

    # 4. run_task
    s, b = await handler.handle_request(
        path="/plugins/webhooks/main",
        method="POST",
        headers=headers,
        body_bytes=json.dumps(
            {
                "action": "run_task",
                "flowId": "flow-123",
                "runtime": "subagent",
                "task": "Run tests",
            }
        ).encode("utf-8"),
    )
    assert s == 200
    assert b["task"]["taskId"] == "task-999"


def test_webhooks_doctor_checks() -> None:
    """Test doctor diagnostics for webhooks."""
    # 1. No routes
    f1 = run_webhooks_doctor_checks({})
    assert f1[0].status == "ok"
    assert "idle" in f1[0].message

    # 2. Active valid routes
    f2 = run_webhooks_doctor_checks(
        {
            "routes": {
                "github": {"sessionKey": "gh-session", "secret": "s1"},
            }
        }
    )
    assert len(f2) == 2
    assert all(f.status == "ok" for f in f2)

    # 3. Invalid route configuration (missing secret)
    f3 = run_webhooks_doctor_checks(
        {
            "routes": {
                "github": {"sessionKey": "gh-session"},
            }
        }
    )
    assert any(f.status == "error" for f in f3)
