"""memory_core.dreaming_repair — audit + repair dreaming artifacts.

OpenClaw parity: mirrors ``extensions/memory-core/src/dreaming-repair.ts``
(310 LOC). Two top-level operations:

- ``audit_dreaming_artifacts(workspace_dir)`` — inspect ``DREAMS.md``,
  the session corpus directory, and the session-ingestion state. Emits
  warnings for "self-ingested" narrative content that leaked into the
  corpus, and errors for unreadable artifacts.
- ``repair_dreaming_artifacts(workspace_dir, archive_diary=False,
  now=None)`` — archive (move) the session corpus and session-ingestion
  state into a timestamped ``.openclaw-repair/dreaming/<ts>/`` folder
  inside the workspace, optionally also archiving the DREAMS.md diary.

Key port decisions:
- All paths are validated as absolute (raises ``ValueError`` otherwise).
- Symlinks and non-file/non-dir artifacts are refused when archiving
  (mirrors OpenClaw's ``ensureArchivablePath``).
- The session corpus "suspicious line" check matches
  ``isSuspiciousSessionCorpusLine``: line contains both the narrative
  prompt prefix ("Write a dream diary entry from these memory
  fragments") AND a ``dreaming-narrative-`` session key prefix.
- Archive directory is named ``<ts>`` where ``<ts>`` is an
  ISO-8601 timestamp with ``:`` and ``.`` replaced by ``-`` (matches
  OpenClaw's ``buildArchiveTimestamp``).
- Each archived path gets a ``.<uuid>`` suffix to avoid collisions
  within the same archive batch.
- The session-ingestion state is cleared in two places:
  1. The legacy JSON file at
     ``<workspace>/memory/.dreams/session-ingestion.json`` is moved.
  2. The SQLite plugin state under the
     ``DREAMING_SESSION_INGESTION_FILES_NAMESPACE`` +
     ``DREAMING_SESSION_INGESTION_SEEN_NAMESPACE`` namespaces is
     cleared via ``clear_memory_core_workspace_namespace``.
"""

from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime
from typing import Literal, TypedDict

from .dreaming_dreams_file import DREAMS_FILENAMES
from .dreaming_state import (
    DREAMING_SESSION_INGESTION_FILES_NAMESPACE,
    DREAMING_SESSION_INGESTION_SEEN_NAMESPACE,
    clear_memory_core_workspace_namespace,
    read_memory_core_workspace_entries,
)

# ── Constants ──────────────────────────────────────────────────────────

SESSION_CORPUS_RELATIVE_DIR = os.path.join("memory", ".dreams", "session-corpus")
SESSION_INGESTION_RELATIVE_PATH = os.path.join("memory", ".dreams", "session-ingestion.json")
REPAIR_ARCHIVE_RELATIVE_DIR = os.path.join(".openclaw-repair", "dreaming")
DREAMING_NARRATIVE_RUN_PREFIX = "dreaming-narrative-"
DREAMING_NARRATIVE_PROMPT_PREFIX = "Write a dream diary entry from these memory fragments"


# ── Types ──────────────────────────────────────────────────────────────

DreamingIssueCode = Literal[
    "dreaming-session-corpus-unreadable",
    "dreaming-session-corpus-self-ingested",
    "dreaming-session-ingestion-unreadable",
    "dreaming-diary-unreadable",
]


class DreamingArtifactsAuditIssue(TypedDict, total=False):
    severity: Literal["warn", "error"]
    code: str
    message: str
    fixable: bool


class DreamingArtifactsAuditSummary(TypedDict, total=False):
    dreamsPath: str
    sessionCorpusDir: str
    sessionCorpusFileCount: int
    suspiciousSessionCorpusFileCount: int
    suspiciousSessionCorpusLineCount: int
    sessionIngestionPath: str
    sessionIngestionExists: bool
    issues: list[DreamingArtifactsAuditIssue]


class RepairDreamingArtifactsResult(TypedDict, total=False):
    changed: bool
    archiveDir: str
    archivedDreamsDiary: bool
    archivedSessionCorpus: bool
    archivedSessionIngestion: bool
    archivedPaths: list[str]
    warnings: list[str]


# ── Path helpers ───────────────────────────────────────────────────────


def _require_absolute_workspace_dir(raw_workspace_dir: str) -> str:
    """Validate and resolve ``raw_workspace_dir``.

    Mirrors OpenClaw's ``requireAbsoluteWorkspaceDir``. Raises
    ``ValueError`` when the path is empty or relative.
    """
    trimmed = (raw_workspace_dir or "").strip()
    if not trimmed:
        raise ValueError("workspaceDir is required")
    # os.path.isabs is platform-aware; on Windows ``C:\foo`` is absolute.
    if not os.path.isabs(trimmed):
        raise ValueError("workspaceDir must be an absolute path")
    return os.path.normpath(os.path.abspath(trimmed))


