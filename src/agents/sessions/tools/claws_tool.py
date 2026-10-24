"""JARVIS Autonomous Claws Agent Tool.

Exposes Autonomous Claws (background worker agents) to conversational LLM turns:
- list: view registered claws, their schedules, and capabilities
- status: inspect background worker daemons, concurrency, and task queue metrics
- dispatch: trigger an autonomous Claw job with optional payload and priority
- jobs: query pending, running, or completed Claw jobs
- checkpoint: inspect persistent progress checkpoints saved by Claws
- cancel: cancel a pending or executing Claw job
"""

from __future__ import annotations

import logging
from typing import Any

from .tool_definition_wrapper import AgentTool

logger = logging.getLogger("jarvis.tools.claws")


def create_claws_tool_definition() -> dict[str, Any]:
    """Return JSON schema definition for the claws tool."""
    return {
        "name": "claws",
        "description": (
            "Inspect and orchestrate JARVIS autonomous background worker agents (Claws). "
            "Use this tool to list registered Claws (database maintenance, repository health, "
            "system monitor, email/RSS digest, web monitor), inspect background worker pool status, "
            "trigger jobs, query execution results, inspect checkpoints, or cancel jobs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "status", "dispatch", "jobs", "checkpoint", "cancel"],
                    "description": "The Claw operation to perform.",
                },
                "claw_id": {
                    "type": "string",
                    "description": "Identifier of the Claw (e.g. 'claw:database_maintenance', 'claw:repository_health', 'claw:system_monitor', 'claw:digest_telemetry', 'claw:web_monitor').",
                },
                "payload": {
                    "type": "object",
                    "description": "Optional configuration payload for dispatched Claw jobs.",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high", "critical"],
                    "description": "Execution priority level for the dispatched job.",
                },
                "job_id": {
                    "type": "string",
                    "description": "Specific job ID (required for 'cancel', optional for 'jobs').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of jobs to retrieve (default: 20).",
                },
            },
            "required": ["action"],
        },
    }


def create_claws_tool(options: dict[str, Any] | None = None) -> AgentTool:
    """Create the canonical claws tool instance for agent sessions."""

    async def execute(
        args: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        from src.claws import ClawPriority, get_claws_engine

        engine = get_claws_engine()
        action = args.get("action", "list")

        if action == "list":
            claws = engine.list_claws()
            return {"status": "ok", "action": "list", "total": len(claws), "claws": claws}

        elif action == "status":
            engine_status = engine.get_status()
            return {"status": "ok", "action": "status", "engine": engine_status}

        elif action == "dispatch":
            claw_id = args.get("claw_id")
            if not claw_id:
                return {
                    "status": "error",
                    "error": "Parameter 'claw_id' is required for action 'dispatch'.",
                }
            claw = engine.get_claw(claw_id)
            if not claw:
                return {
                    "status": "error",
                    "error": f"Claw '{claw_id}' not found among registered Claws.",
                }

            prio_str = str(args.get("priority", "normal")).lower()
            prio_map = {
                "low": ClawPriority.LOW,
                "normal": ClawPriority.NORMAL,
                "high": ClawPriority.HIGH,
                "critical": ClawPriority.CRITICAL,
            }
            priority = prio_map.get(prio_str, ClawPriority.NORMAL)
            payload = args.get("payload") or {}

            job = engine.dispatch_job(claw_id=claw_id, payload=payload, priority=priority)
            return {
                "status": "ok",
                "action": "dispatch",
                "job_id": job.job_id,
                "claw_id": claw_id,
                "job_status": job.status.value,
            }

        elif action == "jobs":
            claw_id = args.get("claw_id")
            limit = int(args.get("limit", 20))
            specific_job_id = args.get("job_id")
            if specific_job_id:
                job = engine.get_job(specific_job_id)
                if not job:
                    return {
                        "status": "error",
                        "error": f"Job '{specific_job_id}' not found.",
                    }
                return {"status": "ok", "action": "jobs", "job": job.to_dict()}

            jobs = engine.task_queue.list_jobs(claw_id=claw_id, limit=limit)
            return {
                "status": "ok",
                "action": "jobs",
                "total": len(jobs),
                "jobs": [j.to_dict() for j in jobs],
            }

        elif action == "checkpoint":
            claw_id = args.get("claw_id")
            if not claw_id:
                return {
                    "status": "error",
                    "error": "Parameter 'claw_id' is required for action 'checkpoint'.",
                }
            cp = engine.task_queue.get_checkpoint(claw_id)
            return {
                "status": "ok",
                "action": "checkpoint",
                "claw_id": claw_id,
                "checkpoint": cp,
            }

        elif action == "cancel":
            job_id = args.get("job_id")
            if not job_id:
                return {
                    "status": "error",
                    "error": "Parameter 'job_id' is required for action 'cancel'.",
                }
            cancelled = engine.cancel_job(job_id, reason="Cancelled via Agent Tool")
            return {
                "status": "ok" if cancelled else "not_modified",
                "action": "cancel",
                "job_id": job_id,
                "cancelled": cancelled,
            }

        else:
            return {"status": "error", "error": f"Unknown action: {action}"}

    defn = create_claws_tool_definition()

    class _AgentToolWrapper(dict):
        def __getattr__(self, name: str) -> Any:
            try:
                return self[name]
            except KeyError:
                raise AttributeError(f"'AgentTool' object has no attribute '{name}'")

    return _AgentToolWrapper(
        name=defn["name"],
        description=defn["description"],
        parameter_schema=defn["inputSchema"],
        execute=execute,
    )


__all__ = [
    "create_claws_tool",
    "create_claws_tool_definition",
]
