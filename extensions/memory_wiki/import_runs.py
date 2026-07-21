"""import_runs — Memory Wiki import runs list (Phase 4.3g-mr3).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/import-runs.ts``.

Lists the per-vault import-run records
(``meta`` + ``path`` rows from the
import-runs state store) and exposes
them as a sorted, normalized summary
list. The host consumes this from the
``wiki.importRuns`` gateway method.
"""

# ruff: noqa: PLR0911, PLR0912, PLR0915 — mirrors the
# OpenClaw helper's exhaustive per-field
# ladder; the value coercion + defaulting
# branches are intentionally long so
# the function mirrors OpenClaw 1:1.

# ruff: noqa: N815 — field names mirror the
# OpenClaw camelCase JSON shape so the
# ``wiki.importRuns`` gateway response is
# byte-compatible with the OpenClaw host.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .import_runs_state import list_memory_wiki_import_run_records

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


@dataclass(frozen=True, slots=True)
class MemoryWikiImportRunSummary:
    """A single import-run summary.

    Mirrors the OpenClaw
    ``MemoryWikiImportRunSummary`` type.
    Field names are camelCase.
    """

    runId: str
    importType: str
    appliedAt: str
    exportPath: str
    sourcePath: str
    conversationCount: int
    createdCount: int
    updatedCount: int
    skippedCount: int
    status: str  # "applied" | "rolled_back"
    pagePaths: list[str] = field(default_factory=list)
    samplePaths: list[str] = field(default_factory=list)
    rolledBackAt: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryWikiImportRunsStatus:
    """The result of :func:`list_memory_wiki_import_runs`.

    Mirrors the OpenClaw
    ``MemoryWikiImportRunsStatus`` type.
    Field names are camelCase.
    """

    runs: list[MemoryWikiImportRunSummary]
    totalRuns: int
    activeRuns: int
    rolledBackRuns: int


def _as_record(value: Any) -> dict[str, Any] | None:
    """Coerce ``value`` to a plain dict or
    return ``None``.

    Mirrors the OpenClaw ``asRecord`` helper.
    """
    if value is None or not isinstance(value, dict):
        return None
    return dict(value)


def _as_string_array(value: Any) -> list[str]:
    """Return the subset of ``value`` that are
    non-empty strings.

    Mirrors the OpenClaw ``asStringArray`` helper.
    """
    if not isinstance(value, list):
        return []
    return [entry.strip() for entry in value if isinstance(entry, str) and entry.strip()]


def _unique_strings(values: list[str]) -> list[str]:
    """Deduplicate ``values`` (preserving
    order).

    Mirrors the OpenClaw ``uniqueStrings`` helper.
    """
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _normalize_finite_int(value: Any) -> int:
    """Coerce ``value`` to a non-negative int.

    Mirrors the OpenClaw
    ``normalizeFiniteInt`` helper.
    """
    if not isinstance(value, int | float) or isinstance(value, bool):
        return 0
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0
    import math

    if math.isnan(f):
        return 0
    return max(0, int(f))


def normalize_import_run_summary(
    raw: Any,
) -> MemoryWikiImportRunSummary | None:
    """Return a normalized summary for ``raw``,
    or ``None`` if the record is missing
    required fields.

    Mirrors the OpenClaw
    ``normalizeImportRunSummary`` helper.
    """
    record = _as_record(raw)
    if record is None:
        return None
    run_id = record.get("runId", "").strip() if isinstance(record.get("runId"), str) else ""
    import_type = (
        record.get("importType", "").strip() if isinstance(record.get("importType"), str) else ""
    )
    applied_at = (
        record.get("appliedAt", "").strip() if isinstance(record.get("appliedAt"), str) else ""
    )
    export_path = (
        record.get("exportPath", "").strip() if isinstance(record.get("exportPath"), str) else ""
    )
    source_path = (
        record.get("sourcePath", "").strip() if isinstance(record.get("sourcePath"), str) else ""
    )
    if not (run_id and import_type and applied_at and export_path and source_path):
        return None

    created_paths = _as_string_array(record.get("createdPaths"))
    updated_paths_raw = record.get("updatedPaths")
    if isinstance(updated_paths_raw, list):
        updated_paths: list[str] = []
        for entry in updated_paths_raw:
            sub = _as_record(entry)
            if sub is None:
                continue
            sub_path = sub.get("path")
            if isinstance(sub_path, str) and sub_path.strip():
                updated_paths.append(sub_path.strip())
    else:
        updated_paths = []
    page_paths = _unique_strings([*created_paths, *updated_paths])
    conversation_count = _normalize_finite_int(record.get("conversationCount")) or len(
        created_paths
    ) + len(updated_paths)
    created_count = _normalize_finite_int(record.get("createdCount")) or len(created_paths)
    updated_count = _normalize_finite_int(record.get("updatedCount")) or len(updated_paths)
    skipped_count = max(
        0,
        _normalize_finite_int(record.get("skippedCount"))
        or (conversation_count - created_count - updated_count),
    )
    rolled_back_at_raw = record.get("rolledBackAt")
    rolled_back_at: str | None = None
    if isinstance(rolled_back_at_raw, str) and rolled_back_at_raw.strip():
        rolled_back_at = rolled_back_at_raw.strip()

    return MemoryWikiImportRunSummary(
        runId=run_id,
        importType=import_type,
        appliedAt=applied_at,
        exportPath=export_path,
        sourcePath=source_path,
        conversationCount=conversation_count,
        createdCount=created_count,
        updatedCount=updated_count,
        skippedCount=skipped_count,
        status="rolled_back" if rolled_back_at else "applied",
        pagePaths=page_paths,
        samplePaths=page_paths[:5],
        rolledBackAt=rolled_back_at,
    )


async def list_memory_wiki_import_runs(
    config: ResolvedMemoryWikiConfig,
    *,
    limit: int | None = None,
) -> MemoryWikiImportRunsStatus:
    """List the per-vault import runs.

    Mirrors the OpenClaw
    :func:`listMemoryWikiImportRuns`.
    Returns at most ``limit`` (default
    ``10``) summaries, sorted by
    ``appliedAt`` descending.
    """
    effective_limit = max(1, int(limit or 10))
    records = list_memory_wiki_import_run_records(config.vault.path)
    summaries: list[MemoryWikiImportRunSummary] = []
    for record in records:
        summary = normalize_import_run_summary(record)
        if summary is not None:
            summaries.append(summary)
    summaries.sort(key=lambda s: s.appliedAt, reverse=True)
    return MemoryWikiImportRunsStatus(
        runs=summaries[:effective_limit],
        totalRuns=len(summaries),
        activeRuns=sum(1 for s in summaries if s.status == "applied"),
        rolledBackRuns=sum(1 for s in summaries if s.status == "rolled_back"),
    )


def reset_memory_wiki_import_runs_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


__all__ = [
    "MemoryWikiImportRunSummary",
    "MemoryWikiImportRunsStatus",
    "list_memory_wiki_import_runs",
    "normalize_import_run_summary",
    "reset_memory_wiki_import_runs_state_for_tests",
]
