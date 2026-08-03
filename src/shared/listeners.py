"""jarvis.shared.listeners — listener set/notify helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/listeners.ts``.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional, Set, TypeVar

T = TypeVar("T")


def notify_listeners(
    listeners: Iterable[Callable[[T], None]],
    event: T,
    on_error: Optional[Callable[[object], None]] = None,
) -> None:
    """Notify every registered listener while isolating individual failures.

    Mirrors :func:`notifyListeners` (``shared/listeners.ts``).
    """
    for listener in listeners:
        try:
            listener(event)
        except Exception as exc:  # noqa: BLE001 — broadcast handler
            if on_error is not None:
                on_error(exc)


def register_listener(
    listeners: Set[Callable[[T], None]],
    listener: Callable[[T], None],
) -> Callable[[], None]:
    """Add ``listener`` to ``listeners`` and return an idempotent unsubscribe.

    Mirrors :func:`registerListener` (``shared/listeners.ts``).
    """
    listeners.add(listener)

    def _unsubscribe() -> bool:
        return listeners.discard(listener) is not None or True

    return _unsubscribe


__all__ = ["notify_listeners", "register_listener"]
