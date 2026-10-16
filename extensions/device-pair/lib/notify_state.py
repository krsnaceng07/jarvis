"""Device Pair notify state helpers.

Mirrors OpenClaw's ``extensions/device-pair/notify-state.ts``.

Public surface (mirrors the TS source):
- ``DEVICE_PAIR_NOTIFY_LEGACY_STATE_FILE`` —
  ``"device-pair-notify.json"``
- ``DEVICE_PAIR_NOTIFY_SUBSCRIBER_NAMESPACE`` —
  ``"notify-subscribers"``
- ``DEVICE_PAIR_NOTIFY_SEEN_REQUEST_NAMESPACE`` —
  ``"notify-seen-requests"``
- ``DEVICE_PAIR_NOTIFY_SUBSCRIBER_MAX_ENTRIES`` = 1024
- ``DEVICE_PAIR_NOTIFY_SEEN_REQUEST_MAX_ENTRIES`` = 4096
- ``DEVICE_PAIR_NOTIFY_MAX_SEEN_AGE_MS`` = 24 hours
- ``NotifySubscription`` / ``NotifySeenRequest`` /
  ``LegacyNotifyStateFile`` TypedDicts
- ``normalizeLegacyNotifyState`` — normalize the legacy
  on-disk state file
- ``notifySubscriberKey`` / ``notifySubscriberStoreKey`` /
  ``notifyRequestStoreKey`` — stable string keys

Python adaptations (documented in code):
- TS crypto.createHash → Python hashlib.sha256
- TS ``Map`` / ``Set`` shapes → Python ``dict`` /
  ``set`` (membership only)
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal, TypedDict, Union

from jarvis_normalization_core.string_coerce import normalize_optional_string


# Public constants (mirrors the TS source).
DEVICE_PAIR_NOTIFY_LEGACY_STATE_FILE = "device-pair-notify.json"
DEVICE_PAIR_NOTIFY_SUBSCRIBER_NAMESPACE = "notify-subscribers"
DEVICE_PAIR_NOTIFY_SEEN_REQUEST_NAMESPACE = "notify-seen-requests"
DEVICE_PAIR_NOTIFY_SUBSCRIBER_MAX_ENTRIES = 1024
DEVICE_PAIR_NOTIFY_SEEN_REQUEST_MAX_ENTRIES = 4096
DEVICE_PAIR_NOTIFY_MAX_SEEN_AGE_MS = 24 * 60 * 60 * 1000


# ── Types ──────────────────────────────────────────────────


NotifySubscriptionMode = Literal["persistent", "once"]
VALID_NOTIFY_SUBSCRIPTION_MODES: frozenset[str] = frozenset({"persistent", "once"})


class NotifySubscription(TypedDict, total=False):
    to: str
    accountId: str
    messageThreadId: Union[str, int]
    mode: NotifySubscriptionMode
    addedAtMs: int
    """Unique for new arms; absent only on subscriptions imported from legacy state."""
    armId: str


class NotifySeenRequest(TypedDict, total=False):
    requestId: str
    notifiedAtMs: int


class LegacyNotifyStateFile(TypedDict, total=False):
    subscribers: list[NotifySubscription]
    notifiedRequestIds: dict[str, int]


# ── Normalization ────────────────────────────────────────


def _normalize_message_thread_id(value: object) -> Union[str, int, None]:
    """Coerce a messageThreadId to a normalized ``str | int | None``.

    Mirrors the private message-thread-id coercion in the
    TS source. Strings are trimmed; numeric values are
    truncated to an int.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            return int(value)  # type: ignore[return-value]
        except (TypeError, ValueError):
            return None
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        return int(value)
    if isinstance(value, str):
        return value
    return None


