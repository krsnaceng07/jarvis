"""PyQt6 thread-safe signal bridge for Desktop HUD (Track 3.5).

Enforces Invariant T35-11:
Desktop GUI isolates network/WebSocket operations onto dedicated background threads.
Communicates strictly via typed signals to prevent UI freezes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from jarvis_client.protocol.client import JarvisClient
from jarvis_client.state.client_view import TaskViewState


@dataclass(frozen=True, slots=True)
class DesktopSignalPayload:
    """Type-safe signal container for desktop UI updates."""

    signal_name: str
    data: Any


class DesktopHudAdapter:
    """Bridges JarvisClient background operations to Desktop PyQt6 UI events."""

    def __init__(self, client: JarvisClient) -> None:
        self.client = client
        self._signal_listeners: dict[str, list[Callable[[Any], None]]] = {}

        # Forward lifecycle and reduction updates
        self.client.lifecycle.add_listener(self._on_connection_lifecycle_changed)

    def connect_signal(self, signal_name: str, handler: Callable[[Any], None]) -> None:
        """Register a UI thread callback for a named signal."""
        if signal_name not in self._signal_listeners:
            self._signal_listeners[signal_name] = []
        self._signal_listeners[signal_name].append(handler)

    def emit_signal(self, signal_name: str, data: Any) -> None:
        """Dispatch signal to registered UI listeners."""
        listeners = self._signal_listeners.get(signal_name, [])
        for listener in listeners:
            try:
                listener(data)
            except Exception:
                pass

    def get_current_task_view(self, task_id: str | None = None) -> TaskViewState | None:
        """Read-only view query (safe to call from UI thread)."""
        tid = task_id or self.client.view_state.active_task_id
        if not tid:
            return None
        return self.client.view_state.tasks.get(tid)

    def submit_user_chat(self, message: str) -> dict[str, Any]:
        """Send chat turn from HUD input field."""
        acceptance = self.client.send_chat(message=message)
        return {
            "accepted": acceptance.accepted,
            "requestId": acceptance.request_id,
            "turnId": acceptance.turn_id,
            "taskId": acceptance.task_id,
            "error": acceptance.error_message,
        }

    def submit_approval(
        self,
        approval_id: str,
        approved: bool,
        expected_plan_revision: int,
        current_plan_revision: int,
        expires_at_utc: str | None = None,
        reason: str = "",
    ) -> bool:
        """Submit approval decision from modal dialog."""
        return self.client.respond_to_approval(
            approval_id=approval_id,
            approved=approved,
            expected_plan_revision=expected_plan_revision,
            current_plan_revision=current_plan_revision,
            expires_at_utc=expires_at_utc,
            decision_reason=reason,
        )

    def submit_cancellation(
        self, task_id: str, reason: str = "User cancelled from HUD"
    ) -> dict[str, Any]:
        """Trigger cancellation from HUD stop button."""
        res = self.client.cancel_task(task_id=task_id, reason=reason)
        return {
            "accepted": res.accepted,
            "cancellationRequestId": res.cancellation_request_id,
            "taskId": res.task_id,
            "error": res.error_message,
        }

    def _on_connection_lifecycle_changed(self, old_state: Any, new_state: Any) -> None:
        self.emit_signal(
            "connection_changed", {"oldState": old_state.value, "newState": new_state.value}
        )


__all__ = ["DesktopSignalPayload", "DesktopHudAdapter"]
