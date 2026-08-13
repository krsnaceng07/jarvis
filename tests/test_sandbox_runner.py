from __future__ import annotations

import asyncio
import sys
from src.agents.embedded_agent_runner.sandbox_runner import SandboxRunner


def test_run_simple_python_echo() -> None:
    runner = SandboxRunner()
    cmd = [sys.executable, "-c", "import sys; print(2+2); sys.stderr.write('err')"]
    res = asyncio.run(runner.run_command(cmd, cwd=None, timeout=5))
    assert "4" in res["stdout"]
    assert "err" in res["stderr"]
    assert isinstance(res["returncode"], int)


def test_missing_executable_raises() -> None:
    runner = SandboxRunner()
    try:
        asyncio.run(runner.run_command(["no-such-exe-___"], cwd=None, timeout=1))
        raised = False
    except Exception:
        raised = True
    assert raised
