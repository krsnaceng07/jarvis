"""JARVIS 1Password infra extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import _1PasswordPlugin, onepassword_plugin, entry

__all__ = [
    "_1PasswordPlugin",
    "onepassword_plugin",
    "entry",
]
