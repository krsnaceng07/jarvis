"""JARVIS Nextcloud Talk channel extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import NextcloudTalkPlugin, nextcloud_talk_plugin, entry
from .runtime import NextcloudTalkRuntime, get_nextcloud_talk_runtime

__all__ = [
    "NextcloudTalkPlugin",
    "nextcloud_talk_plugin",
    "entry",
    "NextcloudTalkRuntime",
    "get_nextcloud_talk_runtime",
]
