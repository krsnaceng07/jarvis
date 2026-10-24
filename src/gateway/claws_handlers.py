"""Gateway Claws RPC handlers — JARVIS Autonomous Architecture (Section 6 & 8).

Exposes JSON-RPC endpoints for autonomous background worker Claws:
- claws.list: list all registered Claws and schedules
- claws.dispatch / claws.run: trigger execution of a Claw
- claws.status: engine health, worker count, and task queue metrics
- claws.jobs: list pending and completed Claw jobs
- claws.get: get details of a specific job by jobId
- claws.checkpoint: read latest checkpoint for a Claw
- claws.cancel: cancel a pending or running job
- claws.audit: inspect audit ledger records
"""

from __future__ import annotations

import logging
from typing import Any

from src.claws import ClawsEngine, get_claws_engine
from .rpc_dispatcher import RPCDispatchError

logger = logging.getLogger("jarvis.gateway.claws")


def make_claws_handlers(engine: ClawsEngine | None = None) -> dict[str, Any]:
    """Build and return gateway RPC handlers for autonomous Claws."""
    claws_engine = engine or get_claws_engine()

    def list_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        claws = claws_engine.list_claws()
        return {"claws": claws, "total": len(claws)}

    def status_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        return claws_engine.get_status()

    def dispatch_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        claw_id = params.get("clawId") or params.get("claw_id")
        if not claw_id:
            raise RPCDispatchError(
                -32602, "Invalid params: 'clawId' is required to dispatch a Claw"
            )
        claw = claws_engine.get_claw(claw_id)
        if not claw:
            raise RPCDispatchError(-32602, f"Claw '{claw_id}' not found")

        payload = params.get("payload") or {}
        job = claws_engine.dispatch_job(claw_id, payload=payload)
        return {"jobId": job.job_id, "clawId": claw_id, "status": job.status.value}

    def jobs_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        claw_id = params.get("clawId") or params.get("claw_id")
        limit = int(params.get("limit", 50))
        jobs = claws_engine.task_queue.list_jobs(claw_id=claw_id, limit=limit)
        return {"jobs": [j.to_dict() for j in jobs], "total": len(jobs)}

    def get_job_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        job_id = params.get("jobId") or params.get("job_id")
        if not job_id:
            raise RPCDispatchError(-32602, "Invalid params: 'jobId' is required")
        job = claws_engine.get_job(job_id)
        if not job:
            raise RPCDispatchError(-32602, f"Job '{job_id}' not found")
        return {"job": job.to_dict()}

    def checkpoint_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        claw_id = params.get("clawId") or params.get("claw_id")
        if not claw_id:
            raise RPCDispatchError(-32602, "Invalid params: 'clawId' is required")
        data = claws_engine.task_queue.get_checkpoint(claw_id)
        return {"clawId": claw_id, "checkpoint": data}

    def cancel_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        job_id = params.get("jobId") or params.get("job_id")
        if not job_id:
            raise RPCDispatchError(-32602, "Invalid params: 'jobId' is required")
        reason = params.get("reason", "Cancelled via gateway RPC")
        cancelled = claws_engine.cancel_job(job_id, reason=reason)
        return {"jobId": job_id, "cancelled": cancelled}

    def audit_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        claw_id = params.get("clawId") or params.get("claw_id")
        limit = int(params.get("limit", 50))
        entries = claws_engine.task_queue.get_audit_log(claw_id=claw_id, limit=limit)
        return {"entries": entries, "total": len(entries)}

    return {
        "claws.list": list_handler,
        "claws.status": status_handler,
        "claws.dispatch": dispatch_handler,
        "claws.run": dispatch_handler,
        "claws.jobs": jobs_handler,
        "claws.get": get_job_handler,
        "claws.checkpoint": checkpoint_handler,
        "claws.cancel": cancel_handler,
        "claws.audit": audit_handler,
    }


__all__ = ["make_claws_handlers"]
