"""JARVIS SMS channel extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import SMSPlugin, sms_plugin, entry
from .runtime import SMSRuntime, get_sms_runtime

__all__ = [
    "SMSPlugin",
    "sms_plugin",
    "entry",
    "SMSRuntime",
    "get_sms_runtime",
]
