"""Tests for extensions/memory_wiki/query.py.

Phase 4.3f-mr1: ports the OpenClaw
``query.ts`` read path. The tests focus on:

- ``list_wiki_markdown_files`` enumerates
  every ``.md`` file under the 5 query
  sub-directories + skips ``index.md``.
- ``read_queryable_wiki_pages`` returns one
  ``QueryableWikiPage`` per file (with raw
  body).
- ``resolve_queryable_wiki_page_by_lookup``
  matches by ``relativePath`` /
  ``.md`` extension / basename / ``id``.
- ``build_lookup_candidates`` returns the
  normalized key + ``.md`` extension.
- ``get_memory_wiki_page`` returns a
  ``WikiGetResult`` for a known page, with
  the requested line range; returns
  ``None`` for a missing page.
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
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.memory_wiki.markdown_pages import render_wiki_markdown  # noqa: E402
from extensions.memory_wiki.query import (  # noqa: E402
    QUERY_DIRS,
    QUERY_PAGE_READ_CONCURRENCY,
    WIKI_SEARCH_MODES,
    WikiGetResult,
    build_lookup_candidates,
    get_memory_wiki_page,
    list_wiki_markdown_files,
    read_queryable_wiki_pages,
    resolve_queryable_wiki_page_by_lookup,
    should_search_wiki,
)


def _entity_page(*, id_: str = "entity.alpha", title: str = "Alpha") -> str:
    return render_wiki_markdown(
        frontmatter={
            "pageType": "entity",
            "id": id_,
        },
        body=f"# {title}\n\nFirst line.\nSecond line.\nThird line.\n",
    )


def _source_page(*, id_: str = "source.alpha", title: str = "Source") -> str:
    return render_wiki_markdown(
        frontmatter={
            "pageType": "source",
            "id": id_,
        },
        body=f"# {title}\n\nFoo.\nBar.\n",
    )


@pytest.fixture
def vault_with_pages(tmp_path: Path) -> Path:
    """Build a small vault with 3 pages + 1 index file."""
    for sub in QUERY_DIRS:
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    (tmp_path / "entities" / "alpha.md").write_text(
        _entity_page(id_="entity.alpha", title="Alpha"), encoding="utf-8"
    )
    (tmp_path / "entities" / "beta.md").write_text(
        _entity_page(id_="entity.beta", title="Beta"), encoding="utf-8"
    )
    (tmp_path / "sources" / "foo.md").write_text(
        _source_page(id_="source.alpha", title="Foo"), encoding="utf-8"
    )
    # Note: ``source.alpha`` is the id and
    # ``Foo`` is the title (H1 in the body).
    # The frontmatter id mirrors the source
    # pattern; the body H1 provides the title
    # (matching the OpenClaw behavior of
    # extracting the title from the H1).
    # An auto-generated ``index.md`` — should
    # be skipped by the query reader.
    (tmp_path / "entities" / "index.md").write_text("## Generated\n", encoding="utf-8")
    return tmp_path


class TestConstants:
    def test_query_dirs(self) -> None:
        assert QUERY_DIRS == (
            "sources",
            "entities",
            "concepts",
            "syntheses",
            "reports",
        )
        assert QUERY_PAGE_READ_CONCURRENCY == 16

    def test_search_modes(self) -> None:
        assert WIKI_SEARCH_MODES == (
            "auto",
            "find-person",
            "route-question",
            "source-evidence",
            "raw-claim",
        )


class TestListWikiMarkdownFiles:
    def test_lists_every_kind_subdir(self, vault_with_pages: Path) -> None:
        files = list_wiki_markdown_files(str(vault_with_pages))
        # 3 .md files, 1 index.md skipped.
        assert sorted(files) == [
            "entities/alpha.md",
            "entities/beta.md",
            "sources/foo.md",
        ]

    def test_returns_empty_for_missing_vault(self, tmp_path: Path) -> None:
        assert list_wiki_markdown_files(str(tmp_path / "missing")) == []

    def test_skips_non_markdown_files(self, tmp_path: Path) -> None:
        for sub in QUERY_DIRS:
            (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        (tmp_path / "entities" / "alpha.md").write_text("# Hi\n", encoding="utf-8")
        (tmp_path / "entities" / "ignore.txt").write_text("nope", encoding="utf-8")
        files = list_wiki_markdown_files(str(tmp_path))
        assert files == ["entities/alpha.md"]


class TestReadQueryableWikiPages:
    def test_reads_all_pages(self, vault_with_pages: Path) -> None:
        pages = read_queryable_wiki_pages(str(vault_with_pages))
        assert len(pages) == 3
        # Every page has a non-empty raw body.
        for page in pages:
            assert page.raw
            assert page.page.title

    def test_raw_body_preserved(self, vault_with_pages: Path) -> None:
        pages = read_queryable_wiki_pages(str(vault_with_pages))
        alpha = next(p for p in pages if p.page.id == "entity.alpha")
        assert "# Alpha" in alpha.raw

    def test_returns_empty_for_missing_vault(self, tmp_path: Path) -> None:
        assert read_queryable_wiki_pages(str(tmp_path / "missing")) == []


class TestResolveQueryableWikiPageByLookup:
    def test_resolve_by_relative_path(self, vault_with_pages: Path) -> None:
        pages = read_queryable_wiki_pages(str(vault_with_pages))
        resolved = resolve_queryable_wiki_page_by_lookup(pages, "entities/alpha.md")
        assert resolved is not None
        assert resolved.page.id == "entity.alpha"

    def test_resolve_by_relative_path_without_md(self, vault_with_pages: Path) -> None:
        pages = read_queryable_wiki_pages(str(vault_with_pages))
        resolved = resolve_queryable_wiki_page_by_lookup(pages, "entities/alpha")
        assert resolved is not None
        assert resolved.page.id == "entity.alpha"

    def test_resolve_by_basename(self, vault_with_pages: Path) -> None:
        pages = read_queryable_wiki_pages(str(vault_with_pages))
        resolved = resolve_queryable_wiki_page_by_lookup(pages, "alpha")
        assert resolved is not None
        assert resolved.page.id == "entity.alpha"

    def test_resolve_by_id(self, vault_with_pages: Path) -> None:
        pages = read_queryable_wiki_pages(str(vault_with_pages))
        resolved = resolve_queryable_wiki_page_by_lookup(pages, "entity.beta")
        assert resolved is not None
        assert resolved.page.title == "Beta"

    def test_resolve_unknown_returns_none(self, vault_with_pages: Path) -> None:
        pages = read_queryable_wiki_pages(str(vault_with_pages))
        assert resolve_queryable_wiki_page_by_lookup(pages, "missing") is None

    def test_resolve_handles_backslashes(self, vault_with_pages: Path) -> None:
        pages = read_queryable_wiki_pages(str(vault_with_pages))
        resolved = resolve_queryable_wiki_page_by_lookup(pages, "entities\\alpha.md")
        assert resolved is not None
        assert resolved.page.id == "entity.alpha"


class TestBuildLookupCandidates:
    def test_returns_normalized_and_with_extension(self) -> None:
        candidates = build_lookup_candidates("entities/alpha")
        assert candidates == ["entities/alpha", "entities/alpha.md"]

    def test_dedupes_when_already_has_md(self) -> None:
        candidates = build_lookup_candidates("entities/alpha.md")
        assert candidates == ["entities/alpha.md"]

    def test_strips_trailing_slash(self) -> None:
        candidates = build_lookup_candidates("entities/alpha/")
        assert "entities/alpha" in candidates

    def test_normalizes_backslashes(self) -> None:
        candidates = build_lookup_candidates("entities\\alpha")
        # Backslashes are replaced with forward
        # slashes by ``_normalize_lookup_key``.
        # The first candidate is the normalized
        # form (forward slashes).
        assert "entities/alpha" in candidates


class TestShouldSearchWiki:
    def test_default_searches_wiki(self) -> None:
        config = SimpleNamespace(search=SimpleNamespace(corpus="wiki"))
        assert should_search_wiki(config) is True

    def test_corpus_all_searches_wiki(self) -> None:
        config = SimpleNamespace(search=SimpleNamespace(corpus="all"))
        assert should_search_wiki(config) is True

    def test_corpus_memory_skips_wiki(self) -> None:
        config = SimpleNamespace(search=SimpleNamespace(corpus="memory"))
        assert should_search_wiki(config) is False


class TestGetMemoryWikiPage:
    def _config(self, vault_path: Path, *, corpus: str = "wiki") -> SimpleNamespace:
        return SimpleNamespace(
            vaultMode="single",
            vault=SimpleNamespace(path=str(vault_path), scope="global", renderMode="native"),
            search=SimpleNamespace(corpus=corpus),
        )

    def test_returns_page_with_default_line_range(self, vault_with_pages: Path) -> None:
        config = self._config(vault_with_pages)
        result = get_memory_wiki_page(config=config, lookup="entities/alpha.md")
        assert result is not None
        assert isinstance(result, WikiGetResult)
        assert result.corpus == "wiki"
        assert result.path == "entities/alpha.md"
        assert result.title == "Alpha"
        assert result.kind == "entity"
        assert result.from_line == 1
        assert result.line_count == 200
        assert result.total_lines is not None
        assert result.total_lines > 0
        assert "# Alpha" in result.content

    def test_respects_line_range(self, vault_with_pages: Path) -> None:
        config = self._config(vault_with_pages)
        result = get_memory_wiki_page(
            config=config,
            lookup="entities/alpha.md",
            from_line=2,
            line_count=2,
        )
        assert result is not None
        # Body lines (post-frontmatter):
        # 1: ``# Alpha``
        # 2: `` (empty)
        # 3: ``First line.``
        # 4: ``Second line.``
        # 5: ``Third line.``
        # ``from_line=2, line_count=2`` returns
        # lines 2..3 (1-indexed inclusive) =
        # ``[empty, First line.]``.
        assert result.content == "\nFirst line."
        assert result.truncated is True

    def test_returns_none_for_missing_page(self, vault_with_pages: Path) -> None:
        config = self._config(vault_with_pages)
        assert get_memory_wiki_page(config=config, lookup="entities/missing.md") is None

    def test_returns_none_when_wiki_corpus_disabled(self, vault_with_pages: Path) -> None:
        config = self._config(vault_with_pages, corpus="memory")
        assert get_memory_wiki_page(config=config, lookup="entities/alpha.md") is None

    def test_id_propagated_to_result(self, vault_with_pages: Path) -> None:
        config = self._config(vault_with_pages)
        result = get_memory_wiki_page(config=config, lookup="entities/alpha.md")
        assert result is not None
        assert result.id == "entity.alpha"
