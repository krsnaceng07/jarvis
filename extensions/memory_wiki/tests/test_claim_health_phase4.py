"""Tests for extensions/memory_wiki/claim_health.py.

Phase 4.3d-mr2: ports the OpenClaw claim-health
helpers. The tests focus on:

- ``normalizeClaimStatus`` lowercases + defaults to
  ``"supported"`` on blank input.
- ``isClaimContestedStatus`` returns True for the
  four contested / contradicted / refuted /
  superseded values.
- ``assessPageFreshness`` / ``assessClaimFreshness``
  return the right ``level`` for the
  ``WIKI_AGING_DAYS`` (30) / ``WIKI_STALE_DAYS`` (90)
  cutoffs.
- ``assessClaimFreshness`` picks the latest
  timestamp across the claim + its evidence.
- ``collectWikiClaimHealth`` flattens pages into
  per-claim rows with the OpenClaw-shaped ``key``.
- ``buildClaimContradictionClusters`` groups
  claims with the same ``id`` but distinct text or
  status; skips singletons.
- ``buildPageContradictionClusters`` groups
  page-level contradiction notes by normalized
  text.
"""

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

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

from extensions.memory_wiki.claim_health import (  # noqa: E402
    WIKI_AGING_DAYS,
    WIKI_STALE_DAYS,
    WikiClaimContradictionCluster,
    WikiClaimHealth,
    WikiFreshness,
    WikiPageContradictionCluster,
    assess_claim_freshness,
    assess_page_freshness,
    build_claim_contradiction_clusters,
    build_page_contradiction_clusters,
    collect_wiki_claim_health,
    is_claim_contested_status,
    normalize_claim_status,
)

# ── Helpers ──────────────────────────────────────────────────


