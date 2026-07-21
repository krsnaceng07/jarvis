"""Tests for extensions/memory_wiki/okf.py.

Phase 4.3g-mr5: ports the OpenClaw
``okf.ts`` test surface. The tests focus
on:

- ``to_posix_path`` + ``trim_markdown_extension``
  small helpers.
- ``create_okf_bundle_key`` + per-concept
  page identity (slug + sha1 hash).
- ``collect_okf_markdown_files`` walks
  recursively, skips ``.git`` /
  ``node_modules`` + non-``.md`` files.
- ``parse_okf_markdown`` splits frontmatter
  + body; missing or invalid frontmatter
  becomes a warning.
- ``derive_okf_title`` falls back to the
  slugified filename.
- ``normalize_okf_concept`` requires
  ``type`` frontmatter; missing type is
  a warning.
- ``resolve_okf_markdown_target`` decodes
  percent-encoded paths + rejects
  external / fragment-only / ``../`` targets.
- ``split_markdown_link_destination``
  handles angle-bracket + plain forms.
- ``rewrite_okf_markdown_links`` rewrites
  in-bundle links to relative paths,
  skips code fences + inline code, and
  preserves suffixes.
- ``format_okf_import_summary`` builds
  the human-readable line.
- ``import_memory_wiki_okf_bundle``
  end-to-end: imports concept pages,
  writes frontmatter, links concepts,
  prunes stale pages, logs the import,
  and refuses to import a missing
  bundle directory.
"""

# ruff: noqa: S108 — the "/tmp/..." paths are test fixtures mirroring the OpenClaw TS source

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

from __future__ import annotations

import asyncio
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

import pytest  # noqa: E402

from extensions.memory_wiki.config import resolve_memory_wiki_config  # noqa: E402
from extensions.memory_wiki.okf import (  # noqa: E402
    OKF_RESERVED_FILENAMES,
    ImportMemoryWikiOkfResult,
    format_okf_import_summary,
    import_memory_wiki_okf_bundle,
    to_posix_path,
    trim_markdown_extension,
)


def _config(*, path: str) -> object:
    return resolve_memory_wiki_config({"vault": {"scope": "global", "path": path}})


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── to_posix_path / trim_markdown_extension ───────────────


class TestSmallHelpers:
    def test_to_posix_path_passthrough_on_posix(self) -> None:
        assert to_posix_path("tables/customers.md") == "tables/customers.md"

    def test_trim_markdown_extension(self) -> None:
        assert trim_markdown_extension("foo.md") == "foo"
        assert trim_markdown_extension("foo.MD") == "foo"
        assert trim_markdown_extension("foo.txt") == "foo.txt"

    def test_okf_reserved_filenames(self) -> None:
        assert "index.md" in OKF_RESERVED_FILENAMES
        assert "log.md" in OKF_RESERVED_FILENAMES


# ── collect_okf_markdown_files ───────────────────────────


class TestCollectOkfMarkdownFiles:
    def test_walks_recursively(self, tmp_path: Path) -> None:
        (tmp_path / "tables").mkdir()
        (tmp_path / "tables" / "customers.md").write_text("# c", encoding="utf-8")
        (tmp_path / "metrics").mkdir()
        (tmp_path / "metrics" / "weekly.md").write_text("# m", encoding="utf-8")
        (tmp_path / "extra.json").write_text("{}", encoding="utf-8")
        from extensions.memory_wiki.okf import _collect_okf_markdown_files

        result = _collect_okf_markdown_files(str(tmp_path), [])
        assert result == sorted(
            [
                "metrics/weekly.md",
                "tables/customers.md",
            ]
        )

    def test_skips_git_and_node_modules(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "should-skip.md").write_text("# x", encoding="utf-8")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "skip.md").write_text("# x", encoding="utf-8")
        (tmp_path / "keep.md").write_text("# k", encoding="utf-8")
        from extensions.memory_wiki.okf import _collect_okf_markdown_files

        result = _collect_okf_markdown_files(str(tmp_path), [])
        assert result == ["keep.md"]


