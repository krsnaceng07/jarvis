"""JARVIS Feishu channel extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import FeishuPlugin, feishu_plugin, entry
from .runtime import FeishuRuntime, get_feishu_runtime

__all__ = [
    "FeishuPlugin",
    "feishu_plugin",
    "entry",
    "FeishuRuntime",
    "get_feishu_runtime",
]
