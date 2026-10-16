"""Tests for memory_core.dreaming_repair — Phase 4.4f.

Mirrors the TypeScript ``test_dreaming-repair.test.ts`` patterns.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from extensions.memory_core import dreaming_repair as dr


# ── Path validation ────────────────────────────────────────────────────


def test_require_absolute_workspace_dir_rejects_empty(tmp_path: Path) -> None:
    """Empty path raises ValueError."""
    with pytest.raises(ValueError, match="required"):
        dr._require_absolute_workspace_dir("")
    with pytest.raises(ValueError, match="required"):
        dr._require_absolute_workspace_dir("   ")


def test_require_absolute_workspace_dir_rejects_relative(tmp_path: Path) -> None:
    """Relative path raises ValueError."""
    with pytest.raises(ValueError, match="absolute"):
        dr._require_absolute_workspace_dir("relative/path")


def test_require_absolute_workspace_dir_accepts_absolute(tmp_path: Path) -> None:
    """Absolute path is resolved and returned."""
    result = dr._require_absolute_workspace_dir(str(tmp_path))
    assert os.path.isabs(result)
    assert os.path.normpath(result) == os.path.normpath(str(tmp_path))


# ── Dreams path resolution ─────────────────────────────────────────────


def test_resolve_existing_dreams_path_uppercase(tmp_path: Path) -> None:
    """``DREAMS.md`` found first."""
    (tmp_path / "DREAMS.md").write_text("x", encoding="utf-8")
    result = dr._resolve_existing_dreams_path(str(tmp_path))
    assert result is not None
    assert result.endswith("DREAMS.md")


def test_resolve_existing_dreams_path_lowercase(tmp_path: Path) -> None:
    """``dreams.md`` found when DREAMS.md missing (or on case-insensitive FS)."""
    (tmp_path / "dreams.md").write_text("x", encoding="utf-8")
    result = dr._resolve_existing_dreams_path(str(tmp_path))
    # On case-insensitive FS (Windows), DREAMS.md == dreams.md so the
    # first iteration matches.
    assert result is not None
    assert result.lower().endswith("dreams.md")


def test_resolve_existing_dreams_path_missing(tmp_path: Path) -> None:
    """Returns ``None`` when no dreams file exists."""
    assert dr._resolve_existing_dreams_path(str(tmp_path)) is None


# ── Session corpus listing ─────────────────────────────────────────────


def test_list_session_corpus_files_missing_dir(tmp_path: Path) -> None:
    """Returns ``[]`` when the corpus dir doesn't exist."""
    result = dr._list_session_corpus_files(str(tmp_path / "missing"))
    assert result == []


def test_list_session_corpus_files_only_txt(tmp_path: Path) -> None:
    """Only ``*.txt`` files are returned; other files are skipped."""
    corpus = tmp_path / "memory" / ".dreams" / "session-corpus"
    corpus.mkdir(parents=True)
    (corpus / "a.txt").write_text("a", encoding="utf-8")
    (corpus / "b.txt").write_text("b", encoding="utf-8")
    (corpus / "c.json").write_text("{}", encoding="utf-8")
    (corpus / "d.md").write_text("# x", encoding="utf-8")

    result = dr._list_session_corpus_files(str(corpus))
    assert len(result) == 2
    assert all(r.endswith(".txt") for r in result)


