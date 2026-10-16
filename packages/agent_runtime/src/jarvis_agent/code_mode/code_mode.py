import time
import uuid
from typing import Any, Dict, List, Optional

from .code_mode_worker import (
    CodeModeConfig,
    CodeModeWorkerInputExec,
    CodeModeWorkerInputResume,
    CodeModeWorkerResult,
    run_code_mode_worker,
)

# Active runs in memory
active_runs: Dict[str, Dict[str, Any]] = {}

DEFAULT_CODE_MODE_CONFIG: CodeModeConfig = {
    "timeoutMs": 10000,
    "memoryLimitBytes": 64 * 1024 * 1024,
    "maxPendingToolCalls": 16,
    "maxSnapshotBytes": 10 * 1024 * 1024,
}


def execute_code_mode(
    source: str,
    catalog: List[Any],
    namespaces: List[Any],
    config: Optional[CodeModeConfig] = None,
) -> Any:
    """Execute code mode guest script.

    This is called when the `exec` tool is invoked.
    """
    run_id = str(uuid.uuid4())
    resolved_config = config or DEFAULT_CODE_MODE_CONFIG

    input_data: CodeModeWorkerInputExec = {
        "kind": "exec",
        "source": source,
        "config": resolved_config,
        "catalog": catalog,
        "namespaces": namespaces,
        "apiFiles": [],
    }

    result = run_code_mode_worker(input_data)
    return handle_worker_result(run_id, resolved_config, result)


def resume_code_mode(
    run_id: str,
    settled_requests: List[Any],
) -> Any:
    """Resume a suspended code mode run.

    This is called when the `wait` tool is invoked, or automatically
    if bridge requests were resolved by the host.
    """
    if run_id not in active_runs:
        raise ValueError(f"No active run found for runId: {run_id}")

    run_state = active_runs[run_id]

    input_data: CodeModeWorkerInputResume = {
        "kind": "resume",
        "snapshotBytes": run_state["snapshotBytes"],
        "config": run_state["config"],
        "settledRequests": settled_requests,
    }

    result = run_code_mode_worker(input_data)
    return handle_worker_result(run_id, run_state["config"], result)


def handle_worker_result(run_id: str, config: CodeModeConfig, result: CodeModeWorkerResult) -> Any:
    """Process the result from the worker, suspending or completing the run."""
    if result["status"] == "completed":
        if run_id in active_runs:
            del active_runs[run_id]
        return {
            "status": "completed",
            "value": result.get("value"),
            "output": result.get("output", []),
        }

    elif result["status"] == "waiting":
        # Suspend and store state
        active_runs[run_id] = {
            "runId": run_id,
            "snapshotBytes": result["snapshotBytes"],
            "config": config,
            "pendingRequests": result.get("pendingRequests", []),
            "createdAt": time.time(),
        }
        return {
            "status": "waiting",
            "runId": run_id,
            "output": result.get("output", []),
            "pendingRequests": result.get("pendingRequests", []),
        }

    elif result["status"] == "failed":
        if run_id in active_runs:
            del active_runs[run_id]
        return {
            "status": "failed",
            "error": result.get("error", "Unknown error"),
            "code": result.get("code", "internal_error"),
            "output": result.get("output", []),
        }

    raise ValueError(f"Unknown worker result status: {result.get('status')}")
