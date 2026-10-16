"""jarvis.agents.session_suspension — session suspension and lane auto-resume helpers.

OpenClaw parity: mirrors ``src/agents/session-suspension.ts``.

Records quota/manual/circuit suspensions and temporarily lowers command-lane
concurrency so a suspended session's lane does not accept new work until the
suspension expires or is cleared.

Key public functions used by the gateway startup path
------------------------------------------------------
``enable_session_suspension_timers_for_gateway_start``
    Called once at gateway start.  Re-arms timers for sessions that were
    persisted as suspended before this process started.  Returns the set of
    lane IDs whose concurrency is still managed by a live resume timer (so
    the caller can skip setting their concurrency — they will be set when the
    timer fires).

``get_cleanup_suspended_lane_ids_for_gateway_publication``
    Called during config live-reload (not gateway start).  Returns the set of
    lane IDs currently suspended by this runtime so the applier can skip
    overwriting them with the new config value.

``suspend_session``
    Persist a quota/manual suspension for a session and throttle its lane.

``clear_session_suspension_timers``
    Shutdown cleanup — cancel all pending resume timers and record the
    cleared resumes so live-reload can honour the saved concurrency.

``resolve_session_suspension_reason``
    Normalize raw suspension reason strings.

``resolve_session_suspension_target``
    Derive the lane ID for a given session key.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from src.gateway.server_lanes import (
    _lane_concurrency,
    set_command_lane_concurrency,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CUSTOM_LANE_RESUME_CONCURRENCY: int = 1
DEFAULT_QUOTA_SUSPENSION_RESUME_MS: int = 30 * 60 * 1000  # 30 minutes

_VALID_SUSPENSION_REASONS: frozenset[str] = frozenset({
    "quota",
    "manual",
    "circuit",
    "rate_limit",
})

# ---------------------------------------------------------------------------
# Runtime state (process-global singleton)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _LaneResumeTimer:
    timer: threading.Timer
    resume_concurrency: int
    resume_at_ms: int


@dataclass(slots=True)
class _ClearedLaneResume:
    resume_concurrency: int
    resume_at_ms: int


@dataclass
class _SuspensionState:
    lane_resume_timers: dict[str, _LaneResumeTimer] = field(default_factory=dict)
    cleared_lane_resumes: dict[str, _ClearedLaneResume] = field(default_factory=dict)
    cleanup_generation: int = 0
    cleanup_active: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)


_state = _SuspensionState()


def _current_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Public: reason normalization
# ---------------------------------------------------------------------------


def resolve_session_suspension_reason(value: object) -> str:
    """Normalize a raw suspension reason string.

    Mirrors ``resolveSessionSuspensionReason``.
    Defaults unknown/missing values to ``"quota"``.
    """
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _VALID_SUSPENSION_REASONS:
            return normalized
    return "quota"


# ---------------------------------------------------------------------------
# Public: target lane derivation
# ---------------------------------------------------------------------------


def resolve_session_suspension_target(session_key: str | None) -> str:
    """Derive the command-lane ID for *session_key*.

    Mirrors ``resolveSessionSuspensionTarget``.
    Session lanes are prefixed ``session:`` (see :func:`resolve_session_lane`).
    """
    from src.agents.embedded_agent_runner.lanes import resolve_session_lane
    return resolve_session_lane(session_key or "")


# ---------------------------------------------------------------------------
# Internal: lane throttle / resume
# ---------------------------------------------------------------------------


def _throttle_lane(lane_id: str) -> None:
    """Set the lane concurrency to 0 (fully suspended).

    Writes directly into the lane table so the suspension value of 0
    bypasses the ``max(1, …)`` guard in :func:`set_command_lane_concurrency`.
    """
    _lane_concurrency[lane_id] = 0


def _resume_lane(lane_id: str, concurrency: int) -> None:
    """Restore the lane concurrency after a suspension."""
    set_command_lane_concurrency(lane_id, max(1, concurrency))
    with _state._lock:
        _state.lane_resume_timers.pop(lane_id, None)


# ---------------------------------------------------------------------------
# Public: gateway startup
# ---------------------------------------------------------------------------


def enable_session_suspension_timers_for_gateway_start(
    resolve_resume_concurrency: Callable[[str, int], int],
) -> frozenset[str]:
    """Re-arm suspension resume timers at gateway start.

    Mirrors ``enableSessionSuspensionTimersForGatewayStart``.

    *resolve_resume_concurrency* receives ``(lane_id, saved_resume_concurrency)``
    and returns the concurrency to restore when the timer fires. This allows
    the caller (``apply_gateway_lane_concurrency``) to inject the freshly
    resolved config concurrency values.

    Returns the set of lane IDs that have an active suspend timer — the
    caller must NOT overwrite those lanes' concurrency, as the timer owns them.
    """
    suspended: set[str] = set()

    with _state._lock:
        # Re-arm any cleared lane resumes that were saved from a previous
        # shutdown (not yet expired).
        now = _current_ms()
        for lane_id, cleared in list(_state.cleared_lane_resumes.items()):
            remaining_ms = cleared.resume_at_ms - now
            if remaining_ms <= 0:
                # Already expired — just restore.
                _resume_lane(lane_id, cleared.resume_concurrency)
                continue

            resume_concurrency = resolve_resume_concurrency(lane_id, cleared.resume_concurrency)
            _throttle_lane(lane_id)

            def _make_resume(lid: str, rc: int) -> Callable[[], None]:
                def _do_resume() -> None:
                    _resume_lane(lid, rc)
                return _do_resume

            timer = threading.Timer(remaining_ms / 1000.0, _make_resume(lane_id, resume_concurrency))
            timer.daemon = True
            timer.start()
            _state.lane_resume_timers[lane_id] = _LaneResumeTimer(
                timer=timer,
                resume_concurrency=resume_concurrency,
                resume_at_ms=cleared.resume_at_ms,
            )
            suspended.add(lane_id)

        _state.cleared_lane_resumes.clear()
        _state.cleanup_active = False

    return frozenset(suspended)


def get_cleanup_suspended_lane_ids_for_gateway_publication() -> frozenset[str]:
    """Return lane IDs currently held by active suspension timers.

    Mirrors ``getCleanupSuspendedLaneIdsForGatewayPublication``.

    Called during live-reload. The applier skips setting concurrency for
    returned lane IDs so the existing timer continues to own them.
    """
    with _state._lock:
        return frozenset(_state.lane_resume_timers.keys())


# ---------------------------------------------------------------------------
# Public: suspend session
# ---------------------------------------------------------------------------


def suspend_session(
    lane_id: str,
    *,
    resume_after_ms: int = DEFAULT_QUOTA_SUSPENSION_RESUME_MS,
    resume_concurrency: int = DEFAULT_CUSTOM_LANE_RESUME_CONCURRENCY,
    reason: str = "quota",
    session_id: str | None = None,
) -> None:
    """Throttle *lane_id* and schedule its resume after *resume_after_ms*.

    Mirrors ``suspendSession`` (simplified — without SQLite persistence;
    that is handled by the state_core layer).

    If a timer is already running for this lane, it is cancelled and
    replaced with the new one.
    """
    with _state._lock:
        # Cancel any existing timer.
        existing = _state.lane_resume_timers.pop(lane_id, None)
        if existing:
            existing.timer.cancel()

        _throttle_lane(lane_id)
        resume_at_ms = _current_ms() + resume_after_ms

        def _do_resume() -> None:
            _resume_lane(lane_id, resume_concurrency)

        timer = threading.Timer(resume_after_ms / 1000.0, _do_resume)
        timer.daemon = True
        timer.start()
        _state.lane_resume_timers[lane_id] = _LaneResumeTimer(
            timer=timer,
            resume_concurrency=resume_concurrency,
            resume_at_ms=resume_at_ms,
        )


# ---------------------------------------------------------------------------
# Public: shutdown cleanup
# ---------------------------------------------------------------------------


def clear_session_suspension_timers() -> None:
    """Cancel all pending resume timers and save the cleared resumes.

    Mirrors ``clearSessionSuspensionTimers``.
    Called at gateway shutdown so a restart can re-arm the remaining TTL.
    """
    with _state._lock:
        _state.cleanup_active = True
        _state.cleanup_generation += 1
        for lane_id, entry in list(_state.lane_resume_timers.items()):
            entry.timer.cancel()
            _state.cleared_lane_resumes[lane_id] = _ClearedLaneResume(
                resume_concurrency=entry.resume_concurrency,
                resume_at_ms=entry.resume_at_ms,
            )
        _state.lane_resume_timers.clear()


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _reset_session_suspension_state_for_test() -> None:
    """Cancel all timers and reset state. For use in tests only."""
    with _state._lock:
        for entry in _state.lane_resume_timers.values():
            entry.timer.cancel()
        _state.lane_resume_timers.clear()
        _state.cleared_lane_resumes.clear()
        _state.cleanup_generation = 0
        _state.cleanup_active = False


__all__ = [
    "DEFAULT_CUSTOM_LANE_RESUME_CONCURRENCY",
    "DEFAULT_QUOTA_SUSPENSION_RESUME_MS",
    "clear_session_suspension_timers",
    "enable_session_suspension_timers_for_gateway_start",
    "get_cleanup_suspended_lane_ids_for_gateway_publication",
    "resolve_session_suspension_reason",
    "resolve_session_suspension_target",
    "suspend_session",
]