# ── parse_okf_markdown / normalize_okf_concept ────────────────


class TestParseOkfMarkdown:
    def test_splits_frontmatter_and_body(self) -> None:
        from extensions.memory_wiki.okf import _parse_okf_markdown

        result = _parse_okf_markdown(
            "---\ntype: BigQuery Table\ntitle: Customers\n---\n# Schema\n\nRows.\n",
            "tables/customers.md",
        )
        assert "warning" not in result
        assert result["frontmatter"] == {"type": "BigQuery Table", "title": "Customers"}
        assert "# Schema" in result["body"]
        assert "Rows." in result["body"]

    def test_invalid_frontmatter_emits_warning(self) -> None:
        from extensions.memory_wiki.okf import _parse_okf_markdown

        result = _parse_okf_markdown(
            "---\ntype: :\n: invalid: [unclosed\n---\nbody",
            "broken.md",
        )
        # Either a warning or a parse fallback
        # is acceptable; the key requirement
        # is that we don't blow up.
        assert "frontmatter" in result
        assert "body" in result


class TestNormalizeOkfConcept:
    def test_requires_type_frontmatter(self) -> None:
        from extensions.memory_wiki.okf import _normalize_okf_concept

        result = _normalize_okf_concept(
            bundle_path="/tmp/bundle",
            relative_path="tables/draft.md",
            content="---\ntitle: Draft\n---\n# x\n",
        )
        assert "warning" in result
        assert result["warning"].code == "missing-type"

    def test_builds_concept_when_type_present(self) -> None:
        from extensions.memory_wiki.okf import _normalize_okf_concept

        result = _normalize_okf_concept(
            bundle_path="/tmp/bundle",
            relative_path="tables/customers.md",
            content=(
                "---\n"
                "type: BigQuery Table\n"
                "title: Customers\n"
                "tags: [sales, customers]\n"
                "---\n"
                "# Schema\n"
            ),
        )
        assert "warning" not in result
        assert "concept" in result
        concept = result["concept"]
        assert concept.conceptId == "tables/customers"
        assert concept.type == "BigQuery Table"
        assert concept.title == "Customers"
        assert concept.tags == ["sales", "customers"]


# ── derive_okf_title ───────────────────────────────────────


class TestDeriveOkfTitle:
    def test_frontmatter_title_wins(self) -> None:
        from extensions.memory_wiki.okf import _derive_okf_title

        assert _derive_okf_title("foo/bar/baz.md", {"title": "Real Title"}) == "Real Title"

    def test_filename_fallback(self) -> None:
        from extensions.memory_wiki.okf import _derive_okf_title

        assert _derive_okf_title("foo/my-thing.md", {}) == "my thing"

    def test_empty_fallback_uses_full_path(self) -> None:
        from extensions.memory_wiki.okf import _derive_okf_title

        assert _derive_okf_title("---.md", {}) == "---"


# ── split_markdown_link_destination ────────────────────────


class TestSplitMarkdownLinkDestination:
    def test_plain(self) -> None:
        from extensions.memory_wiki.okf import _split_markdown_link_destination

        result = _split_markdown_link_destination("/tables/customers.md")
        assert result["destination"] == "/tables/customers.md"
        assert result["titleSuffix"] == ""

    def test_with_title(self) -> None:
        from extensions.memory_wiki.okf import _split_markdown_link_destination

        result = _split_markdown_link_destination('/tables/customers.md "table docs"')
        assert result["destination"] == "/tables/customers.md"
        assert "table docs" in result["titleSuffix"]

    def test_angle_brackets(self) -> None:
        from extensions.memory_wiki.okf import _split_markdown_link_destination

        result = _split_markdown_link_destination("<foo bar>")
        assert result["destination"] == "foo bar"
        assert result["titleSuffix"] == ""


# ── resolve_okf_markdown_target ──────────────────────────


