"""Route-Bound Channel Execution Adapter for Track 3.2.

Enforces strict transport reply isolation:
- Outbound responses are bound to their originating ResponseRoute (e.g. Telegram/Discord).
- If the remote channel transport is unavailable or unconfigured, execution fails cleanly.
- NEVER silently redirects or leaks remote channel messages to local Desktop HUD.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any
import uuid

from jarvis_agent.execution.adapters.base import (
    AdapterExecutionOutput,
    BaseExecutionAdapter,
)
from jarvis_agent.execution.sandbox.host_adapter import SandboxContext
from jarvis_agent.orchestration.models.command import ExecutionCommand

logger = logging.getLogger(__name__)


class ChannelAdapter(BaseExecutionAdapter):
    """Execution adapter for route-isolated outbound channel messages."""

    def __init__(self, active_transports: set[str] | None = None) -> None:
        self.active_transports = set(
            active_transports or {"telegram", "discord", "slack", "gateway"}
        )
        self._sent_messages: list[dict[str, Any]] = []

    @property
    def adapter_name(self) -> str:
        return "channels"

    def can_handle(self, capability_id: str) -> bool:
        return capability_id == "channels.send_message"

    def execute(
        self,
        command: ExecutionCommand,
        sandbox_ctx: SandboxContext | None = None,
    ) -> AdapterExecutionOutput:
        args = command.arguments
        content = str(args.get("content", ""))
        channel = str(args.get("channel", "telegram")).lower()
        target_id = str(args.get("target_id", ""))

        if channel not in self.active_transports:
            # Strictly fail closed on unknown or inactive transport; DO NOT fallback to desktop HUD!
            logger.error("Channel transport '%s' is unavailable. Refusing fallback.", channel)
            return AdapterExecutionOutput(
                success=False,
                error_message=f"Channel transport '{channel}' is unavailable or unconfigured. Local HUD fallback forbidden.",
            )

        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        record = {
            "message_id": message_id,
            "channel": channel,
            "target_id": target_id,
            "content_length": len(content),
            "delivered_at_utc": now_str,
        }
        self._sent_messages.append(record)

        return AdapterExecutionOutput(
            success=True,
            output_data={
                "message_id": message_id,
                "channel": channel,
                "target_id": target_id,
                "delivered": True,
            },
            raw_evidence=dict(record),
        )

    def get_sent_messages(self) -> list[dict[str, Any]]:
        """Return history of sent messages for testing verification."""
        return list(self._sent_messages)


__all__ = ["ChannelAdapter"]