def _resolve_existing_dreams_path(workspace_dir: str) -> str | None:
    """Return the first existing DREAMS.md / dreams.md path or ``None``.

    Mirrors OpenClaw's ``resolveExistingDreamsPath``. Non-ENOENT errors
    (permission, etc.) propagate.
    """
    for filename in DREAMS_FILENAMES:
        candidate = os.path.join(workspace_dir, filename)
        if os.path.isfile(candidate):
            return candidate
    return None


def _list_session_corpus_files(session_corpus_dir: str) -> list[str]:
    """List ``*.txt`` files in ``session_corpus_dir`` (sorted).

    Mirrors OpenClaw's ``listSessionCorpusFiles``. Returns ``[]`` if
    the directory doesn't exist. Non-ENOENT errors propagate.
    """
    if not os.path.isdir(session_corpus_dir):
        return []
    entries = list(os.scandir(session_corpus_dir))
    files = [
        os.path.join(session_corpus_dir, e.name)
        for e in entries
        if e.is_file() and e.name.endswith(".txt")
    ]
    files.sort()
    return files


def _is_suspicious_session_corpus_line(line: str) -> bool:
    """Return ``True`` if ``line`` looks like a self-ingested narrative.

    Mirrors OpenClaw's ``isSuspiciousSessionCorpusLine``. The check
    combines the narrative prompt prefix with the session key prefix
    — the session corpus should contain user-session text, not
    generated dream diary content.
    """
    return DREAMING_NARRATIVE_PROMPT_PREFIX in line and (
        DREAMING_NARRATIVE_RUN_PREFIX in line or "dreaming-narrative-" in line
    )


def _build_archive_timestamp(now: datetime) -> str:
    """Return an archive directory timestamp (``YYYY-MM-DDTHH-MM-SS-ssssssZ``).

    Mirrors OpenClaw's ``buildArchiveTimestamp``: ISO-8601 with
    ``:`` and ``.`` replaced by ``-`` (filesystem-safe).
    """
    return now.isoformat().replace(":", "-").replace(".", "-")


def _ensure_archivable_path(target_path: str) -> Literal["file", "dir"] | None:
    """Refuse symlinks / non-file-non-dir artifacts; return kind or None.

    Mirrors OpenClaw's ``ensureArchivablePath``. Returns ``None`` for
    missing paths; ``"file"`` for regular files; ``"dir"`` for
    directories. Raises ``RuntimeError`` for symlinks or other
    non-archivable kinds.
    """
    if not os.path.lexists(target_path):
        return None
    if os.path.islink(target_path):
        raise RuntimeError(f"Refusing to archive symlinked path: {target_path}")
    if os.path.isdir(target_path):
        return "dir"
    if os.path.isfile(target_path):
        return "file"
    raise RuntimeError(f"Refusing to archive non-file artifact: {target_path}")


def _move_to_archive(target_path: str, archive_dir: str) -> str | None:
    """Move ``target_path`` into ``archive_dir`` (with uuid suffix).

    Mirrors OpenClaw's ``moveToArchive``. Returns the destination
    path on success, ``None`` if the source didn't exist.
    """
    kind = _ensure_archivable_path(target_path)
    if kind is None:
        return None
    os.makedirs(archive_dir, exist_ok=True)
    base = os.path.basename(target_path)
    destination = os.path.join(archive_dir, f"{base}.{uuid.uuid4()}")
    shutil.move(target_path, destination)
    return destination


# ── Audit ──────────────────────────────────────────────────────────────


