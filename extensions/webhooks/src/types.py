"""Data types and models for the Webhooks plugin.

OpenClaw parity: mirrors @openclaw/webhooks types, route configs,
flow views, and task views.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

WebhookSecretInput = str | dict[str, Any]
SyncMode = Literal["task_mirrored", "managed"]
NotifyPolicy = Literal["done_only", "state_changes", "silent"]
FlowStatus = Literal["queued", "running", "waiting", "blocked", "finished", "failed", "cancelled"]
TaskRuntime = Literal["subagent", "acp"]


@dataclass(frozen=True, slots=True)
class WebhookRouteConfig:
    """User-configured route entry in plugin config."""

    session_key: str
    secret: WebhookSecretInput
    enabled: bool = True
    path: str | None = None
    controller_id: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class ConfiguredWebhookRoute:
    """Resolved and normalized webhook route."""

    route_id: str
    path: str
    session_key: str
    secret: WebhookSecretInput
    controller_id: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class FlowView:
    """Read-only projection of a TaskFlow."""

    flow_id: str
    sync_mode: SyncMode = "managed"
    controller_id: str | None = None
    revision: int = 0
    status: str = "queued"
    notify_policy: str = "done_only"
    goal: str = ""
    current_step: str | None = None
    blocked_task_id: str | None = None
    blocked_summary: str | None = None
    state_json: Any = None
    wait_json: Any = None
    cancel_requested_at: float | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    ended_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "flowId": self.flow_id,
            "syncMode": self.sync_mode,
            "revision": self.revision,
            "status": self.status,
            "notifyPolicy": self.notify_policy,
            "goal": self.goal,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.controller_id:
            data["controllerId"] = self.controller_id
        if self.current_step is not None:
            data["currentStep"] = self.current_step
        if self.blocked_task_id is not None:
            data["blockedTaskId"] = self.blocked_task_id
        if self.blocked_summary is not None:
            data["blockedSummary"] = self.blocked_summary
        if self.state_json is not None:
            data["stateJson"] = self.state_json
        if self.wait_json is not None:
            data["waitJson"] = self.wait_json
        if self.cancel_requested_at is not None:
            data["cancelRequestedAt"] = self.cancel_requested_at
        if self.ended_at is not None:
            data["endedAt"] = self.ended_at
        return data


@dataclass(frozen=True, slots=True)
class TaskView:
    """Read-only projection of a Task."""

    task_id: str
    runtime: str
    task: str
    status: str
    scope_kind: str = "flow"
    source_id: str | None = None
    child_session_key: str | None = None
    parent_flow_id: str | None = None
    parent_task_id: str | None = None
    agent_id: str | None = None
    run_id: str | None = None
    label: str | None = None
    delivery_status: str = "pending"
    notify_policy: str = "done_only"
    created_at: float = 0.0
    started_at: float | None = None
    ended_at: float | None = None
    last_event_at: float | None = None
    cleanup_after: float | None = None
    error: str | None = None
    progress_summary: str | None = None
    terminal_summary: str | None = None
    terminal_outcome: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "taskId": self.task_id,
            "runtime": self.runtime,
            "task": self.task,
            "status": self.status,
            "scopeKind": self.scope_kind,
            "deliveryStatus": self.delivery_status,
            "notifyPolicy": self.notify_policy,
            "createdAt": self.created_at,
        }
        if self.source_id is not None:
            data["sourceId"] = self.source_id
        if self.child_session_key is not None:
            data["childSessionKey"] = self.child_session_key
        if self.parent_flow_id is not None:
            data["parentFlowId"] = self.parent_flow_id
        if self.parent_task_id is not None:
            data["parentTaskId"] = self.parent_task_id
        if self.agent_id is not None:
            data["agentId"] = self.agent_id
        if self.run_id is not None:
            data["runId"] = self.run_id
        if self.label is not None:
            data["label"] = self.label
        if self.started_at is not None:
            data["startedAt"] = self.started_at
        if self.ended_at is not None:
            data["endedAt"] = self.ended_at
        if self.last_event_at is not None:
            data["lastEventAt"] = self.last_event_at
        if self.cleanup_after is not None:
            data["cleanupAfter"] = self.cleanup_after
        if self.error is not None:
            data["error"] = self.error
        if self.progress_summary is not None:
            data["progressSummary"] = self.progress_summary
        if self.terminal_summary is not None:
            data["terminalSummary"] = self.terminal_summary
        if self.terminal_outcome is not None:
            data["terminalOutcome"] = self.terminal_outcome
        return data


@dataclass(frozen=True, slots=True)
class TaskFlowWebhookTarget:
    """Target binding a webhook route to a TaskFlow session runtime."""

    route_id: str
    path: str
    secret_input: WebhookSecretInput
    default_controller_id: str
    task_flow: Any = None
