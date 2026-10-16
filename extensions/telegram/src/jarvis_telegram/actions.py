from __future__ import annotations

from typing import Any


def build_approval_keyboard(approval_id: str) -> dict[str, Any]:
    """Build an inline keyboard for an execution approval.

    The callback_data must be less than 64 bytes for Telegram.
    We'll encode action and id compactly.
    """
    # callback_data max 64 bytes. Let's use a compact JSON or simple delimited string.
    # e.g., "apr:grant:<id>" or "apr:deny:<id>"
    # If approval_id is too long, we might need a local mapping, but for Phase 4 we assume it fits.

    grant_data = f"apr:grant:{approval_id}"
    deny_data = f"apr:deny:{approval_id}"

    # Trim to 64 bytes if needed, but normally IDs from JARVIS fit (UUIDs are 36 chars)
    if len(grant_data) > 64:
        grant_data = grant_data[:64]
    if len(deny_data) > 64:
        deny_data = deny_data[:64]

    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": grant_data},
                {"text": "❌ Deny", "callback_data": deny_data},
            ]
        ]
    }


def parse_callback_query(callback_data: str) -> dict[str, str] | None:
    """Parse a callback query string back into an action and payload.

    Expected format: "apr:<action>:<id>"
    """
    parts = callback_data.split(":", 2)
    if len(parts) == 3 and parts[0] == "apr":
        return {
            "action": parts[1],  # "grant" or "deny"
            "approval_id": parts[2],
        }
    return None
