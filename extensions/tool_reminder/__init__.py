"""tool_reminder — JARVIS reminder tool (Phase 1B).

Sets timed reminders using Windows Task Scheduler (Windows-only on day
one; macOS/Linux land in Phase 9 alongside cron integration).

Mirrors OpenClaw's plugin structure: 8-10 focused files per extension
(``api.ts`` + ``runtime-api.ts`` + ``cli.ts`` + ``doctor-contract-api.ts``
+ ``index.ts`` + ``openclaw.plugin.json``). For Python/JARVIS we mirror
this with: ``__init__.py`` (entry) + ``plugin.py`` (impl) +
``runtime.py`` (helpers) + ``doctor.py`` (migration contract) +
``api.py`` (public API) + ``openclaw.plugin.json`` (manifest).
"""
from __future__ import annotations

from jarvis_sdk import (
    PluginApi,
    define_plugin_entry,
)

from .plugin import ReminderPlugin


def _register(api: PluginApi) -> None:
    """Register the reminder tool with the host's PluginApi."""
    api.register_tool(
        ReminderPlugin(),
        names=["reminder"],
    )

    # Register a slash command for ad-hoc reminder management
    # (mirrors OpenClaw's `registerCommand` pattern in memory-core).
    api.register_command(
        {
            "name": "reminders",
            "description": "List, cancel, or pause scheduled reminders.",
            "accepts_args": True,
            "expose_sender_is_owner": True,
        }
    )

    # Register the doctor contract so the user's existing scheduled tasks
    # (if migrating from MARK XXXIX-OR) can be reindexed.
    api.register_doctor_contract(
        {
            "id": "tool_reminder.legacy_xxxix_oras",
            "version": 1,
            "detect_label": "Legacy MARK XXXIX-OR reminders",
            "detect_path": "core/reminders.json",
        }
    )


# ── Plugin entry (mirrors OpenClaw's `definePluginEntry`) ───────────
entry = define_plugin_entry(
    id="tool_reminder",
    kind="tool",
    name="Reminder",
    description="Set timed reminders via Windows Task Scheduler (Phase 1B: Windows-only).",
    register=_register,
    version="0.1.0",
    activation="on_startup",
    permissions=["os:scheduler", "fs:write:temp"],
)
