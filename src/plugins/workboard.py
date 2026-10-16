"""jarvis.plugins.workboard — Workboard Kanban board plugin constants & contracts.

OpenClaw parity: mirrors
``openclaw-main/extensions/workboard/src/store-constants.ts`` and
``openclaw-main/extensions/workboard/src/tools.ts``.

Features:
- `WORKBOARD_CARD_STATUSES`: `triage`, `backlog`, `todo`, `scheduled`, `ready`, `running`, `review`, `blocked`, `done`.
- `WORKBOARD_CARD_PRIORITIES`: `low`, `normal`, `high`, `urgent`.
- Workboard limits: `POSITION_STEP`, `MAX_CARDS`, `MAX_CARD_EVENTS`, `MAX_CARD_ATTACHMENTS`, `MAX_ATTACHMENT_BYTES`, `DEFAULT_CLAIM_TTL_MS`.
- `WORKBOARD_AGENT_TOOLS`: List of 21 registered workboard agent tools.
- `WorkboardCard`: Core card dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

WorkboardCardStatus = Literal[
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

WorkboardCardPriority = Literal["low", "normal", "high", "urgent"]

WORKBOARD_CARD_STATUSES: list[WorkboardCardStatus] = [
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

WORKBOARD_CARD_PRIORITIES: list[WorkboardCardPriority] = [
    "low",
    "normal",
    "high",
    "urgent",
]

POSITION_STEP: int = 1000
MAX_CARDS: int = 2000
MAX_CARD_EVENTS: int = 50
MAX_CARD_ATTEMPTS: int = 30
MAX_CARD_COMMENTS: int = 50
MAX_CARD_LINKS: int = 50
MAX_CARD_PROOF: int = 40
MAX_CARD_ARTIFACTS: int = 40
MAX_CARD_ATTACHMENTS: int = 20
MAX_ATTACHMENT_BYTES: int = 256 * 1024  # 256 KiB
MAX_CARD_METADATA_BYTES: int = 24 * 1024  # 24 KiB
DEFAULT_CLAIM_TTL_MS: int = 30 * 60 * 1000  # 30 mins

WORKBOARD_AGENT_TOOLS: list[str] = [
    "workboard_list",
    "workboard_read",
    "workboard_create",
    "workboard_link",
    "workboard_claim",
    "workboard_heartbeat",
    "workboard_release",
    "workboard_complete",
    "workboard_block",
    "workboard_attachment_add",
    "workboard_attachment_read",
    "workboard_attachment_delete",
    "workboard_worker_log",
    "workboard_protocol_violation",
    "workboard_board_create",
    "workboard_board_archive",
    "workboard_board_delete",
    "workboard_runs",
    "workboard_specify",
    "workboard_decompose",
    "workboard_notify_subscribe",
    "workboard_notify_list",
    "workboard_notify_events",
    "workboard_notify_advance",
    "workboard_notify_unsubscribe",
    "workboard_boards",
    "workboard_stats",
    "workboard_promote",
    "workboard_reassign",
    "workboard_reclaim",
    "workboard_comment",
    "workboard_proof",
    "workboard_unblock",
    "workboard_move",
    "workboard_dispatch",
]


@dataclass
class WorkboardCard:
    id: str
    title: str
    board_id: str = "default"
    status: WorkboardCardStatus = "todo"
    priority: WorkboardCardPriority = "normal"
    labels: list[str] = field(default_factory=list)
    agent_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    session_key: str | None = None


__all__ = [
    "DEFAULT_CLAIM_TTL_MS",
    "MAX_ATTACHMENT_BYTES",
    "MAX_CARDS",
    "MAX_CARD_ARTIFACTS",
    "MAX_CARD_ATTACHMENTS",
    "MAX_CARD_ATTEMPTS",
    "MAX_CARD_COMMENTS",
    "MAX_CARD_EVENTS",
    "MAX_CARD_LINKS",
    "MAX_CARD_METADATA_BYTES",
    "MAX_CARD_PROOF",
    "POSITION_STEP",
    "WORKBOARD_AGENT_TOOLS",
    "WORKBOARD_CARD_PRIORITIES",
    "WORKBOARD_CARD_STATUSES",
    "WorkboardCard",
    "WorkboardCardPriority",
    "WorkboardCardStatus",
]
