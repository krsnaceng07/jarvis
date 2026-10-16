"""Docker-backed SandboxRunner.

Runs commands inside a lightweight container using `docker run`.
This is a best-effort helper for local dev; the runner checks that
`docker` is available and constructs a `docker run --rm` invocation
mounting the host workspace into the container.

This implementation is intentionally simple: it shells out to the
`docker` client and captures stdout/stderr. It is suitable for tests
that opt-in to use Docker; CI can skip these tests when Docker is
unavailable.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional


class DockerNotAvailable(RuntimeError):
    pass


class DockerSandboxRunner:
    """Run a command inside a Docker container.

    Parameters
    - `image`: container image to use (default: `python:3.11-slim`)
    - `workspace_dir`: host path to mount into `/workspace` in the container
    """

    def __init__(self, image: str = "python:3.11-slim", workspace_dir: Optional[str] = None) -> None:
        self.image = image
        self.workspace_dir = workspace_dir
        self._docker = shutil.which("docker")
        if not self._docker:
            raise DockerNotAvailable("docker CLI not found")

    async def run_command(self, cmd: List[str], cwd: Optional[str] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        if not cmd:
            raise ValueError("cmd must be non-empty")
        cmd = [str(c) for c in cmd]

        # Build docker run command
        docker_cmd = [self._docker, "run", "--rm"]
        # allow mount_dir override via cwd param
        mount_dir = cwd or self.workspace_dir
        if mount_dir:
            docker_cmd += ["-v", f"{mount_dir}:/workspace", "-w", "/workspace"]
        # Keep container ephemeral and non-interactive
        docker_cmd += [self.image] + cmd

        start = time.monotonic()
        try:
            completed = subprocess.run(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
                text=True,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return {
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "returncode": completed.returncode,
                "duration_ms": duration_ms,
            }
        except subprocess.TimeoutExpired as e:
            return {"stdout": e.stdout or "", "stderr": e.stderr or "", "returncode": -1, "duration_ms": int((time.monotonic() - start) * 1000)}


def docker_available() -> bool:
    return shutil.which("docker") is not None


__all__ = ["DockerSandboxRunner", "DockerNotAvailable", "docker_available"]
