"""wiki_page_summary — the WikiPageSummary dataclass + the page scanner.

OpenClaw parity: this file ports the
``WikiPageSummary`` type and the
``scanWikiPageSummary`` /
``WikiPageSummaryScanResult`` discriminated
union from
``extensions/memory-wiki/src/markdown.ts``.

The full mdast-based body extraction (which
walks the markdown AST to derive ``claims``,
``questions``, ``contradictions``, ``linkTargets``
from the page body in addition to the
frontmatter) lives in 4.3d-mr4. The 4.3d-mr3
scanner is a focused, frontmatter-only extractor
that:

- Reads a markdown file from disk.
- Parses the YAML frontmatter.
- Derives the OpenClaw-shaped
  :class:`WikiPageSummary` (kind, title, id,
  aliases, sourceIds, claims, personCard,
  relationships, etc.).
- Extracts the link graph from the body via
  :func:`extensions.memory_wiki.markdown_pages.extract_wiki_links`.
- Returns a discriminated-union result
  (``valid`` / ``invalid-frontmatter`` /
  ``ignored``) so the compile orchestrator can
  surface page-level errors without throwing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from jarvis_sdk import normalize_optional_string

from .markdown import (
    WIKI_PAGE_KINDS,
    WIKI_RAW_SOURCE_MARKER,
    parse_wiki_frontmatter,
)
from .markdown_pages import (
    WikiClaim,
    WikiPersonCard,
    WikiRelationship,
    extract_title_from_markdown,
    extract_wiki_links,
    normalize_optional_number,
    normalize_optional_string_list,
    normalize_source_ids,
    normalize_wiki_claims,
    normalize_wiki_person_card,
    normalize_wiki_relationships,
)

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

WikiScanResultStatus = Literal["valid", "invalid-frontmatter", "ignored"]


@dataclass
class WikiPageSummary:
    """A single wiki page's full summary.

    Mirrors OpenClaw's ``WikiPageSummary`` type.
    The compile pipeline (4.3d-mr4 + 4.3f) reads
    this shape to build dashboards, link graphs,
    and the compiled SQLite snapshot. Optional
    fields are populated only when the underlying
    frontmatter / body has the corresponding
    value, so the dataclass is safe to use as a
    sparse record.
    """

    absolute_path: str
    relative_path: str
    kind: str
    title: str
    has_frontmatter: bool
    id: str | None = None
    page_type: str | None = None
    entity_type: str | None = None
    canonical_id: str | None = None
    aliases: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    link_targets: list[str] = field(default_factory=list)
    claims: list[WikiClaim] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    confidence: float | None = None
    privacy_tier: str | None = None
    person_card: WikiPersonCard | None = None
    relationships: list[WikiRelationship] = field(default_factory=list)
    best_used_for: list[str] = field(default_factory=list)
    not_enough_for: list[str] = field(default_factory=list)
    source_type: str | None = None
    provenance_mode: str | None = None
    imported_source_body: str | None = None
    generated_source_body: str | None = None
    unmanaged_raw_source_body: bool = False
    source_path: str | None = None
    bridge_relative_path: str | None = None
    bridge_workspace_dir: str | None = None
    unsafe_local_configured_path: str | None = None
    unsafe_local_relative_path: str | None = None
    last_refreshed_at: str | None = None
    updated_at: str | None = None


@dataclass
class WikiPageFrontmatterError:
    """An error from validating a page's frontmatter."""

    relative_path: str
    message: str


WikiPageSummaryScanResult = dict[str, Any]


# ── Helpers ──────────────────────────────────────────────────


def _infer_page_kind(
    frontmatter: dict[str, Any],
    relative_path: str,
) -> str:
    """Infer the page kind from the frontmatter or relative path.

    Mirrors OpenClaw's ``inferPageKind``: the
    frontmatter ``kind`` field wins; otherwise the
    path's first directory segment (e.g.
    ``syntheses/foo.md`` → ``synthesis``,
    ``entities/foo.md`` → ``entity``).
    """
    raw_kind = frontmatter.get("kind")
    if isinstance(raw_kind, str) and raw_kind.strip() in WIKI_PAGE_KINDS:
        return raw_kind.strip()
    if not relative_path:
        return "entity"
    # The path's first segment is the plural
    # directory name (e.g. ``syntheses``); map
    # to the singular kind. We accept both the
    # singular and plural forms in the first
    # segment so callers can pass either shape.
    first_segment = relative_path.replace(os.sep, "/").split("/", 1)[0]
    plural_to_singular = {
        "syntheses": "synthesis",
        "entities": "entity",
        "concepts": "concept",
        "sources": "source",
        "reports": "report",
    }
    if first_segment in plural_to_singular:
        return plural_to_singular[first_segment]
    if first_segment in WIKI_PAGE_KINDS:
        return first_segment
    return "entity"


