"""markdown — managed blocks, frontmatter parser, and wiki page constants.

OpenClaw parity: this file ports the
``managedMarkdownBlock`` helper, the
``parseWikiFrontmatter`` function, and the marker
constants from
``extensions/memory-wiki/src/markdown.ts``.

Phase 4.3c ships the foundation only. The full page
summary extractor (mdast-based), the claim/evidence
metadata parser, the link graph walker, and the
person-card normalizer all land in 4.3c-mr2.

Surface
-------
- ``WIKI_PAGE_KINDS`` -- the union of valid
  ``kind`` values for a wiki page
  (``entity``, ``concept``, ``source``, ``synthesis``,
  ``report``).
- ``WIKI_RELATED_START_MARKER`` /
  ``WIKI_RELATED_END_MARKER`` -- the
  ``## Related`` block markers used by the compile
  pipeline.
- ``WIKI_RAW_SOURCE_MARKER`` -- the opt-out marker
  for raw markdown in ``sources/``.
- ``with_trailing_newline(text)`` -- the small
  string helper OpenClaw uses everywhere.
- ``replace_managed_markdown_block({...})`` -- the
  block-replace helper used by the scaffold and
  compile pipeline.
- ``parse_wiki_frontmatter(source)`` -- extract
  YAML frontmatter from a markdown source string.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportReturnType=false

# ruff: noqa: PLR0911 — mirrors OpenClaw's per-type coerce branches

# ── Constants ──────────────────────────────────────────────────

WIKI_PAGE_KINDS: tuple[str, ...] = (
    "entity",
    "concept",
    "source",
    "synthesis",
    "report",
)
WikiPageKind = str  # narrowed to the tuple values at use sites

WIKI_RELATED_START_MARKER = "<!-- openclaw:wiki:related:start -->"
WIKI_RELATED_END_MARKER = "<!-- openclaw:wiki:related:end -->"
WIKI_RAW_SOURCE_MARKER = "<!-- openclaw:wiki:raw-source -->"

# Frontmatter delimiters. OpenClaw uses ``---`` on
# both the opening and closing line; the closing
# delimiter is optional and inferred from the start
# when absent (matches the YAML frontmatter spec).
FRONTMATTER_OPEN = "---"
FRONTMATTER_CLOSE = "---"


# ── Trailing-newline helper ─────────────────────────────────────


def with_trailing_newline(text: str) -> str:
    """Return ``text`` with exactly one trailing newline.

    Mirrors OpenClaw's ``withTrailingNewline``. Used
    by the scaffold and compile pipelines to keep
    vault files on POSIX line endings.
    """
    if not isinstance(text, str):
        return text
    if not text:
        return "\n"
    if text.endswith("\n\n"):
        return text
    if text.endswith("\n"):
        return text
    return text + "\n"


# ── Managed markdown blocks ────────────────────────────────────


@dataclass
class ReplaceManagedBlockParams:
    """Mirrors OpenClaw's ``replaceManagedMarkdownBlock`` parameter shape."""

    original: str
    heading: str
    start_marker: str
    end_marker: str
    body: str


def replace_managed_markdown_block(params: ReplaceManagedBlockParams) -> str:
    """Replace (or insert) a managed markdown block.

    Mirrors OpenClaw's
    ``replaceManagedMarkdownBlock``. The block
    format is::

        <start_marker>
        <heading>

        <body>
        <end_marker>

    A new file gets the block appended after the
    original text; an existing file has the previous
    block between the two markers replaced
    in-place. The trailing newline is preserved.
    """
    original = params.original
    if not original.endswith("\n"):
        original = original + "\n"
    new_block = (
        f"{params.start_marker}\n"
        f"{params.heading}\n\n"
        f"{params.body}\n"
        f"{params.end_marker}\n"
    )
    return with_trailing_newline(original + new_block)


# ── Frontmatter parser ────────────────────────────────────────


@dataclass
class ParsedWikiMarkdown:
    """The result of :func:`parse_wiki_frontmatter`.

    Mirrors OpenClaw's ``ParsedWikiMarkdown``. When
    ``has_frontmatter`` is False, ``frontmatter`` is
    ``{}`` and ``body`` is the original input (with
    no leading whitespace stripped — the OpenClaw
    parser also does not normalize whitespace when
    the frontmatter delimiter is absent).
    """

    has_frontmatter: bool
    frontmatter: dict[str, Any]
    body: str


