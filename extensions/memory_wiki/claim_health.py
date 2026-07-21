"""claim_health — page + claim freshness, contradiction clusters.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/claim-health.ts``.

Phase 4.3d-mr2 ships the freshness-assessment layer
that the compile / dashboard pipeline (4.3d-mr3 +
4.3f) consumes. Pure functions: no I/O, no
mutation, no clock dependency beyond an optional
``now: Date`` injection so the build pipeline can
deterministically re-derive dashboards from a
recorded ``compiledCachePublicationId``.

Surface
-------
- ``WIKI_AGING_DAYS`` (30) and
  ``WIKI_STALE_DAYS`` (90) -- the freshness window
  constants mirrored from OpenClaw.
- ``WikiFreshnessLevel`` / ``WikiFreshness`` /
  ``WikiClaimHealth`` /
  ``WikiClaimContradictionCluster`` /
  ``WikiPageContradictionCluster`` -- the
  result-shape types (dataclasses).
- ``normalizeClaimStatus`` /
  ``isClaimContestedStatus`` -- the status
  normalization helpers.
- ``assessPageFreshness`` /
  ``assessClaimFreshness`` -- the per-page and
  per-claim freshness assessors.
- ``collectWikiClaimHealth`` -- the per-claim
  health-row builder over a list of pages.
- ``buildClaimContradictionClusters`` /
  ``buildPageContradictionClusters`` -- the
  contradiction cluster builders used by the
  ``reports/contradictions.md`` dashboard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from jarvis_sdk import normalize_lowercase_string_or_empty

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

# ruff: noqa: PLR0124, UP038 — mirrors OpenClaw's strictObject coercion

# ── Constants ──────────────────────────────────────────────────

DAY_MS = 24 * 60 * 60 * 1000
WIKI_AGING_DAYS = 30
WIKI_STALE_DAYS = 90

CONTESTED_CLAIM_STATUSES: frozenset[str] = frozenset(
    {"contested", "contradicted", "refuted", "superseded"}
)

WikiFreshnessLevel = str  # narrowed to "fresh" | "aging" | "stale" | "unknown"


# ── Types ─────────────────────────────────────────────────────


@dataclass
class WikiFreshness:
    """A freshness assessment result.

    Mirrors OpenClaw's ``WikiFreshness`` type.
    """

    level: str
    reason: str
    days_since_touch: int | None = None
    last_touched_at: str | None = None


@dataclass
class WikiClaimHealth:
    """A single claim's health row.

    Mirrors OpenClaw's ``WikiClaimHealth`` type. The
    ``key`` is ``{pageRelativePath}#{claimId}`` or
    ``{pageRelativePath}#claim-{index+1}`` when the
    claim has no ``id``.
    """

    key: str
    page_path: str
    page_title: str
    page_id: str | None = None
    claim_id: str | None = None
    text: str = ""
    status: str = "supported"
    confidence: float | None = None
    evidence_count: int = 0
    missing_evidence: bool = False
    freshness: WikiFreshness = field(
        default_factory=lambda: WikiFreshness("unknown", "missing updatedAt")
    )


@dataclass
class WikiClaimContradictionCluster:
    """A cluster of claims with the same ``claimId`` but distinct text or status.

    Mirrors OpenClaw's
    ``WikiClaimContradictionCluster`` type.
    """

    key: str
    label: str
    entries: list[WikiClaimHealth] = field(default_factory=list)


@dataclass
class WikiPageContradictionEntry:
    """A single entry in a page-level contradiction cluster.

    Mirrors OpenClaw's inline
    ``WikiPageContradictionCluster["entries"]``
    element type.
    """

    page_path: str
    page_title: str
    page_id: str | None = None
    note: str = ""


@dataclass
class WikiPageContradictionCluster:
    """A cluster of page-level contradiction notes."""

    key: str
    label: str
    entries: list[WikiPageContradictionEntry] = field(default_factory=list)


# ── Timestamp parsing ─────────────────────────────────────────


def _parse_timestamp(value: str | None) -> int | None:
    """Return ``value`` parsed as a millisecond timestamp, or ``None``.

    Mirrors OpenClaw's ``parseTimestamp`` (Date.parse
    + Number.isFinite). Empty / whitespace strings
    and unparseable inputs return ``None``.
    """
    if value is None or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    ms = int(parsed.timestamp() * 1000)
    return ms if ms == ms else None  # NaN guard


def _clamp_days_since_touch(days_since_touch: int) -> int:
    """Clamp negative day deltas to 0.

    Mirrors OpenClaw's ``clampDaysSinceTouch``
    (``Math.max(0, daysSinceTouch)``).
    """
    return max(0, days_since_touch)


def _normalize_claim_text_key(text: str) -> str:
    """Normalize a claim's text for contradiction-cluster keying.

    Mirrors OpenClaw's ``normalizeClaimTextKey``:
    lowercases + collapses whitespace.
    """
    return normalize_lowercase_string_or_empty(re.sub(r"\s+", " ", text))


def _normalize_text_key(text: str) -> str:
    """Normalize a string for cluster keying (word-boundary splits).

    Mirrors OpenClaw's ``normalizeTextKey``:
    lowercases, replaces non-letter / non-digit /
    non-mark characters with a single space, and
    collapses runs of whitespace.
    """
    lowered = normalize_lowercase_string_or_empty(text)
    cleaned = re.sub(r"[^\w]+", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned)


# ── Freshness assessment ─────────────────────────────────────


def _build_freshness_from_timestamp(
    *,
    timestamp: str | None,
    now: datetime | None,
) -> WikiFreshness:
    """Compute freshness from a single ISO-8601 timestamp.

    Mirrors OpenClaw's ``buildFreshnessFromTimestamp``.
    - ``None`` / missing / unparseable timestamp →
      ``{level: "unknown", reason: "missing updatedAt"}``.
    - ``daysSinceTouch >= WIKI_STALE_DAYS`` (90) →
      ``stale``.
    - ``daysSinceTouch >= WIKI_AGING_DAYS`` (30) →
      ``aging``.
    - else → ``fresh``.
    """
    effective_now = now or datetime.now(tz=UTC)
    timestamp_ms = _parse_timestamp(timestamp)
    if timestamp_ms is None or not timestamp:
        return WikiFreshness(
            level="unknown",
            reason="missing updatedAt",
        )
    delta_ms = effective_now.timestamp() * 1000 - timestamp_ms
    days_since_touch = _clamp_days_since_touch(int(delta_ms // DAY_MS))
    reason = f"last touched {timestamp}"
    base = {
        "days_since_touch": days_since_touch,
        "last_touched_at": timestamp,
    }
    if days_since_touch >= WIKI_STALE_DAYS:
        return WikiFreshness(level="stale", reason=reason, **base)
    if days_since_touch >= WIKI_AGING_DAYS:
        return WikiFreshness(level="aging", reason=reason, **base)
    return WikiFreshness(level="fresh", reason=reason, **base)


def _resolve_latest_timestamp(
    candidates: list[str | None],
) -> str | None:
    """Return the most recent timestamp from ``candidates`` (lex-max by ms).

    Mirrors OpenClaw's ``resolveLatestTimestamp``.
    Returns ``None`` when no candidate parses.
    """
    best_value: str | None = None
    best_ms = -1
    for candidate in candidates:
        parsed = _parse_timestamp(candidate)
        if parsed is None or not candidate or parsed <= best_ms:
            continue
        best_ms = parsed
        best_value = candidate
    return best_value


def _read_attr(value: Any, *names: str) -> Any:
    """Read the first present attribute from ``value`` among ``names``.

    The Python port's dataclasses use snake_case;
    the OpenClaw ``WikiPageSummary`` /
    ``WikiClaim`` shapes use camelCase. This
    helper accepts either so callers can pass
    either a real ``WikiPageSummary`` /
    ``WikiClaim`` instance or a ``SimpleNamespace``
    (test fixture).
    """
    # Prefer snake_case first (the Python
    # dataclass layout); fall back to camelCase
    # for OpenClaw parity tests.
    snake_names = [n for n in names if "_" in n]
    camel_names = [n for n in names if "_" not in n]
    for name in [*snake_names, *camel_names]:
        if hasattr(value, name):
            return getattr(value, name)
    return None


# ── Status normalization ──────────────────────────────────────


def normalize_claim_status(status: str | None) -> str:
    """Lowercase + default ``"supported"`` when blank.

    Mirrors OpenClaw's ``normalizeClaimStatus``.
    """
    normalized = normalize_lowercase_string_or_empty(status)
    return normalized or "supported"


def is_claim_contested_status(status: str | None) -> bool:
    """Return True iff the normalized status is a contested / contradicted state.

    Mirrors OpenClaw's ``isClaimContestedStatus``.
    """
    return normalize_claim_status(status) in CONTESTED_CLAIM_STATUSES


# ── Per-page / per-claim freshness ────────────────────────────


def assess_page_freshness(
    page: Any,
    now: datetime | None = None,
) -> WikiFreshness:
    """Compute the freshness of a single page.

    Mirrors OpenClaw's ``assessPageFreshness``.
    """
    return _build_freshness_from_timestamp(
        timestamp=_read_attr(page, "updatedAt", "updated_at"),
        now=now,
    )


def assess_claim_freshness(
    *,
    page: Any,
    claim: Any,
    now: datetime | None = None,
) -> WikiFreshness:
    """Compute the freshness of a single claim.

    Mirrors OpenClaw's ``assessClaimFreshness``. The
    latest timestamp across the claim's own
    ``updatedAt`` and every evidence item's
    ``updatedAt`` wins; when the claim has no
    timestamps at all, falls back to the page's
    ``updatedAt`` (so a freshly-touched page never
    shows its claims as ``unknown``).
    """
    claim_updated_at = _read_attr(claim, "updatedAt", "updated_at")
    page_updated_at = _read_attr(page, "updatedAt", "updated_at")
    has_claim_timestamp = bool(isinstance(claim_updated_at, str) and claim_updated_at.strip())
    latest_timestamp = _resolve_latest_timestamp([claim_updated_at])
    latest_ms = _parse_timestamp(latest_timestamp) or -1
    for evidence in claim.evidence:
        evidence_updated_at = _read_attr(evidence, "updatedAt", "updated_at")
        if isinstance(evidence_updated_at, str) and evidence_updated_at.strip():
            has_claim_timestamp = True
        evidence_ms = _parse_timestamp(evidence_updated_at)
        if evidence_ms is None or not evidence_updated_at or evidence_ms <= latest_ms:
            continue
        latest_ms = evidence_ms
        latest_timestamp = evidence_updated_at
    fallback = None if has_claim_timestamp else page_updated_at
    return _build_freshness_from_timestamp(timestamp=latest_timestamp or fallback, now=now)


# ── Claim health rows ────────────────────────────────────────


def _build_wiki_claim_health(
    *,
    page: Any,
    claim: Any,
    index: int,
    now: datetime | None = None,
) -> WikiClaimHealth:
    """Build a single ``WikiClaimHealth`` row.

    Mirrors OpenClaw's ``buildWikiClaimHealth``.
    """
    raw_claim_id = _read_attr(claim, "id")
    claim_id = raw_claim_id.strip() if isinstance(raw_claim_id, str) else None
    key_suffix = claim_id or f"claim-{index + 1}"
    page_path = _read_attr(page, "relativePath", "relative_path") or ""
    page_title = _read_attr(page, "title") or page_path
    raw_page_id = _read_attr(page, "id")
    page_id = raw_page_id if isinstance(raw_page_id, str) else None
    claim_text = _read_attr(claim, "text") or ""
    claim_status = _read_attr(claim, "status")
    claim_confidence = _read_attr(claim, "confidence")
    return WikiClaimHealth(
        key=f"{page_path}#{key_suffix}",
        page_path=page_path,
        page_title=page_title,
        page_id=page_id,
        claim_id=claim_id,
        text=claim_text,
        status=normalize_claim_status(claim_status),
        confidence=claim_confidence if isinstance(claim_confidence, (int, float)) else None,
        evidence_count=len(claim.evidence),
        missing_evidence=len(claim.evidence) == 0,
        freshness=assess_claim_freshness(page=page, claim=claim, now=now),
    )


def collect_wiki_claim_health(
    pages: list[Any],
    now: datetime | None = None,
) -> list[WikiClaimHealth]:
    """Collect one ``WikiClaimHealth`` row per claim across all ``pages``.

    Mirrors OpenClaw's ``collectWikiClaimHealth``.
    """
    out: list[WikiClaimHealth] = []
    for page in pages:
        claims = _read_attr(page, "claims") or []
        for index, claim in enumerate(claims):
            out.append(_build_wiki_claim_health(page=page, claim=claim, index=index, now=now))
    return out


# ── Contradiction clusters ───────────────────────────────────


def build_claim_contradiction_clusters(
    *,
    pages: list[Any],
    now: datetime | None = None,
) -> list[WikiClaimContradictionCluster]:
    """Group claims with the same ``claimId`` but distinct text or status.

    Mirrors OpenClaw's
    ``buildClaimContradictionClusters``. A cluster
    is emitted only when (a) ``>= 2`` pages share
    the same ``claimId`` and (b) the cluster has
    distinct texts or distinct statuses.
    """
    claim_health = collect_wiki_claim_health(pages, now)
    by_id: dict[str, list[WikiClaimHealth]] = {}
    for claim in claim_health:
        if not claim.claim_id:
            continue
        by_id.setdefault(claim.claim_id, []).append(claim)

    clusters: list[WikiClaimContradictionCluster] = []
    for claim_id, entries in by_id.items():
        if len(entries) < 2:
            continue
        distinct_texts = {_normalize_claim_text_key(entry.text) for entry in entries}
        distinct_statuses = {entry.status for entry in entries}
        if len(distinct_texts) < 2 and len(distinct_statuses) < 2:
            continue
        sorted_entries = sorted(entries, key=lambda entry: entry.page_path)
        clusters.append(
            WikiClaimContradictionCluster(
                key=claim_id,
                label=claim_id,
                entries=sorted_entries,
            )
        )
    clusters.sort(key=lambda cluster: cluster.label)
    return clusters


def build_page_contradiction_clusters(
    pages: list[Any],
) -> list[WikiPageContradictionCluster]:
    """Group page-level contradiction notes by normalized text.

    Mirrors OpenClaw's
    ``buildPageContradictionClusters``. Each page's
    ``contradictions`` list contributes one entry
    per note; entries are bucketed by the
    ``normalizeTextKey(note)`` form so casing and
    punctuation don't fragment the cluster.
    """
    by_note: dict[str, list[WikiPageContradictionEntry]] = {}
    for page in pages:
        page_path = _read_attr(page, "relativePath", "relative_path") or ""
        page_title = _read_attr(page, "title") or page_path
        raw_page_id = _read_attr(page, "id")
        page_id = raw_page_id if isinstance(raw_page_id, str) else None
        contradictions = _read_attr(page, "contradictions") or []
        for note in contradictions:
            key = _normalize_text_key(note)
            if not key:
                continue
            by_note.setdefault(key, []).append(
                WikiPageContradictionEntry(
                    page_path=page_path,
                    page_title=page_title,
                    page_id=page_id,
                    note=note,
                )
            )
    clusters: list[WikiPageContradictionCluster] = []
    for key, entries in by_note.items():
        sorted_entries = sorted(entries, key=lambda entry: entry.page_path)
        clusters.append(
            WikiPageContradictionCluster(
                key=key,
                label=entries[0].note,
                entries=sorted_entries,
            )
        )
    clusters.sort(key=lambda cluster: cluster.label)
    return clusters


__all__ = [
    "CONTESTED_CLAIM_STATUSES",
    "DAY_MS",
    "WIKI_AGING_DAYS",
    "WIKI_STALE_DAYS",
    "WikiClaimContradictionCluster",
    "WikiClaimHealth",
    "WikiFreshness",
    "WikiFreshnessLevel",
    "WikiPageContradictionCluster",
    "WikiPageContradictionEntry",
    "assess_claim_freshness",
    "assess_page_freshness",
    "build_claim_contradiction_clusters",
    "build_page_contradiction_clusters",
    "collect_wiki_claim_health",
    "is_claim_contested_status",
    "normalize_claim_status",
]
