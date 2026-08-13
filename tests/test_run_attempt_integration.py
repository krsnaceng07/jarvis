from __future__ import annotations

import asyncio
from typing import Any, Dict

from src.agents.embedded_agent_runner.run.run_attempt_dispatch import (
    dispatch_embedded_run_attempt,
    set_dispatch_embedded_run_attempt_hook,
)
from src.agents.embedded_agent_runner.run.default_dispatch_hook import (
    make_default_dispatch_hook,
)
from src.agents.embedded_agent_runner.sandbox_runner import SandboxRunner


def test_dispatch_runs_tool_calls() -> None:
    # simple plugin dispatch mapping
    async def echo(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"echoed": args}

    plugin_dispatch = {"echo": echo}

    set_dispatch_embedded_run_attempt_hook(make_default_dispatch_hook(plugin_dispatch))

    input_obj = {
        "toolCalls": [
            {"name": "echo", "args": {"x": 1}, "id": "t1"},
        ]
    }

    res = asyncio.run(dispatch_embedded_run_attempt(input_obj))
    assert res["outcome"] == "complete"
    attempt = res.get("attemptResult")
    assert attempt is not None
    tool_results = attempt.get("toolResults")
    assert isinstance(tool_results, list)
    assert any(r.get("tool_name") == "echo" for r in tool_results)


def test_dispatch_exec_via_sandbox() -> None:
    async def echo(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"echoed": args}

    plugin_dispatch = {"echo": echo}
    runner = SandboxRunner()

    set_dispatch_embedded_run_attempt_hook(make_default_dispatch_hook(plugin_dispatch, sandbox_runner=runner))

    input_obj = {
        "toolCalls": [
            {"name": "run", "args": {"command": ["python", "-c", "print(42)"]}, "id": "t2"},
        ]
    }

    res = asyncio.run(dispatch_embedded_run_attempt(input_obj))
    assert res["outcome"] == "complete"
    attempt = res.get("attemptResult")
    assert attempt is not None
    tool_results = attempt.get("toolResults")
    assert isinstance(tool_results, list)
    assert any(r.get("tool_name") == "run" for r in tool_results)


def test_dispatch_exec_denied_by_policy() -> None:
    async def echo(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"echoed": args}

    plugin_dispatch = {"echo": echo}
    runner = SandboxRunner()

    set_dispatch_embedded_run_attempt_hook(make_default_dispatch_hook(plugin_dispatch, sandbox_runner=runner))

    # execElevated configured but fullAccessAvailable = False => should be denied
    input_obj = {
        "execElevated": {"enabled": True, "allowed": True, "fullAccessAvailable": False, "fullAccessBlockedReason": "host-policy"},
        "toolCalls": [
            {"name": "run", "args": {"command": ["python", "-c", "print(1)"]}, "id": "t3"},
        ],
    }

    res = asyncio.run(dispatch_embedded_run_attempt(input_obj))
    assert res["outcome"] == "complete"
    attempt = res.get("attemptResult")
    assert attempt is not None
    tool_results = attempt.get("toolResults")
    assert isinstance(tool_results, list)
    # find 'run' result and assert it is an error and mentions blockedReason
    run_res = next((r for r in tool_results if r.get("tool_name") == "run"), None)
    assert run_res is not None
    assert run_res.get("is_error") is True
    assert "exec not allowed" in (run_res.get("content") or "")


def test_exec_with_skill_materialization(tmp_path: str) -> None:
    # create a small source workspace with a skill file
    src_workspace = tmp_path / "ws"
    src_workspace.mkdir()
    skills_dir = src_workspace / "skills"
    skills_dir.mkdir()
    f = skills_dir / "s1.py"
    f.write_text("print('from_skill')")

    async def echo(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"echoed": args}

    plugin_dispatch = {"echo": echo}
    runner = SandboxRunner()

    set_dispatch_embedded_run_attempt_hook(make_default_dispatch_hook(plugin_dispatch, sandbox_runner=runner))

    entries = [{"skill": {"filePath": str(f.relative_to(src_workspace))}}]

    input_obj = {
        "skillsEntries": entries,
        "skillsWorkspaceDir": str(src_workspace),
        "execElevated": {"enabled": True, "allowed": True},
        "toolCalls": [
            {
                "name": "run",
                "args": {"command": ["python", "-c", "import pathlib; print(pathlib.Path('skills/s1.py').read_text())"]},
                "id": "t4",
            }
        ],
    }

    res = asyncio.run(dispatch_embedded_run_attempt(input_obj))
    assert res["outcome"] == "complete"
    attempt = res.get("attemptResult")
    tool_results = attempt.get("toolResults")
    run_res = next((r for r in tool_results if r.get("tool_name") == "run"), None)
    assert run_res is not None
    assert "from_skill" in (run_res.get("content") or "")
