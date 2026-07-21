"""Tests for extensions/memory_wiki/compile_pipeline.py.

Phase 4.3d-mr4: ports the OpenClaw
``compileMemoryWiki`` orchestrator (scan phase).
The tests focus on:

- ``should_skip_page_for_compile`` correctly
  filters out auto-generated ``index.md`` files
  + the ``.openclaw-wiki/`` / ``_attachments/`` /
  ``_views/`` skip directories.
- ``compile_wiki_vault`` walks the vault, scans
  every ``.md`` page, and returns a populated
  ``CompileWikiVaultResult`` with the right
  per-page results.
- Pages with no frontmatter are recorded as
  ``ignored_paths`` (not ``pages``).
- Pages with malformed (non-mapping) YAML
  frontmatter are recorded as ``invalid_paths``.
- A ``compile`` log entry is appended on a
  successful scan.
- Empty / non-existent vaults return an empty
  result without raising.
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

from extensions.memory_wiki.compile_pipeline import (  # noqa: E402
    CompileWikiVaultResult,
    compile_wiki_vault,
    should_skip_page_for_compile,
)
from extensions.memory_wiki.config import resolve_memory_wiki_config  # noqa: E402


def _make_page(
    path: Path,
    *,
    frontmatter: dict[str, object] | None = None,
) -> None:
    """Write a markdown file with the given frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if frontmatter is None:
        path.write_text("# No frontmatter\n\nbody\n", encoding="utf-8")
    else:
        fm_text = json.dumps(frontmatter, ensure_ascii=False)
        path.write_text(
            f"---\n{fm_text}\n---\n# Title\n\nbody\n",
            encoding="utf-8",
        )


class TestShouldSkipPageForCompile:
    def test_skips_index_md(self) -> None:
        assert should_skip_page_for_compile("entities/index.md") is True
        assert should_skip_page_for_compile("sources/index.md") is True

    def test_skips_metadata_directories(self) -> None:
        assert should_skip_page_for_compile(".openclaw-wiki/log.jsonl") is True
        assert should_skip_page_for_compile("_attachments/foo.md") is True
        assert should_skip_page_for_compile("_views/index.md") is True

    def test_keeps_real_pages(self) -> None:
        assert should_skip_page_for_compile("entities/alpha.md") is False
        assert should_skip_page_for_compile("syntheses/foo.md") is False
        assert should_skip_page_for_compile("reports/x.md") is False


class TestCompileWikiVault:
    def test_empty_vault(self, tmp_path: Path) -> None:
        config = resolve_memory_wiki_config({"vault": {"path": str(tmp_path)}}, homedir="/h")
        result = compile_wiki_vault(config)
        assert isinstance(result, CompileWikiVaultResult)
        assert result.vault_path == str(tmp_path)
        assert result.pages == []
        assert result.ignored_paths == []
        assert result.invalid_paths == []
        assert result.scanned_count == 0
        assert result.invalid_count == 0
        assert result.ignored_count == 0
        assert result.valid_count == 0

    def test_nonexistent_vault(self, tmp_path: Path) -> None:
        config = resolve_memory_wiki_config(
            {"vault": {"path": str(tmp_path / "missing")}}, homedir="/h"
        )
        result = compile_wiki_vault(config)
        assert result.pages == []
        assert result.scanned_count == 0

    def test_walks_vault_and_scans_pages(self, tmp_path: Path) -> None:
        _make_page(
            tmp_path / "entities" / "alpha.md",
            frontmatter={"id": "entity.alpha", "title": "Alpha"},
        )
        _make_page(
            tmp_path / "syntheses" / "summary.md",
            frontmatter={"id": "synthesis.summary", "title": "Summary"},
        )
        _make_page(
            tmp_path / "sources" / "raw.md",
            frontmatter={"id": "source.raw", "title": "Raw"},
        )
        config = resolve_memory_wiki_config({"vault": {"path": str(tmp_path)}}, homedir="/h")
        result = compile_wiki_vault(config)
        assert result.scanned_count == 3
        assert result.invalid_count == 0
        assert result.ignored_count == 0
        # Each page has the right relative path +
        # frontmatter id.
        ids = sorted(page.id for page in result.pages)
        assert ids == [
            "entity.alpha",
            "source.raw",
            "synthesis.summary",
        ]
        # Relative paths use forward slashes.
        for page in result.pages:
            assert "\\" not in page.relative_path

    def test_skips_index_md(self, tmp_path: Path) -> None:
        _make_page(
            tmp_path / "entities" / "index.md",
            frontmatter=None,  # no frontmatter
        )
        _make_page(
            tmp_path / "entities" / "alpha.md",
            frontmatter={"id": "entity.alpha"},
        )
        config = resolve_memory_wiki_config({"vault": {"path": str(tmp_path)}}, homedir="/h")
        result = compile_wiki_vault(config)
        # Only ``alpha.md`` is scanned; the
        # auto-generated ``index.md`` is filtered
        # out at the orchestrator level.
        assert result.scanned_count == 1
        assert result.pages[0].id == "entity.alpha"

    def test_records_ignored_pages(self, tmp_path: Path) -> None:
        # A page without frontmatter is ``ignored``
        # by the scan; the orchestrator records the
        # path in ``ignored_paths``.
        _make_page(tmp_path / "notes" / "scratch.md", frontmatter=None)
        config = resolve_memory_wiki_config({"vault": {"path": str(tmp_path)}}, homedir="/h")
        result = compile_wiki_vault(config)
        assert result.scanned_count == 0
        assert result.ignored_count == 1
        assert "notes/scratch.md" in result.ignored_paths

    def test_records_invalid_frontmatter(self, tmp_path: Path) -> None:
        page = tmp_path / "entities" / "broken.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        # Malformed: a non-mapping YAML frontmatter.
        page.write_text("---\n[a, b]\n---\n# Body\n", encoding="utf-8")
        config = resolve_memory_wiki_config({"vault": {"path": str(tmp_path)}}, homedir="/h")
        result = compile_wiki_vault(config)
        assert result.invalid_count == 1
        assert result.invalid_paths[0].relative_path == "entities/broken.md"

    def test_appends_compile_log_entry(self, tmp_path: Path) -> None:
        _make_page(
            tmp_path / "entities" / "alpha.md",
            frontmatter={"id": "entity.alpha"},
        )
        config = resolve_memory_wiki_config({"vault": {"path": str(tmp_path)}}, homedir="/h")
        compile_wiki_vault(config)
        # The log entry is appended to
        # ``.openclaw-wiki/log.jsonl``.
        log_path = tmp_path / ".openclaw-wiki" / "log.jsonl"
        assert log_path.exists()
        text = log_path.read_text(encoding="utf-8")
        # Find the compile entry.
        for line in text.splitlines():
            if not line.strip():
                continue
            parsed = json.loads(line)
            if parsed.get("type") == "compile":
                details = parsed.get("details", {})
                assert details.get("scannedCount") == 1
                assert details.get("invalidCount") == 0
                break
        else:
            raise AssertionError("no compile log entry found")
