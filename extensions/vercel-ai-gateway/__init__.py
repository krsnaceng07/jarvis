"""JARVIS Vercel AI Gateway provider extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import VercelAIGatewayProvider, vercel_ai_gateway_provider, entry

__all__ = [
    "VercelAIGatewayProvider",
    "vercel_ai_gateway_provider",
    "entry",
]
