"""Tests for extensions/memory_wiki/markdown_pages.py.

Phase 4.3c-mr2: ports the OpenClaw markdown.ts
type definitions, normalization helpers, slug +
filename helpers, markdown link extraction, and the
``renderWikiMarkdown`` writer. The full
``scanWikiPage`` (mdast-based) lands in 4.3d
alongside the compile pipeline.

The tests focus on:
- Slug + filename helpers respect the
  ``MAX_WIKI_*_BYTES`` caps.
- ``render_wiki_markdown`` round-trips a complete
  ``---\\n<fm>\\n---\\n\\n<body>`` block.
- ``extract_title_from_markdown`` returns the first
  H1; missing / blank inputs return ``None``.
- ``normalize_optional_number`` /
  ``normalize_optional_string_list`` /
  ``normalize_source_ids`` match the OpenClaw
  coercion contract.
- ``normalize_wiki_claim_evidence`` /
  ``normalize_wiki_claims`` /
  ``normalize_wiki_person_card`` /
  ``normalize_wiki_relationships`` handle the empty
  case, the well-formed case, and the malformed
  case.
- ``extract_wiki_links`` collects Obsidian
  ``[[wikilinks]]`` and standard markdown links;
  ignores the auto-generated ``## Related`` block;
  ignores URLs in fenced / indented code blocks;
  de-duplicates while preserving first occurrence.
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
    WIKI_RELATED_END_MARKER,
    WIKI_RELATED_START_MARKER,
    WikiClaim,
    WikiPersonCard,
    WikiRelationship,
    create_wiki_page_filename,
    extract_title_from_markdown,
    extract_wiki_links,
    normalize_optional_number,
    normalize_optional_string_list,
    normalize_source_ids,
    normalize_wiki_claim_evidence,
    normalize_wiki_claims,
    normalize_wiki_person_card,
    normalize_wiki_relationships,
    render_wiki_markdown,
    slugify_wiki_page_stem,
    slugify_wiki_segment,
)


class TestSlugifyWikiSegment:
    def test_lowercases_and_dashes(self) -> None:
        assert slugify_wiki_segment("Alpha Bravo") == "alpha-bravo"

    def test_collapses_runs_of_dashes(self) -> None:
        assert slugify_wiki_segment("alpha---bravo") == "alpha-bravo"

    def test_trims_leading_trailing_dashes(self) -> None:
        assert slugify_wiki_segment("--alpha--") == "alpha"

    def test_empty_returns_page(self) -> None:
        assert slugify_wiki_segment("") == "page"

    def test_only_special_chars_returns_page(self) -> None:
        assert slugify_wiki_segment("///") == "page"

    def test_long_input_is_capped_with_hash(self) -> None:
        long = "a" * 1000
        out = slugify_wiki_segment(long)
        # The cap is ``MAX_WIKI_SEGMENT_BYTES`` (240
        # UTF-8 bytes) with a 12-char hash suffix.
        assert len(out.encode("utf-8")) <= 240
        # Hash suffix format: ``-<12 hex>``.
        suffix = out.rsplit("-", 1)[-1]
        assert len(suffix) == 12
        assert all(c in "0123456789abcdef" for c in suffix)


class TestSlugifyWikiPageStem:
    def test_reserved_stem_gets_hash(self) -> None:
        out = slugify_wiki_page_stem("index")
        assert out != "index"
        assert out.startswith("index-")
        suffix = out.rsplit("-", 1)[-1]
        assert len(suffix) == 12

    def test_normal_stem_passes_through(self) -> None:
        assert slugify_wiki_page_stem("alpha-bravo") == "alpha-bravo"


class TestCreateWikiPageFilename:
    def test_default_extension(self) -> None:
        out = create_wiki_page_filename("alpha")
        assert out.endswith(".md")

    def test_normalizes_extension(self) -> None:
        out = create_wiki_page_filename("alpha", extension="md")
        assert out.endswith(".md")

    def test_long_stem_capped(self) -> None:
        out = create_wiki_page_filename("a" * 1000)
        assert out.endswith(".md")
        # The total byte length of the stem part is
        # bounded by
        # ``MAX_WIKI_SAFE_WRITE_FILENAME_COMPONENT_BYTES``
        # minus the extension.
        stem = out[:-3]
        assert len(stem.encode("utf-8")) <= 252


class TestRenderWikiMarkdown:
    def test_renders_frontmatter_and_body(self) -> None:
        out = render_wiki_markdown(
            frontmatter={"title": "Alpha", "kind": "entity"},
            body="# Body\n\nSome text.\n",
        )
        assert out.startswith("---\n")
        assert "title: Alpha" in out
        assert "kind: entity" in out
        assert "---" in out.split("\n\n", 1)[0]
        # Body is included.
        assert "# Body" in out

    def test_strips_leading_whitespace_from_body(self) -> None:
        out = render_wiki_markdown(
            frontmatter={"title": "Alpha"},
            body="\n\n\n# Body\n",
        )
        # The first non-frontmatter content is
        # ``# Body`` (no leading blank lines).
        body_part = out.split("---", 2)[-1].lstrip("\n")
        assert body_part.startswith("# Body")

    def test_ends_with_trailing_newline(self) -> None:
        out = render_wiki_markdown(
            frontmatter={"title": "Alpha"},
            body="# Body",
        )
        assert out.endswith("\n")


class TestExtractTitleFromMarkdown:
    def test_first_h1(self) -> None:
        body = "Some intro.\n\n# Alpha\n\n## Subheading\n"
        assert extract_title_from_markdown(body) == "Alpha"

    def test_no_h1(self) -> None:
        assert extract_title_from_markdown("## Not an H1\n") is None

    def test_blank_input(self) -> None:
        assert extract_title_from_markdown("") is None

    def test_trims_whitespace(self) -> None:
        body = "#   Spaced   \n"
        assert extract_title_from_markdown(body) == "Spaced"


class TestNormalizeOptionalNumber:
    def test_int(self) -> None:
        assert normalize_optional_number(42) == 42.0

    def test_float(self) -> None:
        assert normalize_optional_number(3.14) == 3.14

    def test_string_number(self) -> None:
        assert normalize_optional_number("1.5") == 1.5

    def test_invalid_string(self) -> None:
        assert normalize_optional_number("nope") is None

    def test_nan_string(self) -> None:
        assert normalize_optional_number("nan") is None

    def test_bool_returns_none(self) -> None:
        assert normalize_optional_number(True) is None

    def test_empty_string(self) -> None:
        assert normalize_optional_number("") is None

    def test_none(self) -> None:
        assert normalize_optional_number(None) is None


class TestNormalizeOptionalStringList:
    def test_list_of_strings(self) -> None:
        assert normalize_optional_string_list(["a", "b", "c"]) == [
            "a",
            "b",
            "c",
        ]

    def test_trims_and_dedupes(self) -> None:
        assert normalize_optional_string_list(["a", "  b  ", "a", "", "b"]) == ["a", "b"]

    def test_string_input_wrapped(self) -> None:
        assert normalize_optional_string_list("solo") == ["solo"]

    def test_non_list_non_string_returns_empty(self) -> None:
        assert normalize_optional_string_list(None) == []
        assert normalize_optional_string_list(42) == []

    def test_filters_non_strings(self) -> None:
        assert normalize_optional_string_list(["a", 1, None, "b"]) == [
            "a",
            "b",
        ]


class TestNormalizeSourceIds:
    def test_basic(self) -> None:
        assert normalize_source_ids(["source.alpha", "source.beta"]) == [
            "source.alpha",
            "source.beta",
        ]

    def test_empty(self) -> None:
        assert normalize_source_ids([]) == []

    def test_none(self) -> None:
        assert normalize_source_ids(None) == []


class TestNormalizeWikiClaimEvidence:
    def test_minimal(self) -> None:
        out = normalize_wiki_claim_evidence({"sourceId": "src.1"})
        assert out is not None
        assert out.source_id == "src.1"

    def test_empty_object_returns_none(self) -> None:
        assert normalize_wiki_claim_evidence({}) is None

    def test_non_object_returns_none(self) -> None:
        assert normalize_wiki_claim_evidence("not a dict") is None
        assert normalize_wiki_claim_evidence([1, 2]) is None

    def test_all_fields(self) -> None:
        raw = {
            "kind": "primary",
            "sourceId": "src.1",
            "path": "notes/alpha.md",
            "lines": "10-20",
            "weight": 0.8,
            "confidence": 0.9,
            "privacyTier": "private",
            "note": "see also",
            "updatedAt": "2026-07-21T00:00:00Z",
        }
        out = normalize_wiki_claim_evidence(raw)
        assert out is not None
        assert out.kind == "primary"
        assert out.path == "notes/alpha.md"
        assert out.weight == 0.8
        assert out.confidence == 0.9


class TestNormalizeWikiClaims:
    def test_empty(self) -> None:
        assert normalize_wiki_claims([]) == []
        assert normalize_wiki_claims(None) == []

    def test_basic(self) -> None:
        claims = normalize_wiki_claims(
            [
                {"text": "alpha", "confidence": 0.8, "status": "active"},
                {"text": "beta", "evidence": [{"sourceId": "src.1"}]},
            ]
        )
        assert len(claims) == 2
        assert isinstance(claims[0], WikiClaim)
        assert claims[0].text == "alpha"
        assert claims[0].confidence == 0.8
        assert claims[1].text == "beta"
        assert len(claims[1].evidence) == 1

    def test_drops_text_less_entries(self) -> None:
        claims = normalize_wiki_claims([{"id": "x"}, {"text": "keep"}, {"confidence": 0.5}])
        assert len(claims) == 1
        assert claims[0].text == "keep"


class TestNormalizeWikiPersonCard:
    def test_empty(self) -> None:
        assert normalize_wiki_person_card({}) is None
        assert normalize_wiki_person_card(None) is None
        assert normalize_wiki_person_card("not a dict") is None

    def test_basic(self) -> None:
        card = normalize_wiki_person_card(
            {
                "canonicalId": "person.alpha",
                "handles": ["@alpha"],
                "socials": ["https://alpha.example"],
                "emails": ["alpha@example.com"],
                "timezone": "Europe/Berlin",
                "lane": "support",
                "askFor": ["intro"],
                "avoidAskingFor": ["salary"],
                "bestUsedFor": ["review"],
                "notEnoughFor": ["crisis"],
                "confidence": 0.7,
                "privacyTier": "private",
                "lastRefreshedAt": "2026-07-21T00:00:00Z",
            }
        )
        assert card is not None
        assert isinstance(card, WikiPersonCard)
        assert card.canonical_id == "person.alpha"
        assert card.handles == ["@alpha"]
        assert card.emails == ["alpha@example.com"]
        assert card.ask_for == ["intro"]
        assert card.avoid_asking_for == ["salary"]
        assert card.best_used_for == ["review"]
        assert card.not_enough_for == ["crisis"]

    def test_email_alias(self) -> None:
        card = normalize_wiki_person_card({"canonicalId": "p.1", "email": "fallback@example.com"})
        assert card is not None
        assert card.emails == ["fallback@example.com"]


class TestNormalizeWikiRelationships:
    def test_empty(self) -> None:
        assert normalize_wiki_relationships([]) == []
        assert normalize_wiki_relationships(None) == []

    def test_basic(self) -> None:
        rels = normalize_wiki_relationships(
            [
                {
                    "targetId": "entity.alpha",
                    "kind": "knows",
                    "weight": 0.5,
                },
                {"note": "see also"},
            ]
        )
        assert len(rels) == 2
        assert isinstance(rels[0], WikiRelationship)
        assert rels[0].target_id == "entity.alpha"
        assert rels[0].kind == "knows"
        assert rels[1].note == "see also"

    def test_drops_empty_entries(self) -> None:
        rels = normalize_wiki_relationships([{}, {"note": "x"}])
        assert len(rels) == 1


class TestExtractWikiLinks:
    def test_obsidian_wikilinks(self) -> None:
        body = "See [[entity.alpha]] and [[entity.beta|the beta]]."
        assert extract_wiki_links(body, "syntheses/alpha.md") == [
            "entity.alpha",
            "entity.beta",
        ]

    def test_markdown_links_resolved_relative(self) -> None:
        body = "See [Alpha](../entities/alpha.md) and [Beta](./beta.md)."
        out = extract_wiki_links(body, "syntheses/foo.md")
        # POSIX normpath collapses ``syntheses/..``
        # so the resolved form is ``entities/alpha.md``.
        assert "entities/alpha.md" in out
        assert "syntheses/beta.md" in out

    def test_dedupes(self) -> None:
        body = "[[alpha]] and [[alpha]] and [Alpha](alpha.md)"
        out = extract_wiki_links(body, "notes/x.md")
        # Each unique target appears once.
        assert out.count("alpha") == 1

    def test_ignores_related_block(self) -> None:
        body = (
            "Real text [[real]].\n\n"
            f"{WIKI_RELATED_START_MARKER}\n"
            "[[auto]]\n"
            f"{WIKI_RELATED_END_MARKER}\n"
        )
        out = extract_wiki_links(body, "notes/x.md")
        assert out == ["real"]

    def test_ignores_fenced_code_links(self) -> None:
        body = "Real [[alpha]].\n\n```\nskipme [[in-code]] and [link](in-code.md)\n```\n"
        out = extract_wiki_links(body, "notes/x.md")
        assert out == ["alpha"]

    def test_ignores_indented_code_links(self) -> None:
        body = "Real [[alpha]].\n\n    skipme [[in-code]] and [link](in-code.md)\n"
        out = extract_wiki_links(body, "notes/x.md")
        assert out == ["alpha"]

    def test_absolute_target_passed_through(self) -> None:
        body = "[Root](/entities/alpha.md)"
        out = extract_wiki_links(body, "notes/x.md")
        assert "/entities/alpha.md" in out

    def test_blank_input(self) -> None:
        assert extract_wiki_links("", "notes/x.md") == []