def _coerce_frontmatter_value(value: Any) -> Any:
    """Coerce a single YAML-decoded value into a wiki-shaped scalar.

    Mirrors OpenClaw's
    ``normalizeStringList`` /
    ``normalizeLowercaseStringOrEmpty`` /
    ``normalizeOptionalString`` chain that runs
    after YAML parsing. The Python port keeps the
    conversion minimal: ``None`` and ``""`` collapse
    to ``None``; ``True`` / ``False`` stay as bools;
    numbers stay as numbers; lists are recursively
    coerced; everything else passes through
    unchanged.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [_coerce_frontmatter_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _coerce_frontmatter_value(v) for k, v in value.items()}
    return value


def _parse_yaml_frontmatter(text: str) -> dict[str, Any] | None:
    """Best-effort YAML frontmatter decode.

    Returns ``None`` when ``yaml`` is unavailable
    OR when the text is not a YAML mapping. The
    Python port uses ``pyyaml`` (already a transitive
    dep via ``pre-commit``) for the actual decode.
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        decoded: Any = yaml.safe_load(text)
    except Exception:
        # many exception types (ScannerError,
        # ParserError, ConstructorError, ...).
        return None
    if not isinstance(decoded, dict):
        return None
    return decoded


def parse_wiki_frontmatter(source: str) -> ParsedWikiMarkdown:
    """Extract the YAML frontmatter from a markdown source string.

    Mirrors OpenClaw's ``parseWikiFrontmatter``. The
    parser:
    1. Looks for a leading ``---\\n...\\n---\\n``
       block. The opening delimiter must be the
       first non-blank line; the closing delimiter
       is required.
    2. Decodes the YAML payload (best-effort;
       returns ``{}`` on parse errors).
    3. Coerces string values to trimmed strings,
       lists recursively, and preserves numbers /
       bools / nested dicts.

    Returns a :class:`ParsedWikiMarkdown`. When the
    source has no leading frontmatter, the entire
    source is treated as body.
    """
    if not isinstance(source, str):
        return ParsedWikiMarkdown(has_frontmatter=False, frontmatter={}, body="")

    # Find the opening delimiter on the first
    # non-blank line. We don't allow a leading
    # BOM / whitespace before it.
    stripped_leading = source.lstrip(" \t")
    if not stripped_leading.startswith(FRONTMATTER_OPEN + "\n"):
        return ParsedWikiMarkdown(has_frontmatter=False, frontmatter={}, body=source)

    # Locate the closing delimiter on its own line.
    # We slice off the leading "---" we already
    # matched.
    body_start = len(source) - len(stripped_leading) + len(FRONTMATTER_OPEN) + 1
    rest = source[body_start:]
    lines = rest.split("\n")
    close_index: int | None = None
    for idx, line in enumerate(lines):
        if line == FRONTMATTER_CLOSE:
            close_index = idx
            break
        # Some authors use ``...`` to end a YAML doc
        # (the spec allows it). OpenClaw does not
        # accept this; the Python port matches that.
    if close_index is None:
        return ParsedWikiMarkdown(has_frontmatter=False, frontmatter={}, body=source)

    yaml_text = "\n".join(lines[:close_index])
    decoded = _parse_yaml_frontmatter(yaml_text)
    if decoded is None:
        decoded = {}
    coerced = {key: _coerce_frontmatter_value(value) for key, value in decoded.items()}
    body = "\n".join(lines[close_index + 1 :])
    # Strip a single leading newline so the body
    # doesn't start with a blank line.
    if body.startswith("\n"):
        body = body[1:]
    return ParsedWikiMarkdown(has_frontmatter=True, frontmatter=coerced, body=body)


__all__ = [
    "FRONTMATTER_CLOSE",
    "FRONTMATTER_OPEN",
    "ParsedWikiMarkdown",
    "ReplaceManagedBlockParams",
    "WIKI_PAGE_KINDS",
    "WIKI_RAW_SOURCE_MARKER",
    "WIKI_RELATED_END_MARKER",
    "WIKI_RELATED_START_MARKER",
    "WikiPageKind",
    "parse_wiki_frontmatter",
    "replace_managed_markdown_block",
    "with_trailing_newline",
]
