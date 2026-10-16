"""CliAdapter: Thin headless CLI command adapter for Track 3.5.

Enforces:
- Invariant T35-03: Thin client communicating strictly over JSON-RPC. Zero imports
  of agent_runtime, plugin_sdk, or core execution engines.
- Invariant T35-18: Offline mode is strictly read-only; no local execution fallback.
"""

from __future__ import annotations

import json
from typing import Any

from jarvis_client.errors import ClientErrorCode, OfflineError
from jarvis_client.protocol.client import JarvisClient


class CliAdapter:
    """Thin CLI adapter dispatching commands strictly through JarvisClient RPCs."""

    def __init__(self, client: JarvisClient) -> None:
        self.client = client

    def send_chat_command(
        self,
        message: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch chat send from CLI arguments."""
        try:
            acc = self.client.send_chat(message=message, conversation_id=conversation_id)
            return {
                "success": acc.accepted,
                "requestId": acc.request_id,
                "turnId": acc.turn_id,
                "taskId": acc.task_id,
                "error": acc.error_message,
            }
        except OfflineError as err:
            return {
                "success": False,
                "error": str(err),
                "code": int(err.code),
            }
        except Exception as err:
            return {
                "success": False,
                "error": str(err),
                "code": int(ClientErrorCode.INTERNAL_ERROR),
            }

    def status_command(self, task_id: str | None = None) -> dict[str, Any]:
        """Query state projection and diagnostics from CLI."""
        diag = self.client.diagnostics
        tid = task_id or self.client.view_state.active_task_id
        task_view = self.client.view_state.tasks.get(tid) if tid else None

        task_data = None
        if task_view:
            task_data = {
                "taskId": task_view.task_id,
                "state": task_view.state.value,
                "title": task_view.title,
                "planRevision": task_view.plan_revision,
                "nodeCount": len(task_view.nodes),
            }

        return {
            "status": diag.status.value,
            "connected": diag.is_live,
            "activeTaskId": tid,
            "freshness": self.client.view_state.freshness.value,
            "task": task_data,
            "reconnectCount": diag.reconnect_count,
            "lastRttMs": diag.last_rtt_ms,
        }

    def list_approvals_command(self) -> list[dict[str, Any]]:
        """List all pending approvals across active tasks in state projection."""
        pending: list[dict[str, Any]] = []
        for tid, task in self.client.view_state.tasks.items():
            for nid, node in task.nodes.items():
                if node.requires_approval and node.approval_id:
                    pending.append(
                        {
                            "approvalId": node.approval_id,
                            "taskId": tid,
                            "nodeId": nid,
                            "title": node.title,
                            "planRevision": task.plan_revision,
                        }
                    )
        return pending

    def respond_approval_command(
        self,
        approval_id: str,
        approved: bool,
        expected_plan_revision: int,
        current_plan_revision: int,
        expires_at_utc: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Submit approval decision from CLI."""
        try:
            ok = self.client.respond_to_approval(
                approval_id=approval_id,
                approved=approved,
                expected_plan_revision=expected_plan_revision,
                current_plan_revision=current_plan_revision,
                expires_at_utc=expires_at_utc,
                decision_reason=reason,
            )
            return {"success": ok, "approvalId": approval_id, "approved": approved}
        except OfflineError as err:
            return {"success": False, "error": str(err), "code": int(err.code)}
        except Exception as err:
            return {
                "success": False,
                "error": str(err),
                "code": int(ClientErrorCode.INTERNAL_ERROR),
            }

    def cancel_command(self, task_id: str, reason: str = "CLI cancellation") -> dict[str, Any]:
        """Submit task cancellation from CLI."""
        try:
            res = self.client.cancel_task(task_id=task_id, reason=reason)
            return {
                "success": res.accepted,
                "taskId": res.task_id,
                "cancellationRequestId": res.cancellation_request_id,
                "error": res.error_message,
            }
        except OfflineError as err:
            return {"success": False, "error": str(err), "code": int(err.code)}
        except Exception as err:
            return {
                "success": False,
                "error": str(err),
                "code": int(ClientErrorCode.INTERNAL_ERROR),
            }

    @staticmethod
    def format_json(data: Any, indent: int = 2) -> str:
        """Format command result as stable JSON for headless automation."""
        return json.dumps(data, indent=indent, default=str)


__all__ = ["CliAdapter"]
