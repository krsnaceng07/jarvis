"""JARVIS Slack channel extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import SlackPlugin, slack_plugin, entry
from .runtime import SlackRuntime, get_slack_runtime

__all__ = [
    "SlackPlugin",
    "slack_plugin",
    "entry",
    "SlackRuntime",
    "get_slack_runtime",
]
