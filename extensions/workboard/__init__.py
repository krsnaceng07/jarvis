"""Workboard extension root entrypoint."""

from __future__ import annotations

from .src.cli import handle_workboard_cli, repair_workboard_config
from .src.plugin import WorkboardPlugin, entry, workboard_plugin
from .src.store import WorkboardStore
from .src.tools import register_workboard_tools
from .src.types import (
    WORKBOARD_PRIORITIES,
    WORKBOARD_STATUSES,
    WorkboardAttachment,
    WorkboardBoardMetadata,
    WorkboardCard,
    WorkboardClaim,
    WorkboardComment,
    WorkboardEvent,
    WorkboardPriority,
    WorkboardProof,
    WorkboardStatus,
)

__all__ = [
    "WORKBOARD_PRIORITIES",
    "WORKBOARD_STATUSES",
    "WorkboardAttachment",
    "WorkboardBoardMetadata",
    "WorkboardCard",
    "WorkboardClaim",
    "WorkboardComment",
    "WorkboardEvent",
    "WorkboardPlugin",
    "WorkboardPriority",
    "WorkboardProof",
    "WorkboardStatus",
    "WorkboardStore",
    "entry",
    "handle_workboard_cli",
    "register_workboard_tools",
    "repair_workboard_config",
    "workboard_plugin",
]
