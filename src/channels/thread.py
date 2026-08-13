"""Thread routing context — mirrors OpenClaw ``src/channels/thread-*.ts``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ThreadContext:
    channel_id: str
    thread_id: str | None
    is_group: bool = False
    parent_msg_id: str | None = None


def resolve_thread_id(raw_message: dict[str, Any]) -> str | None:
    """Extract thread / topic ID from channel message payload."""
    if not isinstance(raw_message, dict):
        return None

    # Telegram message_thread_id / topic
    thread_id = raw_message.get("message_thread_id") or raw_message.get("thread_id")
    if thread_id:
        return str(thread_id)

    # Discord / Slack thread_ts / channel topic
    ts = raw_message.get("thread_ts") or raw_message.get("parent_id")
    if ts:
        return str(ts)

    return None


def thread_reply_target(context: ThreadContext) -> dict[str, Any]:
    """Build kwargs for channel send function targeting thread context."""
    target: dict[str, Any] = {"channel_id": context.channel_id}
    if context.thread_id:
        target["thread_id"] = context.thread_id
    if context.parent_msg_id:
        target["reply_to_message_id"] = context.parent_msg_id
    return target


__all__ = ["ThreadContext", "resolve_thread_id", "thread_reply_target"]
