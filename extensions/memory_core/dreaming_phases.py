"""memory_core.dreaming_phases — light + REM + deep phase runners.

OpenClaw parity: mirrors ``extensions/memory-core/src/dreaming-phases.ts``
(1861 LOC) for the deterministic building blocks + public types. The
LLM orchestrators (``run_light_dreaming``, ``run_rem_dreaming``,
``run_dreaming_sweep_phases``, ``preview_rem_dreaming``,
``seed_historical_daily_memory_signals``) are stubbed — the LLM
subagent surface and short-term-promotion module aren't ported yet.

This module is the foundation for the dreaming sweep:

- Constants: ingestion state paths, score thresholds, snippet limits.
- Snippet extraction: ``build_daily_snippet_chunks`` walks a daily
  memory file and groups lines into headed chunks (list/paragraph).
- Lookback filter: ``filter_recall_entries_within_lookback`` uses
  either ``recallDays`` or ``lastRecalledAt`` to decide which short
  term recall entries are within the dreaming lookback window.
- Ingestion state CRUD: ``normalize_daily_ingestion_state`` /
  ``normalize_session_ingestion_state`` validate + coerce state
  payloads; ``read_*`` / ``write_*`` go through the SQLite plugin
  state (via ``dreaming_state``).
- Dedupe helpers: ``dedupe_entries`` collapses near-duplicate short
  term recall entries by text similarity.
- Diary coverage helpers: ``normalize_diary_coverage_text`` and
  ``is_entry_covered_by_recent_diary`` check whether an entry is
  already represented in the recent dream diary.

The LLM-dependent orchestrators are intentionally stubbed with
``pragma: no cover`` so the public API surface is documented and
importable. They will be filled in once the LLM subagent and
short-term-promotion modules are ported.

Key port decisions:
- The deterministic helpers preserve the exact thresholds and limits
  from OpenClaw (e.g. ``DAILY_INGESTION_SCORE = 0.62``,
  ``SESSION_INGESTION_SCORE = 0.58``,
  ``DAILY_INGESTION_MAX_SNIPPET_CHARS = 280``, etc.) so a future
  orchestrator can use the same constants verbatim.
- Text similarity is inlined as a simple whitespace-token Jaccard
  ratio. OpenClaw's ``textSimilarity`` is more sophisticated (uses
  ``tokenize.ts``), but Jaccard is a reasonable placeholder and is
  documented as such.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Callable, Literal, TypedDict

# ── Path constants ────────────────────────────────────────────────────

DAILY_INGESTION_STATE_RELATIVE_PATH = os.path.join(
    "memory", ".dreams", "daily-ingestion.json"
)
SESSION_INGESTION_STATE_RELATIVE_PATH = os.path.join(
    "memory", ".dreams", "session-ingestion.json"
)
SESSION_CORPUS_RELATIVE_DIR = os.path.join("memory", ".dreams", "session-corpus")

# ── Ingestion scoring + size constants ────────────────────────────────

DAILY_INGESTION_SCORE = 0.62
DAILY_INGESTION_MAX_SNIPPET_CHARS = 280
DAILY_INGESTION_MIN_SNIPPET_CHARS = 8
DAILY_INGESTION_MAX_CHUNK_LINES = 4

SESSION_INGESTION_SCORE = 0.58
SESSION_INGESTION_MAX_SNIPPET_CHARS = 280
SESSION_INGESTION_MIN_SNIPPET_CHARS = 12
SESSION_INGESTION_MAX_MESSAGES_PER_SWEEP = 240
SESSION_INGESTION_MAX_MESSAGES_PER_FILE = 80
SESSION_INGESTION_MIN_MESSAGES_PER_FILE = 12
SESSION_INGESTION_MAX_TRACKED_MESSAGES_PER_SESSION = 4096
SESSION_INGESTION_MAX_TRACKED_SCOPES = 2048

# ── Light/REM reflection constants ────────────────────────────────────

LIGHT_DIARY_HISTORY_LIMIT = 4
LIGHT_DIARY_SNIPPET_SIMILARITY_THRESHOLD = 0.35

# ── Regex patterns ────────────────────────────────────────────────────

MEMORY_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DAILY_MEMORY_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-[^/]+)?\.md$", re.IGNORECASE)
SESSION_CHECKPOINT_TRANSCRIPT_FILENAME_RE = re.compile(
    r"\.checkpoint\..+\.jsonl$", re.IGNORECASE
)
_GENERIC_DAY_HEADING_RE = re.compile(
    r"^(?:(?:mon|monday|tue|tues|tuesday|wed|wednesday|thu|thur|thursday|fri|friday|sat|saturday|sun|sunday)(?:,\s+)?)?"
    r"(?:(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}[/-]\d{2}[/-]\d{2})$",
    re.IGNORECASE,
)

# ── Managed daily dreaming blocks (mirrors OpenClaw) ──────────────────

MANAGED_DAILY_DREAMING_BLOCKS: list[dict[str, str]] = [
    {
        "heading": "## Light Sleep",
        "startMarker": "<!-- openclaw:dreaming:light:start -->",
        "endMarker": "<!-- openclaw:dreaming:light:end -->",
    },
    {
        "heading": "## REM Sleep",
        "startMarker": "<!-- openclaw:dreaming:rem:start -->",
        "endMarker": "<!-- openclaw:dreaming:rem:end -->",
    },
]

# ── Types ─────────────────────────────────────────────────────────────


class DailySnippetChunk(TypedDict, total=False):
    startLine: int
    endLine: int
    snippet: str


class DailyMemoryFile(TypedDict, total=False):
    fileName: str
    day: str
    canonical: bool


class DailyIngestionFileState(TypedDict, total=False):
    mtimeMs: int
    size: int
    lastDreamingDayIngested: str


class DailyIngestionState(TypedDict, total=False):
    version: Literal[1]
    files: dict[str, DailyIngestionFileState]


class SessionIngestionFileState(TypedDict, total=False):
    mtimeMs: int
    size: int
    contentHash: str
    lineCount: int
    lastContentLine: int


class SessionIngestionState(TypedDict, total=False):
    version: Literal[3]
    files: dict[str, SessionIngestionFileState]
    seenMessages: dict[str, list[str]]


class ShortTermRecallEntry(TypedDict, total=False):
    key: str
    snippet: str
    lastRecalledAt: str
    recallDays: list[str]


class RemDreamingPreview(TypedDict, total=False):
    snippet: str
    reason: str
    confidence: float
    riskFlags: list[str]
    evidenceRefs: list[str]


# ── Lookback helpers ──────────────────────────────────────────────────


def _calculate_lookback_cutoff_ms(now_ms: int, lookback_days: int) -> int:
    """Return ``now_ms - max(0, lookback_days) * 86400_000``.

    Mirrors OpenClaw's ``calculateLookbackCutoffMs``.
    """
    return int(now_ms) - max(0, int(lookback_days)) * 86_400_000


def _is_day_within_lookback(day: str, cutoff_ms: int) -> bool:
    """Return ``True`` if ``day`` (YYYY-MM-DD) is on or after the cutoff.

    Mirrors OpenClaw's ``isDayWithinLookback``. Parses the day as
    ``<day>T23:59:59.999Z`` so the entire day is considered "within".
    """
    # The "T23:59:59.999Z" suffix is preserved verbatim from OpenClaw
    # so timezone semantics match: any time during the day qualifies.
    from datetime import datetime, timezone

    try:
        day_dt = datetime.strptime(f"{day}T23:59:59.999Z", "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return False
    day_ms = int(day_dt.timestamp() * 1000)
    return day_ms >= cutoff_ms


def _entry_within_lookback(entry: ShortTermRecallEntry, cutoff_ms: int) -> bool:
    """Decide whether a short term recall entry is within the lookback.

    Mirrors OpenClaw's ``entryWithinLookback``. Prefers ``recallDays``;
    falls back to ``lastRecalledAt`` parsed as ISO-8601.
    """
    recall_days = entry.get("recallDays") or []
    for day in recall_days:
        if _is_day_within_lookback(day, cutoff_ms):
            return True
    last_recalled = entry.get("lastRecalledAt") or ""
    if not last_recalled:
        return False
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(last_recalled.replace("Z", "+00:00"))
        last_ms = int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return False
    return last_ms >= cutoff_ms


def filter_recall_entries_within_lookback(
    entries: list[ShortTermRecallEntry],
    now_ms: int,
    lookback_days: int,
) -> list[ShortTermRecallEntry]:
    """Filter ``entries`` to those within the dreaming lookback window.

    Mirrors OpenClaw's ``filterRecallEntriesWithinLookback``. Public
    surface used by gateway doctor, CLI harness, and internal REM /
    light dreaming paths so the lookback semantics are consistent.
    """
    cutoff_ms = _calculate_lookback_cutoff_ms(now_ms, lookback_days)
    return [e for e in entries if _entry_within_lookback(e, cutoff_ms)]


# ── Daily snippet extraction ──────────────────────────────────────────


def _normalize_daily_list_marker(line: str) -> str:
    """Strip ``- `` / ``* `` / ``+ `` / ``N. `` list markers from ``line``.

    Mirrors OpenClaw's ``normalizeDailyListMarker``.
    """
    return re.sub(r"^\d+\.\s+", "", re.sub(r"^[-*+]\s+", "", line)).strip()


def _is_generic_daily_heading(heading: str) -> bool:
    """Return ``True`` when the heading is a date/generic day label.

    Mirrors OpenClaw's ``isGenericDailyHeading``. Rejects headings
    like "Today", "Yesterday", "December 15", "12/15/2025", etc.
    """
    normalized = " ".join(heading.split())
    if not normalized:
        return True
    lower = normalized.lower()
    if lower in ("today", "yesterday", "tomorrow"):
        return True
    if lower in ("morning", "afternoon", "evening", "night"):
        return True
    return bool(_GENERIC_DAY_HEADING_RE.match(normalized))


def _truncate_utf16_safe(value: str, limit: int) -> str:
    """Truncate ``value`` to ``limit`` characters (UTF-16 safe).

    Mirrors OpenClaw's ``truncateUtf16Safe`` from the SDK. Python's
    string indexing is already code-point safe; we just slice.
    """
    if len(value) <= limit:
        return value
    return value[:limit]


def _normalize_daily_heading(line: str) -> str | None:
    """Extract a heading from ``line`` (1-6 ``#`` prefixes) or return ``None``.

    Mirrors OpenClaw's ``normalizeDailyHeading``. Returns ``None`` for
    non-heading lines, empty headings, daily-file-name headings, or
    generic day labels.
    """
    trimmed = line.strip()
    match = re.match(r"^#{1,6}\s+(.+)$", trimmed)
    if not match:
        return None
    inner = match.group(1) if match.lastindex else ""
    heading = _normalize_daily_list_marker(inner)
    if not heading or DAILY_MEMORY_FILENAME_RE.match(heading) or _is_generic_daily_heading(heading):
        return None
    return _truncate_utf16_safe(heading, DAILY_INGESTION_MAX_SNIPPET_CHARS).replace("  ", " ").strip()


def _normalize_daily_snippet(line: str) -> str | None:
    """Trim a daily memory line into a normalized snippet.

    Mirrors OpenClaw's ``normalizeDailySnippet``. Returns ``None``
    for empty lines, comments, headings, or lines shorter than
    ``DAILY_INGESTION_MIN_SNIPPET_CHARS``.
    """
    trimmed = line.strip()
    if not trimmed or trimmed.startswith("#") or trimmed.startswith("<!--"):
        return None
    without_marker = _normalize_daily_list_marker(trimmed)
    if len(without_marker) < DAILY_INGESTION_MIN_SNIPPET_CHARS:
        return None
    return _truncate_utf16_safe(without_marker, DAILY_INGESTION_MAX_SNIPPET_CHARS).replace(
        "  ", " "
    ).strip()


def _build_daily_chunk_snippet(
    heading: str | None,
    chunk_lines: list[str],
    chunk_kind: Literal["list", "paragraph"] | None,
) -> str:
    """Combine a chunk's lines into a single snippet string.

    Mirrors OpenClaw's ``buildDailyChunkSnippet``. List chunks are
    joined with ``"; "``; paragraph chunks are joined with ``" "``.
    The optional heading is prefixed with ``": "``.
    """
    joiner = "; " if chunk_kind == "list" else " "
    body = joiner.join(chunk_lines).strip()
    prefixed = f"{heading}: {body}" if heading else body
    return _truncate_utf16_safe(prefixed, DAILY_INGESTION_MAX_SNIPPET_CHARS).replace("  ", " ").strip()


def build_daily_snippet_chunks(
    lines: list[str], limit: int
) -> list[DailySnippetChunk]:
    """Walk ``lines`` (1-indexed) and group them into headed chunks.

    Mirrors OpenClaw's ``buildDailySnippetChunks``. Each chunk has
    a ``startLine``, ``endLine``, and ``snippet``. Chunks split on:
    - heading boundary
    - comment/empty line
    - kind change (list ↔ paragraph)
    - chunk line count exceeding ``DAILY_INGESTION_MAX_CHUNK_LINES``
    - chunk snippet exceeding ``DAILY_INGESTION_MAX_SNIPPET_CHARS``

    Capped at ``limit`` chunks.
    """
    chunks: list[DailySnippetChunk] = []
    active_heading: str | None = None
    chunk_lines: list[str] = []
    chunk_kind: Literal["list", "paragraph"] | None = None
    chunk_start_line = 0
    chunk_end_line = 0

    def _flush() -> None:
        nonlocal chunk_lines, chunk_kind, chunk_start_line, chunk_end_line
        if not chunk_lines:
            chunk_kind = None
            chunk_start_line = 0
            chunk_end_line = 0
            return
        snippet = _build_daily_chunk_snippet(active_heading, chunk_lines, chunk_kind)
        if len(snippet) >= DAILY_INGESTION_MIN_SNIPPET_CHARS:
            chunks.append(
                {"startLine": chunk_start_line, "endLine": chunk_end_line, "snippet": snippet}
            )
        chunk_lines = []
        chunk_kind = None
        chunk_start_line = 0
        chunk_end_line = 0

    for index, line in enumerate(lines):
        if not isinstance(line, str):
            continue
        heading = _normalize_daily_heading(line)
        if heading is not None:
            _flush()
            active_heading = heading
            continue
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("<!--"):
            _flush()
            continue
        snippet = _normalize_daily_snippet(line)
        if snippet is None:
            _flush()
            continue
        next_kind: Literal["list", "paragraph"] = (
            "list" if re.match(r"^([-*+]\s+|\d+\.\s+)", trimmed) else "paragraph"
        )
        next_chunk_lines = [snippet] if not chunk_lines else chunk_lines + [snippet]
        candidate = _build_daily_chunk_snippet(active_heading, next_chunk_lines, next_kind)
        should_split = chunk_lines and (
            chunk_kind != next_kind
            or len(chunk_lines) >= DAILY_INGESTION_MAX_CHUNK_LINES
            or len(candidate) > DAILY_INGESTION_MAX_SNIPPET_CHARS
        )
        if should_split:
            _flush()
        if not chunk_lines:
            chunk_start_line = index + 1
            chunk_kind = next_kind
        chunk_lines.append(snippet)
        chunk_end_line = index + 1
        if len(chunks) >= limit:
            break

    _flush()
    return chunks[:limit]


# ── Daily memory file helpers ────────────────────────────────────────


def _parse_daily_memory_file_name(file_name: str) -> DailyMemoryFile | None:
    """Parse a daily memory file name (with optional ``-<slug>`` suffix).

    Mirrors OpenClaw's ``parseDailyMemoryFileName``. Returns ``None``
    for non-matching names; otherwise returns the day + a ``canonical``
    flag (``True`` when the name is exactly ``<day>.md``).
    """
    match = DAILY_MEMORY_FILENAME_RE.match(file_name)
    day = match.group(1) if match else None
    if not day:
        return None
    return {
        "fileName": file_name,
        "day": day,
        "canonical": file_name.lower() == f"{day.lower()}.md",
    }


def _compare_daily_memory_files_by_newest_day(
    left: DailyMemoryFile, right: DailyMemoryFile
) -> int:
    """Compare two daily memory files; newest day first, then canonical.

    Mirrors OpenClaw's ``compareDailyMemoryFilesByNewestDay``.
    """
    # Newest day first: negative when right is newer
    if right["day"] < left["day"]:
        return -1
    if right["day"] > left["day"]:
        return 1
    # Same day: canonical first
    left_canon = left.get("canonical", False)
    right_canon = right.get("canonical", False)
    if left_canon != right_canon:
        return -1 if left_canon else 1
    # Final tiebreaker: fileName ascending
    lf = left.get("fileName") or ""
    rf = right.get("fileName") or ""
    return -1 if lf < rf else (1 if lf > rf else 0)


# ── Managed block stripping ──────────────────────────────────────────


def _strip_managed_daily_dreaming_lines(lines: list[str]) -> list[str]:
    """Remove the Light/REM managed blocks from ``lines``.

    Mirrors OpenClaw's ``stripManagedDailyDreamingLines``. Used when
    a daily memory file is re-ingested to avoid re-processing the
    output of a previous dreaming run.
    """
    block_by_start: dict[str, dict[str, str]] = {
        block["startMarker"]: block for block in MANAGED_DAILY_DREAMING_BLOCKS
    }
    sanitized = list(lines)
    index = 0
    while index < len(sanitized):
        block = block_by_start.get((sanitized[index] or "").strip())
        if not block:
            index += 1
            continue
        strip_until = -1
        cursor = index + 1
        while cursor < len(sanitized):
            line = sanitized[cursor]
            trimmed = (line or "").strip()
            if trimmed == block["endMarker"]:
                strip_until = cursor
                break
            if line and (
                re.match(r"^#{1,6}\s+", trimmed) or block_by_start.get(trimmed) is not None
            ):
                strip_until = cursor - 1
                break
            cursor += 1
        if strip_until < index:
            index += 1
            continue
        heading_index = _find_managed_daily_dreaming_heading_index(
            lines, index, block["heading"]
        )
        start_index = heading_index if heading_index is not None else index
        for c in range(start_index, strip_until + 1):
            sanitized[c] = ""
        index = strip_until + 1
    return sanitized


def _find_managed_daily_dreaming_heading_index(
    lines: list[str], start_index: int, heading: str
) -> int | None:
    """Walk backwards from ``start_index - 1`` to find the heading.

    Mirrors OpenClaw's ``findManagedDailyDreamingHeadingIndex``.
    """
    for i in range(start_index - 1, -1, -1):
        trimmed = (lines[i] or "").strip() if i < len(lines) else ""
        if not trimmed:
            continue
        return i if trimmed == heading else None
    return None


# ── Dedupe (text similarity) ─────────────────────────────────────────


def _text_similarity_jaccard(a: str, b: str) -> float:
    """Return the Jaccard similarity of whitespace tokens in ``a`` and ``b``.

    Inlined placeholder for OpenClaw's ``textSimilarity`` (which uses
    a richer tokenizer). Sufficient for the dedupe helper's threshold
    gate; the threshold is calibrated for Jaccard.
    """
    if not a or not b:
        return 0.0
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if not a_tokens or not b_tokens:
        return 0.0
    intersection = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    return intersection / union if union else 0.0


def _entry_average_score(entry: ShortTermRecallEntry) -> float:
    """Return the average score of a short term recall entry.

    Mirrors OpenClaw's ``entryAverageScore``. Falls back to 0 when
    the entry has no score field.
    """
    score = entry.get("score")
    if isinstance(score, (int, float)):
        return float(score)
    return 0.0


def dedupe_entries(
    entries: list[ShortTermRecallEntry], threshold: float
) -> list[ShortTermRecallEntry]:
    """Remove near-duplicate entries by snippet Jaccard similarity.

    Mirrors OpenClaw's ``dedupeEntries``. Keeps the first occurrence;
    drops later entries whose snippet similarity is above ``threshold``.
    """
    kept: list[ShortTermRecallEntry] = []
    for entry in entries:
        snippet = entry.get("snippet") or ""
        is_duplicate = False
        for prev in kept:
            if _text_similarity_jaccard(snippet, prev.get("snippet") or "") >= threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            kept.append(entry)
    return kept


# ── Diary coverage helpers ───────────────────────────────────────────


def normalize_diary_coverage_text(text: str) -> str:
    """Normalize text for diary-coverage comparison.

    Mirrors OpenClaw's ``normalizeDiaryCoverageText``. Strips
    non-alphanumeric chars + lowercases + collapses whitespace.
    """
    return " ".join(re.sub(r"[^a-z0-9\s]", "", text.lower()).split())


def is_entry_covered_by_recent_diary(
    snippet: str, recent_diary_entries: list[str]
) -> bool:
    """Return ``True`` if any recent diary entry is similar to ``snippet``.

    Mirrors OpenClaw's ``isEntryCoveredByRecentDiary``. Uses
    ``LIGHT_DIARY_SNIPPET_SIMILARITY_THRESHOLD`` as the cutoff.
    """
    target = normalize_diary_coverage_text(snippet)
    if not target:
        return False
    for entry in recent_diary_entries:
        candidate = normalize_diary_coverage_text(entry)
        if not candidate:
            continue
        if _text_similarity_jaccard(target, candidate) >= LIGHT_DIARY_SNIPPET_SIMILARITY_THRESHOLD:
            return True
    return False


def prioritize_light_entries_by_diary_coverage(
    entries: list[ShortTermRecallEntry], recent_diary_entries: list[str]
) -> list[ShortTermRecallEntry]:
    """Sort entries so uncovered ones come first.

    Mirrors OpenClaw's ``prioritizeLightEntriesByDiaryCoverage``.
    Within each group, score-desc tie-broken by snippet length.
    """
    uncovered: list[ShortTermRecallEntry] = []
    covered: list[ShortTermRecallEntry] = []
    for entry in entries:
        if is_entry_covered_by_recent_diary(entry.get("snippet") or "", recent_diary_entries):
            covered.append(entry)
        else:
            uncovered.append(entry)
    uncovered.sort(
        key=lambda e: (-_entry_average_score(e), -(len(e.get("snippet") or "")))
    )
    covered.sort(
        key=lambda e: (-_entry_average_score(e), -(len(e.get("snippet") or "")))
    )
    return uncovered + covered


# ── Ingestion state normalizers (mirrors OpenClaw) ────────────────────


def _as_record(value: Any) -> dict[str, Any] | None:
    """Inlined equivalent of OpenClaw's ``asRecord``."""
    if isinstance(value, dict):
        return value
    return None


