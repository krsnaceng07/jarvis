"""JARVIS Copilot Proxy provider extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import CopilotProxyProvider, copilot_proxy_provider, entry

__all__ = [
    "CopilotProxyProvider",
    "copilot_proxy_provider",
    "entry",
]
