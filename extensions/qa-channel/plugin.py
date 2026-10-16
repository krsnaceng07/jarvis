"""QA Channel channel plugin definition.

OpenClaw parity: mirrors the OpenClaw ``qa-channel`` channel
extension (31 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin
from jarvis_normalization_core.result import Ok

from .runtime import enqueue_qa_channel_message, get_qa_channel_runtime


@dataclass(frozen=True, slots=True)
class QAChannelPlugin(ChannelPlugin):
    """QA Channel channel descriptor."""

    id: str = "qa-channel"
    name: str = "QA Channel"
    kind: str = "channel"
    base_url: str = "ws://localhost:7777"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel init hook (auth + connection)."""
        runtime = get_qa_channel_runtime()
        if runtime is None:
            from .runtime import QAChannelRuntime, set_qa_channel_runtime

            set_qa_channel_runtime(QAChannelRuntime(started=True))

    def send(self, target: str, message: Any):  # type: ignore[override]
        """Queue a synthetic QA message for the target."""
        payload = message if isinstance(message, dict) else {"text": str(message)}
        result = enqueue_qa_channel_message(target, payload, direction="outbound")
        if result is None:
            return Ok({"target": target, "message": payload, "queued": False})
        return Ok({"target": result["target"], "message": result["message"], "queued": True})

    def listen(self, callback: Any) -> None:  # type: ignore[override]
        """Emit queued QA messages to the callback when present."""
        if callback is None:
            return None
        runtime = get_qa_channel_runtime()
        if runtime is None:
            return None
        for entry in list(runtime.messages):
            callback(entry)
        return None


qa_channel_plugin = QAChannelPlugin()
entry = qa_channel_plugin
