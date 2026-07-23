"""memory_core.dreaming_markdown — phase block writers for the dreaming pipeline.

OpenClaw parity: mirrors ``extensions/memory-core/src/dreaming-markdown.ts``
(145 LOC). Provides helpers for writing dreaming phase output to disk:

- ``write_daily_dreaming_phase_block`` — appends the ``light`` or ``rem``
  block to ``<workspace>/memory/<iso-day>.md`` (inline) and optionally
  writes a separate report under ``memory/dreaming/<phase>/<iso-day>.md``.
- ``write_deep_dreaming_report`` — updates the "Deep Sleep" managed
  block in ``DREAMS.md`` (delegated to ``update_deep_dreams_file``) and
  optionally writes a separate report under
  ``memory/dreaming/deep/<iso-day>.md``.

Both functions emit a ``memory.dream.completed`` event via the host's
event log (best-effort, no-op when the SDK event API isn't available).
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Literal, TypedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .dreaming_dreams_file import update_deep_dreams_file
from .time import resolve_memory_core_now_ms, resolve_memory_core_timestamp

# Mirrors OpenClaw's ``DAILY_PHASE_HEADINGS`` and ``DAILY_PHASE_LABELS``
# maps. The ``deep`` phase is excluded because it has its own dedicated
# destination (``DREAMS.md``), not a daily memory page.
DAILY_PHASE_HEADINGS: dict[str, str] = {
    "light": "## Light Sleep",
    "rem": "## REM Sleep",
}

DAILY_PHASE_LABELS: dict[str, str] = {
    "light": "light",
    "rem": "rem",
}


# Mirrors OpenClaw's ``MemoryDreamingPhaseName`` for the daily phase
# subset (deep is excluded).
DailyDreamingPhaseName = Literal["light", "rem"]


# Mirrors OpenClaw's ``MemoryDreamingStorageConfig``.
class MemoryDreamingStorageConfig(TypedDict, total=False):
    mode: Literal["inline", "separate", "both"]
    separateReports: bool


# Returns from ``write_daily_dreaming_phase_block``. ``inlinePath`` is
# set when the inline daily-memory block was written; ``reportPath`` is
# set when the separate report file was written. Either may be missing
# depending on the storage config.
class DailyPhaseBlockResult(TypedDict, total=False):
    inlinePath: str
    reportPath: str


def _resolve_phase_markers(phase: DailyDreamingPhaseName) -> dict[str, str]:
    """Return the start / end managed-block markers for ``phase``.

    Mirrors OpenClaw's ``resolvePhaseMarkers``. The marker format mirrors
    the deep phase markers so the markdown editor (Obsidian) preserves
    them as HTML comments.
    """
    label = DAILY_PHASE_LABELS[phase]
    return {
        "start": f"<!-- openclaw:dreaming:{label}:start -->",
        "end": f"<!-- openclaw:dreaming:{label}:end -->",
    }


def _format_memory_dreaming_day(epoch_ms: int, timezone_name: str | None = None) -> str:
    """Return ``YYYY-MM-DD`` for the dreaming day of ``epoch_ms``.

    Mirrors OpenClaw's ``formatMemoryDreamingDay`` (in the SDK). If
    ``timezone_name`` is missing or unknown, falls back to the local
    day (UTC) — Python has no equivalent of JS's ``Intl.DateTimeFormat``
    returning local-zone dates, so we always use the provided zone.
    """
    if timezone_name:
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            tz = UTC
    else:
        tz = UTC
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=tz)
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"


def _resolve_daily_memory_path(
    workspace_dir: str, epoch_ms: int, timezone_name: str | None = None
) -> str:
    """Return the inline daily-memory file path.

    Mirrors OpenClaw's ``resolveDailyMemoryPath``:
    ``<workspace>/memory/<iso-day>.md``.
    """
    iso_day = _format_memory_dreaming_day(epoch_ms, timezone_name)
    return os.path.join(workspace_dir, "memory", f"{iso_day}.md")


def _resolve_separate_report_path(
    workspace_dir: str,
    phase: str,
    epoch_ms: int,
    timezone_name: str | None = None,
) -> str:
    """Return the per-phase separate report path.

    Mirrors OpenClaw's ``resolveSeparateReportPath``:
    ``<workspace>/memory/dreaming/<phase>/<iso-day>.md``.
    """
    iso_day = _format_memory_dreaming_day(epoch_ms, timezone_name)
    return os.path.join(workspace_dir, "memory", "dreaming", phase, f"{iso_day}.md")


def _should_write_inline(storage: MemoryDreamingStorageConfig) -> bool:
    """Return ``True`` when the inline daily-memory block should be written.

    Mirrors OpenClaw's ``shouldWriteInline``. Inline is the "default"
    channel (one markdown file per day, multiple phase blocks).
    """
    return storage.get("mode") in ("inline", "both")


def _should_write_separate(storage: MemoryDreamingStorageConfig) -> bool:
    """Return ``True`` when a separate per-phase report should be written.

    Mirrors OpenClaw's ``shouldWriteSeparate``. Separate is enabled by
    explicit mode (``separate`` / ``both``) or by the legacy
    ``separateReports`` flag (default off).
    """
    mode = storage.get("mode")
    if mode in ("separate", "both"):
        return True
    return bool(storage.get("separateReports", False))


# ── Managed markdown block helper (inlined) ────────────────────────────
# Mirrors OpenClaw's ``replaceManagedMarkdownBlock`` from
# ``openclaw/plugin-sdk/memory-host-markdown``. The SDK's markdown
# helper isn't ported yet; inlined here to avoid a cycle through the
# dreams-file module. Behaves identically to the equivalent helper
# inside ``dreaming_dreams_file.py`` but keeps its scope local.
import re  # noqa: E402

_RE_MD_MARKER = re.compile(r"^[ \t]*<!--[ \t]*([\w-]+):([\w.-]+):start[ \t]*-->\s*$")


def _replace_managed_markdown_block(
    original: str,
    body: str,
    start_marker: str,
    end_marker: str,
    heading: str | None = None,
) -> str:
    """Replace the managed block in ``original``; append if missing.

    Mirrors OpenClaw's ``replaceManagedMarkdownBlock``. Matches the
    signature used by ``dreaming_dreams_file`` so behavior is consistent
    across inline + deep writers.
    """
    if start_marker in original and end_marker in original:
        # Replace existing block in place.
        start_idx = original.index(start_marker)
        end_idx = original.index(end_marker, start_idx)
        before = original[:start_idx]
        after = original[end_idx + len(end_marker) :]
        heading_prefix = f"{heading}\n" if heading else ""
        return f"{before}{heading_prefix}{start_marker}\n{body}\n{end_marker}{after}"

    # No existing block — append a new section.
    heading_line = f"{heading}\n" if heading else ""
    if original and not original.endswith("\n"):
        return f"{original}\n\n{heading_line}{start_marker}\n{body}\n{end_marker}\n"
    return f"{original}\n\n{heading_line}{start_marker}\n{body}\n{end_marker}\n"


# ── Public API ─────────────────────────────────────────────────────────


async def write_daily_dreaming_phase_block(
    *,
    workspace_dir: str,
    phase: DailyDreamingPhaseName,
    body_lines: list[str],
    storage: MemoryDreamingStorageConfig,
    now_ms: int | float | None = None,
    timezone_name: str | None = None,
) -> DailyPhaseBlockResult:
    """Write the ``light`` or ``rem`` phase block for today.

    Mirrors OpenClaw's ``writeDailyDreamingPhaseBlock``. Writes the
    inline block to ``<workspace>/memory/<iso-day>.md`` when storage
    mode is ``inline`` or ``both``; writes a separate report under
    ``memory/dreaming/<phase>/<iso-day>.md`` when storage mode is
    ``separate`` or ``both`` (or the legacy ``separateReports`` flag is
    on). Emits a ``memory.dream.completed`` event with
    ``outcome: "completed"`` via the host's event log (best-effort).
    """
    resolved_now_ms = resolve_memory_core_now_ms(now_ms)
    body = "\n".join(body_lines) if body_lines else "- No notable updates."
    inline_path: str | None = None
    report_path: str | None = None

    if _should_write_inline(storage):
        inline_path = _resolve_daily_memory_path(workspace_dir, resolved_now_ms, timezone_name)
        os.makedirs(os.path.dirname(inline_path) or ".", exist_ok=True)
        try:
            with open(inline_path, encoding="utf-8") as f:
                original = f.read()
        except FileNotFoundError:
            original = ""
        markers = _resolve_phase_markers(phase)
        updated = _replace_managed_markdown_block(
            original=original,
            body=body,
            start_marker=markers["start"],
            end_marker=markers["end"],
            heading=DAILY_PHASE_HEADINGS[phase],
        )
        if not updated.endswith("\n"):
            updated = f"{updated}\n"
        # Atomic write: use a sibling temp file so a crash mid-write
        # doesn't truncate the daily memory file.
        _atomic_write_text(inline_path, updated)

    if _should_write_separate(storage):
        report_path = _resolve_separate_report_path(
            workspace_dir, phase, resolved_now_ms, timezone_name
        )
        os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
        report_heading = "Light Sleep" if phase == "light" else "REM Sleep"
        report = f"# {report_heading}\n\n{body}\n\n"
        _atomic_write_text(report_path, report)

    await _emit_completed_event(
        workspace_dir=workspace_dir,
        phase=phase,
        now_ms=resolved_now_ms,
        line_count=len(body_lines),
        storage_mode=storage.get("mode") or "separate",
        inline_path=inline_path,
        report_path=report_path,
    )

    result: DailyPhaseBlockResult = {}
    if inline_path is not None:
        result["inlinePath"] = inline_path
    if report_path is not None:
        result["reportPath"] = report_path
    return result


async def write_deep_dreaming_report(
    *,
    workspace_dir: str,
    body_lines: list[str],
    storage: MemoryDreamingStorageConfig,
    now_ms: int | float | None = None,
    timezone_name: str | None = None,
) -> str | None:
    """Write the deep-sleep report to ``DREAMS.md`` (+ optional separate report).

    Mirrors OpenClaw's ``writeDeepDreamingReport``. Returns the
    separate report path when written, else ``None``. Emits a
    ``memory.dream.completed`` event with ``phase: "deep"``.
    """
    resolved_now_ms = resolve_memory_core_now_ms(now_ms)
    body = "\n".join(body_lines) if body_lines else "- No durable changes."
    inline_path = update_deep_dreams_file(workspace_dir, body_lines)

    report_path: str | None = None
    if _should_write_separate(storage):
        report_path = _resolve_separate_report_path(
            workspace_dir, "deep", resolved_now_ms, timezone_name
        )
        os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
        _atomic_write_text(report_path, f"# Deep Sleep\n\n{body}\n")

    await _emit_completed_event(
        workspace_dir=workspace_dir,
        phase="deep",
        now_ms=resolved_now_ms,
        line_count=len(body_lines),
        storage_mode=storage.get("mode") or "separate",
        inline_path=inline_path,
        report_path=report_path,
    )
    return report_path


# ── Internal helpers ───────────────────────────────────────────────────


def _atomic_write_text(path: str, content: str) -> None:
    """Atomically write ``content`` to ``path``.

    Used for daily-memory and separate-report files. Mirrors
    OpenClaw's ``fs.writeFile`` + ``withTrailingNewline`` semantics
    but adds a sibling-temp + ``os.replace`` so partial writes don't
    truncate the destination.
    """
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    import tempfile

    fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.tmp.", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


async def _emit_completed_event(
    *,
    workspace_dir: str,
    phase: str,
    now_ms: int,
    line_count: int,
    storage_mode: str,
    inline_path: str | None,
    report_path: str | None,
) -> None:
    """Append a ``memory.dream.completed`` event to the host event log.

    Best-effort: when the SDK's ``memory_host_events`` API isn't
    available, the event is silently dropped. The dreaming pipeline
    is not blocked by event-log failures.
    """
    try:
        from jarvis_sdk.memory_host_events import (  # pyright: ignore[reportMissingImports]
            append_memory_host_event,  # type: ignore[attr-defined]
        )
    except ImportError:
        # SDK doesn't expose the events API yet — degrade to a no-op.
        return

    event: dict = {
        "type": "memory.dream.completed",
        "timestamp": resolve_memory_core_timestamp(now_ms),
        "phase": phase,
        "outcome": "completed",
        "lineCount": line_count,
        "storageMode": storage_mode,
    }
    if inline_path is not None:
        event["inlinePath"] = inline_path
    if report_path is not None:
        event["reportPath"] = report_path

    try:
        result = append_memory_host_event(workspace_dir, event)
        # The host helper may be sync (returning None) or async
        # (returning a coroutine). Await it if it's awaitable.
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        # Best-effort: swallowing write errors matches OpenClaw's
        # ``appendMemoryHostEvent`` semantics (the host catches and
        # logs internally too).
        return


__all__ = [
    "DAILY_PHASE_HEADINGS",
    "DAILY_PHASE_LABELS",
    "DailyDreamingPhaseName",
    "MemoryDreamingStorageConfig",
    "DailyPhaseBlockResult",
    "write_daily_dreaming_phase_block",
    "write_deep_dreaming_report",
]
