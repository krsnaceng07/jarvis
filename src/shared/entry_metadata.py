"""jarvis.shared.entry_metadata — entry emoji/homepage resolvers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/entry-metadata.ts``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict


class _FrontmatterLike(TypedDict, total=False):
    emoji: str
    homepage: str
    website: str
    url: str


class _MetadataLike(TypedDict, total=False):
    emoji: str
    homepage: str


def _normalize_optional_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return None


def resolve_emoji_and_homepage(params: dict) -> dict:
    """Resolve entry emoji/homepage with metadata > frontmatter ordering.

    Mirrors :func:`resolveEmojiAndHomepage` (``shared/entry-metadata.ts``).
    """
    metadata = params.get("metadata") or {}
    frontmatter = params.get("frontmatter") or {}
    emoji = metadata.get("emoji") if isinstance(metadata, dict) else None
    if emoji is None and isinstance(frontmatter, dict):
        emoji = frontmatter.get("emoji")

    homepage_raw: Any = None
    if isinstance(metadata, dict) and metadata.get("homepage"):
        homepage_raw = metadata.get("homepage")
    elif isinstance(frontmatter, dict):
        homepage_raw = (
            frontmatter.get("homepage")
            or frontmatter.get("website")
            or frontmatter.get("url")
        )
    homepage = _normalize_optional_string(homepage_raw)

    out: Dict[str, str] = {}
    if isinstance(emoji, str) and emoji:
        out["emoji"] = emoji
    if homepage:
        out["homepage"] = homepage
    return out


__all__ = ["resolve_emoji_and_homepage"]
