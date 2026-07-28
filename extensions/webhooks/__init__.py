"""JARVIS Webhooks infra extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import WebhooksPlugin, webhooks_plugin, entry

__all__ = [
    "WebhooksPlugin",
    "webhooks_plugin",
    "entry",
]
