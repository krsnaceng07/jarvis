"""Test-support shim for context-engine-maintenance.test-support.ts.

This module exposes a tiny test API compatible with the OpenClaw
``context-engine-maintenance.test-support.ts`` contract. Tests can
install a test API object on ``builtins`` under the name
``openclaw_contextEngineMaintenanceTestApi`` to control the behavior.

If no test API is installed the shim falls back to reasonable no-op
behaviour and will attempt to call the runtime reset function directly
when resetting state for tests.
"""
from __future__ import annotations

import builtins
from typing import Any, Dict, Optional


_BUILTIN_API_NAME = "openclaw_contextEngineMaintenanceTestApi"


def _get_test_api() -> Any:
    return getattr(builtins, _BUILTIN_API_NAME, None)


def create_deferred_turn_maintenance_abort_signal(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Call the registered test API to create an abort signal for deferred maintenance.

    Returns an object with keys ``abortSignal`` and ``dispose``. If no test API
    is registered a harmless default is returned (``abortSignal`` = None,
    ``dispose`` = noop).
    """
    api = _get_test_api()
    if api is None:
        return {"abortSignal": None, "dispose": lambda: None}
    # Honor TS camelCase or Python snake_case names.
    if hasattr(api, "createDeferredTurnMaintenanceAbortSignal"):
        return getattr(api, "createDeferredTurnMaintenanceAbortSignal")(params or {})
    if hasattr(api, "create_deferred_turn_maintenance_abort_signal"):
        return getattr(api, "create_deferred_turn_maintenance_abort_signal")(params or {})
    return {"abortSignal": None, "dispose": lambda: None}


def reset_deferred_turn_maintenance_state_for_test() -> None:
    """Reset process-local deferred-turn-maintenance state used by tests.

    If a test API is installed it is invoked. Otherwise the runtime
    reset is attempted directly as a best-effort fallback.
    """
    api = _get_test_api()
    if api is None:
        # Best-effort fallback to reset the runtime module state if available.
        try:
            from src.agents.embedded_agent_runner.context_engine_maintenance import (
                reset_deferred_turn_maintenance_state_for_test as _reset,
            )

            _reset()
        except Exception:
            # If import or call fails, treat as no-op for test shim.
            pass
        return
    if hasattr(api, "resetDeferredTurnMaintenanceStateForTest"):
        getattr(api, "resetDeferredTurnMaintenanceStateForTest")()
    elif hasattr(api, "reset_deferred_turn_maintenance_state_for_test"):
        getattr(api, "reset_deferred_turn_maintenance_state_for_test")()


__all__ = [
    "create_deferred_turn_maintenance_abort_signal",
    "reset_deferred_turn_maintenance_state_for_test",
]
