"""jarvis.shared.thread_binding_lifecycle — channel thread binding lifecycle.

OpenClaw parity: mirrors
``openclaw-main/src/shared/thread-binding-lifecycle.ts``.

Public surface:

- :func:`resolve_thread_binding_lifecycle`
- :class:`ThreadBindingLifecycleRecord`
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional


class ThreadBindingLifecycleRecord:
    """Persisted timestamps and optional TTL overrides for one channel thread binding."""

    def __init__(
        self,
        bound_at: int,
        last_activity_at: int,
        idle_timeout_ms: Optional[int] = None,
        max_age_ms: Optional[int] = None,
    ) -> None:
        self.bound_at = int(bound_at)
        self.last_activity_at = int(last_activity_at)
        self.idle_timeout_ms = idle_timeout_ms
        self.max_age_ms = max_age_ms

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "boundAt": self.bound_at,
            "lastActivityAt": self.last_activity_at,
        }
        if self.idle_timeout_ms is not None:
            out["idleTimeoutMs"] = self.idle_timeout_ms
        if self.max_age_ms is not None:
            out["maxAgeMs"] = self.max_age_ms
        return out


def resolve_thread_binding_lifecycle(params: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve the next expiration for a channel thread binding.

    Mirrors :func:`resolveThreadBindingLifecycle` (``shared/thread-binding-lifecycle.ts``).
    """
    record = params.get("record")
    if not isinstance(record, dict):
        return {}
    bound_at = int(record.get("boundAt", 0) or 0)
    last_activity = int(record.get("lastActivityAt", bound_at) or bound_at)
    idle_raw = record.get("idleTimeoutMs")
    idle_timeout_ms = (
        max(0, math.floor(idle_raw)) if isinstance(idle_raw, (int, float)) and not isinstance(idle_raw, bool)
        else params.get("defaultIdleTimeoutMs", 0)
    )
    max_raw = record.get("maxAgeMs")
    max_age_ms = (
        max(0, math.floor(max_raw)) if isinstance(max_raw, (int, float)) and not isinstance(max_raw, bool)
        else params.get("defaultMaxAgeMs", 0)
    )
    inactivity_expires_at = (
        max(last_activity, bound_at) + idle_timeout_ms
        if idle_timeout_ms and idle_timeout_ms > 0
        else None
    )
    max_age_expires_at = (
        bound_at + max_age_ms if max_age_ms and max_age_ms > 0 else None
    )
    if inactivity_expires_at is not None and max_age_expires_at is not None:
        if inactivity_expires_at <= max_age_expires_at:
            return {"expiresAt": inactivity_expires_at, "reason": "idle-expired"}
        return {"expiresAt": max_age_expires_at, "reason": "max-age-expired"}
    if inactivity_expires_at is not None:
        return {"expiresAt": inactivity_expires_at, "reason": "idle-expired"}
    if max_age_expires_at is not None:
        return {"expiresAt": max_age_expires_at, "reason": "max-age-expired"}
    return {}


__all__ = [
    "ThreadBindingLifecycleRecord",
    "resolve_thread_binding_lifecycle",
]
