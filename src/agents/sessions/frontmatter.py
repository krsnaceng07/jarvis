"""jarvis.agents.sessions.frontmatter — YAML front-matter helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/utils/frontmatter.ts``.

Public surface (matches the OpenClaw
source):

- :func:`parse_frontmatter` —
  parse optional YAML front-matter
  from a markdown-style content
  string. Returns
  ``{"frontmatter": dict, "body":
  str}``. Mirrors
  :func:`parseFrontmatter`
  (``frontmatter.ts:20-30``).
- :func:`strip_frontmatter` —
  remove the leading YAML
  front-matter block + return the
  body. Mirrors
  :func:`stripFrontmatter`
  (``frontmatter.ts:33``).

Phase 6.13b — focused port.

Adaptations
-----------
- The OpenClaw source uses
  ``yaml.parse`` from the ``yaml``
  package + a
  :func:`extractFrontmatterBlock`
  helper from
  ``@openclaw/markdown-core``.
  The Python port uses the
  ``PyYAML`` library (when
  available) + a focused minimal
  front-matter extractor. When
  PyYAML isn't installed, the
  port falls back to a no-op
  parser that returns the input
  unchanged (matches the
  pre-6.13b STUB behaviour).
"""
from __future__ import annotations

import re
from typing import Any, TypedDict


class _ParsedFrontmatter(TypedDict, total=False):
    frontmatter: dict
    body: str


#: Pre-compiled regex matching a
#: leading ``---\\n...\\n---\\n`` block
#: (the OpenClaw source uses
#: :func:`extractFrontmatterBlock`
#: which is more permissive; the
#: Python port uses a focused regex
#: that handles the common case).
_FRONTMATTER_RE = re.compile(
    r"\A---\r?\n(?P<block>.*?)\r?\n---\r?\n(?P<body>.*)",
    re.DOTALL,
)


def _try_import_yaml() -> Any:
    """Try to import :mod:`yaml`. Returns
    the module on success, ``None``
    on :class:`ImportError`."""
    try:
        import yaml  # type: ignore[import-not-found]
        return yaml
    except ImportError:
        return None


_YAML = _try_import_yaml()


def _normalize_newlines(value: str) -> str:
    """Normalize ``\\r\\n`` + ``\\r`` to
    ``\\n``. Mirrors the OpenClaw
    source's :func:`normalizeNewlines`
    (``frontmatter.ts:16-17``)."""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def parse_frontmatter(
    content: str,
) -> _ParsedFrontmatter:
    """Parse optional YAML front-matter
    from ``content`` (a markdown-style
    string). Returns a dict with
    ``frontmatter`` (parsed YAML,
    default ``{}``) + ``body`` (the
    remaining content, with the
    leading ``---\\n...\\n---\\n``
    block removed + the body
    trimmed).

    Mirrors :func:`parseFrontmatter`
    (``frontmatter.ts:20-30``).
    """
    normalized = _normalize_newlines(content)
    match = _FRONTMATTER_RE.match(normalized)
    if not match:
        return {"frontmatter": {}, "body": normalized}
    block = match.group("block")
    body = match.group("body").strip("\n")
    if _YAML is not None:
        try:
            parsed = _YAML.safe_load(block)
        except Exception:
            parsed = None
    else:
        parsed = None
    frontmatter = parsed if isinstance(parsed, dict) else {}
    return {"frontmatter": frontmatter, "body": body}


def strip_frontmatter(content: str) -> str:
    """Remove the leading YAML
    front-matter block from
    ``content`` + return the rest.
    Mirrors :func:`stripFrontmatter`
    (``frontmatter.ts:33``)."""
    return parse_frontmatter(content)["body"]


# ============================================================================
# Backwards-compat alias (camelCase
# OpenClaw-style name).
# ============================================================================


stripFrontmatter = strip_frontmatter
parseFrontmatter = parse_frontmatter


__all__ = [
    "parse_frontmatter",
    "parseFrontmatter",
    "strip_frontmatter",
    "stripFrontmatter",
]
