import json
import os
import subprocess
from typing import Any, List, Literal, Optional, TypedDict, Union


class CodeModeConfig(TypedDict):
    timeoutMs: int
    memoryLimitBytes: int
    maxPendingToolCalls: int
    maxSnapshotBytes: int


class PendingBridgeRequest(TypedDict):
    id: str
    method: Literal["search", "describe", "call", "callValue", "yield", "namespace"]
    args: List[Any]


class SettledBridgeRequest(TypedDict):
    id: str
    ok: bool
    value: Optional[Any]
    error: Optional[str]


class SerializedCodeModeNamespaceValue(TypedDict, total=False):
    kind: Literal["array", "function", "object", "value"]
    items: Optional[List["SerializedCodeModeNamespaceValue"]]
    path: Optional[List[str]]
    entries: Optional[List[tuple[str, "SerializedCodeModeNamespaceValue"]]]
    value: Optional[Any]


class CodeModeNamespaceDescriptor(TypedDict):
    id: str
    globalName: str
    description: Optional[str]
    scope: SerializedCodeModeNamespaceValue


class CodeModeApiVirtualFile(TypedDict):
    filename: str
    content: str


class CodeModeWorkerInputExec(TypedDict, total=False):
    kind: Literal["exec"]
    source: str
    config: CodeModeConfig
    catalog: List[Any]
    apiFiles: Optional[List[CodeModeApiVirtualFile]]
    namespaces: List[CodeModeNamespaceDescriptor]


class CodeModeWorkerInputResume(TypedDict):
    kind: Literal["resume"]
    snapshotBytes: str  # Base64 encoded
    config: CodeModeConfig
    settledRequests: List[SettledBridgeRequest]


CodeModeWorkerInput = Union[CodeModeWorkerInputExec, CodeModeWorkerInputResume]


class CodeModeWorkerResultCompleted(TypedDict):
    status: Literal["completed"]
    value: Any
    output: List[Any]


class CodeModeWorkerResultWaiting(TypedDict):
    status: Literal["waiting"]
    snapshotBytes: str  # Base64 encoded
    pendingRequests: List[PendingBridgeRequest]
    output: List[Any]


class CodeModeWorkerResultFailed(TypedDict):
    status: Literal["failed"]
    error: str
    code: Literal[
        "invalid_input",
        "runtime_unavailable",
        "timeout",
        "snapshot_limit_exceeded",
        "internal_error",
    ]
    output: List[Any]


CodeModeWorkerResult = Union[
    CodeModeWorkerResultCompleted,
    CodeModeWorkerResultWaiting,
    CodeModeWorkerResultFailed,
]


class CodeModeWorkerFailure(Exception):
    def __init__(self, code: str, message: str, output: Optional[List[Any]] = None):
        super().__init__(message)
        self.code = code
        self.output = output or []


def run_code_mode_worker(input_data: CodeModeWorkerInput) -> CodeModeWorkerResult:
    """Run the code mode worker subprocess and wait for the result."""
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    worker_host_path = os.path.join(assets_dir, "worker_host.js")

    if not os.path.exists(worker_host_path):
        raise CodeModeWorkerFailure(
            "runtime_unavailable",
            f"worker_host.js not found in {assets_dir}",
        )

    try:
        proc = subprocess.Popen(
            ["node", worker_host_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=assets_dir,
        )
    except FileNotFoundError:
        raise CodeModeWorkerFailure(
            "runtime_unavailable",
            "Node.js is not installed or not in PATH.",
        )

    input_json = json.dumps(input_data)

    try:
        stdout_data, stderr_data = proc.communicate(input_json + "\n")
    except Exception as e:
        proc.kill()
        raise CodeModeWorkerFailure("internal_error", f"Worker communication failed: {str(e)}")

    if not stdout_data.strip():
        # The worker might have crashed
        raise CodeModeWorkerFailure(
            "internal_error",
            f"Worker crashed with exit code {proc.returncode}. Stderr: {stderr_data.strip()}",
        )

    try:
        # The worker always returns exactly one JSON line before exiting.
        lines = [line for line in stdout_data.splitlines() if line.strip()]
        last_line = lines[-1]
        result = json.loads(last_line)
        return result  # type: ignore
    except json.JSONDecodeError as e:
        raise CodeModeWorkerFailure(
            "internal_error",
            f"Failed to parse worker output: {str(e)}. Stdout: {stdout_data.strip()} Stderr: {stderr_data.strip()}",
        )
