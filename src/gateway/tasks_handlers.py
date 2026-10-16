"""Gateway task RPC handlers — mirrors OpenClaw's src/gateway/server-methods/tasks.ts.

Exposes detached background task list, get, and cancel operations over the
canonical in-process task ledger.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.tasks import (
    get_task_by_id,
    list_task_records,
    summarize_task_records,
    upsert_task,
)


def make_tasks_handlers() -> dict[str, Any]:
    """Build and return gateway RPC handlers for background tasks."""

    def list_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        status_filter = params.get("status")
        runtime_filter = params.get("runtime")
        limit = int(params.get("limit", 100))
        offset = int(params.get("offset", 0))

        all_tasks = list_task_records()

        # Apply optional filters
        filtered = all_tasks
        if status_filter:
            allowed_statuses = (
                set(status_filter) if isinstance(status_filter, list) else {str(status_filter)}
            )
            filtered = [t for t in filtered if t.status in allowed_statuses]

        if runtime_filter:
            allowed_runtimes = (
                set(runtime_filter) if isinstance(runtime_filter, list) else {str(runtime_filter)}
            )
            filtered = [t for t in filtered if t.runtime in allowed_runtimes]

        sliced = filtered[offset : offset + limit] if limit else filtered[offset:]

        return {
            "tasks": [asdict(t) for t in sliced],
            "total": len(filtered),
            "summary": asdict(summarize_task_records(all_tasks)),
        }

    def get_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        task_id = str(params.get("taskId") or params.get("task_id") or "")
        if not task_id:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(-32602, "Invalid params: 'taskId' or 'task_id' is required")

        task = get_task_by_id(task_id)
        if task is None:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(404, f"Task not found: {task_id}")

        return {"task": asdict(task)}

    def cancel_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        task_id = str(params.get("taskId") or params.get("task_id") or "")
        if not task_id:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(-32602, "Invalid params: 'taskId' or 'task_id' is required")

        task = get_task_by_id(task_id)
        if task is None:
            return {"found": False, "cancelled": False}

        import dataclasses
        import time
        from src.tasks.delivery import maybe_deliver_task_terminal_update

        reason = str(params.get("reason") or "cancelled_via_rpc")
        now_ms = int(time.time() * 1000)
        updated = dataclasses.replace(
            task,
            status="cancelled",
            ended_at=now_ms,
            last_event_at=now_ms,
            error=reason,
            delivery_status="pending" if task.notify_policy != "silent" else "not_applicable",
        )
        upsert_task(updated)
        maybe_deliver_task_terminal_update(task.task_id)

        return {
            "found": True,
            "cancelled": True,
            "reason": reason,
            "task": asdict(updated),
        }

    def retry_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        raw_ids = params.get("taskIds") or params.get("task_ids")
        if raw_ids is None:
            single_id = params.get("taskId") or params.get("task_id")
            raw_ids = [str(single_id)] if single_id else []
        elif isinstance(raw_ids, str):
            raw_ids = [raw_ids]

        if not raw_ids:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(-32602, "Invalid params: 'taskId' or 'taskIds' is required")

        import dataclasses
        import time
        from src.tasks.delivery import maybe_deliver_task_terminal_update

        results = []
        for tid in raw_ids:
            task = get_task_by_id(str(tid))
            if task is None:
                results.append({"taskId": str(tid), "ok": False, "reason": "task not found"})
                continue

            now_ms = int(time.time() * 1000)
            updated = dataclasses.replace(
                task,
                delivery_status="pending",
                last_event_at=now_ms,
                error=None,
            )
            upsert_task(updated)
            delivered = maybe_deliver_task_terminal_update(task.task_id)
            results.append({
                "taskId": task.task_id,
                "ok": True,
                "task": asdict(delivered or updated),
            })

        return {
            "ok": any(r["ok"] for r in results),
            "results": results,
        }

    def dismiss_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        raw_ids = params.get("taskIds") or params.get("task_ids")
        if raw_ids is None:
            single_id = params.get("taskId") or params.get("task_id")
            raw_ids = [str(single_id)] if single_id else []
        elif isinstance(raw_ids, str):
            raw_ids = [raw_ids]

        if not raw_ids:
            from .rpc_dispatcher import RPCDispatchError

            raise RPCDispatchError(-32602, "Invalid params: 'taskId' or 'taskIds' is required")

        import dataclasses
        import time

        results = []
        for tid in raw_ids:
            task = get_task_by_id(str(tid))
            if task is None:
                results.append({"taskId": str(tid), "ok": False, "reason": "task not found"})
                continue

            now_ms = int(time.time() * 1000)
            updated = dataclasses.replace(
                task,
                delivery_status="dismissed",
                last_event_at=now_ms,
            )
            upsert_task(updated)
            results.append({
                "taskId": task.task_id,
                "ok": True,
                "task": asdict(updated),
            })

        return {
            "ok": any(r["ok"] for r in results),
            "results": results,
        }

    return {
        "tasks.list": list_handler,
        "task.list": list_handler,
        "tasks.get": get_handler,
        "task.get": get_handler,
        "tasks.cancel": cancel_handler,
        "task.cancel": cancel_handler,
        "tasks.retry": retry_handler,
        "task.retry": retry_handler,
        "tasks.dismiss": dismiss_handler,
        "task.dismiss": dismiss_handler,
    }


__all__ = ["make_tasks_handlers"]
