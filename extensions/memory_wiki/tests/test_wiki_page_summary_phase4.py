"""Tests for extensions/memory_wiki/wiki_page_summary.py.

Phase 4.3d-mr3: ports the OpenClaw ``scanWikiPageSummary``
function. The tests focus on:

- A well-formed frontmatter produces a
  :class:`WikiPageSummary` with the right kind,
  title, id, aliases, sourceIds, claims, link
  graph, etc.
- A page without frontmatter is ``ignored``.
- A page with a malformed (non-mapping) YAML
  frontmatter is ``invalid-frontmatter``.
- The page kind is inferred from the first
  directory segment when the frontmatter doesn't
  pin it.
- Link targets are extracted from both Obsidian
  ``[[wikilinks]]`` and standard markdown
  ``[text](target)`` references.
- The unmanaged-raw-source-body detection
  recognizes the ``<!-- openclaw:wiki:raw-source -->``
  marker.
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

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

from extensions.memory_wiki.markdown_pages import (  # noqa: E402
    WikiClaim,
    WikiPersonCard,
    WikiRelationship,
)
from extensions.memory_wiki.wiki_page_summary import (  # noqa: E402
    WikiPageFrontmatterError,
    WikiPageSummary,
    scan_wiki_page_summary,
    scan_wiki_page_summary_from_file,
)


def _minimal_frontmatter(**overrides: object) -> str:
    """Build a minimal YAML frontmatter block."""
    fm: dict[str, object] = {
        "title": "Alpha",
        "kind": "entity",
    }
    fm.update(overrides)
    text = json.dumps(fm, ensure_ascii=False)  # JSON is a subset of YAML for our use
    return f"---\n{text}\n---\n"


class TestScanWikiPageSummary:
    def test_well_formed_page(self) -> None:
        source = (
            _minimal_frontmatter(
                id="entity.alpha",
                aliases=["Alpha", "Al"],
                sourceIds=["source.x"],
                questions=["What is X?"],
                contradictions=["Source Y says Z"],
                confidence=0.85,
            )
            + "\n# Alpha\n\nSome body text.\n\n"
            "[[entity.beta]] and [Beta](betas/beta.md).\n"
        )
        result = scan_wiki_page_summary(
            absolute_path="/vault/entities/alpha.md",
            relative_path="entities/alpha.md",
            raw_markdown=source,
        )
        assert result["status"] == "valid"
        page = result["page"]
        assert isinstance(page, WikiPageSummary)
        assert page.absolute_path == "/vault/entities/alpha.md"
        assert page.relative_path == "entities/alpha.md"
        assert page.kind == "entity"
        assert page.title == "Alpha"
        assert page.has_frontmatter is True
        assert page.id == "entity.alpha"
        assert page.aliases == ["Alpha", "Al"]
        assert page.source_ids == ["source.x"]
        assert page.questions == ["What is X?"]
        assert page.contradictions == ["Source Y says Z"]
        assert page.confidence == 0.85
        assert "entity.beta" in page.link_targets
        assert any(target.endswith("betas/beta.md") for target in page.link_targets)

    def test_no_frontmatter_is_ignored(self) -> None:
        source = "# Just a title\n\nNo frontmatter here.\n"
        result = scan_wiki_page_summary(
            absolute_path="/vault/x.md",
            relative_path="x.md",
            raw_markdown=source,
        )
        assert result["status"] == "ignored"

    def test_invalid_yaml_frontmatter(self) -> None:
        # The frontmatter opens with ``---`` but the
        # YAML inside is not a mapping.
        source = "---\n[a, b]\n---\n# Body\n"
        result = scan_wiki_page_summary(
            absolute_path="/vault/x.md",
            relative_path="x.md",
            raw_markdown=source,
        )
        assert result["status"] == "invalid-frontmatter"
        err = result["error"]
        assert isinstance(err, WikiPageFrontmatterError)
        assert err.relative_path == "x.md"

    def test_kind_inferred_from_path(self) -> None:
        # No ``kind`` in the frontmatter; the first
        # path segment drives the inference.
        # We build a custom frontmatter without
        # ``kind`` so the path-based inference wins.
        fm = json.dumps({"title": "Alpha"})
        source = f"---\n{fm}\n---\n# Body\n"
        result = scan_wiki_page_summary(
            absolute_path="/vault/syntheses/alpha.md",
            relative_path="syntheses/alpha.md",
            raw_markdown=source,
        )
        assert result["status"] == "valid"
        assert result["page"].kind == "synthesis"

    def test_explicit_kind_overrides_path(self) -> None:
        source = _minimal_frontmatter(kind="report") + "# Body\n"
        result = scan_wiki_page_summary(
            absolute_path="/vault/syntheses/alpha.md",
            relative_path="syntheses/alpha.md",
            raw_markdown=source,
        )
        assert result["page"].kind == "report"

    def test_invalid_kind_falls_back_to_path(self) -> None:
        source = _minimal_frontmatter(kind="not-a-kind") + "# Body\n"
        result = scan_wiki_page_summary(
            absolute_path="/vault/entities/alpha.md",
            relative_path="entities/alpha.md",
            raw_markdown=source,
        )
        # ``kind`` validation falls back to the
        # inferred path kind.
        assert result["page"].kind == "entity"

    def test_title_from_h1_falls_back_to_relative_path(self) -> None:
        # No ``title`` in frontmatter AND no H1
        # in the body; falls back to the relative
        # path.
        source = "---\nkind: entity\n---\n" "No heading here.\n"
        result = scan_wiki_page_summary(
            absolute_path="/vault/entities/x.md",
            relative_path="entities/x.md",
            raw_markdown=source,
        )
        # No title in frontmatter, no H1; falls back
        # to the relative path.
        assert result["page"].title == "entities/x.md"

    def test_title_from_h1_used(self) -> None:
        source = _minimal_frontmatter(title="ignored-frontmatter-title") + "# H1 Title\n\nbody\n"
        result = scan_wiki_page_summary(
            absolute_path="/vault/x.md",
            relative_path="x.md",
            raw_markdown=source,
        )
        # OpenClaw's extractTitleFromMarkdown takes
        # priority over the frontmatter ``title``.
        assert result["page"].title == "H1 Title"

    def test_claims_extracted_from_frontmatter(self) -> None:
        source = (
            _minimal_frontmatter(
                claims=[
                    {
                        "id": "c1",
                        "text": "first",
                        "status": "active",
                        "evidence": [{"sourceId": "s.1"}],
                    },
                    {"text": "second"},
                ]
            )
            + "# Body\n"
        )
        result = scan_wiki_page_summary(
            absolute_path="/vault/x.md",
            relative_path="x.md",
            raw_markdown=source,
        )
        page = result["page"]
        assert len(page.claims) == 2
        assert isinstance(page.claims[0], WikiClaim)
        assert page.claims[0].id == "c1"
        assert page.claims[0].text == "first"
        assert page.claims[0].status == "active"
        assert len(page.claims[0].evidence) == 1

    def test_person_card_extracted(self) -> None:
        source = (
            _minimal_frontmatter(
                personCard={
                    "canonicalId": "person.alpha",
                    "handles": ["@alpha"],
                }
            )
            + "# Body\n"
        )
        result = scan_wiki_page_summary(
            absolute_path="/vault/x.md",
            relative_path="x.md",
            raw_markdown=source,
        )
        card = result["page"].person_card
        assert card is not None
        assert isinstance(card, WikiPersonCard)
        assert card.canonical_id == "person.alpha"
        assert card.handles == ["@alpha"]

    def test_relationships_extracted(self) -> None:
        source = (
            _minimal_frontmatter(
                relationships=[
                    {"targetId": "entity.beta", "kind": "knows"},
                ]
            )
            + "# Body\n"
        )
        result = scan_wiki_page_summary(
            absolute_path="/vault/x.md",
            relative_path="x.md",
            raw_markdown=source,
        )
        rels = result["page"].relationships
        assert len(rels) == 1
        assert isinstance(rels[0], WikiRelationship)
        assert rels[0].target_id == "entity.beta"
        assert rels[0].kind == "knows"

    def test_raw_source_marker_detected(self) -> None:
        source = _minimal_frontmatter() + "# Title\n\n<!-- openclaw:wiki:raw-source -->\n\nbody\n"
        result = scan_wiki_page_summary(
            absolute_path="/vault/sources/raw.md",
            relative_path="sources/raw.md",
            raw_markdown=source,
        )
        assert result["page"].unmanaged_raw_source_body is True

    def test_no_raw_source_marker_default(self) -> None:
        source = _minimal_frontmatter() + "# Title\n\nnormal body\n"
        result = scan_wiki_page_summary(
            absolute_path="/vault/sources/x.md",
            relative_path="sources/x.md",
            raw_markdown=source,
        )
        assert result["page"].unmanaged_raw_source_body is False


class TestScanWikiPageSummaryFromFile:
    def test_reads_file_and_computes_relative_path(self, tmp_path: Path) -> None:
        # Create a wiki page at
        # ``tmp_path/entities/alpha.md``.
        entities_dir = tmp_path / "entities"
        entities_dir.mkdir()
        page_path = entities_dir / "alpha.md"
        page_path.write_text(
            _minimal_frontmatter(id="entity.alpha") + "# Alpha\n\n[[entity.beta]]\n",
            encoding="utf-8",
        )
        result = scan_wiki_page_summary_from_file(
            absolute_path=str(page_path),
            vault_root=str(tmp_path),
        )
        assert result["status"] == "valid"
        page = result["page"]
        # The relative path uses forward slashes.
        assert page.relative_path == "entities/alpha.md"
        assert page.kind == "entity"
        assert page.id == "entity.alpha"