def _normalize_memory_day(value: Any) -> str | None:
    """Inlined equivalent of OpenClaw's ``normalizeMemoryDay``."""
    if not isinstance(value, str):
        return None
    day = value.strip()
    return day if MEMORY_DAY_RE.match(day) else None


def normalize_daily_ingestion_state(raw: Any) -> DailyIngestionState:
    """Validate + coerce a daily ingestion state payload.

    Mirrors OpenClaw's ``normalizeDailyIngestionState``. Returns a
    fresh ``{version: 1, files: {}}`` shell for invalid input. File
    entries with non-numeric mtime/size are dropped.
    """
    record = _as_record(raw)
    files_raw = _as_record(record.get("files")) if record else None
    files: dict[str, DailyIngestionFileState] = {}
    if files_raw:
        for key, value in files_raw.items():
            if not isinstance(key, str) or not key.strip():
                continue
            file_rec = _as_record(value)
            if not file_rec:
                continue
            try:
                mtime_ms = float(file_rec.get("mtimeMs"))
                size = float(file_rec.get("size"))
            except (TypeError, ValueError):
                continue
            if not (mtime_ms >= 0 and size >= 0):
                continue
            entry: DailyIngestionFileState = {
                "mtimeMs": int(mtime_ms),
                "size": int(size),
            }
            last_day = _normalize_memory_day(file_rec.get("lastDreamingDayIngested"))
            if last_day:
                entry["lastDreamingDayIngested"] = last_day
            files[key] = entry
    return {"version": 1, "files": files}


