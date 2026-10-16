"""jarvis.agents.embedded_agent_runner.run.execution_phase_diagnostics — execution-phase diagnostics helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/execution-phase-diagnostics.ts``.

Public surface:

- :func:`record_execution_phase_diagnostic`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Installable hook for the record-execution-phase-diagnostic step.
_RECORD_EXECUTION_PHASE_DIAGNOSTIC: Callable[
    [Dict[str, Any]], None
] = lambda _p: None


def set_record_execution_phase_diagnostic_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom recordExecutionPhaseDiagnostic hook."""
    global _RECORD_EXECUTION_PHASE_DIAGNOSTIC
    _RECORD_EXECUTION_PHASE_DIAGNOSTIC = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record_execution_phase_diagnostic(params: Dict[str, Any]) -> None:
    """Record an execution-phase diagnostic.

    Mirrors :func:`recordExecutionPhaseDiagnostic`
    (``execution-phase-diagnostics.ts``).
    """
    _RECORD_EXECUTION_PHASE_DIAGNOSTIC(dict(params or {}))


__all__ = [
    "record_execution_phase_diagnostic",
    "set_record_execution_phase_diagnostic_hook",
]
