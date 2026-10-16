"""Workboard contract types and data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

WORKBOARD_STATUSES = (
    "triage",
    "backlog",
    "todo",
    "scheduled",
    "ready",
    "running",
    "review",
    "blocked",
    "done",
)

WORKBOARD_PRIORITIES = ("low", "normal", "high", "urgent")

WorkboardStatus = Literal[
    "triage",
    "backlog",
    "todo",
    "scheduled",
    "ready",
    "running",
    "review",
    "blocked",
    "done",
]

WorkboardPriority = Literal["low", "normal", "high", "urgent"]


@dataclass(frozen=True, slots=True)
class WorkboardClaim:
    """Represents a worker claim on a card."""

    owner_id: str
    token: str
    claimed_at: int
    last_heartbeat_at: int
    expires_at: int | None = None


@dataclass(frozen=True, slots=True)
class WorkboardComment:
    """A comment attached to a card."""

    id: str
    body: str
    created_at: int
    updated_at: int | None = None


@dataclass(frozen=True, slots=True)
class WorkboardProof:
    """Proof of completion/verification for a card."""

    id: str
    status: Literal["passed", "failed", "skipped", "unknown"]
    created_at: int
    label: str | None = None
    command: str | None = None
    url: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class WorkboardAttachment:
    """Attachment metadata for a card."""

    id: str
    card_id: str
    file_name: str
    byte_size: int
    created_at: int
    mime_type: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class WorkboardEvent:
    """Audit lifecycle event on a card."""

    id: str
    kind: str
    at: int
    from_status: str | None = None
    to_status: str | None = None
    session_key: str | None = None
    run_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkboardCard:
    """Workboard task card."""

    id: str
    title: str
    status: WorkboardStatus = "todo"
    priority: WorkboardPriority = "normal"
    board_id: str = "default"
    notes: str | None = None
    labels: list[str] = field(default_factory=list)
    agent_id: str | None = None
    session_key: str | None = None
    run_id: str | None = None
    position: int = 0
    created_at: int = 0
    updated_at: int = 0
    started_at: int | None = None
    completed_at: int | None = None
    claim: WorkboardClaim | None = None
    comments: list[WorkboardComment] = field(default_factory=list)
    proof: list[WorkboardProof] = field(default_factory=list)
    attachments: list[WorkboardAttachment] = field(default_factory=list)
    events: list[WorkboardEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkboardBoardMetadata:
    """Workboard board metadata."""

    id: str
    name: str = "Default Board"
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    created_at: int = 0
    updated_at: int = 0
    archived_at: int | None = None
