"""tool_reminder — JARVIS reminder tool (Phase 1B/1C).

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
    PluginCommandContext,
    PluginCommandResult,
    define_plugin_entry,
)

from .plugin import ReminderPlugin


async def _reminders_command_handler(ctx: PluginCommandContext) -> PluginCommandResult:
    """Slash command handler for ``/reminders [list|cancel-all]``.

    Mirrors OpenClaw's required-``handler`` contract on
    ``OpenClawPluginCommandDefinition``. Phase 1C keeps this simple —
    lists the user's currently-scheduled Windows tasks under
    ``JARVISReminder_*``. A real cancel-all / per-id cancel lands in
    Phase 2 once the reminder runtime exposes a public API.
    """
    sub = (ctx.args or "").strip().lower()
    if sub in ("list", ""):
        from .runtime import list_scheduled_reminders

        rows = list_scheduled_reminders()
        if not rows:
            return PluginCommandResult(
                reply_text="No scheduled reminders.",
            )
        body = "\n".join(f"  - {row}" for row in rows)
        return PluginCommandResult(reply_text=f"Scheduled reminders:\n{body}")
    if sub == "cancel-all":
        from .runtime import cancel_all_reminders

        n = cancel_all_reminders()
        return PluginCommandResult(reply_text=f"Cancelled {n} reminder(s).")
    return PluginCommandResult(
        reply_text=f"Unknown subcommand {sub!r}. Try: list, cancel-all.",
    )


def _register(api: PluginApi) -> None:
    """Register the reminder tool with the host's PluginApi."""
    api.register_tool(
        ReminderPlugin(),
        names=["reminder"],
    )

    # Slash command with a real handler (Phase 1C: required).
    api.register_command(
        {
            "name": "reminders",
            "description": "List, cancel, or pause scheduled reminders.",
            "accepts_args": True,
            "expose_sender_is_owner": True,
            "handler": _reminders_command_handler,
        }
    )

    # Doctor / migration contract for legacy data. The runner
    # (jarvis/doctor.py) calls detect(state_dir, config) to find
    # legacy data; we ship a real closure here so the contract is
    # actually runnable.
    from .doctor import detect_reminder_legacy

    api.register_doctor_contract(
        {
            "id": "tool_reminder.legacy_xxxix_oras",
            "version": 1,
            "detect_label": "Legacy MARK XXXIX-OR reminders",
            "detect_path": "core/reminders.json",
            "detect": detect_reminder_legacy,
        }
    )


# ── Plugin entry (mirrors OpenClaw's `definePluginEntry`) ───────────
entry = define_plugin_entry(
    id="tool_reminder",
    kind="tool",
    name="Reminder",
    description="Set timed reminders via Windows Task Scheduler (Phase 1B/1C: Windows-only).",
    register=_register,
    version="0.1.0",
    activation="on_startup",
    permissions=["os:scheduler", "fs:write:temp"],
)