def normalize_session_ingestion_state(raw: Any) -> SessionIngestionState:
    """Validate + coerce a session ingestion state payload.

    Mirrors OpenClaw's ``normalizeSessionIngestionState``. Caps seen
    message hash lists at ``SESSION_INGESTION_MAX_TRACKED_MESSAGES_PER_SESSION``.
    """
    record = _as_record(raw)
    files: dict[str, SessionIngestionFileState] = {}
    files_raw = _as_record(record.get("files")) if record else None
    if files_raw:
        for key, value in files_raw.items():
            if not isinstance(key, str) or not key.strip():
                continue
            file_rec = _as_record(value)
            if not file_rec:
                continue
            try:
                mtime_ms = float(file_rec.get("mtimeMs"))
                size = float(file_rec.get("size"))
            except (TypeError, ValueError):
                continue
            if not (mtime_ms >= 0 and size >= 0):
                continue
            try:
                line_count_raw = float(file_rec.get("lineCount", 0))
                last_line_raw = float(file_rec.get("lastContentLine", 0))
            except (TypeError, ValueError):
                line_count_raw = 0.0
                last_line_raw = 0.0
            line_count = int(line_count_raw) if line_count_raw >= 0 else 0
            last_line = int(last_line_raw) if last_line_raw >= 0 else 0
            files[key] = {
                "mtimeMs": int(mtime_ms),
                "size": int(size),
                "contentHash": (
                    file_rec.get("contentHash", "").strip()
                    if isinstance(file_rec.get("contentHash"), str)
                    else ""
                ),
                "lineCount": line_count,
                "lastContentLine": min(line_count, last_line),
            }
    seen_messages: dict[str, list[str]] = {}
    seen_raw = _as_record(record.get("seenMessages")) if record else None
    if seen_raw:
        for scope, value in seen_raw.items():
            if not isinstance(scope, str) or not scope.strip() or not isinstance(value, list):
                continue
            unique: list[str] = []
            seen = set()
            for item in value:
                if not isinstance(item, str):
                    continue
                if item in seen:
                    continue
                seen.add(item)
                unique.append(item)
            unique = unique[-SESSION_INGESTION_MAX_TRACKED_MESSAGES_PER_SESSION:]
            if unique:
                seen_messages[scope] = unique
    return {"version": 3, "files": files, "seenMessages": seen_messages}


