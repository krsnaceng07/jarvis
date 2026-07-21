"""Tests for extensions/memory_wiki/lint.py.

Phase 4.3g-mr1: ports the OpenClaw
``lint.ts`` test surface (focused on
the contract surface — full test
coverage of the per-issue collectors
lands alongside 4.3g in subsequent
phases). Tests focus on:

- :func:`lint_memory_wiki_vault` returns
  a result with the right shape
  (camelCase fields, categorized
  issues, report path).
- The :func:`_collect_page_issues`
  helper emits the expected codes for
  the well-known failure modes.
- The :func:`_build_issues_by_category`
  helper groups issues by category.
- The :func:`_build_lint_report_body`
  helper produces a stable markdown
  body.
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
import os
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


from extensions.memory_wiki import lint as lt  # noqa: E402
from extensions.memory_wiki.config import resolve_memory_wiki_config  # noqa: E402
from extensions.memory_wiki.markdown_pages import render_wiki_markdown  # noqa: E402


def _vault_config(tmp_path: Path) -> SimpleNamespace:
    return resolve_memory_wiki_config({"vault": {"scope": "global", "path": str(tmp_path)}})


def _entity_page(*, id_: str = "entity.alpha", title: str = "Alpha", **kwargs) -> str:
    return render_wiki_markdown(
        frontmatter={"pageType": "entity", "id": id_, "title": title, **kwargs},
        body=f"# {title}\n",
    )


def _write_page(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _empty_page() -> SimpleNamespace:
    return SimpleNamespace(
        id=None,
        page_type=None,
        pageType=None,
        title="",
        kind="entity",
        source_ids=[],
        sourceIds=[],
        source_type=None,
        sourceType=None,
        provenance_mode=None,
        provenanceMode=None,
        source_path=None,
        sourcePath=None,
        bridge_relative_path=None,
        bridgeRelativePath=None,
        bridge_workspace_dir=None,
        bridgeWorkspaceDir=None,
        unsafe_local_configured_path=None,
        unsafeLocalConfiguredPath=None,
        unsafe_local_relative_path=None,
        unsafeLocalRelativePath=None,
        contradictions=[],
        questions=[],
        confidence=None,
        relative_path="entities/empty.md",
        relativePath="entities/empty.md",
        title_or_id="",
        link_targets=[],
        linkTargets=[],
        unmanaged_raw_source_body=False,
        unmanagedRawSourceBody=False,
    )


class TestBuildIssuesByCategory:
    def test_groups_by_known_category(self) -> None:
        issues = [
            lt.WikiLintIssue(
                severity="error",
                category="structure",
                code="missing-id",
                path="a.md",
                message="x",
            ),
            lt.WikiLintIssue(
                severity="warning",
                category="provenance",
                code="missing-source-ids",
                path="b.md",
                message="y",
            ),
            lt.WikiLintIssue(
                severity="warning",
                category="links",
                code="broken-wikilink",
                path="c.md",
                message="z",
            ),
        ]
        grouped = lt._build_issues_by_category(issues)
        assert len(grouped["structure"]) == 1
        assert len(grouped["provenance"]) == 1
        assert len(grouped["links"]) == 1
        assert len(grouped["contradictions"]) == 0
        assert len(grouped["open-questions"]) == 0
        assert len(grouped["quality"]) == 0

    def test_empty_input_returns_all_categories(self) -> None:
        grouped = lt._build_issues_by_category([])
        for cat in lt.LINT_ISSUE_CATEGORIES:
            assert grouped[cat] == []


class TestBuildLintReportBody:
    def test_no_issues_returns_clean_message(self) -> None:
        body = lt._build_lint_report_body([])
        assert body == "No issues found."

    def test_renders_errors_warnings_and_categories(self) -> None:
        issues = [
            lt.WikiLintIssue(
                severity="error",
                category="structure",
                code="missing-id",
                path="a.md",
                message="Missing id",
            ),
            lt.WikiLintIssue(
                severity="warning",
                category="open-questions",
                code="open-question",
                path="b.md",
                message="Open question",
            ),
        ]
        body = lt._build_lint_report_body(issues)
        assert "- Errors: 1" in body
        assert "- Warnings: 1" in body
        assert "### Errors" in body
        assert "### Warnings" in body
        assert "### Open Questions" in body
        assert "`a.md`: Missing id" in body
        assert "`b.md`: Open question" in body


class TestNormalizeLintTarget:
    def test_strips_md_extension(self) -> None:
        assert lt._normalize_lint_path_target("entities/alpha.md") == "entities/alpha"

    def test_strips_leading_slash(self) -> None:
        assert lt._normalize_lint_path_target("/entities/alpha") == "entities/alpha"

    def test_strips_query_string_when_strip_query_true(self) -> None:
        assert lt._normalize_lint_path_target("alpha?section=1") == "alpha"

    def test_keeps_query_string_when_strip_query_false(self) -> None:
        assert lt._normalize_lint_alias_text_target("alpha?section=1") == "alpha?section=1"

    def test_lowercases_alias_target(self) -> None:
        assert lt._normalize_lint_alias_target("ALPHA") == "alpha"


class TestLinkTargetIndex:
    def test_path_index_includes_basename(self) -> None:
        page = SimpleNamespace(
            relative_path="entities/alpha.md",
            title="Alpha",
            source_path=None,
            bridge_relative_path=None,
            unsafe_local_relative_path=None,
        )
        index = lt._build_wiki_link_target_index([page])
        assert "entities/alpha" in index["pathTargets"]
        assert "alpha" in index["pathTargets"]
        assert "alpha" in index["aliasTargets"]

    def test_resolves_title_alias(self) -> None:
        page = SimpleNamespace(
            relative_path="entities/alpha.md",
            title="Alpha",
            source_path=None,
            bridge_relative_path=None,
            unsafe_local_relative_path=None,
        )
        index = lt._build_wiki_link_target_index([page])
        assert lt._has_valid_wiki_link_target(index, "alpha") is True
        assert lt._has_valid_wiki_link_target(index, "missing") is False

    def test_handles_query_with_path_target(self) -> None:
        page = SimpleNamespace(
            relative_path="entities/alpha.md",
            title="Alpha",
            source_path=None,
            bridge_relative_path=None,
            unsafe_local_relative_path=None,
        )
        index = lt._build_wiki_link_target_index([page])
        # Path-style query matches a path
        # target → valid.
        assert lt._has_valid_wiki_link_target(index, "entities/alpha?section=1") is True


class TestCollectBrokenLinkIssues:
    def test_emits_issue_for_broken_link(self) -> None:
        page = SimpleNamespace(
            relative_path="entities/alpha.md",
            title="Alpha",
            source_path=None,
            bridge_relative_path=None,
            unsafe_local_relative_path=None,
            link_targets=["missing-page"],
        )
        issues = lt._collect_broken_link_issues([page])
        assert any(i.code == "broken-wikilink" for i in issues)

    def test_no_issue_for_existing_link(self) -> None:
        page = SimpleNamespace(
            relative_path="entities/alpha.md",
            title="Alpha",
            source_path=None,
            bridge_relative_path=None,
            unsafe_local_relative_path=None,
            link_targets=["alpha"],
        )
        issues = lt._collect_broken_link_issues([page])
        assert issues == []


class TestCollectPageIssues:
    def test_emits_missing_id_for_managed_page(self) -> None:
        page = _empty_page()
        # Mark as managed (not unmanaged
        # raw source) so the missing-id
        # check fires.
        page.unmanaged_raw_source_body = False
        page.unmanagedRawSourceBody = False
        issues = lt._collect_page_issues([page], set())
        codes = [i.code for i in issues]
        assert "missing-id" in codes
        assert "missing-page-type" in codes
        assert "missing-title" in codes

    def test_skips_missing_id_for_unmanaged_raw_source(self) -> None:
        page = _empty_page()
        page.unmanaged_raw_source_body = True
        page.unmanagedRawSourceBody = True
        issues = lt._collect_page_issues([page], set())
        codes = [i.code for i in issues]
        # Unmanaged raw source pages are
        # allowed to lack structured
        # metadata.
        assert "missing-id" not in codes
        assert "missing-page-type" not in codes


class TestLintMemoryWikiVault:
    def test_runs_on_empty_vault(self, tmp_path: Path) -> None:
        config = _vault_config(tmp_path)
        result = asyncio.run(lt.lint_memory_wiki_vault(config))
        assert result.vaultRoot == str(tmp_path)
        assert result.issueCount == 0
        assert result.issues == []
        # The report file is still written
        # (with the "No issues found."
        # body).
        assert os.path.isfile(result.reportPath)
        assert result.reportPath.endswith(os.path.join("reports", "lint.md"))

    def test_emits_issue_for_unknown_page_type(self, tmp_path: Path) -> None:
        _write_page(
            tmp_path / "entities" / "bad.md",
            _entity_page(id_="entity.bad", title="Bad").replace(
                "pageType: entity", "pageType: concept"
            ),
        )
        config = _vault_config(tmp_path)
        result = asyncio.run(lt.lint_memory_wiki_vault(config))
        codes = [i.code for i in result.issues]
        assert "page-type-mismatch" in codes

    def test_emits_issue_for_duplicate_id(self, tmp_path: Path) -> None:
        _write_page(
            tmp_path / "entities" / "a.md",
            _entity_page(id_="entity.dup", title="A"),
        )
        _write_page(
            tmp_path / "concepts" / "b.md",
            _entity_page(id_="entity.dup", title="B"),
        )
        config = _vault_config(tmp_path)
        result = asyncio.run(lt.lint_memory_wiki_vault(config))
        codes = [i.code for i in result.issues]
        assert "duplicate-id" in codes

    def test_emits_issue_for_missing_source_ids(self, tmp_path: Path) -> None:
        # A non-source page with no sourceIds
        # should be flagged.
        _write_page(
            tmp_path / "entities" / "no-source.md",
            _entity_page(id_="entity.no-source", title="No source"),
        )
        config = _vault_config(tmp_path)
        result = asyncio.run(lt.lint_memory_wiki_vault(config))
        codes = [i.code for i in result.issues]
        assert "missing-source-ids" in codes

    def test_report_groups_issues_by_category(self, tmp_path: Path) -> None:
        _write_page(
            tmp_path / "entities" / "broken.md",
            "---\nbroken: [unclosed\n---\n\n# Broken\n",
        )
        _write_page(
            tmp_path / "entities" / "duplicate-a.md",
            _entity_page(id_="entity.dup", title="A"),
        )
        _write_page(
            tmp_path / "concepts" / "duplicate-b.md",
            _entity_page(id_="entity.dup", title="B"),
        )
        config = _vault_config(tmp_path)
        result = asyncio.run(lt.lint_memory_wiki_vault(config))
        # Categories: structure (missing-id /
        # missing-page-type / invalid-
        # frontmatter / duplicate-id).
        assert len(result.issuesByCategory["structure"]) >= 1


class TestReset:
    def test_reset_returns_none(self) -> None:
        assert lt.reset_memory_wiki_lint_state_for_tests() is None


class TestExports:
    def test_all_exports(self) -> None:
        for name in (
            "LINT_ISSUE_CATEGORIES",
            "LINT_ISSUE_CODES",
            "WikiLintIssue",
            "WikiLintResult",
            "lint_memory_wiki_vault",
            "reset_memory_wiki_lint_state_for_tests",
        ):
            assert hasattr(lt, name), f"missing export: {name}"
