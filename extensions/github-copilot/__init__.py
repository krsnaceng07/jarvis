"""JARVIS GitHub Copilot provider extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import GitHubCopilotProvider, github_copilot_provider, entry

__all__ = [
    "GitHubCopilotProvider",
    "github_copilot_provider",
    "entry",
]
