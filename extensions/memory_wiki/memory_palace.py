"""memory_palace — Memory Wiki palace layout / scene cards.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/memory-palace.ts``.

A small async helper that groups every
queryable wiki page by kind and returns a
"palace" snapshot — counts + per-kind
clusters + per-item scene cards (claims,
questions, contradictions, snippet). The
host renders this in the
``wiki.palace`` gateway method (Phase
4.3f-mr7 stub) and in the per-vault
dashboard.

The OpenClaw source reads the same
``readQueryableWikiPages`` helper that
Phase 4.3f-mr1 ships in
:mod:`extensions.memory_wiki.query`. The
Python port reuses that helper and the
frontmatter parser, so the per-page shape
is the same as the rest of the memory-wiki
read path.
"""

# ruff: noqa: N815 — field names mirror the
# OpenClaw camelCase JSON shape so the
# ``wiki.palace`` gateway response is
# byte-compatible with the OpenClaw host.

from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key
from typing import TYPE_CHECKING, Literal, TypedDict

from .markdown import parse_wiki_frontmatter
from .query import read_queryable_wiki_pages

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


# Mirrors the OpenClaw
# ``WikiPageKind = "synthesis" | "entity" | "concept" | "source" | "report"``
# union.
WikiPageKind = Literal["synthesis", "entity", "concept", "source", "report"]


# Mirrors the OpenClaw
# ``PALACE_KIND_ORDER = ["synthesis", "entity", "concept", "source", "report"]``
# constant. Controls the cluster ordering
# in the palace status.
PALACE_KIND_ORDER: tuple[WikiPageKind, ...] = (
    "synthesis",
    "entity",
    "concept",
    "source",
    "report",
)

# Mirrors the OpenClaw
# ``PRIMARY_PALACE_KINDS = new Set<WikiPageKind>(["synthesis", "entity", "concept"])``
# constant. Pages of these kinds are always
# surfaced in the palace; other-kind pages
# are only surfaced when they carry claims,
# questions, or contradictions.
PRIMARY_PALACE_KINDS: frozenset[WikiPageKind] = frozenset({"synthesis", "entity", "concept"})

# Mirrors the OpenClaw
# ``PALACE_KIND_LABELS = { synthesis: "Syntheses", entity: "Entities", ... }``
# constant.
PALACE_KIND_LABELS: dict[WikiPageKind, str] = {
    "synthesis": "Syntheses",
    "entity": "Entities",
    "concept": "Concepts",
    "source": "Sources",
    "report": "Reports",
}

# Per-item slice caps (mirrors the
# ``slice(0, 3)`` in OpenClaw's
# ``listMemoryWikiPalace``).
PALACE_ITEM_TOP_CLAIMS = 3
PALACE_ITEM_TOP_QUESTIONS = 3
PALACE_ITEM_TOP_CONTRADICTIONS = 3


# ── Public dataclasses ───────────────────────────────────────


class MemoryWikiPalacePageCounts(TypedDict):
    """Per-kind page count. Mirrors the OpenClaw
    ``MemoryWikiPalacePageCounts`` type."""

    synthesis: int
    entity: int
    concept: int
    source: int
    report: int


@dataclass(frozen=True, slots=True)
class MemoryWikiPalaceItem:
    """A single palace item (one wiki page).

    Mirrors the OpenClaw
    ``MemoryWikiPalaceItem`` type. All
    fields are camelCase to match the
    OpenClaw JSON shape that the
    ``wiki.palace`` gateway method returns.
    """

    pagePath: str
    title: str
    kind: WikiPageKind
    claimCount: int
    questionCount: int
    contradictionCount: int
    claims: list[str]
    questions: list[str]
    contradictions: list[str]
    id: str | None = None
    updatedAt: str | None = None
    sourceType: str | None = None
    snippet: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryWikiPalaceCluster:
    """A per-kind cluster in the palace status.

    Mirrors the OpenClaw
    ``MemoryWikiPalaceCluster`` type. The
    ``items`` list is the sorted
    ``MemoryWikiPalaceItem`` list (sorted
    by :func:`compare_palace_items`).
    """

    key: WikiPageKind
    label: str
    itemCount: int
    claimCount: int
    questionCount: int
    contradictionCount: int
    items: list[MemoryWikiPalaceItem]
    updatedAt: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryWikiPalaceStatus:
    """The full palace status payload.

    Mirrors the OpenClaw
    ``MemoryWikiPalaceStatus`` type. Returned
    by :func:`list_memory_wiki_palace` and
    consumed by the ``wiki.palace`` gateway
    method.
    """

    totalItems: int
    totalPages: int
    pageCounts: MemoryWikiPalacePageCounts
    totalClaims: int
    totalQuestions: int
    totalContradictions: int
    clusters: list[MemoryWikiPalaceCluster]


