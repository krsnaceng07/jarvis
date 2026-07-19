"""cron — JARVIS cross-platform scheduled jobs (Phase 2).

Mirrors OpenClaw's ``src/cron/`` system. The plugin is a thin
facade over ``jarvis.cron.CronRunner``: it exposes the cron table
as LLM-callable tools (``cron_schedule``, ``cron_list``,
``cron_cancel``) and registers a slash command for ad-hoc
management.

Why we ship a cron extension even though ``jarvis.cron.CronRunner``
exists: the extension is the OpenClaw-shaped consumer; the runner
is the host-side implementation. Separating them keeps the host
thin and lets the extension be replaced/swapped without touching
``apps/desktop``.
"""

from __future__ import annotations

from jarvis_sdk import (
    PluginApi,
    PluginCommandContext,
    PluginCommandResult,
    define_plugin_entry,
)

from .plugin import CronExtensionPlugin
from .runtime import CronTable

# ruff: noqa: PLR0911
# Each ``if sub in ...`` branch returns a distinct message — the
# 9 returns mirror the 9 distinct (sub, args) combinations we
# support. Consolidating would lose per-subcommand feedback.


def _cron_command_handler(ctx: PluginCommandContext) -> PluginCommandResult:
    """Slash command handler for ``/cron [list|cancel <id>|run <id>]``."""

    args = (ctx.args or "").strip()
    table = CronTable.default()
    sub, _, rest = args.partition(" ")

    if sub in ("", "list"):
        rows = table.list()
        if not rows:
            return PluginCommandResult(reply_text="No cron jobs scheduled.")
        body = "\n".join(
            f"  - {r['id']}: schedule={r['schedule']!r} enabled={r['enabled']} ({r['description']})"
            for r in rows
        )
        return PluginCommandResult(reply_text=f"Cron jobs:\n{body}")

    if sub == "cancel":
        target = rest.strip()
        if not target:
            return PluginCommandResult(reply_text="Usage: /cron cancel <id>")
        if table.remove(target):
            return PluginCommandResult(reply_text=f"Cancelled cron job {target!r}.")
        return PluginCommandResult(reply_text=f"No cron job with id {target!r}.")

    if sub == "run":
        target = rest.strip()
        if not target:
            return PluginCommandResult(reply_text="Usage: /cron run <id>")
        if table.fire_now(target):
            return PluginCommandResult(reply_text=f"Fired cron job {target!r}.")
        return PluginCommandResult(reply_text=f"No cron job with id {target!r}.")

    return PluginCommandResult(
        reply_text=f"Unknown subcommand {sub!r}. Try: list, cancel <id>, run <id>."
    )


def _register(api: PluginApi) -> None:
    """Register the cron plugin's surface with the host's PluginApi."""
    # Tools (cron_schedule, cron_list, cron_cancel)
    api.register_tool(
        CronExtensionPlugin(),
        names=["cron_schedule", "cron_list", "cron_cancel"],
    )

    # Slash command
    api.register_command(
        {
            "name": "cron",
            "description": "List, cancel, or fire scheduled cron jobs.",
            "accepts_args": True,
            "expose_sender_is_owner": True,
            "handler": _cron_command_handler,
        }
    )


entry = define_plugin_entry(
    id="cron",
    kind="infra",
    name="Cron",
    description="Cross-platform scheduled jobs (cron + one-shots).",
    register=_register,
    version="0.1.0",
    activation="on_startup",
    permissions=["os:scheduler"],
)
