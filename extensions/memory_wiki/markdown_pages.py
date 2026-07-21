"""markdown_pages — page-summary types, normalization, and link extraction.

OpenClaw parity: this file ports the type
definitions, normalization helpers, slug helpers,
markdown link / Obsidian link extraction, and the
``renderWikiMarkdown`` writer from
``extensions/memory-wiki/src/markdown.ts``.

The full ``scanWikiPage`` / ``parseWikiPageSummary``
function (which walks an mdast tree to extract the
page summary) lands in 4.3d alongside the compile
pipeline; the mdast library is a non-trivial
dependency and the compile pipeline is the natural
home for the integration.

Phase 4.3c-mr2 surface
---------------------
- Type literals: ``WikiPageKind``, ``WikiClaim``,
  ``WikiClaimEvidence``, ``WikiRelationship``,
  ``WikiPersonCard``, ``WikiPageSummary``,
  ``WikiPageSummaryScanResult``,
  ``WikiPageFrontmatterError``.
- Normalization helpers: ``normalize_source_ids``,
  ``normalize_wiki_claim_evidence``,
  ``normalize_wiki_claims``,
  ``normalize_wiki_relationships``,
  ``normalize_wiki_person_card``,
  ``normalize_optional_number``,
  ``normalize_optional_string_list``.
- Slug + filename helpers: ``slugify_wiki_segment``,
  ``slugify_wiki_page_stem``,
  ``create_wiki_page_filename``.
- Markdown render: ``render_wiki_markdown`` (the
  OpenClaw writer that emits a complete
  ``---\\n...\\n---\\n\\n<body>`` block).
- Title extraction: ``extract_title_from_markdown``.
- Link graph extraction: ``extract_wiki_links``
  (regex-based; obsidian ``[[wikilink]]`` + standard
  markdown ``[text](target)``).
- Code masking: ``mask_markdown_code``
  (fenced + inline code blocks become spaces so the
  link graph ignores URLs in code samples).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import normalize_optional_string

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
# ruff: noqa: PLR0911, PLR0912, PLR0915, S324, PLR0124, PIE810, UP038 — mirrors OpenClaw's many small normalizers (SHA1 for slug dedup is OpenClaw's choice; ``num != num`` is the canonical NaN check; tuple-isinstance pattern matches OpenClaw's strictObject coercion)
from .markdown import (
    WIKI_RELATED_END_MARKER,
    WIKI_RELATED_START_MARKER,
    with_trailing_newline,
)

# ── Constants ──────────────────────────────────────────────────

# Bytes caps mirror OpenClaw's
# ``MAX_WIKI_*_BYTES`` constants. The Python port
# uses byte-length so cross-platform encodings
# behave consistently (OpenClaw uses ``Buffer.byteLength``).
MAX_WIKI_SEGMENT_BYTES = 240
MAX_WIKI_FILENAME_COMPONENT_BYTES = 255
WIKI_SEGMENT_HASH_BYTES = 12
WIKI_RESERVED_PAGE_STEMS: frozenset[str] = frozenset({"index"})

# ``<!-- openclaw:human:start/end -->`` markers used
# to preserve human notes in the compile pipeline.
HUMAN_START_MARKER = "<!-- openclaw:human:start -->"
HUMAN_END_MARKER = "<!-- openclaw:human:end -->"

# Fs-safe pinned write temp suffix (mirrors
# OpenClaw's ``FS_SAFE_PINNED_WRITE_TEMP_SUFFIX``).
FS_SAFE_PINNED_WRITE_TEMP_SUFFIX = ".00000000-0000-4000-8000-000000000000.fallback.tmp"
MAX_WIKI_SAFE_WRITE_FILENAME_COMPONENT_BYTES = (
    MAX_WIKI_FILENAME_COMPONENT_BYTES
    - len(FS_SAFE_PINNED_WRITE_TEMP_SUFFIX.encode("utf-8"))
    - len(b".")
)

# Frontmatter pattern: ``---\\n...\\n---\\n?``.
# The closing delimiter accepts an optional trailing
# newline. CR / LF / CRLF are all accepted (matches
# OpenClaw's ``/^---\\r?\\n...\\r?\\n---\\r?\\n?/``).
FRONTMATTER_PATTERN = re.compile(
    r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?",
)

# Obsidian wikilink pattern: ``[[target]]`` or
# ``[[target|display text]]``. The optional pipe
# is non-capturing.
OBSIDIAN_LINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

# Standard markdown link pattern:
# ``[text](target)``. The target is captured.
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

# Managed related-block pattern (used by
# ``extractWikiLinks`` to skip the auto-generated
# backlinks block).
RELATED_BLOCK_PATTERN = re.compile(
    f"{re.escape(WIKI_RELATED_START_MARKER)}[\\s\\S]*?{re.escape(WIKI_RELATED_END_MARKER)}",
    re.MULTILINE,
)


# ── Data shapes ────────────────────────────────────────────────


@dataclass
class WikiClaimEvidence:
    """One evidence block for a wiki claim.

    Mirrors OpenClaw's ``WikiClaimEvidence`` type.
    All fields are optional; the dataclass is
    populated only with the fields present in the
    parsed frontmatter.
    """

    kind: str | None = None
    source_id: str | None = None
    path: str | None = None
    lines: str | None = None
    weight: float | None = None
    confidence: float | None = None
    privacy_tier: str | None = None
    note: str | None = None
    updated_at: str | None = None


@dataclass
class WikiClaim:
    """A single key belief on a wiki page.

    Mirrors OpenClaw's ``WikiClaim`` type.
    """

    text: str = ""
    id: str | None = None
    status: str | None = None
    confidence: float | None = None
    evidence: list[WikiClaimEvidence] = field(default_factory=list)
    updated_at: str | None = None


@dataclass
class WikiPersonCard:
    """A wiki page's person card (entity pages with a person)."""

    canonical_id: str | None = None
    handles: list[str] = field(default_factory=list)
    socials: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    timezone: str | None = None
    lane: str | None = None
    ask_for: list[str] = field(default_factory=list)
    avoid_asking_for: list[str] = field(default_factory=list)
    best_used_for: list[str] = field(default_factory=list)
    not_enough_for: list[str] = field(default_factory=list)
    confidence: float | None = None
    privacy_tier: str | None = None
    last_refreshed_at: str | None = None


