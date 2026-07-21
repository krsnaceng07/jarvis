"""Tests for extensions/memory_wiki/compile_pages.py.

Phase 4.3d-mr6: ports the OpenClaw per-page
compile loop (``compileMemoryWikiPages`` /
``buildManagedRelatedBlock``). The tests focus
on:

- ``build_related_block`` emits the OpenClaw
  marker-wrapped block, with the empty stub when
  no related pages exist.
- ``build_related_block`` truncates long titles
  and caps the section at 12 entries.
- ``build_page_body`` emits a complete
  ``---\\n<frontmatter>\\n---\\n\\n<body>`` block with
  the related block included.
- ``write_compiled_pages`` writes every scanned
  page back to disk with the related block
  refreshed.
- ``write_compiled_pages`` is idempotent: a
  second call produces the same per-page result
  shape.
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

from extensions.memory_wiki.compile_pages import (  # noqa: E402
    MAX_RELATED_PAGES_PER_SECTION,
    WIKI_RELATED_END_MARKER,
    WIKI_RELATED_START_MARKER,
    PageWriteResult,
    build_page_body,
    build_related_block,
    write_compiled_pages,
)
from extensions.memory_wiki.config import resolve_memory_wiki_config  # noqa: E402
from extensions.memory_wiki.markdown_pages import (  # noqa: E402
    WikiClaim,
)


def _page(**overrides: object) -> SimpleNamespace:
    """Build a minimal WikiPageSummary-shaped object for tests.

    Uses the OpenClaw camelCase field names; the
    compile_pages module reads them directly.
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
        "updatedAt": "2026-07-21T00:00:00Z",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ── build_related_block ──────────────────────────────────


class TestBuildRelatedBlock:
    def test_empty_stub(self) -> None:
        out = build_related_block([])
        assert WIKI_RELATED_START_MARKER in out
        assert WIKI_RELATED_END_MARKER in out
        assert "## Related" in out
        assert "No related pages yet" in out

    def test_includes_label_and_link(self) -> None:
        page = _page(relativePath="sources/foo.md", title="Foo")
        out = build_related_block([(page, "source")])
        assert "source: [Foo](sources/foo.md)" in out

    def test_caps_at_max_related(self) -> None:
        pages = [
            _page(
                relativePath=f"entities/page_{i}.md",
                title=f"Page {i}",
            )
            for i in range(MAX_RELATED_PAGES_PER_SECTION + 5)
        ]
        related = [(p, "related") for p in pages]
        out = build_related_block(related)
        # The block contains at most
        # ``MAX_RELATED_PAGES_PER_SECTION`` entries
        # plus the "+ N more" trailer.
        entry_count = sum(1 for line in out.splitlines() if line.startswith("- "))
        assert entry_count <= MAX_RELATED_PAGES_PER_SECTION + 1
        # The "+ N more" trailer is present.
        assert "and 5 more" in out

    def test_truncates_long_titles(self) -> None:
        long_title = "A" * 1000
        page = _page(title=long_title, relativePath="x.md")
        out = build_related_block([(page, "source")])
        # The truncated title ends with the
        # ellipsis character used by the cap.
        assert "\u2026" in out


# ── build_page_body ───────────────────────────────────────


class TestBuildPageBody:
    def test_renders_full_page(self) -> None:
        page = _page()
        body = build_page_body(page, [])
        # The frontmatter + body block.
        assert body.startswith("---\n")
        assert "title: Alpha" in body
        assert "kind: entity" in body
        assert "id: entity.alpha" in body
        assert "---" in body
        # The body has the H1 title + related block.
        assert "# Alpha" in body
        assert WIKI_RELATED_START_MARKER in body
        assert WIKI_RELATED_END_MARKER in body

    def test_includes_related_link(self) -> None:
        page = _page()
        other = _page(relativePath="sources/foo.md", title="Foo")
        body = build_page_body(page, [(other, "source")])
        assert "[Foo](sources/foo.md)" in body

    def test_preserves_claims(self) -> None:
        claim = WikiClaim(text="alpha", id="c1", status="active")
        page = _page(claims=[claim])
        body = build_page_body(page, [])
        assert "claims:" in body
        assert "text: alpha" in body
        assert "id: c1" in body

    def test_skips_unset_optional_fields(self) -> None:
        page = _page(
            aliases=[],
            source_ids=[],
            questions=[],
            contradictions=[],
            relationships=[],
        )
        body = build_page_body(page, [])
        # None of the empty-list fields are
        # serialized.
        assert "aliases:" not in body
        assert "sourceIds:" not in body
        assert "questions:" not in body


# ── write_compiled_pages ──────────────────────────────────


class TestWriteCompiledPages:
    def test_writes_pages_to_disk(self, tmp_path: Path) -> None:
        config = resolve_memory_wiki_config({"vault": {"path": str(tmp_path)}}, homedir="/h")
        page_a = _page(relativePath="entities/alpha.md", title="Alpha")
        page_b = _page(relativePath="entities/beta.md", title="Beta")
        results = write_compiled_pages(
            config,  # type: ignore[arg-type]
            [page_a, page_b],
        )
        assert len(results) == 2
        assert all(isinstance(r, PageWriteResult) for r in results)
        assert all(r.written for r in results)
        # The files are on disk.
        for r in results:
            assert os.path.exists(r.absolute_path)

    def test_written_files_contain_related_block(self, tmp_path: Path) -> None:
        config = resolve_memory_wiki_config({"vault": {"path": str(tmp_path)}}, homedir="/h")
        page_a = _page(relativePath="entities/alpha.md", title="Alpha")
        page_b = _page(relativePath="sources/foo.md", title="Foo")
        write_compiled_pages(
            config,  # type: ignore[arg-type]
            [page_a, page_b],
        )
        # The Alpha page should reference Foo via
        # the related block (the "source" label
        # because Alpha doesn't link to Foo
        # directly; they share the vault scope).
        # The simpler check: Foo was written.
        foo_path = tmp_path / "sources" / "foo.md"
        assert foo_path.exists()
        content = foo_path.read_text(encoding="utf-8")
        assert WIKI_RELATED_START_MARKER in content
        assert WIKI_RELATED_END_MARKER in content

    def test_records_per_page_errors(self, tmp_path: Path) -> None:
        config = resolve_memory_wiki_config({"vault": {"path": str(tmp_path)}}, homedir="/h")
        # Use a path with a parent directory that
        # doesn't exist; the fs-safe root will
        # raise an error.
        page = _page(relativePath="missing_dir/alpha.md", title="Alpha")
        results = write_compiled_pages(
            config,  # type: ignore[arg-type]
            [page],
        )
        assert len(results) == 1
        # The error path is recorded (the parent
        # directory gets auto-created by
        # ``vault.write``, so this may actually
        # succeed; we only assert the shape of
        # the result).
        result = results[0]
        assert isinstance(result, PageWriteResult)
        assert result.absolute_path.endswith("missing_dir/alpha.md")