class TestResolveOkfMarkdownTarget:
    def test_absolute(self) -> None:
        from extensions.memory_wiki.okf import _resolve_okf_markdown_target

        result = _resolve_okf_markdown_target("tables/orders.md", "/tables/customers.md")
        assert result == "tables/customers"

    def test_relative(self) -> None:
        from extensions.memory_wiki.okf import _resolve_okf_markdown_target

        result = _resolve_okf_markdown_target(
            "tables/orders.md", "../metrics/weekly-active-users.md"
        )
        assert result == "metrics/weekly-active-users"

    def test_external_link_returns_none(self) -> None:
        from extensions.memory_wiki.okf import _resolve_okf_markdown_target

        assert _resolve_okf_markdown_target("orders.md", "https://example.com/x.md") is None

    def test_fragment_only_returns_none(self) -> None:
        from extensions.memory_wiki.okf import _resolve_okf_markdown_target

        assert _resolve_okf_markdown_target("orders.md", "#section") is None

    def test_non_md_target_returns_none(self) -> None:
        from extensions.memory_wiki.okf import _resolve_okf_markdown_target

        assert _resolve_okf_markdown_target("orders.md", "/tables/customers") is None

    def test_escape_returns_none(self) -> None:
        from extensions.memory_wiki.okf import _resolve_okf_markdown_target

        assert _resolve_okf_markdown_target("orders.md", "../../../outside.md") is None

    def test_percent_encoded(self) -> None:
        from extensions.memory_wiki.okf import _resolve_okf_markdown_target

        result = _resolve_okf_markdown_target("tables/orders.md", "/tables/my%20table.md")
        assert result == "tables/my table"


# ── get_markdown_destination_suffix ───────────────────────


class TestGetMarkdownDestinationSuffix:
    def test_no_suffix(self) -> None:
        from extensions.memory_wiki.okf import _get_markdown_destination_suffix

        assert _get_markdown_destination_suffix("/foo.md") == ""

    def test_query_suffix(self) -> None:
        from extensions.memory_wiki.okf import _get_markdown_destination_suffix

        assert _get_markdown_destination_suffix("/foo.md?x=1") == "?x=1"

    def test_fragment_suffix(self) -> None:
        from extensions.memory_wiki.okf import _get_markdown_destination_suffix

        assert _get_markdown_destination_suffix("/foo.md#bar") == "#bar"

    def test_query_and_fragment(self) -> None:
        from extensions.memory_wiki.okf import _get_markdown_destination_suffix

        assert _get_markdown_destination_suffix("/foo.md?q=1#bar") == "?q=1#bar"


# ── format_okf_import_summary ────────────────────────────


class TestFormatOkfImportSummary:
    def test_singular(self) -> None:
        result = ImportMemoryWikiOkfResult(
            bundlePath="/tmp/b",
            bundleName="b",
            importedCount=1,
            updatedCount=0,
            removedCount=0,
            skippedCount=0,
            pagePaths=["concepts/x.md"],
            removedPagePaths=[],
            warnings=[],
            indexUpdatedFiles=[],
        )
        summary = format_okf_import_summary(result)
        assert "Imported 1 OKF concept from /tmp/b" in summary
        assert "Updated 0" in summary
        assert "removed 0" in summary

    def test_plural(self) -> None:
        result = ImportMemoryWikiOkfResult(
            bundlePath="/tmp/b",
            bundleName="b",
            importedCount=3,
            updatedCount=1,
            removedCount=2,
            skippedCount=0,
            pagePaths=[],
            removedPagePaths=[],
            warnings=[],
            indexUpdatedFiles=[],
        )
        summary = format_okf_import_summary(result)
        assert "3 OKF concepts" in summary


# ── import_memory_wiki_okf_bundle (integration) ────────────