def audit_dreaming_artifacts(workspace_dir: str) -> DreamingArtifactsAuditSummary:
    """Inspect dreaming artifacts; return summary with issues.

    Mirrors OpenClaw's ``auditDreamingArtifacts``. Always returns a
    summary — never raises on missing artifacts. Issues are
    categorized as:

    - ``dreaming-diary-unreadable`` (error, not fixable) — DREAMS.md
      exists but can't be stat'd.
    - ``dreaming-session-corpus-unreadable`` (error, not fixable) —
      the corpus dir exists but can't be listed/read.
    - ``dreaming-session-ingestion-unreadable`` (error, not fixable) —
      the session-ingestion JSON file exists but can't be stat'd.
    - ``dreaming-session-corpus-self-ingested`` (warn, fixable) —
      the corpus contains lines that look like leaked narrative.

    The function also consults the SQLite plugin state as a fallback
    for ``sessionIngestionExists`` (the legacy JSON file may have
    been archived by a prior repair).
    """
    workspace_dir = _require_absolute_workspace_dir(workspace_dir)
    dreams_path = _resolve_existing_dreams_path(workspace_dir)
    session_corpus_dir = os.path.join(workspace_dir, SESSION_CORPUS_RELATIVE_DIR)
    session_ingestion_path = os.path.join(workspace_dir, SESSION_INGESTION_RELATIVE_PATH)
    issues: list[DreamingArtifactsAuditIssue] = []
    session_corpus_file_count = 0
    suspicious_session_corpus_file_count = 0
    suspicious_session_corpus_line_count = 0
    session_ingestion_exists = False

    if dreams_path is not None:
        try:
            os.stat(dreams_path)
        except OSError as err:
            issues.append(
                {
                    "severity": "error",
                    "code": "dreaming-diary-unreadable",
                    "message": (
                        f"Dream diary could not be inspected: "
                        f"{getattr(err, 'code', None) or 'error'}."
                    ),
                    "fixable": False,
                }
            )

    try:
        corpus_files = _list_session_corpus_files(session_corpus_dir)
        session_corpus_file_count = len(corpus_files)
        for corpus_file in corpus_files:
            try:
                with open(corpus_file, "r", encoding="utf-8") as f:
                    content = f.read()
            except OSError as err:
                # Per-file read errors are surfaced as unreadable issues
                # but don't abort the whole audit.
                issues.append(
                    {
                        "severity": "error",
                        "code": "dreaming-session-corpus-unreadable",
                        "message": (
                            f"Dreaming session corpus file could not be read "
                            f"({corpus_file}): {getattr(err, 'code', None) or 'error'}."
                        ),
                        "fixable": False,
                    }
                )
                continue
            for line in content.splitlines():
                trimmed = line.strip()
                if not trimmed:
                    continue
                if _is_suspicious_session_corpus_line(trimmed):
                    suspicious_session_corpus_line_count += 1
            if suspicious_session_corpus_line_count > 0:
                # Bump the per-file count once per file that contained
                # at least one suspicious line.
                suspicious_session_corpus_file_count += 1
    except OSError as err:
        if getattr(err, "errno", None) != 2:  # ENOENT
            issues.append(
                {
                    "severity": "error",
                    "code": "dreaming-session-corpus-unreadable",
                    "message": (
                        f"Dreaming session corpus could not be inspected: "
                        f"{getattr(err, 'code', None) or 'error'}."
                    ),
                    "fixable": False,
                }
            )

    try:
        os.stat(session_ingestion_path)
        session_ingestion_exists = True
    except OSError as err:
        if getattr(err, "errno", None) != 2:  # ENOENT
            issues.append(
                {
                    "severity": "error",
                    "code": "dreaming-session-ingestion-unreadable",
                    "message": (
                        f"Dreaming session-ingestion state could not be inspected: "
                        f"{getattr(err, 'code', None) or 'error'}."
                    ),
                    "fixable": False,
                }
            )

    # Fall back to SQLite plugin state when the legacy JSON file was
    # archived by a prior migration.
    if not session_ingestion_exists:
        try:
            for namespace in (
                DREAMING_SESSION_INGESTION_FILES_NAMESPACE,
                DREAMING_SESSION_INGESTION_SEEN_NAMESPACE,
            ):
                entries = read_memory_core_workspace_entries(
                    namespace=namespace,
                    workspace_dir=workspace_dir,
                )
                if len(entries) > 0:
                    session_ingestion_exists = True
                    break
        except Exception:  # noqa: BLE001
            # SQLite plugin state unavailable — keep filesystem-only
            # result (matches OpenClaw's silent fallback).
            pass

    if suspicious_session_corpus_line_count > 0:
        suffix = "" if suspicious_session_corpus_line_count == 1 else "s"
        issues.append(
            {
                "severity": "warn",
                "code": "dreaming-session-corpus-self-ingested",
                "message": (
                    f"Dreaming session corpus appears to contain self-ingested "
                    f"narrative content ({suspicious_session_corpus_line_count} "
                    f"suspicious line{suffix})."
                ),
                "fixable": True,
            }
        )

    summary: DreamingArtifactsAuditSummary = {
        "sessionCorpusDir": session_corpus_dir,
        "sessionCorpusFileCount": session_corpus_file_count,
        "suspiciousSessionCorpusFileCount": suspicious_session_corpus_file_count,
        "suspiciousSessionCorpusLineCount": suspicious_session_corpus_line_count,
        "sessionIngestionPath": session_ingestion_path,
        "sessionIngestionExists": session_ingestion_exists,
        "issues": issues,
    }
    if dreams_path is not None:
        summary["dreamsPath"] = dreams_path
    return summary


