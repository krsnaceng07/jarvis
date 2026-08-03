"""jarvis.agents.embedded_agent_runner.run.midturn_precheck — mid-turn precheck helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/midturn-precheck.ts``.

Public surface:

- :func:`run_midturn_precheck`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the run-midturn-precheck step.
_RUN_MIDTURN_PRECHECK: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_run_midturn_precheck_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom runMidturnPrecheck hook."""
    global _RUN_MIDTURN_PRECHECK
    _RUN_MIDTURN_PRECHECK = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_midturn_precheck(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Run the mid-turn precheck.

    Mirrors :func:`runMidturnPrecheck` (``midturn-precheck.ts``).
    """
    result: Any = await _maybe_await(
        _RUN_MIDTURN_PRECHECK(dict(params or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "outcome": result.get("outcome", "continue"),
        "result": result.get("result"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "run_midturn_precheck",
    "set_run_midturn_precheck_hook",
]
