"""Gateway cron RPC handlers — mirrors OpenClaw's src/gateway/server-methods/cron.ts.

Connects to existing in-process scheduler (CronRunner in src.cron):
- cron.list: list all scheduled jobs
- cron.add / cron.create: add a new scheduled job
- cron.remove / cron.delete: remove a job
- cron.run: manually trigger a job run
- cron.get: get a job by id
- cron.status: scheduler status
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from src.cron import CronRunner, get_default_cron_runner
from jarvis_sdk.cron import CronDecl

_log = logging.getLogger("jarvis.gateway.cron")


def make_cron_handlers(runner: CronRunner | None = None) -> dict[str, Any]:
    """Build and return gateway RPC handlers for scheduled cron jobs."""
    cron_runner = runner or get_default_cron_runner()

    def list_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        include_disabled = bool(params.get("includeDisabled", True))
        all_jobs = cron_runner.list()
        filtered = all_jobs if include_disabled else [j for j in all_jobs if j.enabled]

        jobs_data = []
        for j in filtered:
            last_fired = cron_runner._last_fired.get(j.id)
            jobs_data.append(
                {
                    "id": j.id,
                    "schedule": j.schedule,
                    "enabled": j.enabled,
                    "timezone": j.timezone,
                    "description": j.description,
                    "automation_payload": j.automation_payload,
                    "lastRunAt": last_fired.isoformat() if last_fired else None,
                }
            )
        return {
            "jobs": jobs_data,
            "total": len(jobs_data),
        }

    def add_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        schedule = params.get("schedule")
        if not schedule or not isinstance(schedule, str) or not schedule.strip():
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(
                -32602, "Invalid params: 'schedule' is required and must be a non-empty string"
            )

        job_id = str(params.get("id") or params.get("jobId") or params.get("name") or uuid.uuid4())
        description = str(params.get("description") or params.get("name") or "")
        timezone = str(params.get("timezone") or "")
        enabled = bool(params.get("enabled", True))
        raw_payload = params.get("payload") or params.get("automation_payload")
        automation_payload = dict(raw_payload) if isinstance(raw_payload, dict) else None

        handler_fn = params.get("handler")
        if not callable(handler_fn):

            async def _default_job_handler() -> None:
                _log.info("cron: executed job %s (schedule: %s)", job_id, schedule)

            handler_fn = _default_job_handler

        decl = CronDecl(
            id=job_id,
            schedule=schedule.strip(),
            handler=handler_fn,
            timezone=timezone,
            enabled=enabled,
            description=description,
            automation_payload=automation_payload,
        )
        cron_runner.add(decl)

        return {
            "ok": True,
            "job": {
                "id": decl.id,
                "schedule": decl.schedule,
                "enabled": decl.enabled,
                "timezone": decl.timezone,
                "description": decl.description,
                "automation_payload": decl.automation_payload,
            },
        }

    def remove_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        job_id = str(params.get("id") or params.get("jobId") or params.get("job_id") or "")
        if not job_id:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(-32602, "Invalid params: 'id' or 'jobId' is required")

        existing = cron_runner.get(job_id)
        if existing is None:
            return {"ok": True, "removed": False, "id": job_id}

        cron_runner.remove(job_id)
        return {"ok": True, "removed": True, "id": job_id}

    def run_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        job_id = str(params.get("id") or params.get("jobId") or params.get("job_id") or "")
        if not job_id:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(-32602, "Invalid params: 'id' or 'jobId' is required")

        existing = cron_runner.get(job_id)
        if existing is None:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(404, f"Cron job not found: {job_id}")

        ran = cron_runner.run_job(job_id)
        return {"ok": True, "ran": ran, "id": job_id}

    def get_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        job_id = str(params.get("id") or params.get("jobId") or params.get("job_id") or "")
        if not job_id:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(-32602, "Invalid params: 'id' or 'jobId' is required")

        job = cron_runner.get(job_id)
        if job is None:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(404, f"Cron job not found: {job_id}")

        last_fired = cron_runner._last_fired.get(job.id)
        return {
            "ok": True,
            "job": {
                "id": job.id,
                "schedule": job.schedule,
                "enabled": job.enabled,
                "timezone": job.timezone,
                "description": job.description,
                "automation_payload": job.automation_payload,
                "lastRunAt": last_fired.isoformat() if last_fired else None,
            },
        }

    def status_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        is_running = cron_runner._thread is not None and cron_runner._thread.is_alive()
        return {
            "ok": True,
            "running": is_running,
            "job_count": len(cron_runner.list()),
        }

    return {
        "cron.list": list_handler,
        "cron_list": list_handler,
        "cron.add": add_handler,
        "cron.create": add_handler,
        "cron_add": add_handler,
        "cron_create": add_handler,
        "cron.remove": remove_handler,
        "cron.delete": remove_handler,
        "cron_remove": remove_handler,
        "cron_delete": remove_handler,
        "cron.run": run_handler,
        "cron_run": run_handler,
        "cron.get": get_handler,
        "cron_get": get_handler,
        "cron.status": status_handler,
        "cron_status": status_handler,
    }


__all__ = ["make_cron_handlers"]
