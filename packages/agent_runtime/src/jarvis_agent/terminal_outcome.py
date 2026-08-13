"""terminal_outcome — normalizes agent-run terminal states.

Mirrors OpenClaw's ``packages/agent-core/src/terminal-outcome.ts``.

An agent run ends in one of four terminal states:
  - ``success``  — the agent completed normally (no abort, no error)
  - ``error``    — the agent ended with an unhandled exception
  - ``timeout``  — the run was interrupted because it exceeded a wall-clock limit
  - ``cancelled``— the run was explicitly cancelled via abort signal

The ``TerminalOutcome`` dataclass carries the outcome kind plus optional
error and timing information. The ``normalize_outcome()`` function merges
an exception, a timeout flag, and a cancellation flag into one canonical
outcome — preventing callers from re-deriving timeout/cancel precedence
in downstream projections.

Precedence (timeout > cancel > error > success) mirrors the OpenClaw
``mergeTerminalState`` function exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ── Outcome kinds ──────────────────────────────────────────────────────


class OutcomeKind(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


# ── TerminalOutcome ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TerminalOutcome:
    """Canonical representation of an agent run's terminal state.

    Mirrors OpenClaw's ``TerminalOutcome`` interface.

    Attributes
    ----------
    kind : OutcomeKind
        The terminal state (``success``, ``error``, ``timeout``, ``cancelled``).
    error : BaseException | None
        The exception that caused the run to end (if ``kind == error``).
    error_message : str | None
        Human-readable error description. Derived from ``error`` when not
        supplied explicitly.
    duration_ms : int | None
        Wall-clock time in milliseconds from turn start to terminal state.
    session_key : str | None
        The session that produced this outcome (for logging/tracing).
    """

    kind: OutcomeKind
    error: BaseException | None = None
    error_message: str | None = None
    duration_ms: int | None = None
    session_key: str | None = None

    @property
    def is_success(self) -> bool:
        return self.kind == OutcomeKind.SUCCESS

    @property
    def is_error(self) -> bool:
        return self.kind == OutcomeKind.ERROR

    @property
    def is_timeout(self) -> bool:
        return self.kind == OutcomeKind.TIMEOUT

    @property
    def is_cancelled(self) -> bool:
        return self.kind == OutcomeKind.CANCELLED

    @property
    def display_message(self) -> str:
        """Human-readable summary for logs / channel replies."""
        if self.error_message:
            return self.error_message
        if self.error:
            return f"{type(self.error).__name__}: {self.error}"
        return self.kind.value

    def __str__(self) -> str:
        return f"TerminalOutcome({self.kind.value})"


# ── Factory helpers ────────────────────────────────────────────────────


def success(
    *,
    duration_ms: int | None = None,
    session_key: str | None = None,
) -> TerminalOutcome:
    """Return a success outcome."""
    return TerminalOutcome(
        kind=OutcomeKind.SUCCESS,
        duration_ms=duration_ms,
        session_key=session_key,
    )


def error(
    exc: BaseException,
    *,
    message: str | None = None,
    duration_ms: int | None = None,
    session_key: str | None = None,
) -> TerminalOutcome:
    """Return an error outcome wrapping ``exc``."""
    return TerminalOutcome(
        kind=OutcomeKind.ERROR,
        error=exc,
        error_message=message or str(exc),
        duration_ms=duration_ms,
        session_key=session_key,
    )


def timeout(
    *,
    duration_ms: int | None = None,
    session_key: str | None = None,
) -> TerminalOutcome:
    """Return a timeout outcome."""
    return TerminalOutcome(
        kind=OutcomeKind.TIMEOUT,
        error_message="Agent run timed out",
        duration_ms=duration_ms,
        session_key=session_key,
    )


def cancelled(
    *,
    duration_ms: int | None = None,
    session_key: str | None = None,
) -> TerminalOutcome:
    """Return a cancelled outcome."""
    return TerminalOutcome(
        kind=OutcomeKind.CANCELLED,
        error_message="Agent run was cancelled",
        duration_ms=duration_ms,
        session_key=session_key,
    )


# ── Normalizer ─────────────────────────────────────────────────────────


def normalize_outcome(
    exc: BaseException | None = None,
    *,
    timed_out: bool = False,
    was_cancelled: bool = False,
    duration_ms: int | None = None,
    session_key: str | None = None,
) -> TerminalOutcome:
    """Merge exception + flags into a single canonical ``TerminalOutcome``.

    Mirrors OpenClaw's ``mergeTerminalState``. Precedence:
    timeout > cancelled > exception > success.

    Parameters
    ----------
    exc : BaseException | None
        Exception that ended the run, if any.
    timed_out : bool
        True when a wall-clock timeout fired.
    was_cancelled : bool
        True when the run was explicitly cancelled (AbortSignal).
    duration_ms : int | None
        Elapsed ms, passed through to the outcome.
    session_key : str | None
        Session identifier for tracing.
    """
    kwargs: dict = {"duration_ms": duration_ms, "session_key": session_key}
    if timed_out:
        return timeout(**kwargs)
    if was_cancelled:
        return cancelled(**kwargs)
    if exc is not None:
        return error(exc, **kwargs)
    return success(**kwargs)


__all__ = [
    "OutcomeKind",
    "TerminalOutcome",
    "cancelled",
    "error",
    "normalize_outcome",
    "success",
    "timeout",
]
