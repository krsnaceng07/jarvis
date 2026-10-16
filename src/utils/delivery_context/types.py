"""jarvis.utils.delivery_context.types — delivery context type definitions.

OpenClaw parity: mirrors
``openclaw-main/src/utils/delivery-context.types.ts``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Union


class DeliveryIntentRef:
    """Deferred outbound delivery intent attached to a session or task."""

    def __init__(
        self,
        id: str,
        kind: str = "outbound_queue",
        queue_policy: Optional[str] = None,
    ) -> None:
        self.id = id
        self.kind = kind
        self.queue_policy = queue_policy

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"id": self.id, "kind": self.kind}
        if self.queue_policy is not None:
            out["queuePolicy"] = self.queue_policy
        return out


class DeliveryContext:
    """Canonical channel delivery target shared by sessions, cron, tasks, and plugins."""

    def __init__(
        self,
        channel: Optional[str] = None,
        to: Optional[str] = None,
        account_id: Optional[str] = None,
        thread_id: Optional[Union[str, int]] = None,
        delivery_intent: Optional[DeliveryIntentRef] = None,
    ) -> None:
        self.channel = channel
        self.to = to
        self.account_id = account_id
        self.thread_id = thread_id
        self.delivery_intent = delivery_intent

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.channel is not None:
            out["channel"] = self.channel
        if self.to is not None:
            out["to"] = self.to
        if self.account_id is not None:
            out["accountId"] = self.account_id
        if self.thread_id is not None:
            out["threadId"] = self.thread_id
        if self.delivery_intent is not None:
            out["deliveryIntent"] = self.delivery_intent.to_dict()
        return out


class DeliveryContextSessionSource:
    """Mixed legacy and modern session fields used to reconstruct a delivery context."""

    def __init__(
        self,
        route: Any = None,
        channel: Optional[str] = None,
        last_channel: Optional[str] = None,
        last_to: Optional[str] = None,
        last_account_id: Optional[str] = None,
        last_thread_id: Optional[Union[str, int]] = None,
        origin: Any = None,
        delivery_context: Optional[DeliveryContext] = None,
    ) -> None:
        self.route = route
        self.channel = channel
        self.last_channel = last_channel
        self.last_to = last_to
        self.last_account_id = last_account_id
        self.last_thread_id = last_thread_id
        self.origin = origin
        self.delivery_context = delivery_context


__all__ = ["DeliveryContext", "DeliveryContextSessionSource", "DeliveryIntentRef"]
