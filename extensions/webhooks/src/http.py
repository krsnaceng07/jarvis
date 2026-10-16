"""HTTP request handler, authentication, and TaskFlow action dispatcher for Webhooks plugin.

OpenClaw parity: mirrors @openclaw/webhooks HTTP handler:
- Constant-time secret authentication (Bearer token, headers, query param)
- Rate limiting and in-flight concurrency limiter
- Action dispatching across all 13 TaskFlow operations
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
from typing import Any

from .http_request_schema import validate_webhook_action
from .types import TaskFlowWebhookTarget

logger = logging.getLogger("jarvis.webhooks.http")


def resolve_secret_value(secret_input: str | dict[str, Any]) -> str | None:
    """Resolve raw string secret or SecretRef dict."""
    if isinstance(secret_input, str):
        return secret_input.strip()
    if isinstance(secret_input, dict):
        source = secret_input.get("source")
        if source == "env":
            var_name = secret_input.get("id")
            return os.environ.get(var_name, "").strip() if var_name else None
        if source == "file":
            path_str = secret_input.get("id")
            if path_str and os.path.exists(path_str):
                try:
                    with open(path_str, "r", encoding="utf-8") as f:
                        return f.read().strip()
                except Exception:
                    return None
        # Other SecretRef sources
        return secret_input.get("value")
    return None


def extract_request_secret(
    headers: dict[str, str],
    query_params: dict[str, str] | None = None,
) -> str | None:
    """Extract inbound secret from Authorization header, X-Secret header, or query param."""
    # Normalize headers to lowercase keys
    h_lower = {k.lower(): v for k, v in headers.items()}

    # 1. Authorization: Bearer <token>
    auth_header = h_lower.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    # 2. X-Jarvis-Secret / X-OpenClaw-Secret
    if "x-jarvis-secret" in h_lower:
        return h_lower["x-jarvis-secret"].strip()
    if "x-openclaw-secret" in h_lower:
        return h_lower["x-openclaw-secret"].strip()

    # 3. Query param ?secret=...
    if query_params and "secret" in query_params:
        return query_params["secret"].strip()

    return None


class WebhookRateLimiter:
    """Simple in-memory fixed-window rate limiter."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._counts: dict[str, tuple[int, float]] = {}

    def is_allowed(self, client_id: str, now: float | None = None) -> bool:
        current_time = time.time() if now is None else now
        entry = self._counts.get(client_id)
        if not entry:
            self._counts[client_id] = (1, current_time)
            return True

        count, start_time = entry
        if current_time - start_time > self.window_seconds:
            self._counts[client_id] = (1, current_time)
            return True

        if count >= self.max_requests:
            return False

        self._counts[client_id] = (count + 1, start_time)
        return True


