"""jarvis.utils.delivery_context — delivery-context re-exports.

OpenClaw parity: mirrors ``openclaw-main/src/utils/delivery-context.ts``.

Public surface: re-exports from :mod:`src.utils.delivery_context.shared`.
"""
from __future__ import annotations

from .delivery_context.shared import (  # noqa: F401
    delivery_context_from_session,
    delivery_context_key,
    merge_delivery_context,
    normalize_delivery_context,
)
from .delivery_context.types import DeliveryContext  # noqa: F401


__all__ = [
    "DeliveryContext",
    "delivery_context_from_session",
    "delivery_context_key",
    "merge_delivery_context",
    "normalize_delivery_context",
]
