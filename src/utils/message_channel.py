"""jarvis.utils.message_channel — message channel and Gateway client classification.

OpenClaw parity: mirrors ``openclaw-main/src/utils/message-channel.ts``.

Public surface:

- :data:`INTERNAL_MESSAGE_CHANNEL`
- :data:`GATEWAY_CLIENT_NAMES`
- :data:`GATEWAY_CLIENT_MODES`
- :func:`is_gateway_cli_client`
- :func:`is_ephemeral_gateway_client`
- :func:`is_operator_ui_client`
- :func:`is_browser_operator_ui_client`
- :func:`is_browser_copilot_client`
- :func:`is_internal_message_channel`
- :func:`is_native_approval_channel`
- :func:`is_webchat_client`
- :func:`is_markdown_capable_message_channel`
- :func:`is_deliverable_message_channel`
- :func:`is_gateway_message_channel`
- :func:`list_deliverable_message_channels`
- :func:`normalize_message_channel`
- :func:`resolve_gateway_message_channel`
- :func:`resolve_message_channel`

Phase 8.1 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .message_channel_constants import (  # noqa: F401
    INTERNAL_MESSAGE_CHANNEL,
    INTERNAL_NON_DELIVERY_CHANNELS,
    internal_session_conversation_id,
    is_internal_non_delivery_channel,
)
from .message_channel_normalize import (  # noqa: F401
    is_deliverable_message_channel,
    is_gateway_message_channel,
    list_deliverable_message_channels,
    normalize_message_channel,
    resolve_gateway_message_channel,
    resolve_message_channel,
)


# Installable hooks ---------------------------------------------------------

GATEWAY_CLIENT_NAMES: Dict[str, str] = {
    "CLI": "cli",
    "WEBCHAT_UI": "webchat-ui",
    "TUI": "tui",
    "BROWSER_COPILOT": "browser-copilot",
    "CONTROL_UI": "control-ui",
}
GATEWAY_CLIENT_MODES: Dict[str, str] = {
    "CLI": "cli",
    "WEBCHAT": "webchat",
    "BACKEND": "backend",
    "PROBE": "probe",
}


def _normalize_mode(value: Any) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip().lower()
        return cleaned or None
    return None


def _normalize_id(value: Any) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip().lower()
        return cleaned or None
    return None


def is_gateway_cli_client(client: Any = None) -> bool:
    """Return whether a Gateway client is the CLI transport.

    Mirrors :func:`isGatewayCliClient` (``utils/message-channel.ts``).
    """
    return _normalize_mode((client or {}).get("mode") if isinstance(client, dict) else None) == GATEWAY_CLIENT_MODES["CLI"]


def is_ephemeral_gateway_client(client: Any = None) -> bool:
    """Return whether a Gateway client is an ephemeral control-plane connection.

    Mirrors :func:`isEphemeralGatewayClient` (``utils/message-channel.ts``).
    """
    mode = _normalize_mode((client or {}).get("mode") if isinstance(client, dict) else None)
    return mode in (
        GATEWAY_CLIENT_MODES["CLI"],
        GATEWAY_CLIENT_MODES["BACKEND"],
        GATEWAY_CLIENT_MODES["PROBE"],
    )


def is_operator_ui_client(client: Any = None) -> bool:
    """Return whether a client is one of the operator UI clients.

    Mirrors :func:`isOperatorUiClient` (``utils/message-channel.ts``).
    """
    client_id = _normalize_id((client or {}).get("id") if isinstance(client, dict) else None)
    return client_id in (
        GATEWAY_CLIENT_NAMES["CONTROL_UI"],
        GATEWAY_CLIENT_NAMES["BROWSER_COPILOT"],
        GATEWAY_CLIENT_NAMES["TUI"],
    )


def is_browser_operator_ui_client(client: Any = None) -> bool:
    """Return whether a client is the browser Control UI.

    Mirrors :func:`isBrowserOperatorUiClient` (``utils/message-channel.ts``).
    """
    client_id = _normalize_id((client or {}).get("id") if isinstance(client, dict) else None)
    return client_id in (
        GATEWAY_CLIENT_NAMES["CONTROL_UI"],
        GATEWAY_CLIENT_NAMES["BROWSER_COPILOT"],
    )


def is_browser_copilot_client(client: Any = None) -> bool:
    """Return whether a client is the first-party browser side-panel copilot.

    Mirrors :func:`isBrowserCopilotClient` (``utils/message-channel.ts``).
    """
    client_id = _normalize_id((client or {}).get("id") if isinstance(client, dict) else None)
    return client_id == GATEWAY_CLIENT_NAMES["BROWSER_COPILOT"]


def is_internal_message_channel(raw: Any = None) -> bool:
    """Return whether a raw channel id resolves to OpenClaw's internal channel.

    Mirrors :func:`isInternalMessageChannel` (``utils/message-channel.ts``).
    """
    return normalize_message_channel(raw) == INTERNAL_MESSAGE_CHANNEL


def is_native_approval_channel(value: Any = None) -> bool:
    """Return whether a channel can resolve exec approvals in the originating chat.

    Mirrors :func:`isNativeApprovalChannel` (``utils/message-channel.ts``).
    """
    if not value:
        return False
    if value == INTERNAL_MESSAGE_CHANNEL:
        return True
    # Bundled channel catalog lookup — installable hook for full parity.
    return False


def is_webchat_client(client: Any = None) -> bool:
    """Return whether a Gateway client is the public webchat surface.

    Mirrors :func:`isWebchatClient` (``utils/message-channel.ts``).
    """
    mode = _normalize_mode((client or {}).get("mode") if isinstance(client, dict) else None)
    if mode == GATEWAY_CLIENT_MODES["WEBCHAT"]:
        return True
    return _normalize_id((client or {}).get("id") if isinstance(client, dict) else None) == GATEWAY_CLIENT_NAMES["WEBCHAT_UI"]


def is_markdown_capable_message_channel(raw: Any = None) -> bool:
    """Resolve whether a channel can receive markdown without plain-text downgrade.

    Mirrors :func:`isMarkdownCapableMessageChannel` (``utils/message-channel.ts``).
    """
    channel = normalize_message_channel(raw)
    if not channel:
        return False
    if channel == INTERNAL_MESSAGE_CHANNEL or channel == "tui":
        return True
    return False


__all__ = [
    "INTERNAL_MESSAGE_CHANNEL",
    "GATEWAY_CLIENT_NAMES",
    "GATEWAY_CLIENT_MODES",
    "is_gateway_cli_client",
    "is_ephemeral_gateway_client",
    "is_operator_ui_client",
    "is_browser_operator_ui_client",
    "is_browser_copilot_client",
    "is_internal_message_channel",
    "is_native_approval_channel",
    "is_webchat_client",
    "is_markdown_capable_message_channel",
    "is_deliverable_message_channel",
    "is_gateway_message_channel",
    "list_deliverable_message_channels",
    "normalize_message_channel",
    "resolve_gateway_message_channel",
    "resolve_message_channel",
]
