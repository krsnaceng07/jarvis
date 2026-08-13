Overview
--------
This directory contains the embedded agent runner wiring and a minimal
host-side sandbox/dispatch implementation used for Phase 7 parity with
OpenClaw. The goal is to provide the same public surface (hooks,
dispatch contracts, and sandbox metadata) so the Layer 3 agent loop can
depend on a predictable host behavior.

Key components
--------------
- `default_dispatch_hook.py`: factory `make_default_dispatch_hook(...)` that
  - accepts a `plugin_dispatch` mapping (`tool_name -> callable`) and optional
    `HookBus` + `SandboxRunner`,
  - routes non-exec tool calls to the async hook-aware dispatcher (`HookAwareAsyncToolDispatcher`),
  - detects exec-style tool calls (args include `command`/`cmd`/`exec`), enforces
    exec policy via `sandbox_info.resolve_embedded_full_access_state`, and
    executes allowed commands using `SandboxRunner`.

- `sandbox_runner.py`: minimal, test-friendly `SandboxRunner` that executes
  commands without a shell using `subprocess.run` and returns structured
  results (`stdout`, `stderr`, `returncode`, `duration_ms`). This is a
  no-docker fallback; a Docker-backed runner can be added behind the same
  interface later.

- `async_dispatch.py` / `hook_async_dispatch.py`: async dispatcher and
  hook-aware wrapper that mirror the sync `ToolDispatcher`/`HookAwareToolDispatcher`.

How to wire the host dispatch hook
----------------------------------
Example host wiring (Python):

```python
from src.agents.embedded_agent_runner.run.default_dispatch_hook import make_default_dispatch_hook
from src.agents.embedded_agent_runner.run.run_attempt_dispatch import set_dispatch_embedded_run_attempt_hook
from src.agents.embedded_agent_runner.sandbox_runner import SandboxRunner

plugin_dispatch = {
    "read_file": lambda name, args: {"text": "..."},
    # plugin functions may be sync or async
}

runner = SandboxRunner(workspace_dir="/workspace")
hook = make_default_dispatch_hook(plugin_dispatch, bus=None, sandbox_runner=runner)
set_dispatch_embedded_run_attempt_hook(hook)
```

Exec-style tool calls
---------------------
If a tool call contains `command`/`cmd`/`exec` in its `args`, the dispatch
hook treats it as a host command request and will:

- Check exec policy via `sandbox_info.resolve_embedded_full_access_state`.
- If allowed, run the command via the `SandboxRunner` and return the
  serialized result to the run attempt (`stdout`, `stderr`, `returncode`).
- If denied, return a `ToolCallResult` with `is_error=True` and a blocked reason.

Testing
-------
Run the focused tests for the new components:

```bash
e:/jarvis/.venv/Scripts/python.exe -m pytest tests/test_run_attempt_integration.py -q
e:/jarvis/.venv/Scripts/python.exe -m pytest tests/test_sandbox_runner.py -q
e:/jarvis/.venv/Scripts/python.exe -m pytest tests/test_async_hook_dispatch.py -q
```

Next steps
----------
- Implement a Docker-backed `SandboxRunner` with workspace materialization.
- Add finer-grained permission checks for read/write paths using
  `sandbox_skills.map_sandbox_skill_entries_for_prompt` and related helpers.
- Document the hook and capability in higher-level docs and changelogs.

Files mentioned
--------------
- [src/agents/embedded_agent_runner/run/default_dispatch_hook.py](src/agents/embedded_agent_runner/run/default_dispatch_hook.py)
- [src/agents/embedded_agent_runner/sandbox_runner.py](src/agents/embedded_agent_runner/sandbox_runner.py)
- [src/tools/hook_async_dispatch.py](src/tools/hook_async_dispatch.py)