@dataclass
class WikiRelationship:
    """A typed relationship between two wiki pages.

    Mirrors OpenClaw's ``WikiRelationship`` type.
    """

    target_id: str | None = None
    target_path: str | None = None
    target_title: str | None = None
    kind: str | None = None
    weight: float | None = None
    confidence: float | None = None
    evidence_kind: str | None = None
    privacy_tier: str | None = None
    note: str | None = None
    updated_at: str | None = None


@dataclass
class WikiPageFrontmatterError:
    """An error from validating a page's frontmatter.

    Mirrors OpenClaw's ``WikiPageFrontmatterError``.
    """

    relative_path: str
    message: str


# Scan result discriminated union. Mirrors OpenClaw's
# ``WikiPageSummaryScanResult``.
WikiPageSummaryScanResult = (
    dict[str, Any]  # {'status': 'valid', 'page': WikiPageSummary}
    | dict[str, Any]  # {'status': 'invalid-frontmatter', 'error': WikiPageFrontmatterError}
    | dict[str, Any]  # {'status': 'ignored'}
)


# ── Slug + filename helpers ─────────────────────────────────────


def _truncate_utf8_codepoint_safe(value: str, max_bytes: int) -> str:
    """Truncate ``value`` to at most ``max_bytes`` UTF-8 bytes.

    Mirrors OpenClaw's ``truncateUtf8CodePointSafe``.
    Walks the string in code-point chunks and stops
    when the next chunk would exceed the cap.
    """
    result: list[str] = []
    total = 0
    for char in value:
        char_bytes = len(char.encode("utf-8"))
        if total + char_bytes > max_bytes:
            break
        result.append(char)
        total += char_bytes
    return "".join(result)


