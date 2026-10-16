"""Minimal sandbox execution engine (no-docker fallback).

This is a compact, test-friendly runner that provides the minimal
surface the embedded-runner expects: materialize workspace paths
(noop here), run a command in a controlled subprocess (no shell), and
return a structured result with stdout/stderr, exit code and timing.

This is intentionally small — the full container-based runner will be
ported from OpenClaw in later waves.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional


class SandboxExecutionError(RuntimeError):
    pass


class SandboxRunner:
    """Run commands in a restricted, sandbox-like way.

    API:
      - `async run_command(cmd: List[str], cwd: Optional[str]=None, timeout: Optional[float]=None)`
        Executes `cmd` (no shell) and returns a dict with keys: stdout, stderr, returncode, duration_ms.
    """

    def __init__(self, workspace_dir: Optional[str] = None) -> None:
        self.workspace_dir = workspace_dir

    async def run_command(self, cmd: List[str], cwd: Optional[str] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        if not cmd:
            raise ValueError("cmd must be a non-empty list")
        # Ensure cmd is a list of strings
        cmd = [str(c) for c in cmd]

        # Disallow shell metacharacters by requiring list invocation (no shell)
        # Validate the executable exists or is discoverable
        exe = shutil.which(cmd[0])
        if exe is None:
            # Allow running the current Python interpreter via sys.executable
            if cmd[0] in ("python", "python3"):
                cmd[0] = sys.executable
            else:
                raise SandboxExecutionError(f"executable not found: {cmd[0]}")

        start = time.monotonic()

        def _run() -> Dict[str, Any]:
            try:
                completed = subprocess.run(
                    cmd,
                    cwd=cwd or self.workspace_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    timeout=timeout,
                    check=False,
                    text=True,
                )
                return {
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "returncode": completed.returncode,
                }
            except subprocess.TimeoutExpired as e:
                return {"stdout": e.stdout or "", "stderr": e.stderr or "", "returncode": -1}

        result = await asyncio.to_thread(_run)
        duration_ms = int((time.monotonic() - start) * 1000)
        out = dict(result)
        out["duration_ms"] = duration_ms
        return out


def serialize_result(res: Dict[str, Any]) -> str:
    try:
        return json.dumps(res, ensure_ascii=False)
    except Exception:
        return str(res)


__all__ = ["SandboxRunner", "SandboxExecutionError", "serialize_result"]
