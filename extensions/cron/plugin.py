"""CronExtensionPlugin — LLM-callable tools for the cron table.

Exposes:
  - ``cron_schedule(id, schedule, ...)`` — register a job
  - ``cron_list()`` — list registered jobs
  - ``cron_cancel(id)`` — remove a job

The actual scheduling is done by ``src.cron.CronRunner`` (the
host). This plugin is the OpenClaw-shaped consumer that talks to
``CronTable.default()`` — a thin alias layer.
"""

from __future__ import annotations

from typing import Any

from jarvis_sdk import (
    Err,
    Ok,
    Result,
    ToolDecl,
    ToolParam,
    ToolPlugin,
)

from .runtime import CronTable

CRON_SCHEDULE_TOOL = ToolDecl(
    name="cron_schedule",
    description=(
        "Schedules a recurring or one-shot job. Returns the registered "
        "job id. Use a 5-field cron expression ('*/5 * * * *') for "
        "recurring, or an ISO timestamp ('2026-07-20T09:00:00') for "
        "a one-shot."
    ),
    parameters=[
        ToolParam(
            name="id",
            type="string",
            description="Stable id for the job.",
            required=True,
        ),
        ToolParam(
            name="schedule",
            type="string",
            description="Cron expression (5 fields) or ISO timestamp.",
            required=True,
        ),
        ToolParam(
            name="description",
            type="string",
            description="Human-readable description.",
            required=False,
        ),
        ToolParam(
            name="enabled",
            type="boolean",
            description="Whether the job is active (default: true).",
            required=False,
        ),
    ],
    returns="string",
    category="infra",
)

CRON_LIST_TOOL = ToolDecl(
    name="cron_list",
    description="Lists all registered cron jobs.",
    parameters=[],
    returns="string",
    category="infra",
)

CRON_CANCEL_TOOL = ToolDecl(
    name="cron_cancel",
    description="Removes a cron job by id.",
    parameters=[
        ToolParam(
            name="id",
            type="string",
            description="The job id to remove.",
            required=True,
        ),
    ],
    returns="string",
    category="infra",
)


class CronExtensionPlugin(ToolPlugin):
    """The LLM-facing cron API."""

    id = "cron"
    kind = "infra"
    version = "0.1.0"
    description = "Cross-platform scheduled jobs (cron + one-shots)."

    def init(self, ctx: Any) -> None:
        return

    async def shutdown(self) -> None:
        return None

    @property
    def tools(self) -> list[ToolDecl]:
        return [CRON_SCHEDULE_TOOL, CRON_LIST_TOOL, CRON_CANCEL_TOOL]

    async def call(self, name: str, args: dict[str, Any]) -> Result[str]:
        table = CronTable.default()
        if name == "cron_schedule":
            return self._schedule(args, table)
        if name == "cron_list":
            return self._list(table)
        if name == "cron_cancel":
            return self._cancel(args, table)
        return Err(f"Unknown tool: {name}", code="UNKNOWN_TOOL")

    def _schedule(self, args: dict[str, Any], table: CronTable) -> Result[str]:
        from jarvis_sdk import CronDecl

        job_id = (args.get("id") or "").strip()
        schedule = (args.get("schedule") or "").strip()
        if not job_id or not schedule:
            return Err(
                "cron_schedule needs both `id` and `schedule`.",
                code="MISSING_ARG",
            )
        desc = (args.get("description") or "").strip()
        enabled = bool(args.get("enabled", True))
        # The handler is a no-op stub here; the real work is done
        # by the CronRunner the host wires up. We only store the
        # metadata for now.
        job = CronDecl(
            id=job_id,
            schedule=schedule,
            handler=_stub_handler,
            description=desc,
            enabled=enabled,
        )
        table.add(job)
        return Ok(f"Registered cron job {job_id!r} (schedule={schedule!r}).")

    def _list(self, table: CronTable) -> Result[str]:
        rows = table.list()
        if not rows:
            return Ok("No cron jobs scheduled.")
        body = "\n".join(
            f"  - {r['id']}: schedule={r['schedule']!r} enabled={r['enabled']} ({r['description']})"
            for r in rows
        )
        return Ok(f"Cron jobs:\n{body}")

    def _cancel(self, args: dict[str, Any], table: CronTable) -> Result[str]:
        job_id = (args.get("id") or "").strip()
        if not job_id:
            return Err("cron_cancel needs an `id`.", code="MISSING_ARG")
        if table.remove(job_id):
            return Ok(f"Cancelled cron job {job_id!r}.")
        return Err(f"No cron job with id {job_id!r}.", code="NOT_FOUND")


async def _stub_handler() -> None:  # pragma: no cover
    """Placeholder handler. The real job handler comes from the
    plugin that registered the cron entry (e.g. ``tool_reminder``)."""
    return


__all__ = [
    "CRON_CANCEL_TOOL",
    "CRON_LIST_TOOL",
    "CRON_SCHEDULE_TOOL",
    "CronExtensionPlugin",
]
