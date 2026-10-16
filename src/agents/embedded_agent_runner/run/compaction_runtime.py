"""jarvis.agents.embedded_agent_runner.run.compaction_runtime — embedded-run compaction-runtime helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/compaction-runtime.ts``.

Public surface:

Functions:

- :func:`should_run_compaction`
- :func:`resolve_compaction_harness`
- :func:`build_compaction_runtime`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Installable hook for the should-run-compaction step.
_SHOULD_RUN_COMPACTION: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_should_run_compaction_compaction_runtime_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldRunCompaction hook."""
    global _SHOULD_RUN_COMPACTION
    _SHOULD_RUN_COMPACTION = hook


#: Installable hook for the resolve-compaction-harness step.
_RESOLVE_COMPACTION_HARNESS: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_resolve_compaction_harness_compaction_runtime_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveCompactionHarness hook."""
    global _RESOLVE_COMPACTION_HARNESS
    _RESOLVE_COMPACTION_HARNESS = hook


#: Installable hook for the build-compaction-runtime step.
_BUILD_COMPACTION_RUNTIME: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_build_compaction_runtime_compaction_runtime_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildCompactionRuntime hook."""
    global _BUILD_COMPACTION_RUNTIME
    _BUILD_COMPACTION_RUNTIME = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def should_run_compaction(params: Dict[str, Any]) -> bool:
    """Return True when the compaction should run.

    Mirrors :func:`shouldRunCompaction` (``compaction-runtime.ts``).
    """
    return _SHOULD_RUN_COMPACTION(dict(params or {}))


def resolve_compaction_harness(params: Dict[str, Any]) -> Any:
    """Resolve the compaction harness.

    Mirrors :func:`resolveCompactionHarness` (``compaction-runtime.ts``).
    """
    return _RESOLVE_COMPACTION_HARNESS(dict(params or {}))


def build_compaction_runtime(params: Dict[str, Any]) -> Any:
    """Build the compaction runtime.

    Mirrors :func:`buildCompactionRuntime` (``compaction-runtime.ts``).
    """
    return _BUILD_COMPACTION_RUNTIME(dict(params or {}))


__all__ = [
    "build_compaction_runtime",
    "resolve_compaction_harness",
    "set_build_compaction_runtime_compaction_runtime_hook",
    "set_resolve_compaction_harness_compaction_runtime_hook",
    "set_should_run_compaction_compaction_runtime_hook",
    "should_run_compaction",
]