# ── Helpers ──────────────────────────────────────────────────


def create_empty_palace_page_counts() -> MemoryWikiPalacePageCounts:
    """Return a fresh all-zero page-counts dict.

    Mirrors the OpenClaw
    ``createEmptyPalacePageCounts`` helper.
    """
    return {
        "synthesis": 0,
        "entity": 0,
        "concept": 0,
        "source": 0,
        "report": 0,
    }


def normalize_timestamp(value: object) -> str | None:
    """Return ``value`` as a non-empty trimmed string, or ``None``.

    Mirrors the OpenClaw
    ``normalizeTimestamp`` helper. Returns
    ``None`` for any non-string input or
    any whitespace-only string.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if len(trimmed) > 0 else None


def extract_snippet(body: str) -> str | None:
    """Return the first non-meta line of ``body`` as a snippet.

    Mirrors the OpenClaw
    ``extractSnippet`` helper. Skips:

    - blank lines
    - Markdown headings (``# ...``)
    - code fences (```` ``` ````)
    - HTML comments (``<!-- ...``)
    - list markers (``- `` / ``* ``)

    Returns ``None`` when no eligible line
    is found.
    """
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("```"):
            continue
        if line.startswith("<!--"):
            continue
        if line.startswith(("- ", "* ")):
            continue
        return line
    return None


def compare_palace_items(left: MemoryWikiPalaceItem, right: MemoryWikiPalaceItem) -> int:
    """Compare two palace items for sorting.

    Mirrors the OpenClaw
    ``comparePalaceItems`` helper:

    - ``updatedAt`` descending
    - ``claimCount`` descending
    - ``title`` ascending
    """
    left_key = left.updatedAt or ""
    right_key = right.updatedAt or ""
    if right_key != left_key:
        return _locale_compare(right_key, left_key)
    if right.claimCount != left.claimCount:
        return right.claimCount - left.claimCount
    return _locale_compare(left.title, right.title)


def _locale_compare(left: str, right: str) -> int:
    """Mimic the OpenClaw ``left.localeCompare(right)`` ordering."""
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def _is_primary_palace_kind(kind: str) -> bool:
    """Return True iff ``kind`` is a primary palace kind."""
    return kind in PRIMARY_PALACE_KINDS


def _claim_text(claim: object) -> str:
    """Return the claim's text (snake / camel tolerant, dict or obj)."""
    if isinstance(claim, dict):
        value = claim.get("text")
        if isinstance(value, str):
            return value
        return ""
    if hasattr(claim, "text"):
        value = claim.text
        if isinstance(value, str):
            return value
    return ""


# ── Public function ──────────────────────────────────────────


async def list_memory_wiki_palace(
    config: ResolvedMemoryWikiConfig,
) -> MemoryWikiPalaceStatus:
    """Read the wiki vault and return the palace status payload.

    Mirrors the OpenClaw
    ``listMemoryWikiPalace``:

    1. Reads every queryable wiki page under
       ``config.vault.path``.
    2. Computes per-kind page counts +
       total claims / questions /
       contradictions.
    3. Maps each page to a
       :class:`MemoryWikiPalaceItem`,
       slicing claims / questions /
       contradictions to the top 3 and
       extracting a snippet from the body.
    4. Filters to:

       - pages of a primary palace kind
         (synthesis / entity / concept), or
       - pages of any other kind with at
         least one claim, question, or
         contradiction.

    5. Sorts the surviving items with
       :func:`compare_palace_items`.
    6. Groups them into clusters in
       :data:`PALACE_KIND_ORDER`, dropping
       empty clusters.
    7. Returns the assembled
       :class:`MemoryWikiPalaceStatus`.
    """
    pages = read_queryable_wiki_pages(config.vault.path)

    page_counts: MemoryWikiPalacePageCounts = create_empty_palace_page_counts()
    for page in pages:
        kind = page.page.kind
        if kind in page_counts:
            page_counts[kind] += 1

    total_claims = sum(len(p.page.claims) for p in pages)
    total_questions = sum(len(p.page.questions) for p in pages)
    total_contradictions = sum(len(p.page.contradictions) for p in pages)

    items: list[MemoryWikiPalaceItem] = []
    for page in pages:
        parsed = parse_wiki_frontmatter(page.raw)
        body = ""
        if parsed is not None and isinstance(parsed.body, str):
            body = parsed.body
        snippet = extract_snippet(body)
        item = MemoryWikiPalaceItem(
            pagePath=page.page.relative_path,
            title=page.page.title,
            kind=page.page.kind,  # type: ignore[arg-type]
            id=page.page.id,
            updatedAt=normalize_timestamp(page.page.updated_at),
            sourceType=(
                page.page.source_type.strip()
                if isinstance(page.page.source_type, str) and page.page.source_type.strip()
                else None
            ),
            claimCount=len(page.page.claims),
            questionCount=len(page.page.questions),
            contradictionCount=len(page.page.contradictions),
            claims=[_claim_text(c) for c in page.page.claims[:PALACE_ITEM_TOP_CLAIMS]],
            questions=list(page.page.questions[:PALACE_ITEM_TOP_QUESTIONS]),
            contradictions=list(page.page.contradictions[:PALACE_ITEM_TOP_CONTRADICTIONS]),
            snippet=snippet,
        )
        items.append(item)

    # Filter: primary kinds always shown;
    # other kinds only when they carry
    # claims / questions / contradictions.
    items = [
        item
        for item in items
        if _is_primary_palace_kind(item.kind)
        or item.claimCount > 0
        or item.questionCount > 0
        or item.contradictionCount > 0
    ]
    items.sort(key=cmp_to_key(compare_palace_items))

    # Group into clusters in PALACE_KIND_ORDER,
    # dropping empty clusters.
    clusters: list[MemoryWikiPalaceCluster] = []
    for kind in PALACE_KIND_ORDER:
        cluster_items = [item for item in items if item.kind == kind]
        if not cluster_items:
            continue
        first_updated = cluster_items[0].updatedAt
        cluster = MemoryWikiPalaceCluster(
            key=kind,
            label=PALACE_KIND_LABELS[kind],
            itemCount=len(cluster_items),
            claimCount=sum(i.claimCount for i in cluster_items),
            questionCount=sum(i.questionCount for i in cluster_items),
            contradictionCount=sum(i.contradictionCount for i in cluster_items),
            items=cluster_items,
            updatedAt=first_updated,
        )
        clusters.append(cluster)

    return MemoryWikiPalaceStatus(
        totalItems=len(items),
        totalPages=len(pages),
        pageCounts=page_counts,
        totalClaims=total_claims,
        totalQuestions=total_questions,
        totalContradictions=total_contradictions,
        clusters=clusters,
    )


__all__ = [
    "PALACE_ITEM_TOP_CLAIMS",
    "PALACE_ITEM_TOP_CONTRADICTIONS",
    "PALACE_ITEM_TOP_QUESTIONS",
    "PALACE_KIND_LABELS",
    "PALACE_KIND_ORDER",
    "PRIMARY_PALACE_KINDS",
    "WikiPageKind",
    "MemoryWikiPalaceCluster",
    "MemoryWikiPalaceItem",
    "MemoryWikiPalacePageCounts",
    "MemoryWikiPalaceStatus",
    "compare_palace_items",
    "create_empty_palace_page_counts",
    "extract_snippet",
    "list_memory_wiki_palace",
    "normalize_timestamp",
]