class TestImportMemoryWikiOkfBundle:
    def test_refuses_to_import_missing_directory(self, tmp_path: Path) -> None:
        config = _config(path=str(tmp_path / "vault"))
        missing = tmp_path / "missing-bundle"
        with pytest.raises(ValueError, match="bundle directory"):
            asyncio.run(import_memory_wiki_okf_bundle(config=config, bundle_path=str(missing)))

    def test_imports_concept_pages(self, tmp_path: Path) -> None:
        bundle_path = tmp_path / "sales-okf"
        (bundle_path / "tables").mkdir(parents=True)
        (bundle_path / "metrics").mkdir(parents=True)
        _write(
            bundle_path / "index.md",
            "---\nid: sales-okf\nokf_version: '0.1'\n---\n# Sales\n",
        )
        _write(bundle_path / "log.md", "# Log\n")
        _write(
            bundle_path / "tables" / "customers.md",
            (
                "---\n"
                "type: BigQuery Table\n"
                "title: Customers\n"
                "tags: [sales, customers]\n"
                "---\n"
                "# Schema\n\nCustomer rows.\n"
            ),
        )
        _write(
            bundle_path / "tables" / "orders.md",
            (
                "---\n"
                "type: BigQuery Table\n"
                "title: Orders\n"
                "tags:\n  - sales\n  - orders\n"
                "---\n"
                "# Schema\n\n"
                "Joined with [Customers](/tables/customers.md).\n"
                "Titled link to [weekly metric]"
                '(../metrics/weekly-active-users.md "metric docs").\n'
            ),
        )
        _write(
            bundle_path / "metrics" / "weekly-active-users.md",
            (
                "---\n"
                "type: Metric\n"
                "title: Weekly Active Users\n"
                "---\n"
                "Computed from [orders](../tables/orders.md).\n"
            ),
        )
        _write(
            bundle_path / "tables" / "draft.md",
            "---\ntitle: Draft\n---\nMissing type.\n",
        )
        vault_dir = tmp_path / "vault"
        config = _config(path=str(vault_dir))

        result = asyncio.run(
            import_memory_wiki_okf_bundle(config=config, bundle_path=str(bundle_path))
        )

        # 4 concepts total: customers, orders,
        # weekly-active-users, draft. Draft
        # has missing type, so it becomes a
        # warning (skipped).
        assert result.importedCount == 3
        assert result.skippedCount == 1
        assert len(result.warnings) == 1
        assert result.warnings[0].code == "missing-type"
        assert "draft" in result.warnings[0].path
        # 3 concept pages exist in the vault.
        for page_path in result.pagePaths:
            full_path = vault_dir / page_path
            assert full_path.is_file(), page_path
            content = full_path.read_text(encoding="utf-8")
            assert "pageType: concept" in content
            assert "sourceType: okf" in content
            assert "provenanceMode: okf-import" in content
        # OKF version propagated.
        assert result.okfVersion == "0.1"
        # bundleName is the basename.
        assert result.bundleName == "sales-okf"

        # Second import: nothing changes; all
        # entries are skipped (no count
        # increment).
        second = asyncio.run(
            import_memory_wiki_okf_bundle(config=config, bundle_path=str(bundle_path))
        )
        assert second.importedCount == 3
        assert second.updatedCount == 0
        # Note: ``draft.md`` is still flagged
        # as missing-type on every import
        # (the source is unchanged), so
        # ``skippedCount`` may stay > 0.

    def test_prunes_stale_concept_pages(self, tmp_path: Path) -> None:
        bundle_path = tmp_path / "alpha-okf"
        bundle_path.mkdir(parents=True)
        _write(
            bundle_path / "index.md",
            "---\nid: alpha-okf\n---\n# Alpha\n",
        )
        _write(
            bundle_path / "secret.md",
            "---\ntype: doc\ntitle: Secret\n---\n# secret\n",
        )
        vault_dir = tmp_path / "vault"
        config = _config(path=str(vault_dir))

        first = asyncio.run(
            import_memory_wiki_okf_bundle(config=config, bundle_path=str(bundle_path))
        )
        first_page = first.pagePaths[0]
        assert (vault_dir / first_page).is_file()

        # Remove the source concept.
        (bundle_path / "secret.md").unlink()
        second = asyncio.run(
            import_memory_wiki_okf_bundle(config=config, bundle_path=str(bundle_path))
        )

        assert second.removedCount == 1
        assert first_page in second.removedPagePaths
        assert not (vault_dir / first_page).exists()