# ── Ingestion state CRUD (delegates to dreaming_state SQLite store) ───


def _read_daily_ingestion_state(workspace_dir: str) -> DailyIngestionState:
    """Read the daily ingestion state from the SQLite plugin store.

    Mirrors OpenClaw's ``readDailyIngestionState`` (which uses the
    keyed store). Returns a fresh empty state if no entries exist.
    """
    from .dreaming_state import (
        DREAMING_DAILY_INGESTION_NAMESPACE,
        read_memory_core_workspace_entries,
    )

    entries = read_memory_core_workspace_entries(
        namespace=DREAMING_DAILY_INGESTION_NAMESPACE,
        workspace_dir=workspace_dir,
    )
    return normalize_daily_ingestion_state(
        {
            "version": 1,
            "files": {key: value for key, value in entries},
        }
    )


def _write_daily_ingestion_state(
    workspace_dir: str, state: DailyIngestionState
) -> None:
    """Write the daily ingestion state to the SQLite plugin store.

    Mirrors OpenClaw's ``writeDailyIngestionState``.
    """
    from .dreaming_state import (
        DREAMING_DAILY_INGESTION_NAMESPACE,
        write_memory_core_workspace_entries,
    )

    write_memory_core_workspace_entries(
        namespace=DREAMING_DAILY_INGESTION_NAMESPACE,
        workspace_dir=workspace_dir,
        entries=[{"key": key, "value": value} for key, value in (state.get("files") or {}).items()],
    )


