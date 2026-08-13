from __future__ import annotations

import asyncio
import pytest
from src.agents.embedded_agent_runner.sandbox_runner_docker import docker_available, DockerSandboxRunner


def test_docker_availability_check() -> None:
    # This test simply exercises the docker_available helper.
    # It does not fail if Docker is absent.
    _ = docker_available()


@pytest.mark.skipif(not docker_available(), reason="docker not installed")
def test_docker_runner_basic() -> None:
    runner = DockerSandboxRunner(image="python:3.11-slim")
    res = asyncio.run(runner.run_command(["python", "-c", "print(7)"] , timeout=10))
    assert res["returncode"] == 0
    assert "7" in res["stdout"]