def normalize_legacy_notify_state(raw: object) -> LegacyNotifyStateFile:
    """Normalize the legacy on-disk notify state into the public shape.

    Mirrors ``normalizeLegacyNotifyState``. Bad entries
    are dropped; missing fields fall back to safe defaults
    (e.g. ``addedAtMs = Date.now()``, ``mode = "persistent"``).
    """
    root = raw if isinstance(raw, dict) else {}
    subscribers_raw = root.get("subscribers") if isinstance(root, dict) else None
    subscribers_input = subscribers_raw if isinstance(subscribers_raw, list) else []
    notified_raw = root.get("notifiedRequestIds") if isinstance(root, dict) else None
    notified_input: dict = notified_raw if isinstance(notified_raw, dict) else {}

    subscribers: list[NotifySubscription] = []
    for item in subscribers_input:
        if not isinstance(item, dict):
            continue
        to_value = normalize_optional_string(item.get("to"))
        if not to_value:
            continue
        account_id = normalize_optional_string(item.get("accountId")) or None
        message_thread_id = _normalize_message_thread_id(item.get("messageThreadId"))
        mode = "once" if item.get("mode") == "once" else "persistent"
        added_at_ms_raw = item.get("addedAtMs")
        if isinstance(added_at_ms_raw, (int, float)) and not isinstance(added_at_ms_raw, bool):
            try:
                added_at_ms = int(added_at_ms_raw)
            except (TypeError, ValueError):
                added_at_ms = _now_ms()
        else:
            added_at_ms = _now_ms()
        entry: NotifySubscription = {
            "to": to_value,
            "mode": mode,  # type: ignore[typeddict-item]
            "addedAtMs": added_at_ms,
        }
        if account_id:
            entry["accountId"] = account_id
        if message_thread_id is not None:
            entry["messageThreadId"] = message_thread_id
        subscribers.append(entry)

    notified_request_ids: dict[str, int] = {}
    for request_id, ts in notified_input.items():
        normalized_id = normalize_optional_string(request_id)
        if not normalized_id:
            continue
        if not isinstance(ts, (int, float)) or isinstance(ts, bool):
            continue
        try:
            ts_int = int(ts)
        except (TypeError, ValueError):
            continue
        if ts_int <= 0:
            continue
        notified_request_ids[normalized_id] = ts_int

    return {
        "subscribers": subscribers,
        "notifiedRequestIds": notified_request_ids,
    }


def _now_ms() -> int:
    """Current epoch milliseconds (Python doesn't have a built-in)."""
    import time

    return int(time.time() * 1000)


# ── Key builders ────────────────────────────────────────────


def _normalize_notify_thread_key(message_thread_id: object) -> str:
    """Normalize a messageThreadId into a stable key segment.

    Mirrors the private ``normalizeNotifyThreadKey`` helper.
    """
    if isinstance(message_thread_id, bool):
        return ""
    if isinstance(message_thread_id, int):
        return str(int(message_thread_id))
    if not isinstance(message_thread_id, str):
        return ""
    normalized = normalize_optional_string(message_thread_id)
    if not normalized:
        return ""
    if not _is_integer_string(normalized):
        return normalized
    try:
        return str(int(normalized))
    except (TypeError, ValueError):
        return normalized


def _is_integer_string(value: str) -> bool:
    return bool(_INTEGER_RE.match(value))


_INTEGER_RE = re.compile(r"^-?\d+$")


def notify_subscriber_key(
    subscriber: Union[NotifySubscription, dict],
) -> str:
    """Stable key for a subscriber across (to, accountId, messageThreadId).

    Mirrors ``notifySubscriberKey``.
    """
    return json.dumps(
        [
            subscriber.get("to", ""),
            subscriber.get("accountId", "") or "",
            _normalize_notify_thread_key(subscriber.get("messageThreadId")),
        ],
        separators=(",", ":"),
    )


def _hash_store_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def notify_subscriber_store_key(
    subscriber: Union[NotifySubscription, dict],
) -> str:
    """Hashed store key for a subscriber. Mirrors ``notifySubscriberStoreKey``."""
    return _hash_store_key(notify_subscriber_key(subscriber))


def notify_request_store_key(request_id: str) -> str:
    """Hashed store key for a request id. Mirrors ``notifyRequestStoreKey``."""
    return _hash_store_key(request_id)


__all__ = [
    "DEVICE_PAIR_NOTIFY_LEGACY_STATE_FILE",
    "DEVICE_PAIR_NOTIFY_MAX_SEEN_AGE_MS",
    "DEVICE_PAIR_NOTIFY_SEEN_REQUEST_MAX_ENTRIES",
    "DEVICE_PAIR_NOTIFY_SEEN_REQUEST_NAMESPACE",
    "DEVICE_PAIR_NOTIFY_SUBSCRIBER_MAX_ENTRIES",
    "DEVICE_PAIR_NOTIFY_SUBSCRIBER_NAMESPACE",
    "LegacyNotifyStateFile",
    "NotifySeenRequest",
    "NotifySubscription",
    "NotifySubscriptionMode",
    "VALID_NOTIFY_SUBSCRIPTION_MODES",
    "normalize_legacy_notify_state",
    "notify_request_store_key",
    "notify_subscriber_key",
    "notify_subscriber_store_key",
]