def _read_session_ingestion_state(workspace_dir: str) -> SessionIngestionState:
    """Read the session ingestion state (files + seenMessages) from SQLite.

    Mirrors OpenClaw's ``readSessionIngestionState``. The seenMessages
    map is reconstructed from chunked entries in the seen namespace
    (key = ``<scope>:<index>``).
    """
    from .dreaming_state import (
        DREAMING_SESSION_INGESTION_FILES_NAMESPACE,
        DREAMING_SESSION_INGESTION_SEEN_NAMESPACE,
        SESSION_SEEN_HASHES_PER_CHUNK,
        read_memory_core_workspace_entries,
    )

    file_entries = read_memory_core_workspace_entries(
        namespace=DREAMING_SESSION_INGESTION_FILES_NAMESPACE,
        workspace_dir=workspace_dir,
    )
    seen_chunks = read_memory_core_workspace_entries(
        namespace=DREAMING_SESSION_INGESTION_SEEN_NAMESPACE,
        workspace_dir=workspace_dir,
    )
    seen_messages: dict[str, list[str]] = {}
    chunks_by_scope: dict[str, list[tuple[int, list[str]]]] = {}
    for entry in seen_chunks:
        scope = (entry[1] or {}).get("scope", "").strip() if isinstance(entry[1], dict) else ""
        if not scope:
            continue
        idx = int((entry[1] or {}).get("index", 0))
        hashes = (entry[1] or {}).get("hashes") or []
        if not isinstance(hashes, list):
            continue
        chunks_by_scope.setdefault(scope, []).append((idx, [h for h in hashes if isinstance(h, str)]))
    for scope, chunks in chunks_by_scope.items():
        chunks.sort(key=lambda c: c[0])
        seen_messages[scope] = [h for _, hs in chunks for h in hs]
    return normalize_session_ingestion_state(
        {
            "version": 3,
            "files": {key: value for key, value in file_entries},
            "seenMessages": seen_messages,
        }
    )


