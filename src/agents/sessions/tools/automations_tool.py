"""jarvis.agents.sessions.tools.automations_tool — Agent cron and scheduling tool.

OpenClaw parity: exposes the cron/scheduler subsystem to the agent loop.
Integrates with `src.cron.CronRunner` and `extensions.cron.runtime.CronTable`.
Actions:
  - list: list all scheduled jobs
  - create: schedule a new job (cron expression or seconds)
  - delete: remove a scheduled job by job ID
  - status: inspect scheduler engine status
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re
import threading
import time
from typing import Any, Optional
import uuid

from jarvis_sdk import CronDecl

from ..extensions.types import AgentToolResult, ToolDefinition

_log = logging.getLogger("jarvis.tools.automations")

_RUNNER_LOCK = threading.Lock()
_SHARED_RUNNER: Any = None


@dataclass(frozen=True, slots=True)
class AutomationJobSummary:
    """Snapshot value object representing a scheduled automation job."""

    job_id: str
    schedule: str
    description: str
    enabled: bool = True
    payload: str = ""


def _get_shared_runner() -> Any:
    """Acquire or lazily initialize the shared CronRunner singleton."""
    global _SHARED_RUNNER
    with _RUNNER_LOCK:
        if _SHARED_RUNNER is None:
            try:
                from src.cron import CronRunner

                runner = CronRunner()
                # Hydrate runner from persistent CronTable
                try:
                    from extensions.cron.runtime import CronTable

                    table = CronTable.default()
                    for item in table.list():
                        decl = table.get(item["id"])
                        if decl:
                            runner.add(decl)
                except Exception as hyd_err:
                    _log.debug("Notice: Could not preload jobs from CronTable: %s", hyd_err)

                runner.start(tick_seconds=15.0)
                _SHARED_RUNNER = runner
            except Exception as init_err:
                _log.warning("Could not initialize CronRunner: %s", init_err)
                return None
        return _SHARED_RUNNER


def _normalize_schedule(schedule_input: str) -> str:
    """Normalize schedule string.

    Supports:
    - Pure integer seconds: "60", "300"
    - Relative duration with suffix: "30s", "10m", "2h", "1d"
    - ISO timestamp: "2026-10-01T12:00:00"
    - 5-field cron expression: "*/5 * * * *"
    """
    raw = schedule_input.strip()
    if not raw:
        raise ValueError("schedule cannot be empty.")

    # 1. Pure numeric seconds
    if raw.isdigit():
        secs = int(raw)
        target = (datetime.now() + timedelta(seconds=secs)).replace(microsecond=0)
        return target.isoformat()

    # 2. Suffix duration: e.g. "30s", "15m", "2h", "1d"
    dur_match = re.match(
        r"^(\d+)\s*(s|sec|seconds|m|min|minutes|h|hr|hours|d|days)$", raw, re.IGNORECASE
    )
    if dur_match:
        val = int(dur_match.group(1))
        unit = dur_match.group(2).lower()
        if unit.startswith("s"):
            delta = timedelta(seconds=val)
        elif unit.startswith("m"):
            delta = timedelta(minutes=val)
        elif unit.startswith("h"):
            delta = timedelta(hours=val)
        elif unit.startswith("d"):
            delta = timedelta(days=val)
        else:
            delta = timedelta(seconds=val)

        target = (datetime.now() + delta).replace(microsecond=0)
        return target.isoformat()

    # 3. ISO timestamp
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", raw):
        return raw

    # 4. Cron expression (5 fields)
    parts = raw.split()
    if len(parts) == 5:
        return raw

    # If format is unrecognized, raise helpful guidance
    raise ValueError(
        f"Unrecognized schedule format '{raw}'. "
        "Use a 5-field cron expression (e.g. '*/5 * * * *'), an ISO timestamp ('2026-10-01T09:00:00'), "
        "or a duration in seconds (e.g. '300' or '5m')."
    )


def _make_automation_handler(job_id: str, payload: str) -> Any:
    """Create a persistent async execution handler for an automation job."""

    async def _handler() -> None:
        _log.info("[AUTOMATION] Fired job '%s' with payload: %s", job_id, payload)
        # Record execution event into transcript or notification queue if available
        try:
            from apps.desktop.src.jarvis_desktop.app import _emit_canonical_event

            _emit_canonical_event(
                event_type="automation_job_fired",
                tool_name="automations",
                args={"job_id": job_id, "payload": payload},
            )
        except Exception:
            pass

    return _handler


def create_automations_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the ToolDefinition for the automations tool."""
    _ = (cwd, options)

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        _ = (tool_call_id, on_update, ctx)
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")

        action = str(params.get("action", "")).strip().lower()
        if not action:
            raise ValueError("action is required (must be one of: list, create, delete, status).")

        from extensions.cron.runtime import CronTable

        table = CronTable.default()
        runner = _get_shared_runner()

        # ── ACTION: LIST ──────────────────────────────────────────────
        if action == "list":
            rows = table.list()
            jobs_summary: list[AutomationJobSummary] = []
            for r in rows:
                decl = table.get(r["id"])
                p_text = ""
                if decl and decl.automation_payload:
                    p_text = str(decl.automation_payload.get("payload", ""))
                jobs_summary.append(
                    AutomationJobSummary(
                        job_id=r["id"],
                        schedule=r["schedule"],
                        description=r.get("description", ""),
                        enabled=bool(r.get("enabled", True)),
                        payload=p_text,
                    )
                )

            if not jobs_summary:
                return {
                    "content": [{"type": "text", "text": "No scheduled automation jobs found."}],
                    "details": {"action": "list", "jobs": [], "count": 0},
                }

            formatted_lines = [f"Scheduled automation jobs ({len(jobs_summary)}):"]
            for job in jobs_summary:
                desc_str = f" — {job.description}" if job.description else ""
                status_str = "enabled" if job.enabled else "disabled"
                formatted_lines.append(
                    f"• ID: '{job.job_id}' | Schedule: '{job.schedule}' ({status_str}){desc_str}"
                )

            return {
                "content": [{"type": "text", "text": "\n".join(formatted_lines)}],
                "details": {
                    "action": "list",
                    "count": len(jobs_summary),
                    "jobs": [
                        {
                            "id": j.job_id,
                            "schedule": j.schedule,
                            "description": j.description,
                            "enabled": j.enabled,
                            "payload": j.payload,
                        }
                        for j in jobs_summary
                    ],
                },
            }

        # ── ACTION: CREATE ────────────────────────────────────────────
        elif action == "create":
            raw_sched = str(params.get("schedule", "")).strip()
            if not raw_sched:
                raise ValueError("schedule is required for 'create' action.")

            norm_schedule = _normalize_schedule(raw_sched)

            raw_job = str(params.get("job_id") or params.get("job", "")).strip()
            job_id = raw_job or f"job_{int(time.time())}_{uuid.uuid4().hex[:4]}"

            payload_str = str(params.get("prompt") or params.get("payload", "")).strip()
            description_str = payload_str or f"Automation job {job_id}"

            job_decl = CronDecl(
                id=job_id,
                schedule=norm_schedule,
                handler=_make_automation_handler(job_id, payload_str),
                description=description_str,
                enabled=True,
                automation_payload={"payload": payload_str} if payload_str else None,
            )

            table.add(job_decl)
            if runner is not None:
                runner.add(job_decl)

            msg = (
                f"Successfully scheduled automation job '{job_id}'.\n"
                f"- Schedule: '{norm_schedule}'\n"
                f"- Payload: '{payload_str or '(None)'}'\n"
                f"- Status: Active"
            )
            return {
                "content": [{"type": "text", "text": msg}],
                "details": {
                    "action": "create",
                    "job_id": job_id,
                    "schedule": norm_schedule,
                    "payload": payload_str,
                    "created": True,
                    "success": True,
                },
            }

        # ── ACTION: DELETE ────────────────────────────────────────────
        elif action == "delete":
            job_id = str(params.get("job_id") or params.get("job", "")).strip()
            if not job_id:
                raise ValueError("job ID is required for 'delete' action.")

            removed_from_table = table.remove(job_id)
            if runner is not None:
                runner.remove(job_id)

            if removed_from_table:
                return {
                    "content": [
                        {"type": "text", "text": f"Successfully deleted automation job '{job_id}'."}
                    ],
                    "details": {
                        "action": "delete",
                        "job_id": job_id,
                        "deleted": True,
                        "success": True,
                    },
                }
            else:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"No scheduled automation job found with ID '{job_id}'.",
                        }
                    ],
                    "details": {
                        "action": "delete",
                        "job_id": job_id,
                        "deleted": False,
                        "success": False,
                    },
                }

        # ── ACTION: STATUS ────────────────────────────────────────────
        elif action == "status":
            target_job_id = str(params.get("job_id") or params.get("job", "")).strip()
            if target_job_id:
                decl = table.get(target_job_id)
                if decl is not None:
                    p_text = ""
                    if decl.automation_payload:
                        p_text = str(decl.automation_payload.get("payload", ""))
                    status_str = "enabled" if decl.enabled else "disabled"
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Automation Job '{target_job_id}':\n"
                                    f"• Schedule: {decl.schedule}\n"
                                    f"• Status: {status_str}\n"
                                    f"• Description/Prompt: {decl.description or p_text}"
                                ),
                            }
                        ],
                        "details": {
                            "action": "status",
                            "job_id": target_job_id,
                            "job": {
                                "id": decl.id,
                                "schedule": decl.schedule,
                                "description": decl.description,
                                "enabled": decl.enabled,
                                "payload": p_text,
                            },
                            "success": True,
                        },
                    }
                else:
                    return {
                        "content": [
                            {"type": "text", "text": f"Automation job '{target_job_id}' not found."}
                        ],
                        "details": {
                            "action": "status",
                            "job_id": target_job_id,
                            "job": None,
                            "success": False,
                        },
                    }

            is_running = runner is not None and getattr(runner, "_thread", None) is not None
            total_jobs = len(table.list())
            now_iso = datetime.now().replace(microsecond=0).isoformat()

            status_lines = [
                "Scheduler Status:",
                f"• Engine Running: {is_running}",
                f"• Total Scheduled Jobs: {total_jobs}",
                f"• Host Local Time: {now_iso}",
                "• Polling Interval: 15s",
            ]

            return {
                "content": [{"type": "text", "text": "\n".join(status_lines)}],
                "details": {
                    "action": "status",
                    "running": is_running,
                    "total_jobs": total_jobs,
                    "current_time": now_iso,
                    "success": True,
                },
            }

        else:
            raise ValueError(
                f"Unknown action '{action}'. Supported actions are: 'list', 'create', 'delete', 'status'."
            )

    return {
        "name": "automations",
        "description": (
            "Agent cron and task scheduling tool. "
            "Actions: "
            "1. 'list': Show all scheduled jobs. "
            "2. 'create': Schedule a new job with job ID, schedule (cron expression or seconds), and payload. "
            "3. 'delete': Remove a scheduled job by job ID. "
            "4. 'status': Check scheduler engine status."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Scheduling action: 'list', 'create', 'delete', or 'status'.",
                    "enum": ["list", "create", "delete", "status"],
                },
                "job": {
                    "type": "STRING",
                    "description": "Identifier for the job. Required for 'delete', optional for 'create'.",
                },
                "schedule": {
                    "type": "STRING",
                    "description": "Cron expression ('*/5 * * * *'), ISO timestamp, or relative delay in seconds (e.g. '300' for 5 minutes). Required for 'create'.",
                },
                "payload": {
                    "type": "STRING",
                    "description": "Prompt instruction or action string to execute when the schedule triggers. Optional for 'create'.",
                },
            },
            "required": ["action"],
        },
        "execute": _execute,
    }


def create_automations_tool(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Convenience alias matching create_write_tool / create_open_path_tool naming."""
    return create_automations_tool_definition(cwd=cwd, options=options)


__all__ = [
    "AutomationJobSummary",
    "create_automations_tool",
    "create_automations_tool_definition",
]