def _questions_from_frontmatter(frontmatter: dict[str, Any]) -> list[str]:
    """Extract the page's open-questions list.

    Mirrors OpenClaw's
    ``normalizeQuestions``. Accepts a string
    (single question) or a list of strings.
    """
    return normalize_optional_string_list(frontmatter.get("questions"))


def _contradictions_from_frontmatter(
    frontmatter: dict[str, Any],
) -> list[str]:
    """Extract the page's contradiction notes.

    Mirrors OpenClaw's
    ``normalizeContradictions``.
    """
    return normalize_optional_string_list(frontmatter.get("contradictions"))


def _detect_unmanaged_raw_source_body(body: str) -> bool:
    """Return True iff ``body`` starts with the raw-source opt-out marker.

    Mirrors OpenClaw's
    ``detectUnmanagedRawSourceBody``.
    """
    if not isinstance(body, str):
        return False
    stripped = body.lstrip()
    if stripped.startswith(WIKI_RAW_SOURCE_MARKER):
        return True
    # If the first non-blank line is the H1 title,
    # allow the marker to follow the title.
    if "\n" in stripped:
        first_line, rest = stripped.split("\n", 1)
        if first_line.startswith("# "):
            return rest.lstrip().startswith(WIKI_RAW_SOURCE_MARKER)
    return False


def _normalize_aliases(frontmatter: dict[str, Any]) -> list[str]:
    """Extract and de-dupe the page's aliases.

    Mirrors OpenClaw's ``normalizeAliases``.
    """
    return normalize_optional_string_list(frontmatter.get("aliases"))


