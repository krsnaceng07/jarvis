"""Tests for extensions/memory_wiki/markdown.py.

Phase 4.3c: ports the OpenClaw managed-block helper
(``replaceManagedMarkdownBlock``), the frontmatter
parser (``parseWikiFrontmatter``), and the wiki
marker constants. The tests focus on:

- ``with_trailing_newline`` adds / normalizes the
  trailing newline.
- ``replace_managed_markdown_block`` produces the
  expected OpenClaw-shaped block (start marker,
  heading, blank line, body, end marker,
  trailing newline).
- ``parse_wiki_frontmatter`` extracts a YAML
  frontmatter dict + body; coerces string values
  (trim) and list values (recursive).
- A source without a leading frontmatter is
  returned as ``has_frontmatter=False`` with the
  original text as body.
- Invalid YAML returns ``frontmatter={}`` (not
  an exception).
- The raw-source marker is preserved verbatim in
  the body when present.
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
# pyright: reportTypedDictNotRequiredAccess=false

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

from extensions.memory_wiki.markdown import (  # noqa: E402
    FRONTMATTER_CLOSE,
    FRONTMATTER_OPEN,
    WIKI_PAGE_KINDS,
    WIKI_RAW_SOURCE_MARKER,
    WIKI_RELATED_END_MARKER,
    WIKI_RELATED_START_MARKER,
    ReplaceManagedBlockParams,
    parse_wiki_frontmatter,
    replace_managed_markdown_block,
    with_trailing_newline,
)


class TestWikiConstants:
    def test_page_kinds(self) -> None:
        assert WIKI_PAGE_KINDS == (
            "entity",
            "concept",
            "source",
            "synthesis",
            "report",
        )

    def test_related_markers(self) -> None:
        assert WIKI_RELATED_START_MARKER == "<!-- openclaw:wiki:related:start -->"
        assert WIKI_RELATED_END_MARKER == "<!-- openclaw:wiki:related:end -->"

    def test_raw_source_marker(self) -> None:
        assert WIKI_RAW_SOURCE_MARKER == "<!-- openclaw:wiki:raw-source -->"

    def test_frontmatter_delimiters(self) -> None:
        assert FRONTMATTER_OPEN == "---"
        assert FRONTMATTER_CLOSE == "---"


class TestWithTrailingNewline:
    def test_empty_string(self) -> None:
        assert with_trailing_newline("") == "\n"

    def test_already_has_one(self) -> None:
        assert with_trailing_newline("hello\n") == "hello\n"

    def test_has_two(self) -> None:
        # No normalization: the helper only ensures
        # "at least one trailing newline".
        assert with_trailing_newline("hello\n\n") == "hello\n\n"

    def test_missing(self) -> None:
        assert with_trailing_newline("hello") == "hello\n"


class TestReplaceManagedMarkdownBlock:
    def test_block_shape(self) -> None:
        params = ReplaceManagedBlockParams(
            original="# Wiki Index\n",
            heading="## Generated",
            start_marker="<!-- openclaw:wiki:index:start -->",
            end_marker="<!-- openclaw:wiki:index:end -->",
            body="- No compiled pages yet.",
        )
        out = replace_managed_markdown_block(params)
        assert out.startswith("# Wiki Index\n")
        assert "<!-- openclaw:wiki:index:start -->" in out
        assert "## Generated" in out
        assert "- No compiled pages yet." in out
        assert "<!-- openclaw:wiki:index:end -->" in out
        assert out.endswith("\n")

    def test_appends_when_original_lacks_newline(self) -> None:
        params = ReplaceManagedBlockParams(
            original="# Index",
            heading="## Generated",
            start_marker="<!-- start -->",
            end_marker="<!-- end -->",
            body="body",
        )
        out = replace_managed_markdown_block(params)
        assert out.startswith("# Index\n")


class TestParseWikiFrontmatter:
    def test_no_frontmatter_returns_whole_source(self) -> None:
        source = "# Hello\n\nSome text.\n"
        parsed = parse_wiki_frontmatter(source)
        assert parsed.has_frontmatter is False
        assert parsed.frontmatter == {}
        assert parsed.body == source

    def test_basic_frontmatter(self) -> None:
        source = "---\ntitle: Alpha\nkind: entity\n---\n\n# Body\n"
        parsed = parse_wiki_frontmatter(source)
        assert parsed.has_frontmatter is True
        assert parsed.frontmatter["title"] == "Alpha"
        assert parsed.frontmatter["kind"] == "entity"
        assert parsed.body.startswith("# Body")

    def test_list_value_is_coerced(self) -> None:
        source = "---\naliases:\n  - alpha\n  - beta\n---\nbody"
        parsed = parse_wiki_frontmatter(source)
        assert parsed.frontmatter["aliases"] == ["alpha", "beta"]

    def test_nested_dict(self) -> None:
        source = "---\nclaim:\n  text: foo\n  status: review\n---\nbody"
        parsed = parse_wiki_frontmatter(source)
        claim = parsed.frontmatter["claim"]
        assert isinstance(claim, dict)
        assert claim["text"] == "foo"
        assert claim["status"] == "review"

    def test_string_value_is_trimmed(self) -> None:
        source = "---\ntitle:   spaced   \n---\nbody"
        parsed = parse_wiki_frontmatter(source)
        assert parsed.frontmatter["title"] == "spaced"

    def test_invalid_yaml_returns_empty_dict(self) -> None:
        source = "---\ntitle: : :\n  : not yaml\n---\nbody"
        parsed = parse_wiki_frontmatter(source)
        # Malformed YAML degrades to an empty
        # frontmatter dict; body is still extracted.
        assert parsed.has_frontmatter is True
        assert parsed.frontmatter == {}

    def test_non_mapping_yaml_returns_empty_dict(self) -> None:
        # ``[a, b]`` is valid YAML but not a mapping.
        source = "---\n[a, b]\n---\nbody"
        parsed = parse_wiki_frontmatter(source)
        assert parsed.has_frontmatter is True
        assert parsed.frontmatter == {}

    def test_missing_closing_delimiter(self) -> None:
        # No closing ``---``; the parser treats the
        # entire source as body.
        source = "---\ntitle: Alpha\nbody"
        parsed = parse_wiki_frontmatter(source)
        assert parsed.has_frontmatter is False
        assert parsed.body == source

    def test_raw_source_marker_preserved_in_body(self) -> None:
        source = f"---\ntitle: Raw\n---\n{WIKI_RAW_SOURCE_MARKER}\n# Body\n"
        parsed = parse_wiki_frontmatter(source)
        assert WIKI_RAW_SOURCE_MARKER in parsed.body
        assert parsed.frontmatter["title"] == "Raw"