def _page(**overrides: object) -> SimpleNamespace:
    """Build a minimal WikiPageSummary-shaped object for tests."""
    base: dict[str, object] = {
        "absolutePath": "/vault/x.md",
        "relativePath": "x.md",
        "kind": "entity",
        "title": "X",
        "hasFrontmatter": True,
        "id": None,
        "pageType": None,
        "entityType": None,
        "canonicalId": None,
        "aliases": [],
        "sourceIds": [],
        "linkTargets": [],
        "claims": [],
        "contradictions": [],
        "questions": [],
        "confidence": None,
        "privacyTier": None,
        "personCard": None,
        "relationships": [],
        "bestUsedFor": [],
        "notEnoughFor": [],
        "sourceType": None,
        "provenanceMode": None,
        "importedSourceBody": None,
        "generatedSourceBody": None,
        "unmanagedRawSourceBody": False,
        "sourcePath": None,
        "bridgeRelativePath": None,
        "bridgeWorkspaceDir": None,
        "unsafeLocalConfiguredPath": None,
        "unsafeLocalRelativePath": None,
        "lastRefreshedAt": None,
        "updatedAt": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _claim(**overrides: object) -> SimpleNamespace:
    """Build a minimal WikiClaim-shaped object for tests."""
    base: dict[str, object] = {
        "text": "alpha",
        "id": None,
        "status": "supported",
        "confidence": None,
        "evidence": [],
        "updatedAt": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _evidence(**overrides: object) -> SimpleNamespace:
    """Build a minimal WikiClaimEvidence-shaped object for tests."""
    base: dict[str, object] = {
        "kind": None,
        "sourceId": None,
        "path": None,
        "lines": None,
        "weight": None,
        "confidence": None,
        "privacyTier": None,
        "note": None,
        "updatedAt": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ── Status normalization ────────────────────────────────────


class TestNormalizeClaimStatus:
    def test_lowercases(self) -> None:
        assert normalize_claim_status("SUPPORTED") == "supported"

    def test_trims_whitespace(self) -> None:
        assert normalize_claim_status("  contested  ") == "contested"

    def test_blank_defaults_to_supported(self) -> None:
        assert normalize_claim_status("") == "supported"
        assert normalize_claim_status(None) == "supported"
        assert normalize_claim_status("   ") == "supported"


class TestIsClaimContestedStatus:
    def test_contested_values(self) -> None:
        for status in ("contested", "contradicted", "refuted", "superseded"):
            assert is_claim_contested_status(status) is True

    def test_non_contested_values(self) -> None:
        for status in ("supported", "active", "draft", ""):
            assert is_claim_contested_status(status) is False

    def test_case_insensitive(self) -> None:
        assert is_claim_contested_status("CONTESTED") is True


# ── Page freshness ──────────────────────────────────────────


class TestAssessPageFreshness:
    def test_missing_timestamp_is_unknown(self) -> None:
        result = assess_page_freshness(_page())
        assert result.level == "unknown"
        assert result.reason == "missing updatedAt"

    def test_fresh_within_30_days(self) -> None:
        now = datetime(2026, 7, 21, tzinfo=UTC)
        page = _page(
            updatedAt="2026-07-01T00:00:00Z"  # 20 days before now
        )
        result = assess_page_freshness(page, now=now)
        assert result.level == "fresh"
        assert result.days_since_touch == 20
        assert result.last_touched_at == "2026-07-01T00:00:00Z"

    def test_aging_between_30_and_90_days(self) -> None:
        now = datetime(2026, 7, 21, tzinfo=UTC)
        page = _page(
            updatedAt="2026-05-22T00:00:00Z"  # 60 days before now
        )
        result = assess_page_freshness(page, now=now)
        assert result.level == "aging"
        assert result.days_since_touch == 60

    def test_stale_after_90_days(self) -> None:
        now = datetime(2026, 7, 21, tzinfo=UTC)
        page = _page(
            updatedAt="2026-01-01T00:00:00Z"  # ~ 201 days before now
        )
        result = assess_page_freshness(page, now=now)
        assert result.level == "stale"
        # ``result.days_since_touch`` is always set
        # for non-unknown freshness levels.
        assert result.days_since_touch is not None
        assert result.days_since_touch >= WIKI_STALE_DAYS

    def test_unparseable_timestamp_is_unknown(self) -> None:
        result = assess_page_freshness(
            _page(updatedAt="not a date"),
        )
        assert result.level == "unknown"


# ── Claim freshness ─────────────────────────────────────────


class TestAssessClaimFreshness:
    def test_uses_latest_evidence_timestamp(self) -> None:
        now = datetime(2026, 7, 21, tzinfo=UTC)
        page = _page(updatedAt="2025-01-01T00:00:00Z")
        claim = _claim(
            updatedAt="2025-01-02T00:00:00Z",
            evidence=[
                _evidence(updatedAt="2026-06-01T00:00:00Z"),  # latest
                _evidence(updatedAt="2025-12-01T00:00:00Z"),
            ],
        )
        result = assess_claim_freshness(page=page, claim=claim, now=now)
        assert result.last_touched_at == "2026-06-01T00:00:00Z"
        # 2026-06-01 -> 2026-07-21 is 50 days; aging
        # (30-90 day window). The point of the test
        # is that the latest evidence timestamp
        # wins, not the freshness bucket.
        assert result.level == "aging"
        assert result.days_since_touch == 50

    def test_falls_back_to_page_when_no_claim_timestamp(self) -> None:
        now = datetime(2026, 7, 21, tzinfo=UTC)
        page = _page(updatedAt="2026-07-01T00:00:00Z")
        claim = _claim(updatedAt=None, evidence=[])
        result = assess_claim_freshness(page=page, claim=claim, now=now)
        assert result.last_touched_at == "2026-07-01T00:00:00Z"
        assert result.level == "fresh"

    def test_unknown_when_no_timestamps_anywhere(self) -> None:
        page = _page(updatedAt=None)
        claim = _claim(updatedAt=None, evidence=[])
        result = assess_claim_freshness(page=page, claim=claim)
        assert result.level == "unknown"


# ── collectWikiClaimHealth ──────────────────────────────────


class TestCollectWikiClaimHealth:
    def test_flattens_pages_into_rows(self) -> None:
        now = datetime(2026, 7, 21, tzinfo=UTC)
        page_a = _page(
            relativePath="a.md",
            title="A",
            updatedAt="2026-07-01T00:00:00Z",
            claims=[
                _claim(
                    id="c1",
                    text="foo",
                    status="active",
                    confidence=0.7,
                    evidence=[_evidence(sourceId="s.1")],
                ),
            ],
        )
        page_b = _page(
            relativePath="b.md",
            title="B",
            updatedAt="2026-07-02T00:00:00Z",
            claims=[
                _claim(text="bar"),  # no id
            ],
        )
        rows = collect_wiki_claim_health([page_a, page_b], now=now)
        assert len(rows) == 2
        assert isinstance(rows[0], WikiClaimHealth)
        assert rows[0].key == "a.md#c1"
        assert rows[0].page_id is None
        assert rows[0].claim_id == "c1"
        assert rows[0].confidence == 0.7
        assert rows[0].evidence_count == 1
        assert rows[0].missing_evidence is False
        # The no-id claim uses the fallback key.
        assert rows[1].key == "b.md#claim-1"
        assert rows[1].claim_id is None

    def test_missing_evidence_flag(self) -> None:
        page = _page(claims=[_claim(text="x")])
        rows = collect_wiki_claim_health([page])
        assert rows[0].missing_evidence is True

    def test_includes_page_id_when_present(self) -> None:
        page = _page(
            id="entity.alpha",
            claims=[_claim(id="c1", text="x")],
        )
        rows = collect_wiki_claim_health([page])
        assert rows[0].page_id == "entity.alpha"


# ── buildClaimContradictionClusters ─────────────────────────


class TestBuildClaimContradictionClusters:
    def test_groups_claims_with_same_id_and_distinct_text(self) -> None:
        now = datetime(2026, 7, 21, tzinfo=UTC)
        page_a = _page(
            relativePath="a.md",
            claims=[_claim(id="c1", text="foo", status="active")],
        )
        page_b = _page(
            relativePath="b.md",
            claims=[_claim(id="c1", text="bar", status="active")],
        )
        clusters = build_claim_contradiction_clusters(pages=[page_a, page_b], now=now)
        assert len(clusters) == 1
        assert isinstance(clusters[0], WikiClaimContradictionCluster)
        assert clusters[0].key == "c1"
        assert len(clusters[0].entries) == 2

    def test_groups_on_distinct_status_too(self) -> None:
        now = datetime(2026, 7, 21, tzinfo=UTC)
        page_a = _page(
            relativePath="a.md",
            claims=[_claim(id="c1", text="same", status="active")],
        )
        page_b = _page(
            relativePath="b.md",
            claims=[_claim(id="c1", text="same", status="contested")],
        )
        clusters = build_claim_contradiction_clusters(pages=[page_a, page_b], now=now)
        assert len(clusters) == 1

    def test_skips_singletons(self) -> None:
        page = _page(claims=[_claim(id="c1", text="foo")])
        assert build_claim_contradiction_clusters(pages=[page]) == []

    def test_skips_id_less_claims(self) -> None:
        page_a = _page(claims=[_claim(text="foo")])
        page_b = _page(claims=[_claim(text="bar")])
        assert build_claim_contradiction_clusters(pages=[page_a, page_b]) == []

    def test_skips_identical_claims(self) -> None:
        # Two pages with the same id, text, AND
        # status: no contradiction.
        page_a = _page(
            relativePath="a.md",
            claims=[_claim(id="c1", text="foo", status="active")],
        )
        page_b = _page(
            relativePath="b.md",
            claims=[_claim(id="c1", text="foo", status="active")],
        )
        assert build_claim_contradiction_clusters(pages=[page_a, page_b]) == []


# ── buildPageContradictionClusters ──────────────────────────


class TestBuildPageContradictionClusters:
    def test_groups_normalized_notes(self) -> None:
        page_a = _page(
            relativePath="a.md",
            title="A",
            contradictions=["Source X says Y."],
        )
        page_b = _page(
            relativePath="b.md",
            title="B",
            contradictions=["source x says y."],  # case + space differ
        )
        clusters = build_page_contradiction_clusters([page_a, page_b])
        assert len(clusters) == 1
        assert isinstance(clusters[0], WikiPageContradictionCluster)
        assert len(clusters[0].entries) == 2

    def test_different_notes_different_clusters(self) -> None:
        page_a = _page(contradictions=["alpha"])
        page_b = _page(contradictions=["beta"])
        clusters = build_page_contradiction_clusters([page_a, page_b])
        assert len(clusters) == 2

    def test_empty_pages(self) -> None:
        assert build_page_contradiction_clusters([]) == []

    def test_label_uses_first_entry_note(self) -> None:
        page = _page(contradictions=["alpha note"])
        clusters = build_page_contradiction_clusters([page])
        assert clusters[0].label == "alpha note"


# ── Constants smoke test ────────────────────────────────────


class TestConstants:
    def test_aging_days(self) -> None:
        assert WIKI_AGING_DAYS == 30

    def test_stale_days(self) -> None:
        assert WIKI_STALE_DAYS == 90


# ── Freshness dataclass smoke test ──────────────────────────


class TestWikiFreshnessDataclass:
    def test_unknown_default(self) -> None:
        result = WikiFreshness("unknown", "missing updatedAt")
        assert result.days_since_touch is None
        assert result.last_touched_at is None

    def test_with_metrics(self) -> None:
        result = WikiFreshness("stale", "last touched 2024-01-01", 200, "2024-01-01")
        assert result.days_since_touch == 200
        assert result.last_touched_at == "2024-01-01"
