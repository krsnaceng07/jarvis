"""Diffs Language Pack extension root entrypoint."""

from __future__ import annotations

from .plugin import DiffsLanguagePackPlugin, entry, diffs_language_pack_plugin

__all__ = [
    "DiffsLanguagePackPlugin",
    "diffs_language_pack_plugin",
    "entry",
]