def _cap_wiki_value_with_hash(raw: str, max_bytes: int, fallback: str) -> str:
    """Cap ``raw`` to ``max_bytes``; if too long, append a hash suffix.

    Mirrors OpenClaw's ``capWikiValueWithHash``. The
    suffix is the first ``WIKI_SEGMENT_HASH_BYTES``
    (12) hex chars of SHA-1 over the original
    ``raw`` value. Trailing dashes are trimmed from
    the truncated head so the final form is
    ``<truncated>-<hash>``.
    """
    if len(raw.encode("utf-8")) <= max_bytes:
        return raw
    suffix_len = WIKI_SEGMENT_HASH_BYTES
    head_bytes = max(0, max_bytes - (suffix_len + 1))  # 1 byte for '-'
    truncated = _truncate_utf8_codepoint_safe(raw, head_bytes)
    truncated = re.sub(r"-+\Z", "", truncated)
    hash_suffix = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:WIKI_SEGMENT_HASH_BYTES]
    head = truncated or fallback
    return f"{head}-{hash_suffix}"


def slugify_wiki_segment(raw: str) -> str:
    """Convert ``raw`` to a wiki-segment-safe slug.

    Mirrors OpenClaw's ``slugifyWikiSegment``. Lower-
    cases, replaces non-letter / non-digit / non-mark
    characters with ``-``, collapses runs of ``-``,
    and trims leading / trailing ``-``. An empty
    result is replaced with ``"page"`` and the result
    is then capped at ``MAX_WIKI_SEGMENT_BYTES``
    (with a hash suffix when truncated).
    """
    # Lowercase. The ``re.UNICODE`` flag enables
    # the ``\p{...}`` Unicode property classes that
    # OpenClaw uses; on Python 3.6+ these are
    # supported under the default ``re`` module.
    lowered = raw.lower()
    slug = re.sub(r"[^\w]+", "-", lowered, flags=re.UNICODE)
    slug = re.sub(r"-+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    if not slug:
        slug = "page"
    return _cap_wiki_value_with_hash(slug, MAX_WIKI_SEGMENT_BYTES, "page")


def slugify_wiki_page_stem(raw: str) -> str:
    """Convert ``raw`` to a wiki page stem (filename minus ``.md``).

    Mirrors OpenClaw's ``slugifyWikiPageStem``.
    Reserved stems (``index``) get a hash suffix so
    they don't collide with the auto-generated
    ``index.md`` files in each vault directory.
    """
    slug = slugify_wiki_segment(raw)
    if slug in WIKI_RESERVED_PAGE_STEMS:
        suffix = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:WIKI_SEGMENT_HASH_BYTES]
        return f"{slug}-{suffix}"
    return slug


def create_wiki_page_filename(stem: str, extension: str = ".md") -> str:
    """Build a safe filename from ``stem`` + ``extension``.

    Mirrors OpenClaw's ``createWikiPageFilename``. The
    final filename is capped at
    ``MAX_WIKI_SAFE_WRITE_FILENAME_COMPONENT_BYTES``
    so the fs-safe pinned write temp suffix never
    overflows the platform's max filename length.
    """
    normalized_extension = extension if extension.startswith(".") else f".{extension}"
    max_stem_bytes = max(
        1,
        MAX_WIKI_SAFE_WRITE_FILENAME_COMPONENT_BYTES - len(normalized_extension.encode("utf-8")),
    )
    capped_stem = _cap_wiki_value_with_hash(stem, max_stem_bytes, "page")
    return f"{capped_stem}{normalized_extension}"


# ── Markdown render ─────────────────────────────────────────────


def render_wiki_markdown(
    *,
    frontmatter: dict[str, Any],
    body: str,
) -> str:
    """Render a complete ``---\\n<fm>\\n---\\n\\n<body>`` block.

    Mirrors OpenClaw's ``renderWikiMarkdown``. The
    body is left-trimmed and the frontmatter is
    YAML-serialized.
    """
    import yaml

    fm_text = yaml.safe_dump(
        frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False
    ).rstrip()
    return with_trailing_newline(f"---\n{fm_text}\n---\n\n{body.lstrip()}")


# ── Title extraction ────────────────────────────────────────────


def extract_title_from_markdown(body: str) -> str | None:
    """Return the first ``# Heading`` from ``body``, or ``None``.

    Mirrors OpenClaw's ``extractTitleFromMarkdown``.
    The first H1 wins.
    """
    if not isinstance(body, str):
        return None
    match = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    if not match:
        return None
    return normalize_optional_string(match.group(1))


# ── String / number coercion helpers ───────────────────────────


