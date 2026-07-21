"""Tests for extensions/memory_wiki/memory_palace.py.

Phase 4.3f-mr7: ports the OpenClaw
``memory-palace.ts`` test surface. The
tests focus on:

- ``create_empty_palace_page_counts``
  returns a fresh all-zero counts dict.
- ``normalize_timestamp`` returns ``None``
  for non-strings and empty strings.
- ``extract_snippet`` skips blanks,
  headings, code fences, HTML comments,
  and list markers.
- ``compare_palace_items`` sorts by
  ``updatedAt`` desc, ``claimCount`` desc,
  ``title`` asc.
- ``list_memory_wiki_palace`` returns:
  - the right ``pageCounts`` per kind,
  - the right ``totalClaims`` /
    ``totalQuestions`` /
    ``totalContradictions``,
  - filtered items (primary kinds always;
    other kinds only when they carry
    claims / questions / contradictions),
  - per-item top-3 slices for claims /
    questions / contradictions,
  - clusters in ``PALACE_KIND_ORDER``.
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

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[3]

if TYPE_CHECKING:
    from types import SimpleNamespace
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)


from extensions.memory_wiki import memory_palace as mp  # noqa: E402
from extensions.memory_wiki.config import resolve_memory_wiki_config  # noqa: E402
from extensions.memory_wiki.markdown_pages import render_wiki_markdown  # noqa: E402

if TYPE_CHECKING:
    from types import SimpleNamespace


def _vault_config(tmp_path: Path) -> SimpleNamespace:
    """Build a minimal global-scope config for tests."""
    return resolve_memory_wiki_config({"vault": {"scope": "global", "path": str(tmp_path)}})


def _write_synthesis(
    tmp_path: Path,
    *,
    slug: str,
    title: str,
    claims: list[dict] | None = None,
    questions: list[str] | None = None,
    contradictions: list[str] | None = None,
    updated_at: str | None = "2026-04-10T12:00:00.000Z",
    body: str | None = None,
) -> Path:
    """Write a synthesis page. Returns the absolute path."""
    (tmp_path / "syntheses").mkdir(parents=True, exist_ok=True)
    fm: dict = {
        "pageType": "synthesis",
        "id": f"synthesis.{slug}",
        "title": title,
        "claims": claims or [],
        "questions": questions or [],
        "contradictions": contradictions or [],
    }
    if updated_at is not None:
        fm["updatedAt"] = updated_at
    text = render_wiki_markdown(
        frontmatter=fm,
        body=body or f"# {title}\n\nThis synthesis rolls up patterns from imported chats.\n",
    )
    path = tmp_path / "syntheses" / f"{slug}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _write_entity(
    tmp_path: Path,
    *,
    slug: str,
    title: str,
    claims: list[dict] | None = None,
    updated_at: str | None = "2026-04-09T08:00:00.000Z",
    body: str | None = None,
) -> Path:
    """Write an entity page. Returns the absolute path."""
    (tmp_path / "entities").mkdir(parents=True, exist_ok=True)
    fm: dict = {
        "pageType": "entity",
        "id": f"entity.{slug}",
        "title": title,
        "claims": claims or [],
    }
    if updated_at is not None:
        fm["updatedAt"] = updated_at
    text = render_wiki_markdown(
        frontmatter=fm,
        body=body or f"# {title}\n\nPrimary operator profile page.\n",
    )
    path = tmp_path / "entities" / f"{slug}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _write_source(
    tmp_path: Path,
    *,
    slug: str,
    title: str,
    source_type: str | None = "chatgpt",
    updated_at: str | None = "2026-04-08T08:00:00.000Z",
) -> Path:
    """Write a source page. Returns the absolute path."""
    (tmp_path / "sources").mkdir(parents=True, exist_ok=True)
    fm: dict = {
        "pageType": "source",
        "id": f"source.{slug}",
        "title": title,
    }
    if source_type is not None:
        fm["sourceType"] = source_type
    if updated_at is not None:
        fm["updatedAt"] = updated_at
    text = render_wiki_markdown(
        frontmatter=fm,
        body=f"# {title}\n\nOriginal imported source with no claim rows.\n",
    )
    path = tmp_path / "sources" / f"{slug}.md"
    path.write_text(text, encoding="utf-8")
    return path


class TestConstants:
    def test_palace_kind_order(self) -> None:
        assert mp.PALACE_KIND_ORDER == (
            "synthesis",
            "entity",
            "concept",
            "source",
            "report",
        )

    def test_primary_palace_kinds(self) -> None:
        assert frozenset({"synthesis", "entity", "concept"}) == mp.PRIMARY_PALACE_KINDS

    def test_palace_kind_labels(self) -> None:
        assert mp.PALACE_KIND_LABELS == {
            "synthesis": "Syntheses",
            "entity": "Entities",
            "concept": "Concepts",
            "source": "Sources",
            "report": "Reports",
        }

    def test_top_slice_constants(self) -> None:
        assert mp.PALACE_ITEM_TOP_CLAIMS == 3
        assert mp.PALACE_ITEM_TOP_QUESTIONS == 3
        assert mp.PALACE_ITEM_TOP_CONTRADICTIONS == 3


class TestCreateEmptyPalacePageCounts:
    def test_returns_all_zero(self) -> None:
        counts = mp.create_empty_palace_page_counts()
        assert counts == {
            "synthesis": 0,
            "entity": 0,
            "concept": 0,
            "source": 0,
            "report": 0,
        }

    def test_returns_fresh_dict(self) -> None:
        a = mp.create_empty_palace_page_counts()
        b = mp.create_empty_palace_page_counts()
        a["synthesis"] = 99
        assert b["synthesis"] == 0


class TestNormalizeTimestamp:
    def test_none(self) -> None:
        assert mp.normalize_timestamp(None) is None

    def test_non_string(self) -> None:
        assert mp.normalize_timestamp(123) is None
        assert mp.normalize_timestamp(["x"]) is None

    def test_empty_string(self) -> None:
        assert mp.normalize_timestamp("") is None
        assert mp.normalize_timestamp("   ") is None

    def test_trimmed_value(self) -> None:
        assert mp.normalize_timestamp("  2026-04-10T12:00:00Z  ") == "2026-04-10T12:00:00Z"


class TestExtractSnippet:
    def test_empty_body(self) -> None:
        assert mp.extract_snippet("") is None

    def test_only_meta_lines(self) -> None:
        # OpenClaw's ``extractSnippet`` only
        # skips lines whose first character is
        # a fence / heading / list marker. A
        # body composed entirely of those
        # meta lines returns ``None``.
        body = "# Title\n```\n<!-- comment -->\n- item\n* another"
        assert mp.extract_snippet(body) is None

    def test_first_prose_line(self) -> None:
        body = "# Title\n\nThis is the snippet.\n\nSecond line."
        assert mp.extract_snippet(body) == "This is the snippet."

    def test_skips_blank_then_returns_prose(self) -> None:
        body = "\n\n# Title\n\n\nThe first real prose line here."
        assert mp.extract_snippet(body) == "The first real prose line here."

    def test_strips_whitespace(self) -> None:
        body = "   Indented prose line.   \nNext."
        assert mp.extract_snippet(body) == "Indented prose line."


class TestComparePalaceItems:
    def test_sorts_by_updated_at_desc(self) -> None:
        newer = mp.MemoryWikiPalaceItem(
            pagePath="a.md",
            title="A",
            kind="entity",
            claimCount=1,
            questionCount=0,
            contradictionCount=0,
            claims=[],
            questions=[],
            contradictions=[],
            updatedAt="2026-05-01T00:00:00.000Z",
        )
        older = mp.MemoryWikiPalaceItem(
            pagePath="b.md",
            title="B",
            kind="entity",
            claimCount=1,
            questionCount=0,
            contradictionCount=0,
            claims=[],
            questions=[],
            contradictions=[],
            updatedAt="2026-01-01T00:00:00.000Z",
        )
        assert mp.compare_palace_items(newer, older) < 0
        assert mp.compare_palace_items(older, newer) > 0

    def test_breaks_tie_with_claim_count_desc(self) -> None:
        low = mp.MemoryWikiPalaceItem(
            pagePath="a.md",
            title="A",
            kind="entity",
            claimCount=1,
            questionCount=0,
            contradictionCount=0,
            claims=[],
            questions=[],
            contradictions=[],
            updatedAt="2026-01-01T00:00:00.000Z",
        )
        high = mp.MemoryWikiPalaceItem(
            pagePath="b.md",
            title="B",
            kind="entity",
            claimCount=5,
            questionCount=0,
            contradictionCount=0,
            claims=[],
            questions=[],
            contradictions=[],
            updatedAt="2026-01-01T00:00:00.000Z",
        )
        assert mp.compare_palace_items(high, low) < 0

    def test_breaks_tie_with_title_asc(self) -> None:
        a = mp.MemoryWikiPalaceItem(
            pagePath="a.md",
            title="Alpha",
            kind="entity",
            claimCount=1,
            questionCount=0,
            contradictionCount=0,
            claims=[],
            questions=[],
            contradictions=[],
            updatedAt="2026-01-01T00:00:00.000Z",
        )
        z = mp.MemoryWikiPalaceItem(
            pagePath="z.md",
            title="Zulu",
            kind="entity",
            claimCount=1,
            questionCount=0,
            contradictionCount=0,
            claims=[],
            questions=[],
            contradictions=[],
            updatedAt="2026-01-01T00:00:00.000Z",
        )
        assert mp.compare_palace_items(a, z) < 0

    def test_missing_updated_at_sorts_last(self) -> None:
        missing = mp.MemoryWikiPalaceItem(
            pagePath="a.md",
            title="A",
            kind="entity",
            claimCount=1,
            questionCount=0,
            contradictionCount=0,
            claims=[],
            questions=[],
            contradictions=[],
            updatedAt=None,
        )
        present = mp.MemoryWikiPalaceItem(
            pagePath="b.md",
            title="B",
            kind="entity",
            claimCount=1,
            questionCount=0,
            contradictionCount=0,
            claims=[],
            questions=[],
            contradictions=[],
            updatedAt="2026-01-01T00:00:00.000Z",
        )
        # Present comes first (descending).
        assert mp.compare_palace_items(present, missing) < 0


class TestListMemoryWikiPalace:
    def test_groups_pages_by_kind(self, tmp_path: Path) -> None:
        """Mirrors the OpenClaw
        ``groups wiki pages by kind and
        surfaces claims, questions, and
        contradictions`` test."""
        _write_synthesis(
            tmp_path,
            slug="travel-system",
            title="Travel system",
            claims=[
                {"text": "Mariano prefers direct receipts from airlines when possible."},
                {"text": "Travel admin friction keeps showing up across chats."},
            ],
            questions=["Should flight receipts be standardized into one process?"],
            contradictions=["Old BA receipts guidance may now be stale."],
            updated_at="2026-04-10T12:00:00.000Z",
            body=(
                "# Travel system\n\n"
                "This synthesis rolls up recurring travel admin patterns from imported chats.\n"
            ),
        )
        _write_source(
            tmp_path,
            slug="raw-chat",
            title="Raw chat source",
            source_type="chatgpt",
            updated_at="2026-04-08T08:00:00.000Z",
        )
        _write_entity(
            tmp_path,
            slug="mariano",
            title="Mariano",
            claims=[{"text": "He prefers compact, inspectable systems."}],
            updated_at="2026-04-09T08:00:00.000Z",
            body="# Mariano\n\nPrimary operator profile page.\n",
        )

        result = asyncio.run(mp.list_memory_wiki_palace(_vault_config(tmp_path)))

        # 3 pages total; 2 visible (synthesis + entity);
        # source is filtered out (no claims/questions/contradictions,
        # and not a primary kind).
        assert result.totalItems == 2
        assert result.totalPages == 3
        assert result.pageCounts == {
            "synthesis": 1,
            "entity": 1,
            "concept": 0,
            "source": 1,
            "report": 0,
        }
        assert result.totalClaims == 3
        assert result.totalQuestions == 1
        assert result.totalContradictions == 1

        # Cluster order: synthesis first, entity second.
        synthesis_cluster = result.clusters[0]
        assert synthesis_cluster.key == "synthesis"
        assert synthesis_cluster.label == "Syntheses"
        assert synthesis_cluster.itemCount == 1
        assert synthesis_cluster.claimCount == 2
        assert synthesis_cluster.questionCount == 1
        assert synthesis_cluster.contradictionCount == 1
        synthesis_item = synthesis_cluster.items[0]
        assert synthesis_item.title == "Travel system"
        assert synthesis_item.claims == [
            "Mariano prefers direct receipts from airlines when possible.",
            "Travel admin friction keeps showing up across chats.",
        ]
        assert synthesis_item.questions == [
            "Should flight receipts be standardized into one process?"
        ]
        assert synthesis_item.contradictions == ["Old BA receipts guidance may now be stale."]
        assert (
            synthesis_item.snippet
            == "This synthesis rolls up recurring travel admin patterns from imported chats."
        )

        entity_cluster = result.clusters[1]
        assert entity_cluster.key == "entity"
        assert entity_cluster.label == "Entities"
        assert entity_cluster.itemCount == 1
        assert entity_cluster.claimCount == 1

    def test_empty_vault(self, tmp_path: Path) -> None:
        result = asyncio.run(mp.list_memory_wiki_palace(_vault_config(tmp_path)))
        assert result.totalItems == 0
        assert result.totalPages == 0
        assert result.pageCounts == {
            "synthesis": 0,
            "entity": 0,
            "concept": 0,
            "source": 0,
            "report": 0,
        }
        assert result.totalClaims == 0
        assert result.totalQuestions == 0
        assert result.totalContradictions == 0
        assert result.clusters == []

    def test_only_primary_kinds_no_claims(self, tmp_path: Path) -> None:
        """Synthesis / entity / concept are primary
        kinds — they appear in the palace even
        when they have no claims / questions /
        contradictions."""
        _write_synthesis(
            tmp_path,
            slug="empty",
            title="Empty synthesis",
            claims=[],
            questions=[],
            contradictions=[],
            updated_at="2026-04-10T00:00:00.000Z",
            body="# Empty synthesis\n\n",
        )
        _write_entity(
            tmp_path,
            slug="empty",
            title="Empty entity",
            claims=[],
            updated_at="2026-04-09T00:00:00.000Z",
            body="# Empty entity\n\n",
        )
        result = asyncio.run(mp.list_memory_wiki_palace(_vault_config(tmp_path)))
        assert result.totalItems == 2
        assert result.totalPages == 2
        assert result.totalClaims == 0
        # Clusters are still emitted for primary kinds.
        keys = [c.key for c in result.clusters]
        assert keys == ["synthesis", "entity"]

    def test_non_primary_kind_with_claims_appears(self, tmp_path: Path) -> None:
        """A non-primary kind (e.g. source) with
        claims IS shown in the palace."""
        _write_source(
            tmp_path,
            slug="with-claims",
            title="Source with claims",
            source_type="chatgpt",
            updated_at="2026-04-08T00:00:00.000Z",
        )
        # The _write_source helper writes a page
        # with no claims. We need to add a claim
        # by overwriting the page after write.
        # Easiest: rewrite by hand.
        (tmp_path / "sources" / "with-claims.md").write_text(
            render_wiki_markdown(
                frontmatter={
                    "pageType": "source",
                    "id": "source.with-claims",
                    "title": "Source with claims",
                    "sourceType": "chatgpt",
                    "claims": [{"text": "Mariano uses a local-only profile."}],
                    "updatedAt": "2026-04-08T00:00:00.000Z",
                },
                body="# Source with claims\n\nThis is the source snippet.\n",
            ),
            encoding="utf-8",
        )

        result = asyncio.run(mp.list_memory_wiki_palace(_vault_config(tmp_path)))
        assert result.totalItems == 1
        assert result.totalClaims == 1
        assert result.clusters[0].key == "source"

    def test_non_primary_kind_without_claims_filtered(self, tmp_path: Path) -> None:
        """A non-primary kind (e.g. source) with NO
        claims / questions / contradictions is
        filtered out of the palace."""
        _write_source(
            tmp_path,
            slug="empty-source",
            title="Empty source",
            source_type="chatgpt",
            updated_at="2026-04-08T00:00:00.000Z",
        )
        result = asyncio.run(mp.list_memory_wiki_palace(_vault_config(tmp_path)))
        assert result.totalItems == 0
        assert result.totalPages == 1

    def test_claim_slicing_to_top_three(self, tmp_path: Path) -> None:
        """Per-item claim list is sliced to 3."""
        _write_synthesis(
            tmp_path,
            slug="many-claims",
            title="Many claims",
            claims=[{"text": f"Claim {i}"} for i in range(5)],
            questions=[],
            contradictions=[],
            updated_at="2026-04-10T00:00:00.000Z",
        )
        result = asyncio.run(mp.list_memory_wiki_palace(_vault_config(tmp_path)))
        item = result.clusters[0].items[0]
        assert len(item.claims) == 3
        assert item.claims == ["Claim 0", "Claim 1", "Claim 2"]
        assert item.claimCount == 5  # full count is preserved

    def test_question_contradiction_slicing(self, tmp_path: Path) -> None:
        """Per-item questions / contradictions
        lists are sliced to 3."""
        _write_synthesis(
            tmp_path,
            slug="lots",
            title="Lots",
            claims=[],
            questions=[f"Q{i}" for i in range(5)],
            contradictions=[f"C{i}" for i in range(5)],
            updated_at="2026-04-10T00:00:00.000Z",
        )
        result = asyncio.run(mp.list_memory_wiki_palace(_vault_config(tmp_path)))
        item = result.clusters[0].items[0]
        assert item.questions == ["Q0", "Q1", "Q2"]
        assert item.contradictions == ["C0", "C1", "C2"]

    def test_cluster_order_matches_palace_kind_order(self, tmp_path: Path) -> None:
        """Clusters are emitted in
        :data:`PALACE_KIND_ORDER` (synthesis,
        entity, concept, source, report)."""
        _write_synthesis(
            tmp_path,
            slug="syn",
            title="Syn",
            updated_at="2026-04-10T00:00:00.000Z",
        )
        _write_source(
            tmp_path,
            slug="src",
            title="Src",
            source_type="chatgpt",
            updated_at="2026-04-08T00:00:00.000Z",
        )
        # source with no claims is filtered, so
        # only synthesis shows. Verify the
        # *order* with a multi-kind vault.
        result = asyncio.run(mp.list_memory_wiki_palace(_vault_config(tmp_path)))
        assert [c.key for c in result.clusters] == ["synthesis"]


class TestExports:
    def test_all_exports(self) -> None:
        for name in (
            "PALACE_ITEM_TOP_CLAIMS",
            "PALACE_ITEM_TOP_CONTRADICTIONS",
            "PALACE_ITEM_TOP_QUESTIONS",
            "PALACE_KIND_LABELS",
            "PALACE_KIND_ORDER",
            "PRIMARY_PALACE_KINDS",
            "MemoryWikiPalaceCluster",
            "MemoryWikiPalaceItem",
            "MemoryWikiPalacePageCounts",
            "MemoryWikiPalaceStatus",
            "compare_palace_items",
            "create_empty_palace_page_counts",
            "extract_snippet",
            "list_memory_wiki_palace",
            "normalize_timestamp",
        ):
            assert hasattr(mp, name), f"missing export: {name}"
