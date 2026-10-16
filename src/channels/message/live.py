"""jarvis.channels.message.live — live message state machine and preview finalization.

OpenClaw parity: mirrors ``src/channels/message/live.ts``.
"""

from __future__ import annotations

import time
from typing import Generic, TypeVar

from src.channels.message.types import LiveMessagePhase, MessageReceipt

T = TypeVar("T")


class LiveMessageState(Generic[T]):
    """Tracks state of a live draft message preview through edit/finalization.

    Mirrors ``LiveMessageState`` (``live.ts``).
    Phase transitions: ``idle`` -> ``previewing`` -> ``finalizing`` -> ``finalized`` / ``cancelled``.
    """

    def __init__(self, initial_payload: T | None = None) -> None:
        self.phase: LiveMessagePhase = "idle"
        self.payload: T | None = initial_payload
        self.preview_receipt: MessageReceipt | None = None
        self.final_receipt: MessageReceipt | None = None
        self.updated_at: int = int(time.time() * 1000)

    @property
    def can_finalize_in_place(self) -> bool:
        """Return True if this preview can be finalized in place via edit."""
        return self.phase in ("idle", "previewing") and self.preview_receipt is not None

    def mark_preview_updated(self, payload: T, receipt: MessageReceipt | None = None) -> None:
        """Update live preview state with a new draft payload and optional receipt."""
        self.phase = "previewing"
        self.payload = payload
        if receipt is not None:
            self.preview_receipt = receipt
        self.updated_at = int(time.time() * 1000)

    def mark_finalized(self, receipt: MessageReceipt) -> None:
        """Mark live preview state as finalized with the final send receipt."""
        self.phase = "finalized"
        self.final_receipt = receipt
        self.updated_at = int(time.time() * 1000)

    def mark_cancelled(self) -> None:
        """Mark live preview state as cancelled."""
        self.phase = "cancelled"
        self.updated_at = int(time.time() * 1000)


def create_live_message_state(initial_payload: T | None = None) -> LiveMessageState[T]:
    """Create a new LiveMessageState instance.

    Mirrors ``createLiveMessageState``.
    """
    return LiveMessageState(initial_payload)


__all__ = [
    "LiveMessageState",
    "create_live_message_state",
]