def normalize_optional_number(value: Any) -> float | None:
    """Return ``value`` as a finite number, else ``None``.

    Mirrors OpenClaw's ``normalizeOptionalNumber``
    (which wraps ``asFiniteNumber`` from
    ``string-coerce-runtime``).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        if num != num or num in (float("inf"), float("-inf")):
            return None
        return num
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        try:
            num = float(trimmed)
        except ValueError:
            return None
        if num != num or num in (float("inf"), float("-inf")):
            return None
        return num
    return None


def normalize_optional_string_list(value: Any) -> list[str]:
    """Coerce ``value`` into a trimmed, de-duplicated string list.

    Mirrors OpenClaw's
    ``normalizeSingleOrTrimmedStringList``. Non-string
    entries are dropped. Empty / whitespace-only
    strings are dropped. The first occurrence wins
    on duplicates (de-duped by exact match).
    """
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for entry in candidates:
        if not isinstance(entry, str):
            continue
        normalized = entry.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def normalize_source_ids(value: Any) -> list[str]:
    """Coerce ``value`` into a trimmed, de-duplicated list of source ids.

    Mirrors OpenClaw's ``normalizeSourceIds``.
    """
    return normalize_optional_string_list(value)


# ── Claim / evidence / person / relationship normalizers ──────


def normalize_wiki_claim_evidence(value: Any) -> WikiClaimEvidence | None:
    """Normalize a single claim-evidence block from the frontmatter.

    Mirrors OpenClaw's ``normalizeWikiClaimEvidence``.
    Returns ``None`` when no meaningful field is
    present (i.e. the block is effectively empty
    after coercion).
    """
    if not isinstance(value, dict) or isinstance(value, list):
        return None
    kind = normalize_optional_string(value.get("kind"))
    source_id = normalize_optional_string(value.get("sourceId"))
    path = normalize_optional_string(value.get("path"))
    lines = normalize_optional_string(value.get("lines"))
    note = normalize_optional_string(value.get("note"))
    updated_at = normalize_optional_string(value.get("updatedAt"))
    privacy_tier = normalize_optional_string(value.get("privacyTier"))
    weight = normalize_optional_number(value.get("weight"))
    confidence = normalize_optional_number(value.get("confidence"))
    if (
        kind is None
        and source_id is None
        and path is None
        and lines is None
        and note is None
        and weight is None
        and confidence is None
        and privacy_tier is None
        and updated_at is None
    ):
        return None
    return WikiClaimEvidence(
        kind=kind,
        source_id=source_id,
        path=path,
        lines=lines,
        weight=weight,
        confidence=confidence,
        privacy_tier=privacy_tier,
        note=note,
        updated_at=updated_at,
    )


def normalize_wiki_claims(value: Any) -> list[WikiClaim]:
    """Normalize the ``claims`` array from a page's frontmatter.

    Mirrors OpenClaw's ``normalizeWikiClaims``.
    Returns an empty list when ``value`` is not an
    array, and silently drops entries that lack a
    non-empty ``text``.
    """
    if not isinstance(value, list):
        return []
    out: list[WikiClaim] = []
    for entry in value:
        if not isinstance(entry, dict) or isinstance(entry, list):
            continue
        text = normalize_optional_string(entry.get("text"))
        if not text:
            continue
        evidence_raw = entry.get("evidence")
        evidence: list[WikiClaimEvidence] = []
        if isinstance(evidence_raw, list):
            for candidate in evidence_raw:
                normalized = normalize_wiki_claim_evidence(candidate)
                if normalized is not None:
                    evidence.append(normalized)
        confidence = normalize_optional_number(entry.get("confidence"))
        out.append(
            WikiClaim(
                text=text,
                id=normalize_optional_string(entry.get("id")),
                status=normalize_optional_string(entry.get("status")),
                confidence=confidence,
                evidence=evidence,
                updated_at=normalize_optional_string(entry.get("updatedAt")),
            )
        )
    return out


def normalize_wiki_person_card(value: Any) -> WikiPersonCard | None:
    """Normalize the ``personCard`` block from a page's frontmatter.

    Mirrors OpenClaw's ``normalizeWikiPersonCard``.
    Returns ``None`` when no meaningful field is
    present so empty objects are pruned.
    """
    if not isinstance(value, dict) or isinstance(value, list):
        return None
    canonical_id = normalize_optional_string(value.get("canonicalId"))
    timezone = normalize_optional_string(value.get("timezone"))
    lane = normalize_optional_string(value.get("lane"))
    privacy_tier = normalize_optional_string(value.get("privacyTier"))
    last_refreshed_at = normalize_optional_string(value.get("lastRefreshedAt"))
    confidence = normalize_optional_number(value.get("confidence"))
    card = WikiPersonCard(
        canonical_id=canonical_id,
        handles=normalize_optional_string_list(value.get("handles")),
        socials=normalize_optional_string_list(value.get("socials")),
        emails=normalize_optional_string_list(value.get("emails") or value.get("email")),
        timezone=timezone,
        lane=lane,
        ask_for=normalize_optional_string_list(value.get("askFor")),
        avoid_asking_for=normalize_optional_string_list(value.get("avoidAskingFor")),
        best_used_for=normalize_optional_string_list(value.get("bestUsedFor")),
        not_enough_for=normalize_optional_string_list(value.get("notEnoughFor")),
        confidence=confidence,
        privacy_tier=privacy_tier,
        last_refreshed_at=last_refreshed_at,
    )
    has_any_value = any(
        [
            card.canonical_id,
            card.timezone,
            card.lane,
            card.privacy_tier,
            card.last_refreshed_at,
            isinstance(card.confidence, (int, float)),
            card.handles,
            card.socials,
            card.emails,
            card.ask_for,
            card.avoid_asking_for,
            card.best_used_for,
            card.not_enough_for,
        ]
    )
    return card if has_any_value else None


def normalize_wiki_relationships(value: Any) -> list[WikiRelationship]:
    """Normalize the ``relationships`` array from a page's frontmatter.

    Mirrors OpenClaw's ``normalizeWikiRelationships``.
    Returns an empty list when ``value`` is not an
    array.
    """
    if not isinstance(value, list):
        return []
    out: list[WikiRelationship] = []
    for entry in value:
        if not isinstance(entry, dict) or isinstance(entry, list):
            continue
        target_id = normalize_optional_string(entry.get("targetId"))
        target_path = normalize_optional_string(entry.get("targetPath"))
        target_title = normalize_optional_string(entry.get("targetTitle"))
        kind = normalize_optional_string(entry.get("kind"))
        weight = normalize_optional_number(entry.get("weight"))
        confidence = normalize_optional_number(entry.get("confidence"))
        evidence_kind = normalize_optional_string(entry.get("evidenceKind"))
        privacy_tier = normalize_optional_string(entry.get("privacyTier"))
        note = normalize_optional_string(entry.get("note"))
        updated_at = normalize_optional_string(entry.get("updatedAt"))
        if not any(
            [
                target_id,
                target_path,
                target_title,
                kind,
                weight is not None,
                confidence is not None,
                evidence_kind,
                privacy_tier,
                note,
                updated_at,
            ]
        ):
            continue
        out.append(
            WikiRelationship(
                target_id=target_id,
                target_path=target_path,
                target_title=target_title,
                kind=kind,
                weight=weight,
                confidence=confidence,
                evidence_kind=evidence_kind,
                privacy_tier=privacy_tier,
                note=note,
                updated_at=updated_at,
            )
        )
    return out


# ── Markdown link extraction ────────────────────────────────────


def _normalize_markdown_link_target(source_relative_path: str, target: str) -> str:
    """Resolve a markdown link target relative to its source page.

    Mirrors OpenClaw's
    ``normalizeMarkdownLinkTarget``. The path is
    POSIX-normalized (forward slashes, ``..`` and
    ``.`` resolution) regardless of the host OS so
    the link graph is portable.
    """
    import posixpath

    if not target:
        return ""
    if target.startswith("/") or target.startswith("~"):
        return target
    source_dir = posixpath.dirname(source_relative_path)
    joined = target if not source_dir or source_dir == "." else f"{source_dir}/{target}"
    # ``posixpath.normpath`` collapses ``..`` and
    # ``.`` segments and uses forward slashes
    # regardless of the host OS. This matches
    # OpenClaw's ``path.posix.normalize``.
    return posixpath.normpath(joined)


def _mask_markdown_code(markdown: str) -> str:
    """Replace every character inside a code block with a space.

    Mirrors OpenClaw's ``maskMarkdownCode``. Fenced
    code blocks (```) and indented code blocks get
    their content blanked so the link graph ignores
    URLs in code samples. The Python port uses a
    line-based scanner (no mdast) since the goal is
    only to suppress code-fenced content from link
    detection.
    """
    lines = markdown.splitlines(keepends=True)
    in_fence = False
    fence_marker: str | None = None
    out: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        # Fenced code block toggle. OpenClaw accepts
        # any leading whitespace before the fence
        # marker (``mdast`` normalizes indent).
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif fence_marker is not None and stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = None
            out.append(line)
            continue
        if in_fence:
            out.append(re.sub(r"[^\r\n]", " ", line))
            continue
        # Indented (4+ spaces) code block.
        if line.startswith("    ") or line.startswith("\t"):
            out.append(re.sub(r"[^\r\n]", " ", line))
            continue
        out.append(line)
    return "".join(out)


def extract_wiki_links(markdown: str, source_relative_path: str) -> list[str]:
    """Extract wiki / markdown link targets from ``markdown``.

    Mirrors OpenClaw's ``extractWikiLinks``. The
    scan:
    1. Strips the auto-generated ``## Related``
       managed block (so the compile's own output
       doesn't seed the next compile's link graph).
    2. Masks fenced + indented code blocks so URLs
       in code samples don't show up as links.
    3. Collects Obsidian ``[[wikilinks]]`` and
       standard markdown ``[text](target)`` targets.
    4. Resolves relative markdown links against
       ``source_relative_path`` via
       :func:`_normalize_markdown_link_target`.
    5. De-duplicates while preserving first
       occurrence.
    """
    if not isinstance(markdown, str):
        return []
    without_related = RELATED_BLOCK_PATTERN.sub("", markdown)
    masked = _mask_markdown_code(without_related)

    targets: list[str] = []
    seen: set[str] = set()

    # Obsidian [[wikilinks]] are always relative
    # to the vault root; the slug is the target.
    for match in OBSIDIAN_LINK_PATTERN.finditer(masked):
        slug = match.group(1).strip()
        if slug and slug not in seen:
            seen.add(slug)
            targets.append(slug)

    # Standard markdown links are relative to the
    # source page's directory.
    for match in MARKDOWN_LINK_PATTERN.finditer(masked):
        raw_target = match.group(1).strip()
        # Drop the optional title (``"url"``) tail.
        raw_target = raw_target.split(" ", 1)[0]
        resolved = _normalize_markdown_link_target(source_relative_path, raw_target)
        if resolved and resolved not in seen:
            seen.add(resolved)
            targets.append(resolved)

    return targets


__all__ = [
    "FRONTMATTER_PATTERN",
    "FS_SAFE_PINNED_WRITE_TEMP_SUFFIX",
    "HUMAN_END_MARKER",
    "HUMAN_START_MARKER",
    "MARKDOWN_LINK_PATTERN",
    "MAX_WIKI_FILENAME_COMPONENT_BYTES",
    "MAX_WIKI_SAFE_WRITE_FILENAME_COMPONENT_BYTES",
    "MAX_WIKI_SEGMENT_BYTES",
    "OBSIDIAN_LINK_PATTERN",
    "RELATED_BLOCK_PATTERN",
    "WIKI_RESERVED_PAGE_STEMS",
    "WIKI_SEGMENT_HASH_BYTES",
    "WikiClaim",
    "WikiClaimEvidence",
    "WikiPageFrontmatterError",
    "WikiPageSummaryScanResult",
    "WikiPersonCard",
    "WikiRelationship",
    "create_wiki_page_filename",
    "extract_title_from_markdown",
    "extract_wiki_links",
    "normalize_optional_number",
    "normalize_optional_string_list",
    "normalize_source_ids",
    "normalize_wiki_claim_evidence",
    "normalize_wiki_claims",
    "normalize_wiki_person_card",
    "normalize_wiki_relationships",
    "render_wiki_markdown",
    "slugify_wiki_page_stem",
    "slugify_wiki_segment",
]
