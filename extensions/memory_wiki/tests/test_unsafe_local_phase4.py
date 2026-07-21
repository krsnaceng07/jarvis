"""Tests for extensions/memory_wiki/unsafe_local.py.

Phase 4.3g-mr4: ports the OpenClaw
``unsafe-local.ts`` test surface. The tests
focus on:

- ``detect_fence_language`` maps the file
  extension to the right markdown fence
  language.
- ``collect_unsafe_local_artifacts`` walks
  every configured path, surfaces
  unavailable paths, and dedupes by
  ``syncKey``.
- ``is_source_within_configured_path``
  detects inside / outside / equal
  relationships for a configured scope.
- ``sync_unsafe_local_sources`` imports
  private text files, is idempotent on a
  second sync, prunes stale pages from an
  available scope, preserves human notes
  during a temporary mount outage, and
  caps composed filenames to the
  filesystem component limit.
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
# pyright: reportReturnType=false

from __future__ import annotations

import asyncio
import os
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

from extensions.memory_wiki import unsafe_local as ul  # noqa: E402
from extensions.memory_wiki.config import resolve_memory_wiki_config  # noqa: E402
from extensions.memory_wiki.source_sync_state import (  # noqa: E402
    is_source_within_configured_path,
    reset_memory_wiki_source_sync_state_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level state before and after each test."""
    reset_memory_wiki_source_sync_state_for_tests()
    yield
    reset_memory_wiki_source_sync_state_for_tests()


def _global_config(
    *,
    path: str,
    vault_mode: str = "unsafe-local",
    unsafe_local_paths: list[str] | None = None,
    allow_private: bool = True,
) -> object:
    raw: dict = {
        "vault": {"scope": "global", "path": path},
        "vaultMode": vault_mode,
        "unsafeLocal": {
            "allowPrivateMemoryCoreAccess": allow_private,
            "paths": unsafe_local_paths or [],
        },
    }
    return resolve_memory_wiki_config(raw)


# ── detect_fence_language ──────────────────────────────────────


class TestDetectFenceLanguage:
    def test_json_extensions(self) -> None:
        assert ul.detect_fence_language("/tmp/x.json") == "json"
        assert ul.detect_fence_language("/tmp/x.jsonl") == "json"

    def test_yaml_extensions(self) -> None:
        assert ul.detect_fence_language("/tmp/x.yaml") == "yaml"
        assert ul.detect_fence_language("/tmp/x.yml") == "yaml"

    def test_txt_extension(self) -> None:
        assert ul.detect_fence_language("/tmp/x.txt") == "text"

    def test_markdown_extension(self) -> None:
        assert ul.detect_fence_language("/tmp/x.md") == "markdown"

    def test_unknown_extension_falls_back_to_markdown(self) -> None:
        assert ul.detect_fence_language("/tmp/x.bin") == "markdown"
        assert ul.detect_fence_language("/tmp/x") == "markdown"

    def test_case_insensitive(self) -> None:
        assert ul.detect_fence_language("/tmp/X.JSON") == "json"
        assert ul.detect_fence_language("/tmp/X.Yaml") == "yaml"


# ── is_source_within_configured_path ──────────────────────────


class TestIsSourceWithinConfiguredPath:
    def test_equal_paths(self, tmp_path: Path) -> None:
        assert is_source_within_configured_path(str(tmp_path), str(tmp_path)) is True

    def test_inside(self, tmp_path: Path) -> None:
        child = tmp_path / "sub" / "file.md"
        assert is_source_within_configured_path(str(child), str(tmp_path)) is True

    def test_outside_sibling(self, tmp_path: Path) -> None:
        other = tmp_path.parent / "elsewhere" / "x.md"
        assert is_source_within_configured_path(str(other), str(tmp_path)) is False

    def test_parent(self, tmp_path: Path) -> None:
        parent = tmp_path.parent
        assert is_source_within_configured_path(str(parent), str(tmp_path)) is False


# ── collect_unsafe_local_artifacts ────────────────────────────


