"""JARVIS Admin HTTP RPC infra extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import AdminHTTPRPCPlugin, admin_http_rpc_plugin, entry

__all__ = [
    "AdminHTTPRPCPlugin",
    "admin_http_rpc_plugin",
    "entry",
]