def _normalize_best_used_for_not_enough(
    frontmatter: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Extract the ``bestUsedFor`` / ``notEnoughFor`` lists.

    Mirrors OpenClaw's
    ``normalizeBestUsedForNotEnoughFor``.
    """
    best = normalize_optional_string_list(frontmatter.get("bestUsedFor"))
    not_enough = normalize_optional_string_list(frontmatter.get("notEnoughFor"))
    return best, not_enough


def _normalize_updated_at(frontmatter: dict[str, Any]) -> str | None:
    """Extract the page's ``updatedAt`` timestamp.

    Mirrors OpenClaw's
    ``normalizePageUpdatedAt``. Accepts the
    frontmatter ``updatedAt`` field.
    """
    return normalize_optional_string(frontmatter.get("updatedAt"))


def _normalize_last_refreshed_at(
    frontmatter: dict[str, Any],
) -> str | None:
    return normalize_optional_string(frontmatter.get("lastRefreshedAt"))


def _normalize_page_confidence(frontmatter: dict[str, Any]) -> float | None:
    """Extract a finite ``confidence`` value.

    Mirrors OpenClaw's ``normalizePageConfidence``.
    """
    return normalize_optional_number(frontmatter.get("confidence"))


def _normalize_privacy_tier(frontmatter: dict[str, Any]) -> str | None:
    return normalize_optional_string(frontmatter.get("privacyTier"))


def _normalize_page_id(frontmatter: dict[str, Any]) -> str | None:
    """Extract the canonical page id (lowercased + trimmed).

    Mirrors OpenClaw's ``normalizePageId``.
    """
    raw = frontmatter.get("id")
    if not isinstance(raw, str):
        return None
    return raw.strip() or None


def _build_wiki_page_summary(
    *,
    absolute_path: str,
    relative_path: str,
    raw_markdown: str,
) -> WikiPageSummary:
    """Build a :class:`WikiPageSummary` from a single markdown file.

    Mirrors OpenClaw's ``scanWikiPageSummary`` (the
    body-derived fields are populated by the
    frontmatter-only extractor in 4.3d-mr3; the
    mdast-based body extraction in 4.3d-mr4 will
    add ``linkTargets``, ``claims``, ``questions``,
    and ``contradictions`` derived from the body).
    """
    parsed = parse_wiki_frontmatter(raw_markdown)
    frontmatter = parsed.frontmatter if parsed.has_frontmatter else {}
    body = parsed.body

    title = extract_title_from_markdown(body) or relative_path
    kind = _infer_page_kind(frontmatter, relative_path)
    link_targets = extract_wiki_links(body, relative_path)
    claims = normalize_wiki_claims(frontmatter.get("claims"))
    person_card = normalize_wiki_person_card(frontmatter.get("personCard"))
    relationships = normalize_wiki_relationships(frontmatter.get("relationships"))
    best_used_for, not_enough_for = _normalize_best_used_for_not_enough(frontmatter)
    source_ids = normalize_source_ids(frontmatter.get("sourceIds"))
    aliases = _normalize_aliases(frontmatter)

    return WikiPageSummary(
        absolute_path=absolute_path,
        relative_path=relative_path,
        kind=kind,
        title=title,
        has_frontmatter=parsed.has_frontmatter,
        id=_normalize_page_id(frontmatter),
        page_type=normalize_optional_string(frontmatter.get("pageType")),
        entity_type=normalize_optional_string(frontmatter.get("entityType")),
        canonical_id=normalize_optional_string(frontmatter.get("canonicalId")),
        aliases=aliases,
        source_ids=source_ids,
        link_targets=link_targets,
        claims=claims,
        contradictions=_contradictions_from_frontmatter(frontmatter),
        questions=_questions_from_frontmatter(frontmatter),
        confidence=_normalize_page_confidence(frontmatter),
        privacy_tier=_normalize_privacy_tier(frontmatter),
        person_card=person_card,
        relationships=relationships,
        best_used_for=best_used_for,
        not_enough_for=not_enough_for,
        source_type=normalize_optional_string(frontmatter.get("sourceType")),
        provenance_mode=normalize_optional_string(frontmatter.get("provenanceMode")),
        imported_source_body=normalize_optional_string(frontmatter.get("importedSourceBody")),
        generated_source_body=normalize_optional_string(frontmatter.get("generatedSourceBody")),
        unmanaged_raw_source_body=_detect_unmanaged_raw_source_body(body),
        source_path=normalize_optional_string(frontmatter.get("sourcePath")),
        bridge_relative_path=normalize_optional_string(frontmatter.get("bridgeRelativePath")),
        bridge_workspace_dir=normalize_optional_string(frontmatter.get("bridgeWorkspaceDir")),
        unsafe_local_configured_path=normalize_optional_string(
            frontmatter.get("unsafeLocalConfiguredPath")
        ),
        unsafe_local_relative_path=normalize_optional_string(
            frontmatter.get("unsafeLocalRelativePath")
        ),
        last_refreshed_at=_normalize_last_refreshed_at(frontmatter),
        updated_at=_normalize_updated_at(frontmatter),
    )


def scan_wiki_page_summary(
    *,
    absolute_path: str,
    relative_path: str,
    raw_markdown: str,
) -> WikiPageSummaryScanResult:
    """Scan a single markdown file into a :class:`WikiPageSummary`.

    Mirrors OpenClaw's ``scanWikiPageSummary``. The
    function returns a discriminated-union result:
    - ``{"status": "valid", "page": WikiPageSummary}``
      on success.
    - ``{"status": "invalid-frontmatter",
       "error": WikiPageFrontmatterError}`` when
      the frontmatter is present but malformed.
    - ``{"status": "ignored"}`` for placeholder
      pages that should be skipped (e.g. the
      auto-generated ``index.md`` in each vault
      directory, which has no frontmatter and
      only a ``## Generated`` block).
    """
    parsed = parse_wiki_frontmatter(raw_markdown)
    if not parsed.has_frontmatter:
        # No frontmatter → likely an auto-generated
        # ``index.md`` or a freeform note. 4.3d-mr4
        # adds the body-only extraction; for now we
        # ignore it.
        return {"status": "ignored"}
    # Validate the frontmatter is a mapping. The
    # ``parse_wiki_frontmatter`` helper already
    # coerces non-mapping YAML to an empty dict,
    # so we treat that as ``invalid-frontmatter``
    # only when the original YAML was non-empty.
    if not parsed.frontmatter and raw_markdown.lstrip().startswith("---"):
        return {
            "status": "invalid-frontmatter",
            "error": WikiPageFrontmatterError(
                relative_path=relative_path,
                message="Wiki frontmatter must be a YAML mapping",
            ),
        }
    page = _build_wiki_page_summary(
        absolute_path=absolute_path,
        relative_path=relative_path,
        raw_markdown=raw_markdown,
    )
    return {"status": "valid", "page": page}


def scan_wiki_page_summary_from_file(
    *,
    absolute_path: str,
    vault_root: str,
) -> WikiPageSummaryScanResult:
    """Read ``absolute_path`` from disk and call :func:`scan_wiki_page_summary`.

    Convenience wrapper used by the compile
    pipeline. The ``vault_root`` is used to
    compute the relative path. The relative path
    uses forward slashes so the link graph stays
    portable across platforms.
    """
    raw = Path(absolute_path).read_text(encoding="utf-8")
    abs_root = os.path.abspath(vault_root)
    rel = os.path.relpath(absolute_path, abs_root).replace(os.sep, "/")
    return scan_wiki_page_summary(
        absolute_path=absolute_path,
        relative_path=rel,
        raw_markdown=raw,
    )


__all__ = [
    "WikiPageFrontmatterError",
    "WikiPageSummary",
    "WikiPageSummaryScanResult",
    "WikiScanResultStatus",
    "scan_wiki_page_summary",
    "scan_wiki_page_summary_from_file",
]