def test_list_session_corpus_files_sorted(tmp_path: Path) -> None:
    """Files are returned in sorted order."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for name in ("z.txt", "a.txt", "m.txt"):
        (corpus / name).write_text("x", encoding="utf-8")
    result = dr._list_session_corpus_files(str(corpus))
    names = [os.path.basename(p) for p in result]
    assert names == ["a.txt", "m.txt", "z.txt"]


# ── Suspicious line detection ─────────────────────────────────────────


def test_is_suspicious_session_corpus_line_clean() -> None:
    """Normal session text is not suspicious."""
    assert dr._is_suspicious_session_corpus_line("user: hello there") is False


def test_is_suspicious_session_corpus_line_self_ingested() -> None:
    """Lines containing both the prompt prefix and session key prefix are suspicious."""
    line = (
        "Write a dream diary entry from these memory fragments "
        "sessionKey=dreaming-narrative-light-abc123"
    )
    assert dr._is_suspicious_session_corpus_line(line) is True


def test_is_suspicious_session_corpus_line_prompt_only() -> None:
    """Prompt prefix alone is not suspicious."""
    assert (
        dr._is_suspicious_session_corpus_line(
            "Write a dream diary entry from these memory fragments"
        )
        is False
    )


def test_is_suspicious_session_corpus_line_session_key_only() -> None:
    """Session key alone is not suspicious."""
    assert (
        dr._is_suspicious_session_corpus_line("sessionKey=dreaming-narrative-light-abc123") is False
    )


# ── Archive timestamp ──────────────────────────────────────────────────


def test_build_archive_timestamp_format() -> None:
    """ISO-8601 with ``:`` and ``.`` replaced by ``-``."""
    now = datetime(2025, 12, 15, 14, 30, 45, 123456, tzinfo=timezone.utc)
    result = dr._build_archive_timestamp(now)
    # Contains no colons or periods
    assert ":" not in result
    assert "." not in result
    # Still recognizable
    assert "2025-12-15" in result


# ── Archivable path safety ─────────────────────────────────────────────


def test_ensure_archivable_path_missing(tmp_path: Path) -> None:
    """Missing path returns ``None``."""
    assert dr._ensure_archivable_path(str(tmp_path / "missing")) is None


def test_ensure_archivable_path_file(tmp_path: Path) -> None:
    """Regular file returns ``"file"``."""
    p = tmp_path / "file.txt"
    p.write_text("x", encoding="utf-8")
    assert dr._ensure_archivable_path(str(p)) == "file"


def test_ensure_archivable_path_dir(tmp_path: Path) -> None:
    """Directory returns ``"dir"``."""
    d = tmp_path / "subdir"
    d.mkdir()
    assert dr._ensure_archivable_path(str(d)) == "dir"


def test_ensure_archivable_path_symlink_refused(tmp_path: Path) -> None:
    """Symlinks raise ``RuntimeError``."""
    if not hasattr(os, "symlink"):
        pytest.skip("symlink not available")
    target = tmp_path / "target.txt"
    target.write_text("x", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink not supported: {exc}")
    with pytest.raises(RuntimeError, match="symlink"):
        dr._ensure_archivable_path(str(link))


# ── Move to archive ────────────────────────────────────────────────────


def test_move_to_archive_missing(tmp_path: Path) -> None:
    """Returns ``None`` for missing paths."""
    archive_dir = str(tmp_path / "archive")
    result = dr._move_to_archive(str(tmp_path / "missing"), archive_dir)
    assert result is None
    assert not os.path.isdir(archive_dir)  # not created


def test_move_to_archive_file(tmp_path: Path) -> None:
    """File is moved into the archive dir with uuid suffix."""
    src = tmp_path / "src.txt"
    src.write_text("contents", encoding="utf-8")
    archive_dir = str(tmp_path / "archive")
    destination = dr._move_to_archive(str(src), archive_dir)
    assert destination is not None
    assert os.path.isdir(archive_dir)
    assert os.path.isfile(destination)
    assert os.path.basename(destination).startswith("src.txt.")
    assert not src.exists()
    assert open(destination, encoding="utf-8").read() == "contents"


def test_move_to_archive_dir(tmp_path: Path) -> None:
    """Directory is moved into the archive dir with uuid suffix."""
    src = tmp_path / "srcdir"
    src.mkdir()
    (src / "file.txt").write_text("x", encoding="utf-8")
    archive_dir = str(tmp_path / "archive")
    destination = dr._move_to_archive(str(src), archive_dir)
    assert destination is not None
    assert os.path.isdir(destination)
    assert not src.exists()
    assert (Path(destination) / "file.txt").exists()


# ── Audit (integration) ───────────────────────────────────────────────


def test_audit_dreaming_artifacts_empty_workspace(tmp_path: Path) -> None:
    """Empty workspace → no issues, no corpus, no ingestion."""
    summary = dr.audit_dreaming_artifacts(str(tmp_path))
    assert summary["sessionCorpusFileCount"] == 0
    assert summary["suspiciousSessionCorpusLineCount"] == 0
    assert summary["sessionIngestionExists"] is False
    assert summary["issues"] == []
    assert "dreamsPath" not in summary


def test_audit_dreaming_artifacts_with_clean_corpus(tmp_path: Path) -> None:
    """Corpus with normal session text → no issues."""
    corpus = tmp_path / "memory" / ".dreams" / "session-corpus"
    corpus.mkdir(parents=True)
    (corpus / "session1.txt").write_text("user: hello\nassistant: hi there", encoding="utf-8")
    summary = dr.audit_dreaming_artifacts(str(tmp_path))
    assert summary["sessionCorpusFileCount"] == 1
    assert summary["suspiciousSessionCorpusFileCount"] == 0
    assert summary["suspiciousSessionCorpusLineCount"] == 0
    assert summary["issues"] == []


def test_audit_dreaming_artifacts_with_self_ingested(tmp_path: Path) -> None:
    """Corpus with leaked narrative content → warn + suspicious counts."""
    corpus = tmp_path / "memory" / ".dreams" / "session-corpus"
    corpus.mkdir(parents=True)
    # One line that contains BOTH the prompt prefix AND the session
    # key prefix — that combination is the "self-ingested" signal.
    (corpus / "leak.txt").write_text(
        "Write a dream diary entry from these memory fragments "
        "sessionKey=dreaming-narrative-light-abc123\n"
        "Some normal text\n",
        encoding="utf-8",
    )
    summary = dr.audit_dreaming_artifacts(str(tmp_path))
    assert summary["sessionCorpusFileCount"] == 1
    assert summary["suspiciousSessionCorpusFileCount"] == 1
    assert summary["suspiciousSessionCorpusLineCount"] == 1
    issue_codes = [i["code"] for i in summary["issues"]]
    assert "dreaming-session-corpus-self-ingested" in issue_codes


def test_audit_dreaming_artifacts_with_diary(tmp_path: Path) -> None:
    """DREAMS.md present → ``dreamsPath`` included in summary."""
    (tmp_path / "DREAMS.md").write_text("# Top", encoding="utf-8")
    summary = dr.audit_dreaming_artifacts(str(tmp_path))
    assert summary.get("dreamsPath", "").endswith("DREAMS.md")
    assert summary["issues"] == []


def test_audit_dreaming_artifacts_with_ingestion_file(tmp_path: Path) -> None:
    """Legacy JSON ingestion file → ``sessionIngestionExists=True``."""
    ing = tmp_path / "memory" / ".dreams" / "session-ingestion.json"
    ing.parent.mkdir(parents=True)
    ing.write_text("[]", encoding="utf-8")
    summary = dr.audit_dreaming_artifacts(str(tmp_path))
    assert summary["sessionIngestionExists"] is True


def test_audit_dreaming_artifacts_rejects_relative_path(tmp_path: Path) -> None:
    """Relative path raises ValueError."""
    with pytest.raises(ValueError, match="absolute"):
        dr.audit_dreaming_artifacts("relative/path")


# ── Repair (integration) ──────────────────────────────────────────────


def test_repair_dreaming_artifacts_empty_workspace(tmp_path: Path) -> None:
    """No artifacts → no changes, empty warnings."""
    result = dr.repair_dreaming_artifacts(str(tmp_path))
    assert result["changed"] is False
    assert result["archivedDreamsDiary"] is False
    assert result["archivedSessionCorpus"] is False
    assert result["archivedSessionIngestion"] is False
    assert result["archivedPaths"] == []
    assert result["warnings"] == []


def test_repair_dreaming_artifacts_archives_corpus(tmp_path: Path) -> None:
    """Session corpus is moved into the archive directory."""
    corpus = tmp_path / "memory" / ".dreams" / "session-corpus"
    corpus.mkdir(parents=True)
    (corpus / "a.txt").write_text("a", encoding="utf-8")
    result = dr.repair_dreaming_artifacts(str(tmp_path))
    assert result["changed"] is True
    assert result["archivedSessionCorpus"] is True
    assert not corpus.exists()
    assert len(result["archivedPaths"]) == 1
    # Archive dir was created
    assert result.get("archiveDir") is not None
    assert os.path.isdir(result["archiveDir"])


def test_repair_dreaming_artifacts_archives_ingestion(tmp_path: Path) -> None:
    """Legacy session-ingestion JSON is moved into the archive directory."""
    ing = tmp_path / "memory" / ".dreams" / "session-ingestion.json"
    ing.parent.mkdir(parents=True)
    ing.write_text("[]", encoding="utf-8")
    result = dr.repair_dreaming_artifacts(str(tmp_path))
    assert result["changed"] is True
    assert result["archivedSessionIngestion"] is True
    assert not ing.exists()
    assert len(result["archivedPaths"]) == 1


def test_repair_dreaming_artifacts_archives_diary_when_requested(tmp_path: Path) -> None:
    """``archive_diary=True`` → DREAMS.md is also moved."""
    (tmp_path / "DREAMS.md").write_text("# Diary", encoding="utf-8")
    result = dr.repair_dreaming_artifacts(str(tmp_path), archive_diary=True)
    assert result["archivedDreamsDiary"] is True
    assert not (tmp_path / "DREAMS.md").exists()


def test_repair_dreaming_artifacts_skips_diary_by_default(tmp_path: Path) -> None:
    """``archive_diary=False`` (default) → DREAMS.md is left in place."""
    (tmp_path / "DREAMS.md").write_text("# Diary", encoding="utf-8")
    result = dr.repair_dreaming_artifacts(str(tmp_path))
    assert result["archivedDreamsDiary"] is False
    assert (tmp_path / "DREAMS.md").exists()


def test_repair_dreaming_artifacts_clears_ingestion_state(tmp_path: Path) -> None:
    """SQLite plugin state for session-ingestion namespaces is cleared.

    The keyed store must be configured (typically by plugin init) for
    the clear to actually run; if not configured, ``RuntimeError`` is
    raised and added to the result's warnings list. Either way, the
    repair itself completes without raising.
    """
    # Seed the legacy JSON file so repair has something to move
    ing = tmp_path / "memory" / ".dreams" / "session-ingestion.json"
    ing.parent.mkdir(parents=True)
    ing.write_text("[]", encoding="utf-8")

    result = dr.repair_dreaming_artifacts(str(tmp_path))
    assert result["changed"] is True
    # The clear is best-effort: warnings may or may not be empty
    # depending on whether the keyed store is configured. The point
    # of this test is "the repair function completes without raising"
    # — so just check the return shape.
    assert "warnings" in result
    assert isinstance(result["warnings"], list)


def test_repair_dreaming_artifacts_rejects_relative_path(tmp_path: Path) -> None:
    """Relative path raises ValueError."""
    with pytest.raises(ValueError, match="absolute"):
        dr.repair_dreaming_artifacts("relative/path")


def test_repair_dreaming_artifacts_uses_now_timestamp(tmp_path: Path) -> None:
    """The ``now`` parameter controls the archive directory name."""
    corpus = tmp_path / "memory" / ".dreams" / "session-corpus"
    corpus.mkdir(parents=True)
    (corpus / "a.txt").write_text("a", encoding="utf-8")
    fixed_now = datetime(2025, 12, 15, 14, 30, 45, tzinfo=timezone.utc)
    result = dr.repair_dreaming_artifacts(str(tmp_path), now=fixed_now)
    assert result.get("archiveDir") is not None
    # The archive dir name is the formatted timestamp
    expected_ts = dr._build_archive_timestamp(fixed_now)
    assert os.path.basename(result["archiveDir"]) == expected_ts
