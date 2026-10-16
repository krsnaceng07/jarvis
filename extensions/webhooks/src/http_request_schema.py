"""HTTP request action schemas and validation for Webhooks plugin.

OpenClaw parity: mirrors @openclaw/webhooks 13 TaskFlow actions,
validation constraints, and type definitions.
"""

from __future__ import annotations

from typing import Any


def validate_webhook_action(body: Any) -> dict[str, Any]:
    """Validate and normalize inbound webhook action payload.

    Raises ValueError on validation failure.
    """
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")

    action = body.get("action")
    if not action or not isinstance(action, str):
        raise ValueError("Missing or invalid 'action' field in request body")

    action = action.strip()

    # ── 1. create_flow ────────────────────────────────────────────────────────
    if action == "create_flow":
        goal = str(body.get("goal") or "").strip()
        if not goal:
            raise ValueError("create_flow: 'goal' is required and cannot be empty")

        status = body.get("status")
        if status is not None and status not in ("queued", "running", "waiting", "blocked"):
            raise ValueError(f"create_flow: invalid status '{status}'")

        notify_policy = body.get("notifyPolicy")
        if notify_policy is not None and notify_policy not in (
            "done_only",
            "state_changes",
            "silent",
        ):
            raise ValueError(f"create_flow: invalid notifyPolicy '{notify_policy}'")

        return {
            "action": "create_flow",
            "goal": goal,
            "controllerId": str(body["controllerId"]).strip() if body.get("controllerId") else None,
            "status": status or "queued",
            "notifyPolicy": notify_policy or "done_only",
            "currentStep": str(body["currentStep"]).strip() if body.get("currentStep") else None,
            "stateJson": body.get("stateJson"),
            "waitJson": body.get("waitJson"),
        }

    # ── 2. get_flow ───────────────────────────────────────────────────────────
    if action == "get_flow":
        flow_id = str(body.get("flowId") or "").strip()
        if not flow_id:
            raise ValueError("get_flow: 'flowId' is required and cannot be empty")
        return {"action": "get_flow", "flowId": flow_id}

    # ── 3. list_flows ─────────────────────────────────────────────────────────
    if action == "list_flows":
        return {"action": "list_flows"}

    # ── 4. find_latest_flow ───────────────────────────────────────────────────
    if action == "find_latest_flow":
        return {"action": "find_latest_flow"}

    # ── 5. resolve_flow ───────────────────────────────────────────────────────
    if action == "resolve_flow":
        token = str(body.get("token") or "").strip()
        if not token:
            raise ValueError("resolve_flow: 'token' is required and cannot be empty")
        return {"action": "resolve_flow", "token": token}

    # ── 6. get_task_summary ───────────────────────────────────────────────────
    if action == "get_task_summary":
        flow_id = str(body.get("flowId") or "").strip()
        if not flow_id:
            raise ValueError("get_task_summary: 'flowId' is required and cannot be empty")
        return {"action": "get_task_summary", "flowId": flow_id}

    # ── 7. set_waiting ────────────────────────────────────────────────────────
    if action == "set_waiting":
        flow_id = str(body.get("flowId") or "").strip()
        if not flow_id:
            raise ValueError("set_waiting: 'flowId' is required and cannot be empty")
        if (
            "expectedRevision" not in body
            or not isinstance(body["expectedRevision"], int)
            or body["expectedRevision"] < 0
        ):
            raise ValueError("set_waiting: 'expectedRevision' must be a non-negative integer")

        return {
            "action": "set_waiting",
            "flowId": flow_id,
            "expectedRevision": body["expectedRevision"],
            "currentStep": str(body["currentStep"]).strip() if body.get("currentStep") else None,
            "stateJson": body.get("stateJson"),
            "waitJson": body.get("waitJson"),
            "blockedTaskId": str(body["blockedTaskId"]).strip()
            if body.get("blockedTaskId")
            else None,
            "blockedSummary": str(body["blockedSummary"]).strip()
            if body.get("blockedSummary")
            else None,
        }

    # ── 8. resume_flow ────────────────────────────────────────────────────────
    if action == "resume_flow":
        flow_id = str(body.get("flowId") or "").strip()
        if not flow_id:
            raise ValueError("resume_flow: 'flowId' is required and cannot be empty")
        if (
            "expectedRevision" not in body
            or not isinstance(body["expectedRevision"], int)
            or body["expectedRevision"] < 0
        ):
            raise ValueError("resume_flow: 'expectedRevision' must be a non-negative integer")

        status = body.get("status")
        if status is not None and status not in ("queued", "running"):
            raise ValueError(f"resume_flow: invalid status '{status}'")

        return {
            "action": "resume_flow",
            "flowId": flow_id,
            "expectedRevision": body["expectedRevision"],
            "status": status or "running",
            "currentStep": str(body["currentStep"]).strip() if body.get("currentStep") else None,
            "stateJson": body.get("stateJson"),
        }

    # ── 9. finish_flow ────────────────────────────────────────────────────────
    if action == "finish_flow":
        flow_id = str(body.get("flowId") or "").strip()
        if not flow_id:
            raise ValueError("finish_flow: 'flowId' is required and cannot be empty")
        if (
            "expectedRevision" not in body
            or not isinstance(body["expectedRevision"], int)
            or body["expectedRevision"] < 0
        ):
            raise ValueError("finish_flow: 'expectedRevision' must be a non-negative integer")

        return {
            "action": "finish_flow",
            "flowId": flow_id,
            "expectedRevision": body["expectedRevision"],
            "stateJson": body.get("stateJson"),
        }

    # ── 10. fail_flow ─────────────────────────────────────────────────────────
    if action == "fail_flow":
        flow_id = str(body.get("flowId") or "").strip()
        if not flow_id:
            raise ValueError("fail_flow: 'flowId' is required and cannot be empty")
        if (
            "expectedRevision" not in body
            or not isinstance(body["expectedRevision"], int)
            or body["expectedRevision"] < 0
        ):
            raise ValueError("fail_flow: 'expectedRevision' must be a non-negative integer")

        return {
            "action": "fail_flow",
            "flowId": flow_id,
            "expectedRevision": body["expectedRevision"],
            "stateJson": body.get("stateJson"),
            "blockedTaskId": str(body["blockedTaskId"]).strip()
            if body.get("blockedTaskId")
            else None,
            "blockedSummary": str(body["blockedSummary"]).strip()
            if body.get("blockedSummary")
            else None,
        }

    # ── 11. request_cancel ────────────────────────────────────────────────────
    if action == "request_cancel":
        flow_id = str(body.get("flowId") or "").strip()
        if not flow_id:
            raise ValueError("request_cancel: 'flowId' is required and cannot be empty")
        if (
            "expectedRevision" not in body
            or not isinstance(body["expectedRevision"], int)
            or body["expectedRevision"] < 0
        ):
            raise ValueError("request_cancel: 'expectedRevision' must be a non-negative integer")

        return {
            "action": "request_cancel",
            "flowId": flow_id,
            "expectedRevision": body["expectedRevision"],
        }

    # ── 12. cancel_flow ───────────────────────────────────────────────────────
    if action == "cancel_flow":
        flow_id = str(body.get("flowId") or "").strip()
        if not flow_id:
            raise ValueError("cancel_flow: 'flowId' is required and cannot be empty")
        return {"action": "cancel_flow", "flowId": flow_id}

    # ── 13. run_task ──────────────────────────────────────────────────────────
    if action == "run_task":
        flow_id = str(body.get("flowId") or "").strip()
        if not flow_id:
            raise ValueError("run_task: 'flowId' is required and cannot be empty")

        runtime = body.get("runtime")
        if runtime not in ("subagent", "acp"):
            raise ValueError("run_task: 'runtime' must be 'subagent' or 'acp'")

        task_desc = str(body.get("task") or "").strip()
        if not task_desc:
            raise ValueError("run_task: 'task' is required and cannot be empty")

        status = body.get("status") or "queued"
        if status not in ("queued", "running"):
            raise ValueError(f"run_task: invalid status '{status}'")

        started_at = body.get("startedAt")
        last_event_at = body.get("lastEventAt")
        progress_summary = body.get("progressSummary")

        if status != "running" and (
            started_at is not None or last_event_at is not None or progress_summary is not None
        ):
            raise ValueError(
                "run_task: status must be 'running' when startedAt, lastEventAt, or progressSummary is provided"
            )

        notify_policy = body.get("notifyPolicy")
        if notify_policy is not None and notify_policy not in (
            "done_only",
            "state_changes",
            "silent",
        ):
            raise ValueError(f"run_task: invalid notifyPolicy '{notify_policy}'")

        return {
            "action": "run_task",
            "flowId": flow_id,
            "runtime": runtime,
            "task": task_desc,
            "status": status,
            "sourceId": str(body["sourceId"]).strip() if body.get("sourceId") else None,
            "childSessionKey": str(body["childSessionKey"]).strip()
            if body.get("childSessionKey")
            else None,
            "parentTaskId": str(body["parentTaskId"]).strip() if body.get("parentTaskId") else None,
            "agentId": str(body["agentId"]).strip() if body.get("agentId") else None,
            "runId": str(body["runId"]).strip() if body.get("runId") else None,
            "label": str(body["label"]).strip() if body.get("label") else None,
            "preferMetadata": bool(body.get("preferMetadata", False)),
            "notifyPolicy": notify_policy or "done_only",
            "startedAt": int(started_at) if started_at is not None else None,
            "lastEventAt": int(last_event_at) if last_event_at is not None else None,
            "progressSummary": str(progress_summary).strip() if progress_summary else None,
        }

    raise ValueError(f"Unknown webhook action '{action}'")
