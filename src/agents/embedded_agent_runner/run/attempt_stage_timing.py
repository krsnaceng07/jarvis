"""jarvis.agents.embedded_agent_runner.run.attempt_stage_timing — track stage timing for an embedded run attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-stage-timing.ts``.

Public surface:

Constants:

- :data:`EMBEDDED_RUN_ATTEMPT_DISPATCH_STAGE`

Functions:

- :func:`create_embedded_run_stage_tracker`
- :func:`should_warn_embedded_run_stage_summary`
- :func:`create_embedded_run_stage_summary_emitter`
- :func:`format_embedded_run_stage_summary`

Phase 7.6d-6 — focused minimal port.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional


#: Embedded-run attempt dispatch stage keys. Mirrors
#: :data:`EMBEDDED_RUN_ATTEMPT_DISPATCH_STAGE`
#: (``attempt-stage-timing.ts``).
EMBEDDED_RUN_ATTEMPT_DISPATCH_STAGE: Dict[str, str] = {
    "auth_plan": "auth-plan",
    "auth": "auth",
    "scope": "scope",
    "store": "store",
    "prepare_plan": "prepare-plan",
    "harness": "harness",
    "hooks": "hooks",
    "session_prepare": "session-prepare",
    "stream_runtime": "stream-runtime",
    "stream_dispatch": "stream-dispatch",
    "stream_settle": "stream-settle",
    "result": "result",
}


#: Default stage-summary warning threshold (ms).
EMBEDDED_RUN_STAGE_SUMMARY_WARN_MS: int = 5_000


#: Default stage-summary emit threshold (ms).
EMBEDDED_RUN_STAGE_SUMMARY_EMIT_MS: int = 30_000


#: Embedded-run stage tracker.
EmbeddedRunStageTracker = Dict[str, Any]


#: Embedded-run stage summary emitter.
EmbeddedRunStageSummaryEmitter = Dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers (ported as-is)
# ---------------------------------------------------------------------------


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_embedded_run_stage_tracker(
    options: Optional[Dict[str, Any]] = None,
) -> EmbeddedRunStageTracker:
    """Create a new stage tracker for the run.

    Mirrors :func:`createEmbeddedRunStageTracker`
    (``attempt-stage-timing.ts``).
    """
    options = options or {}
    return {
        "startedAtMs": _now_ms(),
        "warnMs": int(
            options.get("warnMs", EMBEDDED_RUN_STAGE_SUMMARY_WARN_MS)
        ),
        "emitMs": int(
            options.get("emitMs", EMBEDDED_RUN_STAGE_SUMMARY_EMIT_MS)
        ),
        "stages": [],
        "current": None,
    }


def should_warn_embedded_run_stage_summary(
    tracker: Optional[Dict[str, Any]],
) -> bool:
    """Return True when the tracker has exceeded the warn threshold.

    Mirrors :func:`shouldWarnEmbeddedRunStageSummary`
    (``attempt-stage-timing.ts``).
    """
    if not isinstance(tracker, dict):
        return False
    started_at = tracker.get("startedAtMs")
    warn_ms = tracker.get("warnMs")
    if not isinstance(started_at, (int, float)) or not isinstance(warn_ms, (int, float)):
        return False
    return (_now_ms() - int(started_at)) >= int(warn_ms)


def create_embedded_run_stage_summary_emitter(
    options: Dict[str, Any],
) -> EmbeddedRunStageSummaryEmitter:
    """Create a stage-summary emitter.

    Mirrors :func:`createEmbeddedRunStageSummaryEmitter`
    (``attempt-stage-timing.ts``).
    """
    tracker = options.get("tracker")
    return {
        "tracker": tracker,
        "startedAtMs": (
            tracker.get("startedAtMs") if isinstance(tracker, dict) else None
        ),
    }


def format_embedded_run_stage_summary(
    tracker: Optional[Dict[str, Any]],
) -> str:
    """Format the stage summary for logging.

    Mirrors :func:`formatEmbeddedRunStageSummary`
    (``attempt-stage-timing.ts``).
    """
    if not isinstance(tracker, dict):
        return ""
    stages = tracker.get("stages") or []
    if not stages:
        return "no-stages"
    return ",".join(str(stage) for stage in stages)


__all__ = [
    "EMBEDDED_RUN_ATTEMPT_DISPATCH_STAGE",
    "EMBEDDED_RUN_STAGE_SUMMARY_EMIT_MS",
    "EMBEDDED_RUN_STAGE_SUMMARY_WARN_MS",
    "EmbeddedRunStageSummaryEmitter",
    "EmbeddedRunStageTracker",
    "create_embedded_run_stage_summary_emitter",
    "create_embedded_run_stage_tracker",
    "format_embedded_run_stage_summary",
    "should_warn_embedded_run_stage_summary",
]
