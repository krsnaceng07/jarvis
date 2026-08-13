"""Default host-side dispatch hook for embedded run attempts.

Provides a small async dispatch implementation that looks for a
`toolCalls` list in the attempt input and executes them using a
`HookAwareAsyncToolDispatcher`. This is a minimal host bridge used for
integration tests and early wiring; OpenClaw's full implementation is
much larger and will be ported in later waves.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.hooks import HookBus
from src.tools.hook_async_dispatch import HookAwareAsyncToolDispatcher
from src.agents.embedded_agent_runner import sandbox_info
from src.agents.embedded_agent_runner.sandbox_runner import SandboxRunner, serialize_result
from src.agents.embedded_agent_runner.sandbox_materialize import materialize_skill_entries
import shutil
import os


def make_default_dispatch_hook(
    plugin_dispatch: Dict[str, Callable[[str, dict], Any]],
    bus: HookBus | None = None,
    sandbox_runner: Optional[SandboxRunner] = None,
) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    """Create a dispatch hook that optionally routes exec-style calls to SandboxRunner.

    Exec-style detection: a tool call whose args contain one of the keys
    ``command``, ``cmd`` or ``exec`` will be treated as a host-command
    request and routed to the sandbox runner when available. Exec policy is
    enforced using ``sandbox_info.resolve_embedded_full_access_state`` with
    values taken from the run input (``execElevated``, ``execPolicy``,
    ``hostPolicy``).
    """

    async def _dispatch(input_obj: Dict[str, Any]) -> Dict[str, Any]:
        calls: List[Dict[str, Any]] = input_obj.get("toolCalls") or []
        dispatcher = HookAwareAsyncToolDispatcher(plugin_dispatch, bus)
        results = []

        # Exec policy context from input
        exec_elevated = input_obj.get("execElevated")
        exec_policy = input_obj.get("execPolicy")
        host_policy = input_obj.get("hostPolicy")

        tmpdir: str | None = None
        try:
            # If skillsEntries provided, materialize once into a tempdir and
            # mount that location for container/exec runs.
            skills_entries = input_obj.get("skillsEntries")
            if skills_entries and sandbox_runner is not None:
                source_workspace_dir = input_obj.get("skillsWorkspaceDir") or input_obj.get("workspaceDir") or os.getcwd()
                tmpdir, new_entries = materialize_skill_entries(skills_entries, source_workspace_dir)
                # replace in input so downstream readers see updated file paths
                input_obj["skillsEntries"] = new_entries

            for c in calls:
                name = c.get("name", "")
                args = c.get("args") or {}
                call_id = c.get("id", "")

                # Detect exec-style calls
                is_exec = any(k in args for k in ("command", "cmd", "exec"))

                if is_exec and sandbox_runner is not None:
                    # Enforce exec policy
                    full_access = sandbox_info.resolve_embedded_full_access_state(
                        {"execElevated": exec_elevated, "execPolicy": exec_policy, "hostPolicy": host_policy}
                    )
                    if not full_access.get("available"):
                        # Deny execution
                        from src.tools.dispatch import ToolCallResult

                        results.append(
                            ToolCallResult(
                                tool_name=name,
                                call_id=call_id,
                                content=f"Error: exec not allowed: {full_access.get('blockedReason')}",
                                is_error=True,
                                duration_ms=0,
                            )
                        )
                        continue

                    # Resolve command
                    cmd = args.get("command") or args.get("cmd") or args.get("exec")
                    # Normalize string -> list via shlex.split if needed
                    if isinstance(cmd, str):
                        import shlex

                        cmd_list = shlex.split(cmd)
                    else:
                        cmd_list = list(cmd)

                    # Run via sandbox runner
                    try:
                        mount_dir = tmpdir or input_obj.get("workspaceDir")
                        exec_res = await sandbox_runner.run_command(cmd_list, cwd=mount_dir)
                        from src.tools.dispatch import ToolCallResult

                        results.append(
                            ToolCallResult(
                                tool_name=name,
                                call_id=call_id,
                                content=serialize_result(exec_res),
                                is_error=False,
                                duration_ms=exec_res.get("duration_ms", 0),
                            )
                        )
                    except Exception as e:  # noqa: BLE001
                        from src.tools.dispatch import ToolCallResult

                        results.append(
                            ToolCallResult(
                                tool_name=name,
                                call_id=call_id,
                                content=f"Error: {type(e).__name__}: {e}",
                                is_error=True,
                                duration_ms=0,
                            )
                        )
                    continue

                # Default: route to plugin dispatch
                res = await dispatcher.execute(name, args, call_id=call_id)
                results.append(res)

        finally:
            # cleanup materialized tempdir when present
            if tmpdir:
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass

        # Serialize results to minimal attemptResult shape.
        from dataclasses import asdict

        attempt_result = {"toolResults": [asdict(r) for r in results]}
        return {"attemptResult": attempt_result, "terminal": None, "outcome": "complete"}

    return _dispatch


__all__ = ["make_default_dispatch_hook"]
