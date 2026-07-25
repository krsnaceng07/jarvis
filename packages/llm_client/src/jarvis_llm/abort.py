"""jarvis_llm.abort — explicit cancellation signal.

OpenClaw parity: the ``AbortSignal`` / ``AbortController`` pair that
``StreamOptions.signal`` and every agent-loop hook receives.

Why not asyncio cancellation
============================
This is a deliberate, load-bearing deviation, recorded as a risk in
``docs/OPENCLAW_BRAIN_PORT_PLAN_V2.md`` §7.

OpenClaw's loop checks ``signal?.aborted`` at specific points and then
*synthesizes a complete, well-formed event sequence* before returning
(``agent-loop.ts:270`` ``stopIfAborted``). That is cooperative: abort is
data the loop inspects, not control flow imposed on it.

``asyncio.CancelledError`` is the opposite — it unwinds the stack at an
arbitrary ``await``. If the loop relied on it, an abort would tear out of
``run_loop`` mid-turn without emitting ``turn_end``/``agent_end``, leaving
a dangling ``toolUse`` message that session post-processing would then try
to compact from. That is precisely the corruption the OpenClaw contract
exists to prevent.

JARVIS also exposes sync wrappers over an async loop (per the 4.4c/4.4d
decision), and cancellation does not propagate cleanly across that
boundary while a checkable flag does.

So: abort is an explicit object with a boolean and callbacks. The loop
polls it. Nothing raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


class AbortError(Exception):
    """The reason attached to a signal aborted without an explicit cause.

    Parity: OpenClaw defaults ``signal.reason`` to ``new Error("Agent run
    aborted")`` when none was supplied (``agent-loop.ts`` failure-message
    construction). Held as a type so callers can distinguish a plain abort
    from a domain-specific reason such as a turn handoff.
    """


class TurnHandoffAbort(AbortError):
    """Abort caused by handing the turn to another runtime.

    Parity: ``isTurnHandoffAbort(signal)`` in ``agent-loop.ts``. The loop
    treats this differently — it does **not** append the "interrupted turn"
    message, because the turn is continuing elsewhere rather than being
    cut short. Modelled as a distinct exception type so that check stays a
    single ``isinstance``.
    """


@dataclass
class AbortSignal:
    """Cooperative cancellation flag. Parity: ``AbortSignal``.

    Consumers only read: :attr:`aborted`, :attr:`reason`,
    :meth:`throw_if_aborted` (used sparingly — the loop prefers polling),
    and :meth:`add_listener`. Producers use :class:`AbortController`.
    """

    aborted: bool = False
    reason: BaseException | None = None
    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register an abort callback; returns an unsubscribe callable.

        Fires immediately when the signal is already aborted, matching
        ``addEventListener`` semantics on an already-aborted DOM signal
        closely enough for the loop's teardown needs. A raising listener
        must not break the others, so exceptions are swallowed here —
        teardown callbacks are best-effort by design.
        """
        if self.aborted:
            _safe_call(listener)
            return lambda: None

        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    def throw_if_aborted(self) -> None:
        """Raise :attr:`reason` when aborted.

        Provided for parity with ``signal.throwIfAborted()``. The agent
        loop deliberately does *not* use this on its main path; it polls
        :attr:`aborted` and synthesizes a proper event sequence instead.
        """
        if self.aborted:
            raise self.reason if self.reason is not None else AbortError("Agent run aborted")

    @property
    def is_turn_handoff(self) -> bool:
        """Whether this abort is a turn handoff. Parity: ``isTurnHandoffAbort``."""
        return isinstance(self.reason, TurnHandoffAbort)


class AbortController:
    """Produces and trips an :class:`AbortSignal`. Parity: ``AbortController``."""

    def __init__(self) -> None:
        self._signal = AbortSignal()

    @property
    def signal(self) -> AbortSignal:
        return self._signal

    def abort(self, reason: BaseException | str | None = None) -> None:
        """Trip the signal. Idempotent — a second abort is a no-op.

        Idempotency matters because both a user interrupt and a timeout can
        race to abort the same run; the first reason wins so diagnostics
        report the actual cause.
        """
        if self._signal.aborted:
            return

        if reason is None:
            resolved: BaseException = AbortError("Agent run aborted")
        elif isinstance(reason, BaseException):
            resolved = reason
        else:
            resolved = AbortError(str(reason))

        self._signal.aborted = True
        self._signal.reason = resolved

        listeners = list(self._signal._listeners)
        self._signal._listeners.clear()
        for listener in listeners:
            _safe_call(listener)


def _safe_call(listener: Callable[[], None]) -> None:
    """Invoke a teardown listener, swallowing failures.

    One broken listener must not prevent the rest of teardown, and must not
    surface as an exception on the abort path — the abort path exists to
    avoid exceptions.
    """
    try:
        listener()
    except Exception:  # noqa: BLE001 - best-effort teardown, by design
        pass


def is_aborted(signal: AbortSignal | None) -> bool:
    """``signal?.aborted`` with the None-safety the loop relies on."""
    return signal is not None and signal.aborted


__all__ = [
    "AbortController",
    "AbortError",
    "AbortSignal",
    "TurnHandoffAbort",
    "is_aborted",
]