# ── Repair ─────────────────────────────────────────────────────────────


def _clear_session_ingestion_state(workspace_dir: str) -> None:
    """Clear the SQLite plugin state for session-ingestion namespaces.

    Mirrors OpenClaw's ``clearSessionIngestionState``. Best-effort:
    errors propagate to the caller, which records them as warnings.
    """
    # Sequential is fine here — these are in-process store operations.
    clear_memory_core_workspace_namespace(DREAMING_SESSION_INGESTION_FILES_NAMESPACE, workspace_dir)
    clear_memory_core_workspace_namespace(DREAMING_SESSION_INGESTION_SEEN_NAMESPACE, workspace_dir)


def repair_dreaming_artifacts(
    workspace_dir: str,
    archive_diary: bool = False,
    now: datetime | None = None,
) -> RepairDreamingArtifactsResult:
    """Archive (move) dreaming artifacts into a timestamped repair dir.

    Mirrors OpenClaw's ``repairDreamingArtifacts``. Always archives
    the session corpus and the session-ingestion state (when present);
    archives the DREAMS.md diary only when ``archive_diary=True``.

    Returns a result dict with per-artifact flags, archived path list,
    and a warnings list. Never raises on archive failures — they're
    captured in ``warnings`` and the function continues.
    """
    workspace_dir = _require_absolute_workspace_dir(workspace_dir)
    archive_timestamp = _build_archive_timestamp(now or datetime.now())
    archive_dir: str | None = None
    warnings: list[str] = []
    archived_paths: list[str] = []
    archived_dreams_diary = False
    archived_session_corpus = False
    archived_session_ingestion = False

    def _ensure_archive_dir() -> str:
        nonlocal archive_dir
        if archive_dir is None:
            archive_dir = os.path.join(
                workspace_dir, REPAIR_ARCHIVE_RELATIVE_DIR, archive_timestamp
            )
        return archive_dir

    def _archive_path_if_present(target_path: str) -> str | None:
        try:
            return _move_to_archive(target_path, _ensure_archive_dir())
        except Exception as err:  # noqa: BLE001
            warnings.append(err.__class__.__name__ + ": " + str(err))
            return None

    session_corpus_destination = _archive_path_if_present(
        os.path.join(workspace_dir, SESSION_CORPUS_RELATIVE_DIR)
    )
    if session_corpus_destination is not None:
        archived_session_corpus = True
        archived_paths.append(session_corpus_destination)

    session_ingestion_destination = _archive_path_if_present(
        os.path.join(workspace_dir, SESSION_INGESTION_RELATIVE_PATH)
    )
    if session_ingestion_destination is not None:
        archived_session_ingestion = True
        archived_paths.append(session_ingestion_destination)

    if session_corpus_destination is not None or session_ingestion_destination is not None:
        try:
            _clear_session_ingestion_state(workspace_dir)
        except Exception as err:  # noqa: BLE001
            warnings.append(
                "Failed clearing dreaming session-ingestion SQLite state: "
                f"{err.__class__.__name__}: {err}"
            )

    if archive_diary:
        dreams_path = _resolve_existing_dreams_path(workspace_dir)
        if dreams_path is not None:
            dreams_destination = _archive_path_if_present(dreams_path)
            if dreams_destination is not None:
                archived_dreams_diary = True
                archived_paths.append(dreams_destination)

    changed = archived_dreams_diary or archived_session_corpus or archived_session_ingestion
    result: RepairDreamingArtifactsResult = {
        "changed": changed,
        "archivedDreamsDiary": archived_dreams_diary,
        "archivedSessionCorpus": archived_session_corpus,
        "archivedSessionIngestion": archived_session_ingestion,
        "archivedPaths": archived_paths,
        "warnings": warnings,
    }
    if archive_dir is not None:
        result["archiveDir"] = archive_dir
    return result


__all__ = [
    # Constants
    "SESSION_CORPUS_RELATIVE_DIR",
    "SESSION_INGESTION_RELATIVE_PATH",
    "REPAIR_ARCHIVE_RELATIVE_DIR",
    "DREAMING_NARRATIVE_RUN_PREFIX",
    "DREAMING_NARRATIVE_PROMPT_PREFIX",
    # Types
    "DreamingArtifactsAuditIssue",
    "DreamingArtifactsAuditSummary",
    "RepairDreamingArtifactsResult",
    # API
    "audit_dreaming_artifacts",
    "repair_dreaming_artifacts",
]
