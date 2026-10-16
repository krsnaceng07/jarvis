"""jarvis.utils.delivery_context.shared — delivery context normalization helpers.

OpenClaw parity: mirrors
``openclaw-main/src/utils/delivery-context.shared.ts``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .types import DeliveryContext

#: Internal webchat channel id (mirrors OpenClaw's INTERNAL_MESSAGE_CHANNEL).
INTERNAL_MESSAGE_CHANNEL = "webchat"

#: Internal, non-delivery source channels.
INTERNAL_NON_DELIVERY_CHANNELS = ("heartbeat", "cron", "webhook", "voice", "sessions_send")


# Installable hooks ---------------------------------------------------------

_normalize_delivery_context_hook = None
_merge_delivery_context_hook = None
_delivery_context_from_session_hook = None
_delivery_context_key_hook = None
_normalize_delivery_channel_route_hook = None
_normalize_session_delivery_fields_hook = None


def set_normalize_delivery_context_hook(fn) -> None:
    global _normalize_delivery_context_hook
    _normalize_delivery_context_hook = fn


def set_merge_delivery_context_hook(fn) -> None:
    global _merge_delivery_context_hook
    _merge_delivery_context_hook = fn


def set_delivery_context_from_session_hook(fn) -> None:
    global _delivery_context_from_session_hook
    _delivery_context_from_session_hook = fn


def set_delivery_context_key_hook(fn) -> None:
    global _delivery_context_key_hook
    _delivery_context_key_hook = fn


def set_normalize_delivery_channel_route_hook(fn) -> None:
    global _normalize_delivery_channel_route_hook
    _normalize_delivery_channel_route_hook = fn


def set_normalize_session_delivery_fields_hook(fn) -> None:
    global _normalize_session_delivery_fields_hook
    _normalize_session_delivery_fields_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _normalize_channel(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip().lower()
    return cleaned or None


def _normalize_to(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    return cleaned or None


def _normalize_account_id(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    return cleaned or None


def normalize_delivery_context(
    context: Any = None,
) -> Optional[Dict[str, Any]]:
    """Normalize a delivery context into canonical channel-route fields.

    Mirrors :func:`normalizeDeliveryContext`
    (``utils/delivery-context.shared.ts``).
    """
    if _normalize_delivery_context_hook is not None:
        v = _normalize_delivery_context_hook(context)
        return v if v is None or isinstance(v, dict) else None
    if not context:
        return None
    if isinstance(context, DeliveryContext):
        context = context.to_dict()
    if not isinstance(context, dict):
        return None
    channel = _normalize_channel(context.get("channel"))
    to = _normalize_to(context.get("to"))
    account_id = _normalize_account_id(context.get("accountId") or context.get("account_id"))
    thread_id = context.get("threadId") or context.get("thread_id")
    if channel is None and to is None and account_id is None:
        return None
    out: Dict[str, Any] = {}
    if channel is not None:
        out["channel"] = channel
    if to is not None:
        out["to"] = to
    if account_id is not None:
        out["accountId"] = account_id
    if thread_id is not None:
        out["threadId"] = thread_id
    delivery_intent = context.get("deliveryIntent") or context.get("delivery_intent")
    if isinstance(delivery_intent, dict):
        out["deliveryIntent"] = delivery_intent
    return out


def normalize_delivery_channel_route(route: Any = None) -> Optional[Dict[str, Any]]:
    """Normalize an unknown channel route payload from persisted session/plugin metadata.

    Mirrors :func:`normalizeDeliveryChannelRoute`
    (``utils/delivery-context.shared.ts``).
    """
    if _normalize_delivery_channel_route_hook is not None:
        v = _normalize_delivery_channel_route_hook(route)
        return v
    if not route or not isinstance(route, dict):
        return None
    target = route.get("target") if isinstance(route.get("target"), dict) else {}
    out: Dict[str, Any] = {
        "channel": _normalize_channel(route.get("channel")),
        "accountId": _normalize_account_id(route.get("accountId")),
    }
    if target.get("to") is not None:
        out["to"] = target.get("to")
    thread = route.get("thread") if isinstance(route.get("thread"), dict) else None
    if thread is not None and thread.get("id") is not None:
        out["threadId"] = thread.get("id")
    return out


def delivery_context_from_channel_route(
    route: Any = None,
) -> Optional[Dict[str, Any]]:
    """Convert a normalized channel route reference into a delivery context.

    Mirrors :func:`deliveryContextFromChannelRoute`
    (``utils/delivery-context.shared.ts``).
    """
    normalized = normalize_delivery_channel_route(route)
    return normalize_delivery_context(
        {
            "channel": (normalized or {}).get("channel"),
            "to": (normalized or {}).get("to"),
            "accountId": (normalized or {}).get("accountId"),
            "threadId": (normalized or {}).get("threadId"),
        }
    )


def merge_delivery_context(
    primary: Any = None,
    fallback: Any = None,
) -> Optional[Dict[str, Any]]:
    """Merge delivery contexts without mixing target/account/thread fields.

    Mirrors :func:`mergeDeliveryContext`
    (``utils/delivery-context.shared.ts``).
    """
    if _merge_delivery_context_hook is not None:
        v = _merge_delivery_context_hook({"primary": primary, "fallback": fallback})
        return v
    p = normalize_delivery_context(primary)
    f = normalize_delivery_context(fallback)
    if not p and not f:
        return None
    channels_conflict = bool(
        p and f and p.get("channel") and f.get("channel") and p["channel"] != f["channel"]
    )
    accounts_conflict = bool(
        p and f
        and p.get("accountId")
        and f.get("accountId")
        and p["accountId"] != f["accountId"]
    )
    routes_conflict = channels_conflict or accounts_conflict
    primary_channel = p.get("channel") if p else None
    fallback_channel = f.get("channel") if f else None
    primary_to = p.get("to") if p else None
    fallback_to = f.get("to") if f else None
    primary_account = p.get("accountId") if p else None
    fallback_account = f.get("accountId") if f else None
    primary_thread = p.get("threadId") if p else None
    fallback_thread = f.get("threadId") if f else None
    if routes_conflict:
        return normalize_delivery_context(
            {
                "channel": primary_channel,
                "to": primary_to,
                "accountId": primary_account,
                "threadId": primary_thread,
            }
        )
    return normalize_delivery_context(
        {
            "channel": primary_channel or fallback_channel,
            "to": primary_to or fallback_to,
            "accountId": primary_account or fallback_account,
            "threadId": primary_thread or fallback_thread,
        }
    )


def normalize_session_delivery_fields(
    source: Any = None,
) -> Dict[str, Any]:
    """Reconcile legacy session delivery fields, route metadata, and explicit delivery context.

    Mirrors :func:`normalizeSessionDeliveryFields`
    (``utils/delivery-context.shared.ts``).
    """
    if _normalize_session_delivery_fields_hook is not None:
        v = _normalize_session_delivery_fields_hook(source)
        return v if isinstance(v, dict) else {}
    empty = {
        "route": None,
        "deliveryContext": None,
        "lastChannel": None,
        "lastTo": None,
        "lastAccountId": None,
        "lastThreadId": None,
    }
    if not source or not isinstance(source, dict):
        return empty
    legacy = normalize_delivery_context(
        {
            "channel": source.get("lastChannel") or source.get("channel"),
            "to": source.get("lastTo"),
            "accountId": source.get("lastAccountId"),
            "threadId": source.get("lastThreadId"),
        }
    )
    delivery = normalize_delivery_context(source.get("deliveryContext"))
    merged = merge_delivery_context(legacy, delivery)
    if not merged:
        return empty
    return {
        "route": normalize_delivery_channel_route(source.get("route")),
        "deliveryContext": merged,
        "lastChannel": merged.get("channel"),
        "lastTo": merged.get("to"),
        "lastAccountId": merged.get("accountId"),
        "lastThreadId": merged.get("threadId"),
    }


def delivery_context_from_session(
    entry: Any = None,
) -> Optional[Dict[str, Any]]:
    """Derive the best delivery context from current and legacy session fields.

    Mirrors :func:`deliveryContextFromSession`
    (``utils/delivery-context.shared.ts``).
    """
    if _delivery_context_from_session_hook is not None:
        v = _delivery_context_from_session_hook(entry)
        return v
    if not entry or not isinstance(entry, dict):
        return None
    origin = entry.get("origin") if isinstance(entry.get("origin"), dict) else {}
    source = {
        "route": entry.get("route"),
        "channel": entry.get("channel") or origin.get("provider"),
        "lastChannel": entry.get("lastChannel"),
        "lastTo": entry.get("lastTo"),
        "lastAccountId": entry.get("lastAccountId") or origin.get("accountId"),
        "lastThreadId": entry.get("lastThreadId")
        or (entry.get("deliveryContext") or {}).get("threadId")
        or origin.get("threadId"),
        "deliveryContext": entry.get("deliveryContext"),
    }
    return normalize_session_delivery_fields(source).get("deliveryContext")


def delivery_context_key(context: Any = None) -> Optional[str]:
    """Build a compact stable key for a routable delivery context.

    Mirrors :func:`deliveryContextKey`
    (``utils/delivery-context.shared.ts``).
    """
    if _delivery_context_key_hook is not None:
        v = _delivery_context_key_hook(context)
        return v
    normalized = normalize_delivery_context(context)
    if not normalized:
        return None
    parts = [
        normalized.get("channel") or "",
        normalized.get("accountId") or "",
        normalized.get("to") or "",
        str(normalized.get("threadId") or ""),
    ]
    return "|".join(parts)


__all__ = [
    "INTERNAL_MESSAGE_CHANNEL",
    "INTERNAL_NON_DELIVERY_CHANNELS",
    "normalize_delivery_context",
    "normalize_delivery_channel_route",
    "delivery_context_from_channel_route",
    "merge_delivery_context",
    "normalize_session_delivery_fields",
    "delivery_context_from_session",
    "delivery_context_key",
    "set_normalize_delivery_context_hook",
    "set_merge_delivery_context_hook",
    "set_delivery_context_from_session_hook",
    "set_delivery_context_key_hook",
    "set_normalize_delivery_channel_route_hook",
    "set_normalize_session_delivery_fields_hook",
]
