"""WebSessionAdapter: Model B Web Browser Adapter for Track 3.5.

Enforces:
- Invariant T35-02: Model B direct WebSocket connection to Gateway with strict origin verification.
- Invariant T35-12: Multi-tab web clients share a session via gateway subscription multiplexing;
  each tab maintains its own independent connection_id while sharing the logical session.
- Invariant T35-17: Client view state exposes freshness status (LIVE, DEGRADED, STALE, RECONNECTING, OFFLINE).
- Invariant T35-18: Offline mode is strictly read-only; no local execution fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

from jarvis_client.errors import ClientErrorCode, JarvisClientException
from jarvis_client.protocol.client import JarvisClient
from jarvis_client.state.client_view import ClientViewState, TaskViewState, ViewFreshness


DEFAULT_ALLOWED_ORIGINS = frozenset(
    {
        "http://localhost",
        "https://localhost",
        "http://127.0.0.1",
        "https://127.0.0.1",
        "http://[::1]",
        "https://[::1]",
    }
)


def is_allowed_origin(
    origin: str | None,
    allowed_origins: set[str] | frozenset[str] | None = None,
) -> bool:
    """Verify if the given browser Origin header is permitted.

    Protects against Cross-Site WebSocket Hijacking (CSWSH).
    """
    if not origin:
        # Strict rejection if origin is missing in browser contexts
        return False

    allowed = allowed_origins if allowed_origins is not None else DEFAULT_ALLOWED_ORIGINS

    # Direct match against allowed origin prefixes or exact matches
    parsed = urlparse(origin)
    origin_base = f"{parsed.scheme}://{parsed.hostname}".lower()

    for item in allowed:
        parsed_item = urlparse(item)
        allowed_base = f"{parsed_item.scheme}://{parsed_item.hostname}".lower()
        if origin_base == allowed_base:
            # If allowed item specified a port, verify matching port
            if parsed_item.port is not None:
                if parsed.port == parsed_item.port:
                    return True
            else:
                return True

    return False


@dataclass(frozen=True, slots=True)
class WebTabContext:
    """Context for an individual browser tab within a multi-tab session."""

    tab_id: str
    session_id: str
    origin: str
    is_active: bool = True


class WebSessionAdapter:
    """Adapter for web frontend clients supporting Model B direct gateway connectivity.

    Coordinates multi-tab instances sharing a logical session and provides
    event subscriptions with freshness tracking.
    """

    def __init__(
        self,
        client: JarvisClient,
        tab_id: str,
        origin: str,
        allowed_origins: set[str] | frozenset[str] | None = None,
    ) -> None:
        self.allowed_origins = (
            allowed_origins if allowed_origins is not None else DEFAULT_ALLOWED_ORIGINS
        )
        if not is_allowed_origin(origin, self.allowed_origins):
            raise JarvisClientException(
                code=ClientErrorCode.AUTH_FAILED,
                message=f"Origin '{origin}' is not permitted by Gateway origin policy.",
            )

        self.client = client
        self.tab_id = tab_id
        self.origin = origin
        self._event_listeners: list[Callable[[dict[str, Any]], None]] = []

        # Wire view updates
        self.client.view_state.add_listener(self._on_view_updated)

    @property
    def tab_context(self) -> WebTabContext:
        sess_id = self.client.session.session_id if self.client.session else "sess_web_pending"
        return WebTabContext(
            tab_id=self.tab_id,
            session_id=sess_id,
            origin=self.origin,
            is_active=self.client.lifecycle.is_connected,
        )

    @property
    def view_freshness(self) -> ViewFreshness:
        """Expose current freshness disclosure to web UI."""
        return self.client.view_state.freshness

    def subscribe(self, listener: Callable[[dict[str, Any]], None]) -> None:
        """Register a frontend UI subscriber for real-time state changes."""
        self._event_listeners.append(listener)

    def unsubscribe(self, listener: Callable[[dict[str, Any]], None]) -> None:
        """Remove a registered frontend subscriber."""
        if listener in self._event_listeners:
            self._event_listeners.remove(listener)

    def get_task_view(self, task_id: str | None = None) -> TaskViewState | None:
        """Fetch current task view from client state projection."""
        tid = task_id or self.client.view_state.active_task_id
        if not tid:
            return None
        return self.client.view_state.tasks.get(tid)

    def get_full_state(self) -> dict[str, Any]:
        """Return serialized state projection with freshness for initial tab hydration."""
        return {
            "tabId": self.tab_id,
            "freshness": self.client.view_state.freshness.value,
            "activeTaskId": self.client.view_state.active_task_id,
            "tasks": {
                tid: {
                    "taskId": t.task_id,
                    "state": t.state.value,
                    "title": t.title,
                    "planRevision": t.plan_revision,
                    "nodes": {
                        nid: {
                            "nodeId": n.node_id,
                            "title": n.title,
                            "state": n.state.value,
                            "attempt": n.attempt,
                            "requiresApproval": n.requires_approval,
                        }
                        for nid, n in t.nodes.items()
                    },
                }
                for tid, t in self.client.view_state.tasks.items()
            },
        }

    def send_chat(
        self,
        message: str,
        conversation_id: str | None = None,
        client_turn_id: str | None = None,
    ) -> dict[str, Any]:
        """Send chat message from web input."""
        acceptance = self.client.send_chat(
            message=message,
            conversation_id=conversation_id,
            client_turn_id=client_turn_id,
        )
        return {
            "accepted": acceptance.accepted,
            "requestId": acceptance.request_id,
            "turnId": acceptance.turn_id,
            "taskId": acceptance.task_id,
            "error": acceptance.error_message,
        }

    def respond_to_approval(
        self,
        approval_id: str,
        approved: bool,
        expected_plan_revision: int,
        current_plan_revision: int,
        expires_at_utc: str | None = None,
        reason: str = "",
    ) -> bool:
        """Submit approval decision from web modal."""
        return self.client.respond_to_approval(
            approval_id=approval_id,
            approved=approved,
            expected_plan_revision=expected_plan_revision,
            current_plan_revision=current_plan_revision,
            expires_at_utc=expires_at_utc,
            decision_reason=reason,
        )

    def cancel_task(
        self, task_id: str, reason: str = "User cancelled via Web UI"
    ) -> dict[str, Any]:
        """Request task cancellation from Web UI."""
        res = self.client.cancel_task(task_id=task_id, reason=reason)
        return {
            "accepted": res.accepted,
            "cancellationRequestId": res.cancellation_request_id,
            "taskId": res.task_id,
            "error": res.error_message,
        }

    def _on_view_updated(self, view_state: ClientViewState) -> None:
        """Broadcast view state update to all registered UI subscribers."""
        payload = {
            "type": "VIEW_UPDATED",
            "tabId": self.tab_id,
            "freshness": view_state.freshness.value,
            "activeTaskId": view_state.active_task_id,
            "taskCount": len(view_state.tasks),
        }
        for listener in self._event_listeners:
            try:
                listener(payload)
            except Exception:
                pass


__all__ = [
    "DEFAULT_ALLOWED_ORIGINS",
    "is_allowed_origin",
    "WebTabContext",
    "WebSessionAdapter",
]