class TestCollectUnsafeLocalArtifacts:
    def test_walks_directory_recursively(self, tmp_path: Path) -> None:
        (tmp_path / "nested").mkdir(parents=True)
        (tmp_path / "nested" / "state.md").write_text("# state", encoding="utf-8")
        (tmp_path / "nested" / "cache.json").write_text('{"ok":true}', encoding="utf-8")
        (tmp_path / "events.log").write_text("log", encoding="utf-8")
        direct = tmp_path / "single.md"
        direct.write_text("solo", encoding="utf-8")

        result = ul.collect_unsafe_local_artifacts([str(tmp_path / "nested"), str(direct)])

        # 2 nested + 1 direct = 3
        assert len(result.artifacts) == 3
        assert result.unavailableConfiguredPaths == []
        # All artifacts have the configured path.
        for artifact in result.artifacts:
            assert os.path.isabs(artifact.configuredPath)
            assert os.path.isabs(artifact.absolutePath)
            assert artifact.syncKey
            assert artifact.relativePath

    def test_filters_by_text_extension(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("md", encoding="utf-8")
        (tmp_path / "b.bin").write_bytes(b"\x00\x01")
        (tmp_path / "c.png").write_bytes(b"\x89PNG")
        result = ul.collect_unsafe_local_artifacts([str(tmp_path)])
        relative_paths = sorted(a.relativePath for a in result.artifacts)
        assert relative_paths == ["a.md"]

    def test_marks_unavailable_paths(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist"
        result = ul.collect_unsafe_local_artifacts([str(missing)])
        assert result.artifacts == []
        assert os.path.normpath(result.unavailableConfiguredPaths[0]) == os.path.normpath(
            str(missing)
        )

    def test_dedupes_by_sync_key(self, tmp_path: Path) -> None:
        # Same directory passed twice — same
        # absolute paths appear in both
        # configured scopes, so the dedupe by
        # syncKey keeps the last write wins.
        (tmp_path / "a.md").write_text("a", encoding="utf-8")
        result = ul.collect_unsafe_local_artifacts([str(tmp_path), str(tmp_path)])
        assert len(result.artifacts) == 1
        assert result.artifacts[0].relativePath == "a.md"


# ── sync_unsafe_local_sources ──────────────────────────────────


class TestSyncUnsafeLocalSources:
    def test_imports_private_paths_and_preserves_provenance(self, tmp_path: Path) -> None:
        private_dir = tmp_path / "private"
        nested = private_dir / "nested"
        nested.mkdir(parents=True)
        (nested / "state.md").write_text("# internal state\n", encoding="utf-8")
        (nested / "cache.json").write_text('{"ok":true}\n', encoding="utf-8")
        (nested / "blob.bin").write_bytes(b"\x00\x01")
        direct_path = private_dir / "events.log"
        direct_path.write_text("private log\n", encoding="utf-8")

        vault_dir = tmp_path / "vault"
        config = _global_config(
            path=str(vault_dir),
            unsafe_local_paths=[str(nested), str(direct_path)],
        )

        first = asyncio.run(ul.sync_unsafe_local_sources(config))

        # 2 nested text files + 1 direct file = 3 artifacts.
        assert first.artifact_count == 3
        assert first.imported_count == 3
        assert first.updated_count == 0
        assert first.skipped_count == 0
        assert first.removed_count == 0
        assert len(first.page_paths) == 3

        # First page should contain unsafe-local provenance.
        page_path = first.page_paths[0]
        page = (vault_dir / page_path).read_text(encoding="utf-8")
        assert "sourceType: memory-unsafe-local" in page
        assert "provenanceMode: unsafe-local" in page

        # Second sync: nothing changed, all skipped.
        second = asyncio.run(ul.sync_unsafe_local_sources(config))
        assert second.imported_count == 0
        assert second.updated_count == 0
        assert second.skipped_count == 3
        assert second.removed_count == 0

    def test_prunes_stale_pages_from_available_directory(self, tmp_path: Path) -> None:
        private_dir = tmp_path / "private"
        private_dir.mkdir(parents=True)
        secret = private_dir / "secret.md"
        secret.write_text("# private\n", encoding="utf-8")

        vault_dir = tmp_path / "vault"
        config = _global_config(path=str(vault_dir), unsafe_local_paths=[str(private_dir)])

        first = asyncio.run(ul.sync_unsafe_local_sources(config))
        first_page = first.page_paths[0]
        # The page exists + contains the body.
        assert (vault_dir / first_page).read_text(encoding="utf-8").count("# private") >= 1

        # Remove the source file → second sync
        # should prune the page.
        secret.unlink()
        second = asyncio.run(ul.sync_unsafe_local_sources(config))

        assert second.artifact_count == 0
        assert second.removed_count == 1
        assert not (vault_dir / first_page).exists()

    def test_preserves_pages_for_unavailable_paths(self, tmp_path: Path) -> None:
        unavailable_dir = tmp_path / "unavailable"
        available_dir = tmp_path / "available"
        unavailable_dir.mkdir(parents=True)
        available_dir.mkdir(parents=True)
        (unavailable_dir / "keep.md").write_text("# keep me\n", encoding="utf-8")
        (available_dir / "delete.md").write_text("# delete me\n", encoding="utf-8")

        vault_dir = tmp_path / "vault"
        config = _global_config(
            path=str(vault_dir),
            unsafe_local_paths=[str(unavailable_dir), str(available_dir)],
        )

        first = asyncio.run(ul.sync_unsafe_local_sources(config))
        page_contents = []
        for page_path in first.page_paths:
            content = (vault_dir / page_path).read_text(encoding="utf-8")
            page_contents.append((page_path, content))

        unavailable_page = next(p for p in page_contents if "# keep me" in p[1])
        available_page = next(p for p in page_contents if "# delete me" in p[1])

        # Inject a human note into the
        # unavailable page so we can verify
        # it survives the outage.
        original = (vault_dir / unavailable_page[0]).read_text(encoding="utf-8")
        updated = original.replace(
            "<!-- openclaw:human:start -->\n<!-- openclaw:human:end -->",
            "<!-- openclaw:human:start -->\nremember this\n<!-- openclaw:human:end -->",
        )
        (vault_dir / unavailable_page[0]).write_text(updated, encoding="utf-8")

        # Take the unavailable path offline + delete the available source.
        offline_path = tmp_path / "unavailable.offline"
        unavailable_dir.rename(offline_path)
        (available_dir / "delete.md").unlink()

        during_outage = asyncio.run(ul.sync_unsafe_local_sources(config))
        assert during_outage.artifact_count == 0
        assert during_outage.removed_count == 1
        # The unavailable page still has the
        # human note.
        offline_page_body = (vault_dir / unavailable_page[0]).read_text(encoding="utf-8")
        assert "remember this" in offline_page_body
        # The available page is pruned.
        assert not (vault_dir / available_page[0]).exists()

        # Bring the unavailable path back.
        offline_path.rename(unavailable_dir)
        after_recovery = asyncio.run(ul.sync_unsafe_local_sources(config))
        assert after_recovery.skipped_count == 1
        assert after_recovery.removed_count == 0
        # Human note is still there.
        recovered = (vault_dir / unavailable_page[0]).read_text(encoding="utf-8")
        assert "remember this" in recovered

    def test_no_op_when_vault_mode_is_not_unsafe_local(self, tmp_path: Path) -> None:
        vault_dir = tmp_path / "vault"
        config = _global_config(
            path=str(vault_dir),
            vault_mode="shared",
            unsafe_local_paths=[],
            allow_private=True,
        )
        result = asyncio.run(ul.sync_unsafe_local_sources(config))
        assert result.imported_count == 0
        assert result.updated_count == 0
        assert result.skipped_count == 0
        assert result.removed_count == 0
        assert result.artifact_count == 0
        assert result.page_paths == []

    def test_no_op_when_private_access_disallowed(self, tmp_path: Path) -> None:
        vault_dir = tmp_path / "vault"
        config = _global_config(
            path=str(vault_dir),
            allow_private=False,
            unsafe_local_paths=[str(tmp_path / "anything")],
        )
        result = asyncio.run(ul.sync_unsafe_local_sources(config))
        assert result.imported_count == 0
        assert result.artifact_count == 0

    def test_caps_composed_filenames_to_byte_limit(self, tmp_path: Path) -> None:
        # Use a long CJK prefix so the page
        # filename would exceed the 255-byte
        # limit without the slug cap.
        prefix = "漢" * 50
        private_dir = tmp_path / f"{prefix}-private"
        nested_dir = private_dir / f"{'語' * 50}-nested"
        nested_dir.mkdir(parents=True)
        secret_path = nested_dir / f"{'録' * 50}.md"
        secret_path.write_text("# very private\n", encoding="utf-8")

        vault_dir = tmp_path / "vault"
        config = _global_config(path=str(vault_dir), unsafe_local_paths=[str(private_dir)])

        result = asyncio.run(ul.sync_unsafe_local_sources(config))
        assert result.imported_count == 1
        page_path = result.page_paths[0]
        # The page-path filename is capped
        # to 255 bytes per OpenClaw.
        assert len(os.path.basename(page_path).encode("utf-8")) <= 255
        # The body still round-trips.
        body = (vault_dir / page_path).read_text(encoding="utf-8")
        assert "# very private" in body
