"""Authoritative event reducer for Track 3.5 client runtime.

Reduces gateway events into ephemeral ClientViewState.
Handles task creation, stage transitions, node execution progress, stdout streaming,
approvals, cancellations, and verifications.
"""

from __future__ import annotations

from jarvis_client.events.decoder import DecodedEvent
from jarvis_client.state.client_view import ClientViewState, NodeViewState


class ClientEventReducer:
    """Pure state reduction engine for incoming gateway domain events."""

    def __init__(self, view_state: ClientViewState) -> None:
        self.view_state = view_state

    def reduce(self, event: DecodedEvent) -> None:
        """Apply a decoded event to update the local projection."""
        event_type = event.event_type.upper().replace(".", "_")
        payload = event.payload
        task_id = payload.get("taskId") or payload.get("task_id")
        tid_str = str(task_id) if task_id else None

        self.view_state.last_authoritative_event_utc = event.timestamp_utc

        if not tid_str:
            return

        task = self.view_state.get_or_create_task(tid_str)
        task.last_event_time_utc = event.timestamp_utc

        if event_type in ("TASK_ACCEPTED", "TASK_CREATED", "INTENT_DISCOVERED"):
            title = payload.get("title") or payload.get("userPrompt") or payload.get("goal")
            if title:
                task.title = str(title)
            task.stage = "INTENT_DISCOVERY"
            task.status = "ACTIVE"
            self.view_state.active_task_id = tid_str

        elif event_type in ("STAGE_CHANGED", "ORCHESTRATION_STAGE_CHANGED"):
            new_stage = payload.get("newStage") or payload.get("stage") or payload.get("to_stage")
            if new_stage:
                task.stage = str(new_stage)

        elif event_type in ("PLAN_REGISTERED", "PLAN_DAG_REGISTERED"):
            nodes_dict = payload.get("nodes", {})
            if isinstance(nodes_dict, dict):
                for nid, ndata in nodes_dict.items():
                    task.nodes[nid] = NodeViewState(
                        node_id=nid,
                        goal=str(ndata.get("goal", "")),
                        capability=str(ndata.get("capability", "")),
                        title=str(ndata.get("title", "")),
                        status="READY",
                    )
            elif isinstance(nodes_dict, list):
                for item in nodes_dict:
                    nid = item.get("node_id") or item.get("nodeId")
                    if nid:
                        task.nodes[nid] = NodeViewState(
                            node_id=nid,
                            goal=str(item.get("goal", "")),
                            capability=str(item.get("capability", "")),
                            title=str(item.get("title", "")),
                            status="READY",
                        )

        elif event_type in (
            "NODE_STATE_CHANGED",
            "NODE_STATUS_CHANGED",
            "NODE_SCHEDULED",
            "NODE_STARTED",
            "NODE_COMPLETED",
            "NODE_FINISHED",
        ):
            node_id = payload.get("nodeId") or payload.get("node_id")
            default_status = "COMPLETED" if "COMPLETED" in event_type else "SCHEDULED"
            new_status = payload.get("newStatus") or payload.get("status") or default_status
            if node_id:
                nid_str = str(node_id)
                if nid_str not in task.nodes:
                    task.nodes[nid_str] = NodeViewState(
                        node_id=nid_str,
                        goal=str(payload.get("goal", "")),
                        capability=str(payload.get("capability", "")),
                        title=str(payload.get("title", "")),
                        status=str(new_status),
                        requires_approval=bool(payload.get("requiresApproval", False)),
                        approval_id=payload.get("approvalId"),
                    )
                else:
                    if new_status:
                        task.nodes[nid_str].status = str(new_status)
                    if "requiresApproval" in payload:
                        task.nodes[nid_str].requires_approval = bool(payload["requiresApproval"])
                    if "approvalId" in payload:
                        task.nodes[nid_str].approval_id = payload["approvalId"]
                    if "title" in payload:
                        task.nodes[nid_str].title = str(payload["title"])

        elif event_type in ("EXECUTION_STREAM_CHUNK", "STDOUT_CHUNK", "PROGRESS_CHUNK"):
            chunk = payload.get("chunk") or payload.get("text") or payload.get("data")
            if chunk is not None:
                task.stdout_chunks.append(str(chunk))

        elif event_type in ("NODE_VERIFIED", "VERIFICATION_COMPLETED"):
            node_id = payload.get("nodeId") or payload.get("node_id")
            passed = payload.get("passed", True)
            obs = payload.get("observation") or payload.get("result")
            if node_id:
                nid_str = str(node_id)
                if nid_str in task.nodes:
                    task.nodes[nid_str].verification_passed = bool(passed)
                    task.nodes[nid_str].status = "VERIFIED" if passed else "FAILED"
                    if obs:
                        task.nodes[nid_str].observation = str(obs)

        elif event_type in ("APPROVAL_REQUESTED", "EXEC_APPROVAL_REQUESTED"):
            app_id = payload.get("approvalId") or payload.get("approval_id")
            if app_id:
                task.pending_approvals[str(app_id)] = dict(payload)

        elif event_type in ("APPROVAL_RESOLVED", "EXEC_APPROVAL_RESOLVED"):
            app_id = payload.get("approvalId") or payload.get("approval_id")
            if app_id:
                task.pending_approvals.pop(str(app_id), None)

        elif event_type in ("CANCELLATION_ACCEPTED", "CANCEL_REQUESTED"):
            task.cancellation_requested = True
            task.cancellation_reason = payload.get("reason")

        elif event_type in ("TASK_COMPLETED", "TASK_FINISHED"):
            task.stage = "COMPLETED"
            task.status = "COMPLETED"

        elif event_type in ("TASK_FAILED", "TASK_TERMINATED"):
            task.stage = "FAILED"
            task.status = "FAILED"


__all__ = ["ClientEventReducer"]
