"""Google Meet browser manual action error types."""

from __future__ import annotations

from typing import Any


class GoogleMeetBrowserManualActionError(Exception):
    """Raised when browser automation needs manual user action (login, permission, admission)."""

    def __init__(self, payload: dict[str, Any]) -> None:
        manual_action = payload.get("manualAction") or {}
        reason = manual_action.get("reason", "unknown")
        message = manual_action.get("message", "manual action required")
        super().__init__(f"{reason}: {message}")
        self.payload: dict[str, Any] = {
            "source": "browser",
            "error": str(self),
            **payload,
        }


def is_google_meet_browser_manual_action_error(error: Any) -> bool:
    """Check if error is a GoogleMeetBrowserManualActionError instance."""
    return isinstance(error, GoogleMeetBrowserManualActionError)
