"""jarvis.config.markdown_tables_types — markdown table resolver param types.

OpenClaw parity: mirrors
``openclaw-main/src/config/markdown-tables.types.ts``.
"""
from __future__ import annotations

from typing import Callable, TypedDict

#: Markdown table rendering mode.
MarkdownTableMode = str  # "off" | "bullets" | "code" | "block"


class ResolveMarkdownTableModeParams(TypedDict, total=False):
    """Parameters for resolving markdown table rendering per config + channel."""

    cfg: dict
    channel: str
    accountId: str
    supportsBlockTables: bool


#: Resolver signature for markdown table mode.
ResolveMarkdownTableMode = Callable[[ResolveMarkdownTableModeParams], str]


__all__ = [
    "MarkdownTableMode",
    "ResolveMarkdownTableModeParams",
    "ResolveMarkdownTableMode",
]