def _write_session_ingestion_state(
    workspace_dir: str, state: SessionIngestionState
) -> None:
    """Write the session ingestion state (files + seenMessages) to SQLite.

    Mirrors OpenClaw's ``writeSessionIngestionState``. Splits the
    seenMessages hashes into ``SESSION_SEEN_HASHES_PER_CHUNK`` chunks
    per scope.
    """
    from .dreaming_state import (
        DREAMING_SESSION_INGESTION_FILES_NAMESPACE,
        DREAMING_SESSION_INGESTION_SEEN_NAMESPACE,
        SESSION_SEEN_HASHES_PER_CHUNK,
        write_memory_core_workspace_entries,
    )

    seen_entries: list[dict[str, Any]] = []
    for scope, hashes in (state.get("seenMessages") or {}).items():
        for index in range(0, max(1, (len(hashes) + SESSION_SEEN_HASHES_PER_CHUNK - 1) // SESSION_SEEN_HASHES_PER_CHUNK)):
            chunk = hashes[index * SESSION_SEEN_HASHES_PER_CHUNK:(index + 1) * SESSION_SEEN_HASHES_PER_CHUNK]
            seen_entries.append(
                {"key": f"{scope}:{index}", "value": {"scope": scope, "index": index, "hashes": chunk}}
            )
    # File entries + seen entries are written in parallel.
    import asyncio

    async def _both() -> None:
        await asyncio.gather(
            write_memory_core_workspace_entries(
                namespace=DREAMING_SESSION_INGESTION_FILES_NAMESPACE,
                workspace_dir=workspace_dir,
                entries=[
                    {"key": key, "value": value}
                    for key, value in (state.get("files") or {}).items()
                ],
            ),
            write_memory_core_workspace_entries(
                namespace=DREAMING_SESSION_INGESTION_SEEN_NAMESPACE,
                workspace_dir=workspace_dir,
                entries=seen_entries,
            ),
        )

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Defer to a fresh loop (matches the sync-write pattern used
            # by 4.4d's ``_atomic_write_text``).
            asyncio.run(_both())
        else:
            loop.run_until_complete(_both())
    except RuntimeError:
        # No running loop + no default loop (e.g. inside an async test).
        asyncio.run(_both())


# ── Session ingestion helpers ────────────────────────────────────────


def _hash_session_message_id(value: str) -> str:
    """SHA-1 hex digest of ``value`` (mirrors OpenClaw's ``hashSessionMessageId``)."""
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _normalize_session_corpus_snippet(value: str) -> str:
    """Trim + collapse whitespace + cap to ``SESSION_INGESTION_MAX_SNIPPET_CHARS``.

    Mirrors OpenClaw's ``normalizeSessionCorpusSnippet``.
    """
    return _truncate_utf16_safe(" ".join(value.split()), SESSION_INGESTION_MAX_SNIPPET_CHARS)


def _merge_tracked_message_hashes(
    existing: list[str], additions: list[str]
) -> list[str]:
    """Append unique additions to ``existing``; cap to the per-session max.

    Mirrors OpenClaw's ``mergeTrackedMessageHashes``.
    """
    if not additions:
        return existing
    seen = set(existing)
    next_list = list(existing)
    for h in additions:
        if h not in seen:
            seen.add(h)
            next_list.append(h)
    if len(next_list) <= SESSION_INGESTION_MAX_TRACKED_MESSAGES_PER_SESSION:
        return next_list
    return next_list[-SESSION_INGESTION_MAX_TRACKED_MESSAGES_PER_SESSION:]


def _trim_tracked_session_scopes(
    seen_messages: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Keep the lexicographically last ``MAX_TRACKED_SCOPES`` scopes.

    Mirrors OpenClaw's ``trimTrackedSessionScopes``. Used to bound
    the per-workspace seenMessages map.
    """
    keys = list(seen_messages.keys())
    if len(keys) <= SESSION_INGESTION_MAX_TRACKED_SCOPES:
        return seen_messages
    keep = set(sorted(keys)[-SESSION_INGESTION_MAX_TRACKED_SCOPES:])
    return {scope: hashes for scope, hashes in seen_messages.items() if scope in keep}


# ── LLM orchestrators (STUBS) ────────────────────────────────────────
#
# The full LLM orchestrators (runLightDreaming, runRemDreaming,
# runDreamingSweepPhases, previewRemDreaming,
# seedHistoricalDailyMemorySignals) require:
#   - The LLM subagent surface (port: pending)
#   - The short-term-promotion module (port: pending)
#   - The dreaming-narrative orchestrator (4.4e: stubbed pending LLM)
#   - The full text-similarity tokenizer (port: minimal Jaccard for now)
#
# All deterministic helpers they depend on are implemented above and
# tested. The moment the LLM subagent + short-term-promotion are
# ported, the orchestrators can be filled in without changing any
# helpers in this module.

LoggerLike = Any  # type: ignore[misc]


async def seed_historical_daily_memory_signals(  # pragma: no cover - stub
    workspace_dir: str,
    lookback_days: int,
    logger: LoggerLike | None = None,
    now_ms: int | None = None,
) -> None:
    """[STUB] Seed daily memory signals for the given lookback window.

    Mirrors OpenClaw's ``seedHistoricalDailyMemorySignals``. Logs a
    warning and returns. The full implementation requires the
    short-term-promotion module + search index integration.
    """
    if logger is not None:
        logger.warn(
            "memory-core: seed_historical_daily_memory_signals is a stub "
            "until the short-term-promotion module is ported"
        )


def preview_rem_dreaming(  # pragma: no cover - stub
    entries: list[ShortTermRecallEntry],
    min_pattern_strength: float,
    now_ms: int | None = None,
) -> list[RemDreamingPreview]:
    """[STUB] Preview REM reflections without writing them.

    Mirrors OpenClaw's ``previewRemDreaming``. Logs a warning and
    returns ``[]``. The full implementation requires the LLM subagent.
    """
    return []


async def run_light_dreaming(  # pragma: no cover - stub
    workspace_dir: str,
    config: Any,
    logger: LoggerLike | None = None,
    now_ms: int | None = None,
) -> None:
    """[STUB] Run the light-sleep dreaming phase.

    Mirrors OpenClaw's ``runLightDreaming``. Logs a warning and
    returns. Requires short-term-promotion + LLM subagent.
    """
    if logger is not None:
        logger.warn(
            "memory-core: run_light_dreaming is a stub until the "
            "short-term-promotion + LLM subagent are ported"
        )


async def run_rem_dreaming(  # pragma: no cover - stub
    workspace_dir: str,
    config: Any,
    logger: LoggerLike | None = None,
    now_ms: int | None = None,
) -> None:
    """[STUB] Run the REM-sleep dreaming phase.

    Mirrors OpenClaw's ``runRemDreaming``.
    """
    if logger is not None:
        logger.warn(
            "memory-core: run_rem_dreaming is a stub until the "
            "short-term-promotion + LLM subagent are ported"
        )


async def run_dreaming_sweep_phases(  # pragma: no cover - stub
    workspace_dir: str,
    config: Any,
    logger: LoggerLike | None = None,
    now_ms: int | None = None,
) -> None:
    """[STUB] Run the full dreaming sweep (light → REM → deep).

    Mirrors OpenClaw's ``runDreamingSweepPhases``.
    """
    if logger is not None:
        logger.warn(
            "memory-core: run_dreaming_sweep_phases is a stub until the "
            "short-term-promotion + LLM subagent are ported"
        )


__all__ = [
    # Path constants
    "DAILY_INGESTION_STATE_RELATIVE_PATH",
    "SESSION_INGESTION_STATE_RELATIVE_PATH",
    "SESSION_CORPUS_RELATIVE_DIR",
    # Scoring + size constants
    "DAILY_INGESTION_SCORE",
    "DAILY_INGESTION_MAX_SNIPPET_CHARS",
    "DAILY_INGESTION_MIN_SNIPPET_CHARS",
    "DAILY_INGESTION_MAX_CHUNK_LINES",
    "SESSION_INGESTION_SCORE",
    "SESSION_INGESTION_MAX_SNIPPET_CHARS",
    "SESSION_INGESTION_MIN_SNIPPET_CHARS",
    "SESSION_INGESTION_MAX_MESSAGES_PER_SWEEP",
    "SESSION_INGESTION_MAX_MESSAGES_PER_FILE",
    "SESSION_INGESTION_MIN_MESSAGES_PER_FILE",
    "SESSION_INGESTION_MAX_TRACKED_MESSAGES_PER_SESSION",
    "SESSION_INGESTION_MAX_TRACKED_SCOPES",
    "LIGHT_DIARY_HISTORY_LIMIT",
    "LIGHT_DIARY_SNIPPET_SIMILARITY_THRESHOLD",
    # Regex
    "MEMORY_DAY_RE",
    "DAILY_MEMORY_FILENAME_RE",
    "SESSION_CHECKPOINT_TRANSCRIPT_FILENAME_RE",
    # Managed blocks
    "MANAGED_DAILY_DREAMING_BLOCKS",
    # Types
    "DailySnippetChunk",
    "DailyMemoryFile",
    "DailyIngestionFileState",
    "DailyIngestionState",
    "SessionIngestionFileState",
    "SessionIngestionState",
    "ShortTermRecallEntry",
    "RemDreamingPreview",
    # Lookback + filter
    "filter_recall_entries_within_lookback",
    # Daily snippet extraction
    "build_daily_snippet_chunks",
    # Daily memory file
    "_parse_daily_memory_file_name",
    # Managed block stripping
    "_strip_managed_daily_dreaming_lines",
    # Dedupe + diary coverage
    "dedupe_entries",
    "normalize_diary_coverage_text",
    "is_entry_covered_by_recent_diary",
    "prioritize_light_entries_by_diary_coverage",
    # Ingestion state
    "normalize_daily_ingestion_state",
    "normalize_session_ingestion_state",
    # Session ingestion helpers
    "_hash_session_message_id",
    "_normalize_session_corpus_snippet",
    "_merge_tracked_message_hashes",
    "_trim_tracked_session_scopes",
    # Orchestrators (stubs)
    "seed_historical_daily_memory_signals",
    "preview_rem_dreaming",
    "run_light_dreaming",
    "run_rem_dreaming",
    "run_dreaming_sweep_phases",
]
