"""QA Channel runtime singleton + in-memory message queue.

OpenClaw parity: mirrors the QA transport runtime used by the channel-shaped
live QA harness. It keeps a process-local queue of messages as an observable,
testable state object instead of a pure no-op stub.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, TypedDict


class QAChannelMessage(TypedDict, total=False):
    """Normalized message shape emitted by the QA channel."""

    target: str
    message: dict[str, Any]
    direction: str
    received_at_ms: int


@dataclass
class QAChannelRuntime:
    started: bool = False
    last_message_at_ms: int = 0
    target_count: int = 0
    messages: list[QAChannelMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def record_message(
        self, target: str, message: dict[str, Any], *, direction: str = "inbound"
    ) -> QAChannelMessage:
        payload: QAChannelMessage = {
            "target": target,
            "message": message,
            "direction": direction,
            "received_at_ms": int(time.time() * 1000),
        }
        self.messages.append(payload)
        self.target_count = max(self.target_count, len(self.messages))
        self.last_message_at_ms = payload["received_at_ms"]
        return payload


_RUNTIME_LOCK = threading.Lock()
_RUNTIME: QAChannelRuntime | None = None


def set_qa_channel_runtime(runtime: QAChannelRuntime) -> None:
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = runtime


def get_qa_channel_runtime() -> QAChannelRuntime | None:
    with _RUNTIME_LOCK:
        return _RUNTIME


def reset_qa_channel_runtime() -> None:
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = None


def enqueue_qa_channel_message(
    target: str, message: dict[str, Any], *, direction: str = "inbound"
) -> QAChannelMessage | None:
    runtime = get_qa_channel_runtime()
    if runtime is None:
        runtime = QAChannelRuntime(started=True)
        set_qa_channel_runtime(runtime)
    return runtime.record_message(target, message, direction=direction)


def read_qa_channel_messages() -> list[QAChannelMessage]:
    runtime = get_qa_channel_runtime()
    if runtime is None:
        return []
    return list(runtime.messages)


def clear_qa_channel_messages() -> None:
    runtime = get_qa_channel_runtime()
    if runtime is not None:
        runtime.messages.clear()
        runtime.target_count = 0
        runtime.last_message_at_ms = 0


__all__ = [
    "QAChannelMessage",
    "QAChannelRuntime",
    "clear_qa_channel_messages",
    "enqueue_qa_channel_message",
    "get_qa_channel_runtime",
    "read_qa_channel_messages",
    "reset_qa_channel_runtime",
    "set_qa_channel_runtime",
]
