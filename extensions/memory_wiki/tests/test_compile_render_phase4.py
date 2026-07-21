"""Tests for extensions/memory_wiki/compile_render.py.

Phase 4.3d-mr5: ports the OpenClaw dashboard body
builders (``DASHBOARD_PAGES`` block). The tests
focus on:

- ``format_wiki_link`` produces the native /
  Obsidian form, with POSIX-relative paths in
  the native form.
- ``build_open_questions_body`` lists pages with
  open questions; emits the "no questions" stub
  when the set is empty.
- ``build_contradictions_body`` includes the
  page-note + claim clusters; emits the "no
  contradictions" stub when both are empty.
- ``build_low_confidence_body`` filters pages /
  claims with ``confidence < 0.5``; sorts by
  ascending confidence; emits the empty stub.
- ``build_claim_health_body`` lists missing-
  evidence / contested / stale-or-unknown claims.
- ``build_stale_pages_body`` filters concept /
  synthesis / unmanaged raw-source bodies;
  surfaces aging + stale pages.
- ``render_wiki_dashboards`` returns a
  ``DashboardBuild`` per registered dashboard.
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

import pytest

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

from extensions.memory_wiki.compile_render import (  # noqa: E402
    DASHBOARD_BUILDERS,
    DashboardBuild,
    build_claim_health_body,
    build_contradictions_body,
    build_low_confidence_body,
    build_open_questions_body,
    build_stale_pages_body,
    format_wiki_link,
    render_wiki_dashboards,
)
from extensions.memory_wiki.config import resolve_memory_wiki_config  # noqa: E402
from extensions.memory_wiki.markdown_pages import (  # noqa: E402
    WikiClaim,
    WikiClaimEvidence,
)


def _evidence(**overrides: object) -> WikiClaimEvidence:
    """Build a minimal WikiClaimEvidence-shaped object for tests."""
    base: dict[str, object] = {
        "kind": None,
        "source_id": None,
        "path": None,
        "lines": None,
        "weight": None,
        "confidence": None,
        "privacy_tier": None,
        "note": None,
        "updated_at": None,
    }
    base.update(overrides)
    return WikiClaimEvidence(**base)  # type: ignore[arg-type]


def _page(**overrides: object) -> SimpleNamespace:
    """Build a minimal WikiPageSummary-shaped object for tests.

    Uses the OpenClaw camelCase field names so the
    claim_health module's ``_read_attr`` helper
    picks them up via its snake-case fallback.
    """
    base: dict[str, object] = {
        "absolutePath": "/vault/x.md",
        "relativePath": "entities/alpha.md",
        "kind": "entity",
        "title": "Alpha",
        "hasFrontmatter": True,
        "id": "entity.alpha",
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


@pytest.fixture
def config() -> object:
    """A resolved wiki config rooted at ``/vault``."""
    return resolve_memory_wiki_config({"vault": {"path": "/vault"}}, homedir="/h")


# ── format_wiki_link ──────────────────────────────────────


class TestFormatWikiLink:
    def test_obsidian_form(self) -> None:
        out = format_wiki_link(
            render_mode="obsidian",
            relative_path="entities/alpha.md",
            source_relative_to="",
            title="Alpha",
        )
        assert out == "[[entities/alpha|Alpha]]"

    def test_native_form_no_source_relative_to(self) -> None:
        out = format_wiki_link(
            render_mode="native",
            relative_path="entities/alpha.md",
            source_relative_to="",
            title="Alpha",
        )
        assert out == "[Alpha](entities/alpha.md)"

    def test_native_form_resolves_relative_path(self) -> None:
        out = format_wiki_link(
            render_mode="native",
            relative_path="entities/alpha.md",
            source_relative_to="syntheses/foo.md",
            title="Alpha",
        )
        # POSIX ``relpath`` from
        # ``syntheses/foo.md`` to
        # ``entities/alpha.md`` is
        # ``../entities/alpha.md``.
        assert out == "[Alpha](../entities/alpha.md)"


# ── Open Questions ────────────────────────────────────────


class TestBuildOpenQuestionsBody:
    def test_empty(self, config: object) -> None:
        out = build_open_questions_body(
            config=config,  # type: ignore[arg-type]
            pages=[],
            source_relative_to="",
        )
        assert out == "- No open questions right now."

    def test_lists_pages_with_questions(self, config: object) -> None:
        page_a = _page(
            relative_path="entities/a.md",
            title="A",
            questions=["What is X?"],
        )
        page_b = _page(
            relative_path="entities/b.md",
            title="B",
            questions=["Y or Z?", "When?"],
        )
        out = build_open_questions_body(
            config=config,  # type: ignore[arg-type]
            pages=[page_a, page_b],
            source_relative_to="",
        )
        assert "- Pages with open questions: 2" in out
        assert "[A](entities/a.md): What is X?" in out
        assert "[B](entities/b.md): Y or Z? | When?" in out

    def test_skips_pages_without_questions(self, config: object) -> None:
        page = _page(questions=[])
        out = build_open_questions_body(
            config=config,  # type: ignore[arg-type]
            pages=[page],
            source_relative_to="",
        )
        assert out == "- No open questions right now."


# ── Contradictions ────────────────────────────────────────


class TestBuildContradictionsBody:
    def test_empty(self, config: object) -> None:
        out = build_contradictions_body(
            config=config,  # type: ignore[arg-type]
            pages=[],
            now=datetime(2026, 7, 21, tzinfo=UTC),
            source_relative_to="",
        )
        assert out == "- No contradictions flagged right now."

    def test_lists_page_and_claim_clusters(self, config: object) -> None:
        # Page with a contradiction note.
        page_a = _page(
            relative_path="entities/a.md",
            title="A",
            contradictions=["Source X says Y"],
        )
        # Two pages with the same claim id but
        # distinct text → claim cluster.
        page_b = _page(
            relative_path="entities/b.md",
            title="B",
            id="shared.claim",
        )
        page_c = _page(
            relative_path="entities/c.md",
            title="C",
            id="shared.claim",
        )
        # The claims are stored on the pages; for
        # this test we add them via a quick
        # monkey-patch (the claim id drives the
        # contradiction cluster).
        from extensions.memory_wiki.markdown_pages import WikiClaim

        page_b.claims = [  # type: ignore[attr-defined]
            WikiClaim(text="alpha", id="shared.claim", status="active")
        ]
        page_c.claims = [  # type: ignore[attr-defined]
            WikiClaim(text="beta", id="shared.claim", status="active")
        ]
        out = build_contradictions_body(
            config=config,  # type: ignore[arg-type]
            pages=[page_a, page_b, page_c],
            now=datetime(2026, 7, 21, tzinfo=UTC),
            source_relative_to="",
        )
        assert "- Contradiction note clusters: 1" in out
        assert "- Competing claim clusters: 1" in out
        assert "### Page Notes" in out
        assert "Source X says Y" in out
        assert "### Claim Clusters" in out


# ── Low Confidence ────────────────────────────────────────


class TestBuildLowConfidenceBody:
    def test_empty(self, config: object) -> None:
        out = build_low_confidence_body(
            config=config,  # type: ignore[arg-type]
            pages=[],
            now=datetime(2026, 7, 21, tzinfo=UTC),
            source_relative_to="",
        )
        assert out == "- No low-confidence pages or claims right now."

    def test_filters_by_threshold(self, config: object) -> None:
        page_low = _page(
            relative_path="entities/low.md",
            title="LowPage",
            confidence=0.3,
        )
        page_high = _page(
            relative_path="entities/high.md",
            title="HighPage",
            confidence=0.9,
        )
        page_none = _page(relative_path="entities/x.md", title="X")
        out = build_low_confidence_body(
            config=config,  # type: ignore[arg-type]
            pages=[page_low, page_high, page_none],
            now=datetime(2026, 7, 21, tzinfo=UTC),
            source_relative_to="",
        )
        assert "LowPage" in out
        assert "HighPage" not in out
        assert "- Low-confidence pages: 1" in out

    def test_sorts_by_ascending_confidence(self, config: object) -> None:
        page_mid = _page(
            relative_path="entities/mid.md",
            title="MidPage",
            confidence=0.4,
        )
        page_low = _page(
            relative_path="entities/low.md",
            title="LowPage",
            confidence=0.1,
        )
        out = build_low_confidence_body(
            config=config,  # type: ignore[arg-type]
            pages=[page_mid, page_low],
            now=datetime(2026, 7, 21, tzinfo=UTC),
            source_relative_to="",
        )
        # LowPage should appear before MidPage in
        # the rendered output.
        assert out.index("LowPage") < out.index("MidPage")


# ── Claim Health ──────────────────────────────────────────


class TestBuildClaimHealthBody:
    def test_empty(self, config: object) -> None:
        # A fresh, well-evidenced, supported claim:
        # no missing-evidence, no contested, no
        # stale-or-unknown → empty stub.
        claim = WikiClaim(
            text="supported",
            status="active",
            updated_at="2026-07-21T00:00:00Z",
            evidence=[
                _evidence(updated_at="2026-07-21T00:00:00Z"),
            ],
        )
        page = _page(claims=[claim], updatedAt="2026-07-21T00:00:00Z")
        out = build_claim_health_body(
            config=config,  # type: ignore[arg-type]
            pages=[page],
            now=datetime(2026, 7, 21, tzinfo=UTC),
            source_relative_to="",
        )
        assert out == "- No claim health issues right now."

    def test_lists_missing_evidence(self, config: object) -> None:
        page = _page(claims=[WikiClaim(text="no-evidence")])
        out = build_claim_health_body(
            config=config,  # type: ignore[arg-type]
            pages=[page],
            now=datetime(2026, 7, 21, tzinfo=UTC),
            source_relative_to="",
        )
        assert "Missing Evidence" in out
        assert "- Claims missing evidence: 1" in out


# ── Stale Pages ───────────────────────────────────────────


class TestBuildStalePagesBody:
    def test_empty(self, config: object) -> None:
        # Fresh page (today).
        page = _page(updatedAt="2026-07-21T00:00:00Z")
        out = build_stale_pages_body(
            config=config,  # type: ignore[arg-type]
            pages=[page],
            now=datetime(2026, 7, 21, tzinfo=UTC),
            source_relative_to="",
        )
        assert "No aging or stale" in out

    def test_includes_stale_entity(self, config: object) -> None:
        # Page from 2025 → stale (>90 days).
        page = _page(
            relative_path="entities/old.md",
            title="OldEntity",
            updatedAt="2025-01-01T00:00:00Z",
        )
        out = build_stale_pages_body(
            config=config,  # type: ignore[arg-type]
            pages=[page],
            now=datetime(2026, 7, 21, tzinfo=UTC),
            source_relative_to="",
        )
        assert "OldEntity" in out
        assert "stale" in out

    def test_skips_concept_and_synthesis(self, config: object) -> None:
        page_concept = _page(
            relative_path="concepts/x.md",
            title="X",
            kind="concept",
            updatedAt="2025-01-01T00:00:00Z",
        )
        page_synthesis = _page(
            relative_path="syntheses/x.md",
            title="X",
            kind="synthesis",
            updatedAt="2025-01-01T00:00:00Z",
        )
        out = build_stale_pages_body(
            config=config,  # type: ignore[arg-type]
            pages=[page_concept, page_synthesis],
            now=datetime(2026, 7, 21, tzinfo=UTC),
            source_relative_to="",
        )
        assert "No aging or stale" in out


# ── Registry + orchestrator ──────────────────────────────


class TestDashboardRegistry:
    def test_exposes_five_dashboards(self) -> None:
        assert len(DASHBOARD_BUILDERS) == 5
        assert "report.open-questions" in DASHBOARD_BUILDERS
        assert "report.contradictions" in DASHBOARD_BUILDERS
        assert "report.low-confidence" in DASHBOARD_BUILDERS
        assert "report.claim-health" in DASHBOARD_BUILDERS
        assert "report.stale-pages" in DASHBOARD_BUILDERS


class TestRenderWikiDashboards:
    def test_renders_all_dashboards(self, config: object) -> None:
        builds = render_wiki_dashboards(
            config=config,  # type: ignore[arg-type]
            pages=[],
            now=datetime(2026, 7, 21, tzinfo=UTC),
        )
        assert len(builds) == 5
        assert all(isinstance(b, DashboardBuild) for b in builds)
        ids = {b.id for b in builds}
        assert ids == set(DASHBOARD_BUILDERS.keys())

    def test_include_filter(self, config: object) -> None:
        builds = render_wiki_dashboards(
            config=config,  # type: ignore[arg-type]
            pages=[],
            now=datetime(2026, 7, 21, tzinfo=UTC),
            include=["report.open-questions"],
        )
        assert [b.id for b in builds] == ["report.open-questions"]

    def test_each_build_has_id_title_path_body(self, config: object) -> None:
        builds = render_wiki_dashboards(
            config=config,  # type: ignore[arg-type]
            pages=[],
            now=datetime(2026, 7, 21, tzinfo=UTC),
        )
        for build in builds:
            assert build.id
            assert build.title
            assert build.relative_path.startswith("reports/")
            assert build.relative_path.endswith(".md")
            assert isinstance(build.body, str)
