"""JARVIS WhatsApp channel extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import WhatsAppPlugin, whatsapp_plugin, entry
from .runtime import WhatsAppRuntime, get_whatsapp_runtime

__all__ = [
    "WhatsAppPlugin",
    "whatsapp_plugin",
    "entry",
    "WhatsAppRuntime",
    "get_whatsapp_runtime",
]
