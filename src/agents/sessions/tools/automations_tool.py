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


def _normalize_schedule(schedule_input: str, recurring: bool = False) -> str:
    """Normalize schedule string with full support for wall-clock times, durations, ISO timestamps, and cron expressions.

    Supports:
    - Wall-clock time (24h or 12h): "17:10", "17:10:00", "5:10 PM", "5:10pm", "5pm", "05:10"
    - "tomorrow at 5:10 PM" / "tomorrow 17:10"
    - Relative duration with suffix: "30s", "10m", "15 min", "2h", "1d", "in 5 minutes"
    - Pure integer seconds: "60", "300"
    - ISO timestamp or space-separated date+time: "2026-10-26T17:10:00", "2026-10-26 17:10"
    - 5-field cron expression: "*/5 * * * *", "10 17 * * *"
    """
    raw = schedule_input.strip()
    if not raw:
        raise ValueError("schedule cannot be empty.")

    now = datetime.now()

    # 1. Pure numeric seconds: "60", "300"
    if raw.isdigit():
        secs = int(raw)
        target = (now + timedelta(seconds=secs)).replace(microsecond=0)
        return target.isoformat()

    # 2. Suffix or relative duration: e.g. "in 5 minutes", "30s", "15m", "2h", "1d"
    clean_dur = re.sub(r"^in\s+", "", raw, flags=re.IGNORECASE).strip()
    dur_match = re.match(
        r"^(\d+)\s*(s|sec|seconds?|m|min|minutes?|h|hr|hours?|d|days?)$", clean_dur, re.IGNORECASE
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

        target = (now + delta).replace(microsecond=0)
        return target.isoformat()

    # 3. ISO timestamp or space-separated date+time: e.g. "2026-10-26T17:10:00", "2026-10-26 17:10"
    iso_date_match = re.match(r"^(\d{4}-\d{2}-\d{2})[T\s](\d{1,2}):(\d{2})(?::(\d{2}))?$", raw)
    if iso_date_match:
        d_str, h_str, m_str, s_str = iso_date_match.groups()
        s_val = int(s_str) if s_str else 0
        return f"{d_str}T{int(h_str):02d}:{int(m_str):02d}:{s_val:02d}"

    # 4. Standard 5-field cron expression: "*/5 * * * *"
    parts = raw.split()
    if len(parts) == 5:
        return raw

    # 5. Wall-clock time (12-hour AM/PM or 24-hour): e.g. "17:10", "5:10 PM", "5:10pm", "5pm"
    is_tomorrow = bool(re.search(r"\btomorrow\b", raw, re.IGNORECASE))
    clean_time = re.sub(r"\b(at|tomorrow)\b", "", raw, flags=re.IGNORECASE).strip()

    # 12-hour with AM/PM: e.g. "5:10 PM", "5:10pm", "5pm", "5:10:00 PM"
    ampm_match = re.match(
        r"^(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*(am|pm)$", clean_time, re.IGNORECASE
    )
    if ampm_match:
        h_val = int(ampm_match.group(1))
        m_val = int(ampm_match.group(2)) if ampm_match.group(2) else 0
        s_val = int(ampm_match.group(3)) if ampm_match.group(3) else 0
        is_pm = ampm_match.group(4).lower() == "pm"
        if is_pm and h_val < 12:
            h_val += 12
        elif not is_pm and h_val == 12:
            h_val = 0

        if recurring:
            return f"{m_val} {h_val} * * *"

        target = now.replace(hour=h_val, minute=m_val, second=s_val, microsecond=0)
        if is_tomorrow or target <= now:
            target += timedelta(days=1)
        return target.isoformat()

    # 24-hour: e.g. "17:10", "17:10:00", "05:10"
    h24_match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", clean_time)
    if h24_match:
        h_val = int(h24_match.group(1))
        m_val = int(h24_match.group(2))
        s_val = int(h24_match.group(3)) if h24_match.group(3) else 0

        if 0 <= h_val <= 23 and 0 <= m_val <= 59:
            if recurring:
                return f"{m_val} {h_val} * * *"

            target = now.replace(hour=h_val, minute=m_val, second=s_val, microsecond=0)
            if is_tomorrow or target <= now:
                target += timedelta(days=1)
            return target.isoformat()

    # If format is unrecognized, raise helpful guidance
    raise ValueError(
        f"Unrecognized schedule format '{raw}'. "
        "Use a time (e.g. '17:10' or '5:10 PM'), duration (e.g. '300' or '5m'), "
        "ISO timestamp ('2026-10-01T09:00:00'), or 5-field cron ('*/5 * * * *')."
    )


def _make_automation_handler(job_id: str, payload: str) -> Any:
    """Create a persistent async execution handler for an automation job."""

    async def _handler() -> None:
        _log.info("[AUTOMATION] Fired job '%s' with payload: %s", job_id, payload)
        clean_p = payload.strip() if payload else ""

        # 1. Record execution event into persistent SQLite transcript store
        try:
            from src.agents.task.session_transcript_store import SessionTranscriptStore

            store = SessionTranscriptStore()
            store.add_turn(
                "system",
                f"[AUTOMATION TRIGGERED] Job '{job_id}' executed. Payload: {clean_p or '(no instruction)'}",
            )
        except Exception as store_err:
            _log.debug("Notice: Could not record automation to transcript store: %s", store_err)

        # 2. Push real-time spoken announcement to active Gemini Live voice engine if connected
        try:
            try:
                from jarvis_voice_pipeline.terminal_app import NativeGeminiLiveEngine

                engine = NativeGeminiLiveEngine.get_active_engine()
            except ImportError:
                from packages.voice_pipeline.src.jarvis_voice_pipeline.terminal_app import (
                    NativeGeminiLiveEngine,
                )

                engine = NativeGeminiLiveEngine.get_active_engine()

            if engine is None:
                import builtins

                engine = getattr(builtins, "_JARVIS_ACTIVE_VOICE_ENGINE", None)

            if engine is not None and not getattr(engine, "stop_event", None) and hasattr(engine, "post_system_notification"):
                notification = (
                    f"[SCHEDULED REMINDER / AUTOMATION] Job '{job_id}' has triggered! Instruction: {clean_p}. "
                    f"Briefly inform Sir in 1 warm, natural sentence in Nepali that this scheduled reminder or automation has triggered."
                )
                engine.post_system_notification(notification)
            elif engine is not None and getattr(engine, "stop_event", None) is not None and not engine.stop_event.is_set():
                notification = (
                    f"[SCHEDULED REMINDER / AUTOMATION] Job '{job_id}' has triggered! Instruction: {clean_p}. "
                    f"Briefly inform Sir in 1 warm, natural sentence in Nepali that this scheduled reminder or automation has triggered."
                )
                engine.post_system_notification(notification)
        except Exception as notify_err:
            _log.debug("Notice: Could not post notification to active engine: %s", notify_err)

        # 3. If payload contains an executable action or task, spawn a subagent to execute it in background
        p_lower = clean_p.lower()
        if clean_p and (
            p_lower.startswith(("exec:", "run:", "command:", "task:", "subagent:", "do:"))
            or any(p_lower.startswith(pref) for pref in ("dir", "python ", "git ", "ls ", "uv "))
        ):
            try:
                from src.agents.sessions.tools.subagent_tools import get_default_spawner
                from src.agents.subagents import (
                    SpawnSubagentParams,
                    SubagentSpawnContextMode,
                )

                spawner = get_default_spawner()
                params = SpawnSubagentParams(
                    task=clean_p,
                    label=f"cron_{job_id}",
                    context=SubagentSpawnContextMode.ISOLATED,
                )
                await spawner.spawn(params)
            except Exception as spawner_err:
                _log.warning("Automation subagent dispatch error: %s", spawner_err)

        # 4. Canonical desktop event emit
        try:
            from apps.desktop.src.jarvis_desktop.app import _emit_canonical_event

            _emit_canonical_event(
                event_type="automation_job_fired",
                tool_name="automations",
                args={"job_id": job_id, "payload": clean_p},
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

        raw_action = str(params.get("action", "")).strip().lower()
        if not raw_action:
            raise ValueError(
                "action is required (must be one of: list, create, add, delete, remove, status, get, run)."
            )

        # Normalize action aliases
        if raw_action in ("create", "add", "new", "schedule", "set"):
            action = "create"
        elif raw_action in ("delete", "remove", "cancel", "rm", "del", "clear"):
            action = "delete"
        elif raw_action in ("list", "ls", "all", "show"):
            action = "list"
        elif raw_action in ("status", "get", "info", "check", "inspect"):
            action = "status"
        elif raw_action in ("run", "trigger", "fire", "execute"):
            action = "run"
        else:
            action = raw_action

        # Flexible parameter aliases
        job_id = str(
            params.get("job_id")
            or params.get("job")
            or params.get("jobId")
            or params.get("id")
            or params.get("name")
            or ""
        ).strip()

        schedule_str = str(
            params.get("schedule")
            or params.get("when")
            or params.get("time")
            or params.get("cron")
            or ""
        ).strip()

        payload_str = str(
            params.get("payload")
            or params.get("prompt")
            or params.get("message")
            or params.get("instruction")
            or params.get("task")
            or params.get("text")
            or params.get("command")
            or ""
        ).strip()

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
            if not schedule_str:
                raise ValueError("schedule is required for 'create' action.")

            recurring_flag = bool(params.get("recurring", False))
            norm_schedule = _normalize_schedule(schedule_str, recurring=recurring_flag)
            target_job_id = job_id or f"job_{int(time.time())}_{uuid.uuid4().hex[:4]}"
            description_str = payload_str or f"Automation job {target_job_id}"

            job_decl = CronDecl(
                id=target_job_id,
                schedule=norm_schedule,
                handler=_make_automation_handler(target_job_id, payload_str),
                description=description_str,
                enabled=True,
                automation_payload={"payload": payload_str} if payload_str else None,
            )

            table.add(job_decl)
            if runner is not None:
                runner.add(job_decl)

            msg = (
                f"Successfully scheduled automation job '{target_job_id}'.\n"
                f"- Schedule: '{norm_schedule}'\n"
                f"- Payload: '{payload_str or '(None)'}'\n"
                f"- Status: Active"
            )
            return {
                "content": [{"type": "text", "text": msg}],
                "details": {
                    "action": "create",
                    "job_id": target_job_id,
                    "schedule": norm_schedule,
                    "payload": payload_str,
                    "created": True,
                    "success": True,
                },
            }

        # ── ACTION: DELETE ────────────────────────────────────────────
        elif action == "delete":
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

        # ── ACTION: RUN (TRIGGER IMMEDIATELY) ─────────────────────────
        elif action == "run":
            if not job_id:
                raise ValueError("job ID is required for 'run' action.")
            decl = table.get(job_id)
            if decl is None:
                return {
                    "content": [{"type": "text", "text": f"Automation job '{job_id}' not found."}],
                    "details": {"action": "run", "job_id": job_id, "success": False},
                }
            run_ok = False
            if runner is not None and hasattr(runner, "run_job"):
                run_ok = runner.run_job(job_id)
            else:
                try:
                    res = decl.handler()
                    import asyncio

                    if asyncio.iscoroutine(res):
                        await res
                    run_ok = True
                except Exception as run_err:
                    return {
                        "content": [
                            {"type": "text", "text": f"Error running job '{job_id}': {run_err}"}
                        ],
                        "details": {
                            "action": "run",
                            "job_id": job_id,
                            "success": False,
                            "error": str(run_err),
                        },
                    }
            return {
                "content": [
                    {"type": "text", "text": f"Successfully triggered automation job '{job_id}'."}
                ],
                "details": {"action": "run", "job_id": job_id, "success": run_ok},
            }

        # ── ACTION: STATUS ────────────────────────────────────────────
        elif action == "status":
            if job_id:
                decl = table.get(job_id)
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
                                    f"Automation Job '{job_id}':\n"
                                    f"• Schedule: {decl.schedule}\n"
                                    f"• Status: {status_str}\n"
                                    f"• Description/Prompt: {decl.description or p_text}"
                                ),
                            }
                        ],
                        "details": {
                            "action": "status",
                            "job_id": job_id,
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
                            {"type": "text", "text": f"Automation job '{job_id}' not found."}
                        ],
                        "details": {
                            "action": "status",
                            "job_id": job_id,
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
                f"Unknown action '{action}'. Supported actions are: 'list', 'create', 'add', 'delete', 'remove', 'status', 'run'."
            )

    return {
        "name": "automations",
        "description": (
            "Agent cron and task scheduling tool. "
            "Actions: "
            "1. 'list': Show all scheduled jobs. "
            "2. 'create' / 'add': Schedule a new job with job ID, schedule (cron expression or seconds), and payload. "
            "3. 'delete' / 'remove': Remove a scheduled job by job ID. "
            "4. 'status' / 'get': Check scheduler engine status or specific job. "
            "5. 'run': Trigger an immediate execution of a scheduled job."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Scheduling action: 'list', 'create', 'add', 'delete', 'remove', 'status', or 'run'.",
                    "enum": ["list", "create", "add", "delete", "remove", "status", "run"],
                },
                "job": {
                    "type": "STRING",
                    "description": "Identifier for the job. Required for 'delete' or 'run', optional for 'create'.",
                },
                "job_id": {
                    "type": "STRING",
                    "description": "Alias for job.",
                },
                "schedule": {
                    "type": "STRING",
                    "description": "Schedule time string: wall-clock time ('17:10', '5:10 PM', 'tomorrow at 5:10 PM'), relative delay ('in 10m', '300s', '5m'), ISO timestamp ('2026-10-26T17:10:00'), or 5-field cron ('*/5 * * * *'). Required for 'create'.",
                },
                "recurring": {
                    "type": "BOOLEAN",
                    "description": "Set to True if this schedule should repeat daily/periodically instead of firing once. Optional, defaults to False.",
                },
                "payload": {
                    "type": "STRING",
                    "description": "Prompt instruction or action string to execute when the schedule triggers. Optional for 'create'.",
                },
                "prompt": {
                    "type": "STRING",
                    "description": "Alias for payload.",
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
