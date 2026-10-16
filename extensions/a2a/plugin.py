"""Agent-to-Agent channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Err, Ok, Result

from .src.protocol import create_task_envelope
from .src.client import A2AClient


@dataclass(frozen=True, slots=True)
class A2APlugin(ChannelPlugin):
    """A2A protocol channel descriptor."""

    id: str = "a2a"
    name: str = "Agent-to-Agent"
    kind: str = "channel"
    base_url: str = "http://localhost:7433/a2a"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Dispatch task or message to target agent."""
        endpoint = self.metadata.get("endpoint", self.base_url)
        source_agent = self.metadata.get("agentId", "jarvis-primary")
        client = A2AClient(endpoint=endpoint, api_key=self.metadata.get("apiKey"))

        action = "execute_task"
        payload = {"message": message} if isinstance(message, str) else message
        if isinstance(message, dict) and "action" in message:
            action = message["action"]
            payload = message.get("payload", {})

        envelope = create_task_envelope(
            source_agent=source_agent,
            target_agent=target,
            action=action,
            payload=payload,
        )
        res = client.dispatch_task(envelope)
        if "error" in res:
            return Err(res["error"], code="DISPATCH_FAILED")
        return Ok(res)

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming A2A task envelopes."""
        return None


a2a_plugin = A2APlugin()
entry = a2a_plugin
plugin = a2a_plugin