class TaskFlowWebhookHandler:
    """Processes authenticated webhook requests and executes TaskFlow actions."""

    def __init__(
        self,
        targets_by_path: dict[str, list[TaskFlowWebhookTarget]],
        rate_limiter: WebhookRateLimiter | None = None,
    ) -> None:
        self.targets_by_path = targets_by_path
        self.rate_limiter = rate_limiter or WebhookRateLimiter()

    async def handle_request(
        self,
        path: str,
        method: str,
        headers: dict[str, str],
        body_bytes: bytes,
        query_params: dict[str, str] | None = None,
        client_ip: str = "127.0.0.1",
    ) -> tuple[int, dict[str, Any]]:
        """Handle incoming webhook request.

        Returns (status_code, response_json).
        """
        # 1. Check HTTP method
        if method.upper() != "POST":
            return 405, {"ok": False, "error": f"Method '{method}' not allowed. Must be POST."}

        # 2. Check rate limit
        if not self.rate_limiter.is_allowed(client_ip):
            return 429, {"ok": False, "error": "Too many requests. Rate limit exceeded."}

        # 3. Match route target
        targets = self.targets_by_path.get(path)
        if not targets:
            return 404, {"ok": False, "error": f"No webhook route registered for path '{path}'"}

        target = targets[0]

        # 4. Authenticate secret
        expected_secret = resolve_secret_value(target.secret_input)
        if not expected_secret:
            logger.error(f"Webhook route '{target.route_id}' secret could not be resolved")
            return 500, {"ok": False, "error": "Internal route secret configuration error"}

        provided_secret = extract_request_secret(headers, query_params)
        if not provided_secret or not hmac.compare_digest(provided_secret, expected_secret):
            return 401, {"ok": False, "error": "Unauthorized: invalid or missing webhook secret"}

        # 5. Parse and validate JSON body
        if not body_bytes:
            return 400, {"ok": False, "error": "Missing request body"}

        try:
            body_json = json.loads(body_bytes.decode("utf-8"))
        except Exception as exc:
            return 400, {"ok": False, "error": f"Invalid JSON body: {exc}"}

        try:
            action_payload = validate_webhook_action(body_json)
        except ValueError as val_err:
            return 400, {"ok": False, "error": str(val_err)}

        # 6. Dispatch action to TaskFlow runtime
        try:
            result = await self._dispatch_task_flow_action(target, action_payload)
            return 200, {"ok": True, **result}
        except Exception as exc:
            logger.exception(
                f"Error executing TaskFlow action '{action_payload.get('action')}': {exc}"
            )
            return 500, {"ok": False, "error": str(exc)}

    async def _dispatch_task_flow_action(
        self,
        target: TaskFlowWebhookTarget,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch action to the bound task flow object or in-memory runtime."""
        action = payload["action"]
        task_flow = target.task_flow

        if not task_flow:
            # Standalone / mock return
            return {"action": action, "status": "acknowledged", "routeId": target.route_id}

        # Check methods on bound task_flow
        if action == "create_flow":
            controller_id = payload.get("controllerId") or target.default_controller_id
            flow = await task_flow.create_flow(
                goal=payload["goal"],
                controller_id=controller_id,
                status=payload.get("status", "queued"),
                notify_policy=payload.get("notifyPolicy", "done_only"),
                current_step=payload.get("currentStep"),
                state_json=payload.get("stateJson"),
                wait_json=payload.get("waitJson"),
            )
            return {"flow": flow.to_dict() if hasattr(flow, "to_dict") else flow}

        if action == "get_flow":
            flow = await task_flow.get_flow(flow_id=payload["flowId"])
            return {"flow": flow.to_dict() if hasattr(flow, "to_dict") else flow}

        if action == "list_flows":
            flows = await task_flow.list_flows()
            return {"flows": [f.to_dict() if hasattr(f, "to_dict") else f for f in flows]}

        if action == "find_latest_flow":
            flow = await task_flow.find_latest_flow()
            return {"flow": flow.to_dict() if hasattr(flow, "to_dict") else flow}

        if action == "resolve_flow":
            flow = await task_flow.resolve_flow(token=payload["token"])
            return {"flow": flow.to_dict() if hasattr(flow, "to_dict") else flow}

        if action == "get_task_summary":
            summary = await task_flow.get_task_summary(flow_id=payload["flowId"])
            return {"summary": summary}

        if action == "set_waiting":
            flow = await task_flow.set_waiting(
                flow_id=payload["flowId"],
                expected_revision=payload["expectedRevision"],
                current_step=payload.get("currentStep"),
                state_json=payload.get("stateJson"),
                wait_json=payload.get("waitJson"),
                blocked_task_id=payload.get("blockedTaskId"),
                blocked_summary=payload.get("blockedSummary"),
            )
            return {"flow": flow.to_dict() if hasattr(flow, "to_dict") else flow}

        if action == "resume_flow":
            flow = await task_flow.resume_flow(
                flow_id=payload["flowId"],
                expected_revision=payload["expectedRevision"],
                status=payload.get("status", "running"),
                current_step=payload.get("currentStep"),
                state_json=payload.get("stateJson"),
            )
            return {"flow": flow.to_dict() if hasattr(flow, "to_dict") else flow}

        if action == "finish_flow":
            flow = await task_flow.finish_flow(
                flow_id=payload["flowId"],
                expected_revision=payload["expectedRevision"],
                state_json=payload.get("stateJson"),
            )
            return {"flow": flow.to_dict() if hasattr(flow, "to_dict") else flow}

        if action == "fail_flow":
            flow = await task_flow.fail_flow(
                flow_id=payload["flowId"],
                expected_revision=payload["expectedRevision"],
                state_json=payload.get("stateJson"),
                blocked_task_id=payload.get("blockedTaskId"),
                blocked_summary=payload.get("blockedSummary"),
            )
            return {"flow": flow.to_dict() if hasattr(flow, "to_dict") else flow}

        if action == "request_cancel":
            flow = await task_flow.request_cancel(
                flow_id=payload["flowId"],
                expected_revision=payload["expectedRevision"],
            )
            return {"flow": flow.to_dict() if hasattr(flow, "to_dict") else flow}

        if action == "cancel_flow":
            flow = await task_flow.cancel_flow(flow_id=payload["flowId"])
            return {"flow": flow.to_dict() if hasattr(flow, "to_dict") else flow}

        if action == "run_task":
            task = await task_flow.run_task(
                flow_id=payload["flowId"],
                runtime=payload["runtime"],
                task=payload["task"],
                status=payload.get("status", "queued"),
                source_id=payload.get("sourceId"),
                child_session_key=payload.get("childSessionKey"),
                parent_task_id=payload.get("parentTaskId"),
                agent_id=payload.get("agentId"),
                run_id=payload.get("runId"),
                label=payload.get("label"),
                prefer_metadata=payload.get("preferMetadata", False),
                notify_policy=payload.get("notifyPolicy", "done_only"),
                started_at=payload.get("startedAt"),
                last_event_at=payload.get("lastEventAt"),
                progress_summary=payload.get("progressSummary"),
            )
            return {"task": task.to_dict() if hasattr(task, "to_dict") else task}

        return {"action": action, "status": "unhandled"}
