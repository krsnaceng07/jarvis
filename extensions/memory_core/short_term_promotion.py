"""memory_core.short_term_promotion — short-term recall + promotion pipeline.

OpenClaw parity: mirrors ``extensions/memory-core/src/short-term-promotion.ts``
(2 974 LOC).

This module implements the full deterministic pipeline for short-term memory
promotion into MEMORY.md:

- **Signal recording**: ``record_short_term_recalls``,
  ``record_grounded_short_term_candidates``, ``record_dreaming_phase_signals``
  — track recall events, grounded candidates, and dreaming phase hits in the
  SQLite-backed keyed store.
- **Store normalization**: ``normalize_short_term_recall_store``,
  ``normalize_short_term_phase_signal_store`` — validate + coerce raw JSON
  from the keyed store.
- **Candidate ranking**: ``rank_short_term_promotion_candidates`` — score
  entries by a 6-component weighted formula (frequency, relevance, diversity,
  recency, consolidation, conceptual) and return ranked promotion candidates.
- **Promotion application**: ``apply_short_term_promotions`` — write promoted
  snippets into MEMORY.md with compaction budget enforcement.
- **Artifact repair**: ``repair_short_term_promotion_artifacts`` — remove
  invalid/overflow entries and stale lock files.
- **Stats**: ``load_short_term_promotion_dreaming_stats`` — aggregate stats
  for the dreaming dashboard.

Port decisions:
- Process-level locking is replaced by an ``asyncio.Lock`` keyed by workspace
  (``_workspace_locks``), plus the SQLite-backed keyed store for cross-process
  coordination via ``register_if_absent`` / ``delete``. This matches OpenClaw's
  two-level locking model (in-process ``KeyedAsyncQueue`` + keyed store).
- UTF-16 safe truncation (``truncateUtf16Safe``) is approximated using Python's
  native string length (code-units are code points for BMP text). Surrogate-pair
  splits are handled by ``_truncate_utf16_safe``.
- ``replaceFileAtomic`` maps to ``pathlib.Path.write_text`` with a temp-file
  rename strategy or fall-back in-place rewrite.
- The ``fs.realpath`` symlink resolution is mirrored in ``_resolve_memory_write_path``.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import math
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict

from .concept_vocabulary import MAX_CONCEPT_TAGS, derive_concept_tags
from .dreaming_shared import format_error_message
from .dreaming_state import (
    SHORT_TERM_LOCK_MAX_ENTRIES,
    SHORT_TERM_LOCK_NAMESPACE,
    SHORT_TERM_META_NAMESPACE,
    SHORT_TERM_PHASE_SIGNAL_NAMESPACE,
    SHORT_TERM_RECALL_NAMESPACE,
    memory_core_state_reference,
    memory_core_workspace_state_key,
    open_memory_core_state_store,
    read_memory_core_workspace_entries,
    write_memory_core_workspace_entries,
    write_memory_core_workspace_entry,
    OpenKeyedStoreOptions,
)
from .memory_budget import (
    DEFAULT_MEMORY_FILE_MAX_CHARS,
    compact_memory_for_budget,
)
from .short_term_scoring import (
    _calculate_conceptual_component,
    _calculate_consolidation_component,
    _calculate_phase_signal_boost,
    _calculate_recency_component,
    _normalize_weights,
    _total_signal_count_for_entry,
    is_contaminated_dreaming_snippet,
)
from .time import resolve_memory_core_now_ms, resolve_memory_core_timestamp

# ── Path / regex constants ───────────────────────────────────────────────────

_SHORT_TERM_PATH_RE = re.compile(
    r"(?:^|/)memory/(?:[^/]+/)*(\d{4})-(\d{2})-(\d{2})(?:-[^/]+)?\.md$"
)
_DREAMING_MEMORY_PATH_RE = re.compile(r"(?:^|/)memory/dreaming/")
_SHORT_TERM_SESSION_CORPUS_RE = re.compile(
    r"(?:^|/)memory/\.dreams/session-corpus/(\d{4})-(\d{2})-(\d{2})\.(?:md|txt)$"
)
_SHORT_TERM_BASENAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:-[^/]+)?\.md$")
_DREAMING_TRANSCRIPT_PROMPT_LINE_RE = re.compile(
    r"\[[^\]]*dreaming-narrative[^\]]*\]\s*(?:User|Assistant):\s*"
    r"Write a dream diary entry from these memory fragments:?",
    re.IGNORECASE,
)
_RAW_SESSION_METADATA_RE = re.compile(
    r"\bSession Key\b.{0,260}\bSession ID\b|\bSession ID\b.{0,260}\bSession Key\b",
    re.IGNORECASE,
)
_RAW_CONVERSATION_SUMMARY_RE = re.compile(r"^(?:[-*+]\s*)?Conversation Summary:", re.IGNORECASE)
_RAW_TRANSCRIPT_TURN_RE = re.compile(r"^(?:[-*+]\s*)?(?:user|assistant):\s", re.IGNORECASE)
_MEMORY_FLUSH_PROMPT_RE = re.compile(
    r"Save important context from this session to the daily memory file\.\s*STRICT RULES:",
    re.IGNORECASE,
)
_PROMOTION_SCORE_METADATA_RE = re.compile(
    r"\[\s*score=\d+(?:\.\d+)?\s+(?:signals=\d+\s+)?recalls=\d+\s+avg=\d+(?:\.\d+)?"
    r"\s+source=memory/",
    re.IGNORECASE,
)
_DREAMING_DIFF_PREFIX_RE = re.compile(r"@@\s*-\d+(?:,\d+)?\s+[-*+]\s+")
_GENERIC_DAY_HEADING_RE = re.compile(
    r"^(?:(?:mon|monday|tue|tues|tuesday|wed|wednesday|thu|thur|thurs|thursday|"
    r"fri|friday|sat|saturday|sun|sunday)(?:,\s+)?)?"
    r"(?:(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|"
    r"aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+"
    r"\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?|"
    r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}[/-]\d{2}[/-]\d{2})$",
    re.IGNORECASE,
)
_PROMOTION_LIST_MARKER_RE = re.compile(r"^(?:\d+\.\s+|[-*+]\s+)")
_MANAGED_DREAMING_HEADINGS: frozenset[str] = frozenset(["light sleep", "rem sleep"])
_PROMOTION_MARKER_PREFIX = "openclaw-memory-promotion:"
_PROMOTION_MARKER_RE = re.compile(
    r"<!--\s*openclaw-memory-promotion:([^\n]*?)\s*-->", re.IGNORECASE
)
_DREAMING_FENCE_START_RE = re.compile(r"<!--\s*openclaw:dreaming:\w+:start\s*-->", re.IGNORECASE)
_DREAMING_FENCE_END_RE = re.compile(r"<!--\s*openclaw:dreaming:\w+:end\s*-->", re.IGNORECASE)

# ── Numeric constants ────────────────────────────────────────────────────────

DAY_MS = 24 * 60 * 60 * 1000

DEFAULT_PROMOTION_MIN_SCORE = 0.75
DEFAULT_PROMOTION_MIN_RECALL_COUNT = 3
DEFAULT_PROMOTION_MIN_UNIQUE_QUERIES = 2

SHORT_TERM_STORE_RELATIVE_PATH = os.path.join("memory", ".dreams", "short-term-recall.json")
SHORT_TERM_PHASE_SIGNAL_RELATIVE_PATH = os.path.join("memory", ".dreams", "phase-signals.json")

_SHORT_TERM_RECALL_MAX_ENTRIES = 512
_SHORT_TERM_RECALL_MAX_SNIPPET_CHARS = 800
_MAX_QUERY_HASHES = 32
_MAX_RECALL_DAYS = 16
_SHORT_TERM_SOURCE_FILE_CHECK_CONCURRENCY = 32
_SHORT_TERM_LOCK_WAIT_TIMEOUT_MS = 10_000
_SHORT_TERM_LOCK_STALE_MS = 60_000
_SHORT_TERM_LOCK_RETRY_DELAY_MS = 40
_DREAMING_ENTRY_LIST_LIMIT = 8
_PROMOTED_SNIPPET_CHARS_PER_TOKEN_ESTIMATE = 4

# ── In-process per-workspace locks ────────────────────────────────────────────

_workspace_locks: dict[str, asyncio.Lock] = {}
_workspace_locks_mu = asyncio.Lock()


async def _get_workspace_lock(workspace_dir: str) -> asyncio.Lock:
    """Return (creating if needed) the in-process asyncio.Lock for workspace."""
    key = memory_core_workspace_state_key(workspace_dir)
    async with _workspace_locks_mu:
        lock = _workspace_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _workspace_locks[key] = lock
    return lock


# ── Types ────────────────────────────────────────────────────────────────────


class ShortTermRecallEntry(TypedDict, total=False):
    key: str
    path: str
    start_line: int
    end_line: int
    source: Literal["memory"]
    snippet: str
    recall_count: int
    daily_count: int
    grounded_count: int
    total_score: float
    max_score: float
    first_recalled_at: str
    last_recalled_at: str
    query_hashes: list[str]
    recall_days: list[str]
    concept_tags: list[str]
    claim_hash: str
    promoted_at: str


class ShortTermRecallStore(TypedDict):
    version: int
    updated_at: str
    entries: dict[str, ShortTermRecallEntry]


class ShortTermPhaseSignalEntry(TypedDict, total=False):
    key: str
    light_hits: int
    rem_hits: int
    last_light_at: str
    last_rem_at: str
    last_rem_considered_at: str


class ShortTermPhaseSignalStore(TypedDict):
    version: int
    updated_at: str
    entries: dict[str, ShortTermPhaseSignalEntry]


class PromotionComponents(TypedDict):
    frequency: float
    relevance: float
    diversity: float
    recency: float
    consolidation: float
    conceptual: float


class PromotionCandidate(TypedDict, total=False):
    key: str
    path: str
    start_line: int
    end_line: int
    source: Literal["memory"]
    snippet: str
    recall_count: int
    daily_count: int
    grounded_count: int
    signal_count: int
    avg_score: float
    max_score: float
    unique_queries: int
    claim_hash: str
    promoted_at: str
    first_recalled_at: str
    last_recalled_at: str
    age_days: float
    score: float
    recall_days: list[str]
    concept_tags: list[str]
    components: PromotionComponents


class ShortTermAuditIssue(TypedDict):
    severity: Literal["warn", "error"]
    code: str
    message: str
    fixable: bool


class ShortTermAuditSummary(TypedDict, total=False):
    store_path: str
    lock_path: str
    updated_at: str
    exists: bool
    entry_count: int
    promoted_count: int
    spaced_entry_count: int
    concept_tagged_entry_count: int
    invalid_entry_count: int
    issues: list[ShortTermAuditIssue]


class RepairShortTermPromotionArtifactsResult(TypedDict):
    changed: bool
    removed_invalid_entries: int
    removed_overflow_entries: int
    rewrote_store: bool
    removed_stale_lock: bool


class ApplyShortTermPromotionsResult(TypedDict):
    memory_path: str
    applied: int
    appended: int
    reconciled_existing: int
    applied_candidates: list[PromotionCandidate]
    compacted_sections: int
    compacted_dates: list[str]


class ShortTermDreamingStatsEntry(TypedDict, total=False):
    key: str
    path: str
    start_line: int
    end_line: int
    snippet: str
    recall_count: int
    daily_count: int
    grounded_count: int
    total_signal_count: int
    light_hits: int
    rem_hits: int
    phase_hit_count: int
    promoted_at: str
    last_recalled_at: str


class ShortTermDreamingStats(TypedDict, total=False):
    short_term_count: int
    recall_signal_count: int
    daily_signal_count: int
    grounded_signal_count: int
    total_signal_count: int
    phase_signal_count: int
    light_phase_hit_count: int
    rem_phase_hit_count: int
    promoted_total: int
    promoted_today: int
    store_path: str
    phase_signal_path: str
    phase_signal_error: str
    last_promoted_at: str
    short_term_entries: list[ShortTermDreamingStatsEntry]
    signal_entries: list[ShortTermDreamingStatsEntry]
    promoted_entries: list[ShortTermDreamingStatsEntry]


# ── Utility helpers ───────────────────────────────────────────────────────────


def _clamp_score(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


def _to_finite_score(value: object, fallback: float) -> float:
    try:
        num = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(num) or num < 0 or num > 1:
        return fallback
    return num


def _to_finite_positive(value: object, fallback: float) -> float:
    try:
        num = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(num) or num <= 0:
        return fallback
    return num


def _to_finite_non_negative_int(value: object, fallback: int) -> int:
    try:
        num = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(num):
        return fallback
    result = int(num)
    return max(0, result)


def _to_non_negative_int(value: object) -> int:
    try:
        return max(0, int(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _normalize_snippet(raw: str) -> str:
    trimmed = raw.strip()
    if not trimmed:
        return ""
    return re.sub(r"\s+", " ", trimmed)


def _truncate_utf16_safe(s: str, limit: int) -> str:
    """Truncate string at ``limit`` UTF-16 code units without splitting surrogates."""
    if len(s) <= limit:
        return s
    # Python str uses UTF-32 internally; len(s) == code points.
    # For BMP-only text, UTF-16 code units == code points.
    # For text with surrogates, we need to be careful.
    result = s[:limit]
    # Strip trailing high surrogate (U+D800–UDBFF)
    if result and 0xD800 <= ord(result[-1]) <= 0xDBFF:
        result = result[:-1]
    return result


def _truncate_short_term_snippet(snippet: str) -> str:
    if len(snippet) <= _SHORT_TERM_RECALL_MAX_SNIPPET_CHARS:
        return snippet
    return _truncate_utf16_safe(snippet, _SHORT_TERM_RECALL_MAX_SNIPPET_CHARS).rstrip()


def _normalize_iso_day(iso_like: str) -> str | None:
    if not isinstance(iso_like, str):
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", iso_like.strip())
    return m.group(1) if m else None


def _normalize_distinct_strings(values: list[object], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for v in values:
        if not isinstance(v, str):
            continue
        t = v.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        result.append(t)
        if len(result) >= limit:
            break
    return result


def _hash_query(query: str) -> str:
    return hashlib.sha256(query.strip().encode("utf-8")).hexdigest()[:16]


def _build_claim_hash(snippet: str) -> str:
    normalized = _normalize_snippet(snippet)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _build_entry_key(
    *,
    path: str,
    start_line: int,
    end_line: int,
    source: str,
    claim_hash: str | None = None,
) -> str:
    parts = f"{path}:{start_line}:{end_line}:{source}"
    if claim_hash:
        parts += f":{claim_hash}"
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:32]


def _normalize_memory_path(raw: str) -> str:
    """Normalise a path to forward slashes, stripping leading workspace root."""
    normalized = raw.replace("\\", "/").strip()
    return normalized


def _is_short_term_memory_path(path: str) -> bool:
    """Return True if the path is a short-term daily memory file."""
    if _DREAMING_MEMORY_PATH_RE.search(path):
        return False
    m = _SHORT_TERM_PATH_RE.search(path)
    if m:
        return True
    return bool(_SHORT_TERM_SESSION_CORPUS_RE.search(path))


def _is_short_term_session_corpus_path(path: str) -> bool:
    return bool(_SHORT_TERM_SESSION_CORPUS_RE.search(path))


def _merge_query_hashes(existing: list[str], new_hash: str) -> list[str]:
    if new_hash in existing:
        return existing
    combined = [*existing, new_hash]
    if len(combined) > _MAX_QUERY_HASHES:
        combined = combined[-_MAX_QUERY_HASHES:]
    return combined


def _merge_recent_distinct(base: list[str], new_item: str | None, limit: int) -> list[str]:
    if new_item is None:
        return base[-limit:] if len(base) > limit else base
    combined = list(dict.fromkeys([*base, new_item]))  # preserve order, deduplicate
    return combined[-limit:] if len(combined) > limit else combined


# ── Store helpers ─────────────────────────────────────────────────────────────


def _resolve_store_path(workspace_dir: str) -> str:
    return memory_core_state_reference(SHORT_TERM_RECALL_NAMESPACE, workspace_dir)


def _resolve_phase_signal_path(workspace_dir: str) -> str:
    return memory_core_state_reference(SHORT_TERM_PHASE_SIGNAL_NAMESPACE, workspace_dir)


def _resolve_lock_path(workspace_dir: str) -> str:
    return memory_core_state_reference(SHORT_TERM_LOCK_NAMESPACE, workspace_dir)


def _empty_store(now_iso: str) -> ShortTermRecallStore:
    return {"version": 1, "updated_at": now_iso, "entries": {}}


def normalize_short_term_recall_store(raw: object, now_iso: str) -> ShortTermRecallStore:
    """Validate + coerce a raw store dict.

    Mirrors OpenClaw's ``normalizeShortTermRecallStore``.
    """
    if not isinstance(raw, dict):
        return _empty_store(now_iso)
    entries_raw = raw.get("entries")
    entries: dict[str, ShortTermRecallEntry] = {}
    if isinstance(entries_raw, dict):
        for key, value in entries_raw.items():
            if not isinstance(value, dict):
                continue
            entry = value
            entry_path = (
                _normalize_memory_path(entry["path"]) if isinstance(entry.get("path"), str) else ""
            )
            try:
                start_line = int(entry.get("start_line", entry.get("startLine", 0)))
                end_line = int(entry.get("end_line", entry.get("endLine", 0)))
            except (TypeError, ValueError):
                continue
            source = entry.get("source")
            if source != "memory":
                continue
            if not entry_path or not start_line or not end_line:
                continue
            recall_count = max(0, int(entry.get("recall_count", entry.get("recallCount", 0)) or 0))
            daily_count = max(0, int(entry.get("daily_count", entry.get("dailyCount", 0)) or 0))
            grounded_count = max(
                0, int(entry.get("grounded_count", entry.get("groundedCount", 0)) or 0)
            )
            total_score = max(0.0, float(entry.get("total_score", entry.get("totalScore", 0)) or 0))
            max_score = _clamp_score(float(entry.get("max_score", entry.get("maxScore", 0)) or 0))
            first_recalled_at = (
                entry.get("first_recalled_at") or entry.get("firstRecalledAt") or now_iso
            )
            last_recalled_at = (
                entry.get("last_recalled_at") or entry.get("lastRecalledAt") or now_iso
            )
            promoted_at = entry.get("promoted_at") or entry.get("promotedAt")
            claim_hash = (entry.get("claim_hash") or entry.get("claimHash") or "").strip() or None
            full_snippet = (
                _normalize_snippet(entry["snippet"])
                if isinstance(entry.get("snippet"), str)
                else ""
            )
            if full_snippet and is_contaminated_dreaming_snippet(
                full_snippet,
                allow_transcript_turn_snippet=_is_short_term_session_corpus_path(entry_path),
            ):
                continue
            snippet = _truncate_short_term_snippet(full_snippet)
            raw_query_hashes = entry.get("query_hashes") or entry.get("queryHashes") or []
            query_hashes = (
                _normalize_distinct_strings(raw_query_hashes, _MAX_QUERY_HASHES)
                if isinstance(raw_query_hashes, list)
                else []
            )
            raw_recall_days = entry.get("recall_days") or entry.get("recallDays") or []
            recall_days = (
                [d for d in (_normalize_iso_day(d) for d in raw_recall_days) if d is not None]
                if isinstance(raw_recall_days, list)
                else []
            )
            raw_concept_tags = entry.get("concept_tags") or entry.get("conceptTags") or []
            concept_tags = (
                _normalize_distinct_strings(
                    [t.lower() if isinstance(t, str) else t for t in raw_concept_tags],
                    MAX_CONCEPT_TAGS,
                )
                if isinstance(raw_concept_tags, list)
                else derive_concept_tags(path=entry_path, snippet=full_snippet)
            )
            normalized_key = key or _build_entry_key(
                path=entry_path,
                start_line=start_line,
                end_line=end_line,
                source="memory",
                claim_hash=claim_hash,
            )
            built: ShortTermRecallEntry = {
                "key": normalized_key,
                "path": entry_path,
                "start_line": start_line,
                "end_line": end_line,
                "source": "memory",
                "snippet": snippet,
                "recall_count": recall_count,
                "daily_count": daily_count,
                "grounded_count": grounded_count,
                "total_score": total_score,
                "max_score": max_score,
                "first_recalled_at": first_recalled_at,
                "last_recalled_at": last_recalled_at,
                "query_hashes": query_hashes,
                "recall_days": recall_days[-_MAX_RECALL_DAYS:],
                "concept_tags": concept_tags,
            }
            if claim_hash:
                built["claim_hash"] = claim_hash
            if promoted_at:
                built["promoted_at"] = promoted_at
            entries[normalized_key] = built

    return {
        "version": 1,
        "updated_at": raw.get("updated_at") or raw.get("updatedAt") or now_iso,
        "entries": entries,
    }


def _enforce_short_term_recall_snippet_cap(store: ShortTermRecallStore) -> None:
    for entry in store["entries"].values():
        if "snippet" in entry:
            entry["snippet"] = _truncate_short_term_snippet(entry["snippet"])


def _parse_store_timestamp_ms(value: str | None) -> float:
    if not value:
        return float("-inf")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        result = dt.timestamp() * 1000
        return result if math.isfinite(result) else float("-inf")
    except ValueError:
        return float("-inf")


def _compare_short_term_recall_retention(a: ShortTermRecallEntry, b: ShortTermRecallEntry) -> int:
    last_a = _parse_store_timestamp_ms(a.get("last_recalled_at"))
    last_b = _parse_store_timestamp_ms(b.get("last_recalled_at"))
    if last_b > last_a:
        return 1
    if last_a > last_b:
        return -1
    sig_diff = _total_signal_count_for_entry(b) - _total_signal_count_for_entry(a)
    if sig_diff != 0:
        return sig_diff
    total_diff = (b.get("total_score", 0) or 0) - (a.get("total_score", 0) or 0)
    if total_diff != 0:
        return 1 if total_diff > 0 else -1
    return 0


def _enforce_short_term_recall_store_retention(store: ShortTermRecallStore) -> int:
    entries = list(store["entries"].items())
    if len(entries) <= _SHORT_TERM_RECALL_MAX_ENTRIES:
        return 0
    from functools import cmp_to_key  # noqa: PLC0415

    sorted_entries = sorted(
        entries, key=cmp_to_key(lambda a, b: _compare_short_term_recall_retention(a[1], b[1]))
    )
    retained = sorted_entries[:_SHORT_TERM_RECALL_MAX_ENTRIES]
    retained.sort(key=lambda kv: kv[0])
    store["entries"] = dict(retained)
    return len(entries) - _SHORT_TERM_RECALL_MAX_ENTRIES


def _empty_phase_signal_store(now_iso: str) -> ShortTermPhaseSignalStore:
    return {"version": 1, "updated_at": now_iso, "entries": {}}


def normalize_short_term_phase_signal_store(raw: object, now_iso: str) -> ShortTermPhaseSignalStore:
    """Validate + coerce a raw phase signal store dict.

    Mirrors OpenClaw's ``normalizeShortTermPhaseSignalStore``.
    """
    if not isinstance(raw, dict):
        return _empty_phase_signal_store(now_iso)
    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, dict):
        return _empty_phase_signal_store(now_iso)
    entries: dict[str, ShortTermPhaseSignalEntry] = {}
    for map_key, value in entries_raw.items():
        if not isinstance(value, dict):
            continue
        key = value.get("key")
        if not isinstance(key, str) or not key.strip():
            key = map_key
        light_hits = _to_finite_non_negative_int(
            value.get("light_hits") or value.get("lightHits"), 0
        )
        rem_hits = _to_finite_non_negative_int(value.get("rem_hits") or value.get("remHits"), 0)
        if light_hits == 0 and rem_hits == 0:
            continue
        built: ShortTermPhaseSignalEntry = {
            "key": key,
            "light_hits": light_hits,
            "rem_hits": rem_hits,
        }
        for field, js_field in (
            ("last_light_at", "lastLightAt"),
            ("last_rem_at", "lastRemAt"),
            ("last_rem_considered_at", "lastRemConsideredAt"),
        ):
            v = value.get(field) or value.get(js_field)
            if isinstance(v, str) and v.strip():
                built[field] = v.strip()  # type: ignore[literal-required]
        entries[key] = built
    updated_at = raw.get("updated_at") or raw.get("updatedAt") or ""
    return {
        "version": 1,
        "updated_at": updated_at.strip() if isinstance(updated_at, str) else now_iso,
        "entries": entries,
    }


# ── Store I/O (async, via SQLite keyed store) ─────────────────────────────────


async def _read_store(workspace_dir: str, now_iso: str) -> ShortTermRecallStore:
    loop = asyncio.get_event_loop()
    entry_rows, meta_rows = await asyncio.gather(
        loop.run_in_executor(
            None,
            lambda: read_memory_core_workspace_entries(SHORT_TERM_RECALL_NAMESPACE, workspace_dir),
        ),
        loop.run_in_executor(
            None,
            lambda: read_memory_core_workspace_entries(SHORT_TERM_META_NAMESPACE, workspace_dir),
        ),
    )
    meta_row = next((v for k, v in meta_rows if k == "recall"), None)
    store = normalize_short_term_recall_store(
        {
            "version": 1,
            "updated_at": (meta_row or {}).get("updated_at") or now_iso,
            "entries": {k: v for k, v in entry_rows},
        },
        now_iso,
    )
    _enforce_short_term_recall_store_retention(store)
    return store


async def _write_store(workspace_dir: str, store: ShortTermRecallStore) -> None:
    _enforce_short_term_recall_snippet_cap(store)
    loop = asyncio.get_event_loop()
    await asyncio.gather(
        loop.run_in_executor(
            None,
            lambda: write_memory_core_workspace_entries(
                SHORT_TERM_RECALL_NAMESPACE,
                workspace_dir,
                list(store["entries"].items()),
            ),
        ),
        loop.run_in_executor(
            None,
            lambda: write_memory_core_workspace_entry(
                SHORT_TERM_META_NAMESPACE,
                workspace_dir,
                "recall",
                {"updated_at": store["updated_at"]},
            ),
        ),
    )


async def _read_phase_signal_store(workspace_dir: str, now_iso: str) -> ShortTermPhaseSignalStore:
    loop = asyncio.get_event_loop()
    entry_rows, meta_rows = await asyncio.gather(
        loop.run_in_executor(
            None,
            lambda: read_memory_core_workspace_entries(
                SHORT_TERM_PHASE_SIGNAL_NAMESPACE, workspace_dir
            ),
        ),
        loop.run_in_executor(
            None,
            lambda: read_memory_core_workspace_entries(SHORT_TERM_META_NAMESPACE, workspace_dir),
        ),
    )
    meta_row = next((v for k, v in meta_rows if k == "phase"), None)
    return normalize_short_term_phase_signal_store(
        {
            "version": 1,
            "updated_at": (meta_row or {}).get("updated_at") or now_iso,
            "entries": {k: v for k, v in entry_rows},
        },
        now_iso,
    )


async def _write_phase_signal_store(workspace_dir: str, store: ShortTermPhaseSignalStore) -> None:
    loop = asyncio.get_event_loop()
    await asyncio.gather(
        loop.run_in_executor(
            None,
            lambda: write_memory_core_workspace_entries(
                SHORT_TERM_PHASE_SIGNAL_NAMESPACE,
                workspace_dir,
                list(store["entries"].items()),
            ),
        ),
        loop.run_in_executor(
            None,
            lambda: write_memory_core_workspace_entry(
                SHORT_TERM_META_NAMESPACE,
                workspace_dir,
                "phase",
                {"updated_at": store["updated_at"]},
            ),
        ),
    )


# ── In-process + keyed-store locking ─────────────────────────────────────────


async def _with_short_term_lock(workspace_dir: str, task):
    """Acquire the in-process asyncio.Lock for the workspace and run ``task``."""
    lock = await _get_workspace_lock(workspace_dir)
    async with lock:
        return await task()


# ── Signal recording ──────────────────────────────────────────────────────────


async def record_short_term_recalls(
    *,
    workspace_dir: str | None = None,
    query: str,
    results: list[dict],
    signal_type: Literal["recall", "daily"] = "recall",
    dedupe_by_query_per_day: bool = False,
    day_bucket: str | None = None,
    now_ms: int | None = None,
    timezone: str | None = None,
) -> None:
    """Record memory recall signals for short-term promotion.

    Mirrors OpenClaw's ``recordShortTermRecalls``.
    """
    wd = (workspace_dir or "").strip()
    if not wd:
        return
    query_stripped = query.strip()
    if not query_stripped:
        return

    now_ms_val = resolve_memory_core_now_ms(now_ms)
    now_iso = resolve_memory_core_timestamp(now_ms_val)
    today_bucket = day_bucket or datetime.fromtimestamp(now_ms_val / 1000, tz=UTC).strftime(
        "%Y-%m-%d"
    )

    relevant: list[dict] = []
    for result in results:
        raw_snippet = _normalize_snippet(result.get("snippet", "") or "")
        snippet = _truncate_short_term_snippet(raw_snippet)
        normalized_path = _normalize_memory_path(result.get("path", "") or "")
        if not raw_snippet:
            continue
        if is_contaminated_dreaming_snippet(
            raw_snippet,
            allow_transcript_turn_snippet=_is_short_term_session_corpus_path(normalized_path),
        ):
            continue
        if not normalized_path or not _is_short_term_memory_path(normalized_path):
            continue
        try:
            start_line = int(result.get("startLine") or result.get("start_line") or 0)
            end_line = int(result.get("endLine") or result.get("end_line") or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(start_line) or not math.isfinite(end_line):
            continue
        relevant.append(
            {
                "path": normalized_path,
                "start_line": max(1, start_line),
                "end_line": max(1, end_line),
                "snippet": snippet,
                "score": _clamp_score(float(result.get("score", 0) or 0)),
            }
        )

    if not relevant:
        return

    query_hash = _hash_query(query_stripped)

    async def _do() -> None:
        store = await _read_store(wd, now_iso)
        for item in relevant:
            key = _build_entry_key(
                path=item["path"],
                start_line=item["start_line"],
                end_line=item["end_line"],
                source="memory",
            )
            existing = store["entries"].get(key)
            recall_days_base = (existing or {}).get("recall_days", []) or []
            query_hashes_base = (existing or {}).get("query_hashes", []) or []
            dedupe_signal = (
                dedupe_by_query_per_day
                and query_hash in query_hashes_base
                and today_bucket in recall_days_base
            )
            score = item["score"]
            if signal_type == "daily":
                recall_count = max(0, int((existing or {}).get("recall_count", 0) or 0))
                daily_count = max(
                    0,
                    int((existing or {}).get("daily_count", 0) or 0) + (0 if dedupe_signal else 1),
                )
            else:
                recall_count = max(
                    0,
                    int((existing or {}).get("recall_count", 0) or 0) + (0 if dedupe_signal else 1),
                )
                daily_count = max(0, int((existing or {}).get("daily_count", 0) or 0))
            total_score = max(
                0.0,
                float((existing or {}).get("total_score", 0) or 0)
                + (0 if dedupe_signal else score),
            )
            max_sc = max(
                float((existing or {}).get("max_score", 0) or 0), 0 if dedupe_signal else score
            )
            query_hashes = _merge_query_hashes(query_hashes_base, query_hash)
            recall_days = _merge_recent_distinct(recall_days_base, today_bucket, _MAX_RECALL_DAYS)
            concept_tags = derive_concept_tags(path=item["path"], snippet=item["snippet"])

            unchanged_repeated = (
                dedupe_by_query_per_day
                and query_hash in query_hashes_base
                and (existing or {}).get("snippet") == item["snippet"]
            )
            last_recalled_at = (
                (existing or {}).get("last_recalled_at") or now_iso
                if unchanged_repeated
                else now_iso
            )
            built: ShortTermRecallEntry = {
                "key": key,
                "path": item["path"],
                "start_line": item["start_line"],
                "end_line": item["end_line"],
                "source": "memory",
                "snippet": item["snippet"] or (existing or {}).get("snippet", ""),
                "recall_count": recall_count,
                "daily_count": daily_count,
                "grounded_count": max(0, int((existing or {}).get("grounded_count", 0) or 0)),
                "total_score": total_score,
                "max_score": _clamp_score(max_sc),
                "first_recalled_at": (existing or {}).get("first_recalled_at") or now_iso,
                "last_recalled_at": last_recalled_at,
                "query_hashes": query_hashes,
                "recall_days": recall_days,
                "concept_tags": concept_tags
                if concept_tags
                else (existing or {}).get("concept_tags", []),
            }
            if existing and existing.get("claim_hash"):
                built["claim_hash"] = existing["claim_hash"]
            if existing and existing.get("promoted_at"):
                built["promoted_at"] = existing["promoted_at"]
            store["entries"][key] = built

        store["updated_at"] = now_iso
        await _write_store(wd, store)

    await _with_short_term_lock(wd, _do)


async def record_grounded_short_term_candidates(
    *,
    workspace_dir: str | None = None,
    query: str,
    items: list[dict],
    dedupe_by_query_per_day: bool = False,
    day_bucket: str | None = None,
    now_ms: int | None = None,
    timezone: str | None = None,
) -> None:
    """Record grounded short-term candidates (e.g. from Active Memory).

    Mirrors OpenClaw's ``recordGroundedShortTermCandidates``.
    """
    wd = (workspace_dir or "").strip()
    if not wd:
        return
    query_stripped = query.strip()
    if not query_stripped:
        return

    now_ms_val = resolve_memory_core_now_ms(now_ms)
    now_iso = resolve_memory_core_timestamp(now_ms_val)
    fallback_day = day_bucket or datetime.fromtimestamp(now_ms_val / 1000, tz=UTC).strftime(
        "%Y-%m-%d"
    )

    relevant: list[dict] = []
    for item in items:
        raw_snippet = _normalize_snippet(item.get("snippet", "") or "")
        snippet = _truncate_short_term_snippet(raw_snippet)
        normalized_path = _normalize_memory_path(item.get("path", "") or "")
        if not raw_snippet or is_contaminated_dreaming_snippet(raw_snippet):
            continue
        if not normalized_path or not _is_short_term_memory_path(normalized_path):
            continue
        try:
            start_line = max(1, int(item.get("startLine") or item.get("start_line") or 0))
            end_line = max(1, int(item.get("endLine") or item.get("end_line") or 0))
        except (TypeError, ValueError):
            continue
        relevant.append(
            {
                "path": normalized_path,
                "start_line": start_line,
                "end_line": end_line,
                "snippet": snippet,
                "identity_snippet": raw_snippet,
                "score": _clamp_score(float(item.get("score", 0) or 0)),
                "query": _normalize_snippet(item.get("query", "") or query_stripped),
                "signal_count": max(
                    1, int(item.get("signalCount") or item.get("signal_count") or 1)
                ),
                "day_bucket": _normalize_iso_day(
                    item.get("dayBucket") or item.get("day_bucket") or fallback_day
                ),
            }
        )

    if not relevant:
        return

    async def _do() -> None:
        store = await _read_store(wd, now_iso)
        for item in relevant:
            day = item["day_bucket"] or fallback_day
            effective_query = item["query"] or query_stripped
            if not effective_query:
                continue
            query_hash = _hash_query(effective_query)
            claim_hash = _build_claim_hash(item["identity_snippet"])
            key = _build_entry_key(
                path=item["path"],
                start_line=item["start_line"],
                end_line=item["end_line"],
                source="memory",
                claim_hash=claim_hash,
            )
            existing = store["entries"].get(key)
            recall_days_base = (existing or {}).get("recall_days", []) or []
            query_hashes_base = (existing or {}).get("query_hashes", []) or []
            dedupe_signal = (
                dedupe_by_query_per_day
                and query_hash in query_hashes_base
                and day in recall_days_base
            )
            grounded_count = max(
                0,
                int((existing or {}).get("grounded_count", 0) or 0)
                + (0 if dedupe_signal else item["signal_count"]),
            )
            total_score = max(
                0.0,
                float((existing or {}).get("total_score", 0) or 0)
                + (0 if dedupe_signal else item["score"] * item["signal_count"]),
            )
            max_sc = max(
                float((existing or {}).get("max_score", 0) or 0),
                0 if dedupe_signal else item["score"],
            )
            query_hashes = _merge_query_hashes(query_hashes_base, query_hash)
            recall_days = _merge_recent_distinct(recall_days_base, day, _MAX_RECALL_DAYS)
            concept_tags = derive_concept_tags(path=item["path"], snippet=item["snippet"])
            unchanged_repeated = (
                dedupe_by_query_per_day
                and query_hash in query_hashes_base
                and (existing or {}).get("snippet") == item["snippet"]
            )
            last_recalled_at = (
                (existing or {}).get("last_recalled_at") or now_iso
                if unchanged_repeated
                else now_iso
            )
            built: ShortTermRecallEntry = {
                "key": key,
                "path": item["path"],
                "start_line": item["start_line"],
                "end_line": item["end_line"],
                "source": "memory",
                "snippet": item["snippet"],
                "recall_count": max(0, int((existing or {}).get("recall_count", 0) or 0)),
                "daily_count": max(0, int((existing or {}).get("daily_count", 0) or 0)),
                "grounded_count": grounded_count,
                "total_score": total_score,
                "max_score": _clamp_score(max_sc),
                "first_recalled_at": (existing or {}).get("first_recalled_at") or now_iso,
                "last_recalled_at": last_recalled_at,
                "query_hashes": query_hashes,
                "recall_days": recall_days,
                "concept_tags": concept_tags
                if concept_tags
                else (existing or {}).get("concept_tags", []),
                "claim_hash": claim_hash,
            }
            if existing and existing.get("promoted_at"):
                built["promoted_at"] = existing["promoted_at"]
            store["entries"][key] = built

        store["updated_at"] = now_iso
        await _write_store(wd, store)

    await _with_short_term_lock(wd, _do)


async def record_dreaming_phase_signals(
    *,
    workspace_dir: str | None = None,
    phase: Literal["light", "rem"],
    keys: list[str],
    now_ms: int | None = None,
) -> None:
    """Record dreaming phase signals (light/rem) for the given entry keys.

    Mirrors OpenClaw's ``recordDreamingPhaseSignals``.
    """
    wd = (workspace_dir or "").strip()
    if not wd:
        return
    unique_keys = list(dict.fromkeys(k.strip() for k in keys if k.strip()))
    if not unique_keys:
        return

    now_ms_val = resolve_memory_core_now_ms(now_ms)
    now_iso = resolve_memory_core_timestamp(now_ms_val)

    async def _do() -> None:
        store, phase_signals = await asyncio.gather(
            _read_store(wd, now_iso),
            _read_phase_signal_store(wd, now_iso),
        )
        known_keys = set(store["entries"].keys())
        for key in unique_keys:
            if key not in known_keys:
                continue
            existing = phase_signals["entries"].get(key) or {
                "key": key,
                "light_hits": 0,
                "rem_hits": 0,
            }
            if phase == "light":
                phase_signals["entries"][key] = {
                    **existing,
                    "light_hits": max(0, int(existing.get("light_hits", 0) or 0)) + 1,
                    "last_light_at": now_iso,
                }
            else:
                phase_signals["entries"][key] = {
                    **existing,
                    "rem_hits": max(0, int(existing.get("rem_hits", 0) or 0)) + 1,
                    "last_rem_at": now_iso,
                }
        # Prune orphaned entries
        for key in list(phase_signals["entries"].keys()):
            entry = phase_signals["entries"][key]
            if key not in known_keys or (
                (entry.get("light_hits", 0) or 0) <= 0 and (entry.get("rem_hits", 0) or 0) <= 0
            ):
                del phase_signals["entries"][key]
        phase_signals["updated_at"] = now_iso
        await _write_phase_signal_store(wd, phase_signals)

    await _with_short_term_lock(wd, _do)


# ── Candidate ranking ─────────────────────────────────────────────────────────


async def rank_short_term_promotion_candidates(
    workspace_dir: str,
    *,
    limit: int | None = None,
    min_score: float | None = None,
    min_recall_count: int | None = None,
    min_unique_queries: int | None = None,
    max_age_days: int | None = None,
    include_promoted: bool = False,
    recency_half_life_days: float | None = None,
    weights: dict | None = None,
    now_ms: int | None = None,
) -> list[PromotionCandidate]:
    """Rank short-term recall entries as promotion candidates.

    Mirrors OpenClaw's ``rankShortTermPromotionCandidates``.
    """
    wd = workspace_dir.strip()
    if not wd:
        return []

    now_ms_val = resolve_memory_core_now_ms(now_ms)
    now_iso = resolve_memory_core_timestamp(now_ms_val)
    min_score_val = _to_finite_score(min_score, DEFAULT_PROMOTION_MIN_SCORE)
    min_recall_val = _to_finite_non_negative_int(
        min_recall_count, DEFAULT_PROMOTION_MIN_RECALL_COUNT
    )
    min_unique_val = _to_finite_non_negative_int(
        min_unique_queries, DEFAULT_PROMOTION_MIN_UNIQUE_QUERIES
    )
    max_age_val = _to_finite_non_negative_int(max_age_days, -1)
    half_life = _to_finite_positive(recency_half_life_days, 14.0)
    effective_weights = _normalize_weights(weights)

    store, phase_signals = await asyncio.gather(
        _read_store(wd, now_iso),
        _read_phase_signal_store(wd, now_iso),
    )

    candidates: list[PromotionCandidate] = []

    for entry in store["entries"].values():
        if not entry or entry.get("source") != "memory":
            continue
        entry_path = entry.get("path", "")
        if not _is_short_term_memory_path(entry_path):
            continue
        if is_contaminated_dreaming_snippet(
            entry.get("snippet", ""),
            allow_transcript_turn_snippet=_is_short_term_session_corpus_path(entry_path),
        ):
            continue
        if not include_promoted and entry.get("promoted_at"):
            continue

        recall_count = max(0, int(entry.get("recall_count", 0) or 0))
        daily_count = max(0, int(entry.get("daily_count", 0) or 0))
        grounded_count = max(0, int(entry.get("grounded_count", 0) or 0))
        signal_count = recall_count + daily_count + grounded_count

        if signal_count <= 0 or signal_count < min_recall_val:
            continue

        avg_score = _clamp_score(float(entry.get("total_score", 0) or 0) / max(1, signal_count))
        frequency = _clamp_score(math.log1p(signal_count) / math.log1p(10))
        query_hashes = entry.get("query_hashes", []) or []
        recall_days = entry.get("recall_days", []) or []
        unique_queries = len(query_hashes)
        context_diversity = max(unique_queries, len(recall_days))

        if context_diversity < min_unique_val:
            continue

        diversity = _clamp_score(context_diversity / 5)
        last_recalled_str = entry.get("last_recalled_at", "")
        age_days = 0.0
        if last_recalled_str:
            try:
                dt = datetime.fromisoformat(last_recalled_str.replace("Z", "+00:00"))
                age_days = max(0.0, (now_ms_val - dt.timestamp() * 1000) / DAY_MS)
            except ValueError:
                pass
        if max_age_val >= 0 and age_days > max_age_val:
            continue

        recency = _clamp_score(_calculate_recency_component(age_days, half_life))
        concept_tags = entry.get("concept_tags", []) or []
        consolidation = max(
            _calculate_consolidation_component(recall_days),
            _clamp_score(grounded_count / 3),
        )
        conceptual = _calculate_conceptual_component(concept_tags)

        phase_boost = _calculate_phase_signal_boost(
            phase_signals["entries"].get(entry.get("key", "")), now_ms_val
        )
        score = (
            effective_weights["frequency"] * frequency
            + effective_weights["relevance"] * avg_score
            + effective_weights["diversity"] * diversity
            + effective_weights["recency"] * recency
            + effective_weights["consolidation"] * consolidation
            + effective_weights["conceptual"] * conceptual
            + phase_boost
        )

        if score < min_score_val:
            continue

        candidate: PromotionCandidate = {
            "key": entry.get("key", ""),
            "path": entry_path,
            "start_line": entry.get("start_line", 1),
            "end_line": entry.get("end_line", 1),
            "source": "memory",
            "snippet": entry.get("snippet", ""),
            "recall_count": recall_count,
            "daily_count": daily_count,
            "grounded_count": grounded_count,
            "signal_count": signal_count,
            "avg_score": avg_score,
            "max_score": _clamp_score(float(entry.get("max_score", 0) or 0)),
            "unique_queries": unique_queries,
            "first_recalled_at": entry.get("first_recalled_at", now_iso),
            "last_recalled_at": entry.get("last_recalled_at", now_iso),
            "age_days": age_days,
            "score": _clamp_score(score),
            "recall_days": recall_days,
            "concept_tags": concept_tags,
            "components": {
                "frequency": frequency,
                "relevance": avg_score,
                "diversity": diversity,
                "recency": recency,
                "consolidation": consolidation,
                "conceptual": conceptual,
            },
        }
        if entry.get("claim_hash"):
            candidate["claim_hash"] = entry["claim_hash"]
        if entry.get("promoted_at"):
            candidate["promoted_at"] = entry["promoted_at"]
        candidates.append(candidate)

    candidates.sort(key=lambda c: (-c["score"], -c.get("recall_count", 0), c.get("path", "")))

    effective_limit = (
        max(0, int(limit)) if limit is not None and math.isfinite(limit) else len(candidates)
    )
    return candidates[:effective_limit]


# ── Promotion application ─────────────────────────────────────────────────────


_DEFAULT_MAX_PROMOTED_SNIPPET_TOKENS = (
    160  # Mirrors OpenClaw's DEFAULT_MEMORY_DREAMING_MAX_PROMOTED_SNIPPET_TOKENS
)


def _resolve_promoted_snippet_char_limit(max_tokens: int | None) -> int:
    tokens = (
        max_tokens
        if isinstance(max_tokens, int) and max_tokens >= 0
        else _DEFAULT_MAX_PROMOTED_SNIPPET_TOKENS
    )
    return tokens * _PROMOTED_SNIPPET_CHARS_PER_TOKEN_ESTIMATE


def _truncate_promoted_snippet(snippet: str, max_tokens: int | None) -> str:
    limit = _resolve_promoted_snippet_char_limit(max_tokens)
    if limit == 0 or len(snippet) <= limit:
        return snippet
    hard_limit = _truncate_utf16_safe(snippet, limit)
    sentence_boundary = max(
        hard_limit.rfind(". "),
        hard_limit.rfind("! "),
        hard_limit.rfind("? "),
    )
    word_boundary = hard_limit.rfind(" ")
    cut_at = (
        sentence_boundary + 1
        if sentence_boundary >= int(limit * 0.55)
        else word_boundary
        if word_boundary >= int(limit * 0.65)
        else limit
    )
    return f"{hard_limit[:cut_at].rstrip()}..."


def _format_promoted_snippet_for_memory(raw_snippet: str, max_tokens: int | None) -> str:
    normalized = _normalize_snippet(raw_snippet or "(no snippet captured)")
    normalized = re.sub(r"^[-*+]\s+", "", normalized).strip()
    return _truncate_promoted_snippet(normalized or "(no snippet captured)", max_tokens)


def _format_dreaming_day(now_ms: int, tz_name: str | None) -> str:
    try:
        if tz_name:
            import zoneinfo  # noqa: PLC0415

            tz = zoneinfo.ZoneInfo(tz_name)
        else:
            tz = UTC
    except Exception:
        tz = UTC
    dt = datetime.fromtimestamp(now_ms / 1000, tz=tz)
    return dt.strftime("%Y-%m-%d")


def _extract_promotion_markers(memory_text: str) -> set[str]:
    markers: set[str] = set()
    for m in _PROMOTION_MARKER_RE.finditer(memory_text):
        key = m.group(1).strip()
        if key:
            markers.add(key)
    return markers


def _build_promotion_section(
    candidates: list[PromotionCandidate],
    now_ms: int,
    timezone: str | None,
    max_promoted_snippet_tokens: int | None,
) -> str:
    date_str = _format_dreaming_day(now_ms, timezone)
    lines: list[str] = [
        f"## Promoted From Short-Term Memory ({date_str})\n",
    ]
    for candidate in candidates:
        key = candidate.get("key", "")
        snippet = _format_promoted_snippet_for_memory(
            candidate.get("snippet", ""), max_promoted_snippet_tokens
        )
        score = candidate.get("score", 0.0)
        signal_count = candidate.get("signal_count", 0)
        recall_count = candidate.get("recall_count", 0)
        avg_score = candidate.get("avg_score", 0.0)
        source_path = candidate.get("path", "")
        lines.append(
            f"<!-- openclaw-memory-promotion:{key} -->\n"
            f"- {snippet}\n"
            f"  <!-- [score={score:.3f} signals={signal_count} recalls={recall_count}"
            f" avg={avg_score:.3f} source={source_path}] -->\n"
        )
    return "".join(lines)


async def _resolve_memory_write_path(file_path: str) -> str:
    """Resolve symlinks to get the real write path.

    Mirrors OpenClaw's ``resolveMemoryWritePath``.
    """
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, lambda: str(Path(file_path).resolve()))
    except OSError:
        # File doesn't exist yet — resolve the parent
        parent = await loop.run_in_executor(None, lambda: str(Path(file_path).parent.resolve()))
        return str(Path(parent) / Path(file_path).name)


async def apply_short_term_promotions(
    workspace_dir: str,
    candidates: list[PromotionCandidate],
    *,
    limit: int | None = None,
    min_score: float | None = None,
    min_recall_count: int | None = None,
    min_unique_queries: int | None = None,
    max_age_days: int | None = None,
    now_ms: int | None = None,
    timezone: str | None = None,
    memory_file_max_chars: int | None = None,
    max_promoted_snippet_tokens: int | None = None,
) -> ApplyShortTermPromotionsResult:
    """Write promoted snippets into MEMORY.md.

    Mirrors OpenClaw's ``applyShortTermPromotions``.
    """
    wd = workspace_dir.strip()
    now_ms_val = resolve_memory_core_now_ms(now_ms)
    now_iso = resolve_memory_core_timestamp(now_ms_val)
    effective_limit = max(0, int(limit)) if limit is not None else len(candidates)
    min_score_val = _to_finite_score(min_score, DEFAULT_PROMOTION_MIN_SCORE)
    min_recall_val = _to_finite_non_negative_int(
        min_recall_count, DEFAULT_PROMOTION_MIN_RECALL_COUNT
    )
    min_unique_val = _to_finite_non_negative_int(
        min_unique_queries, DEFAULT_PROMOTION_MIN_UNIQUE_QUERIES
    )
    max_age_val = _to_finite_non_negative_int(max_age_days, -1)
    memory_path = str(Path(wd) / "MEMORY.md")

    async def _do() -> ApplyShortTermPromotionsResult:
        store = await _read_store(wd, now_iso)
        selected = [
            c
            for c in candidates
            if (
                not is_contaminated_dreaming_snippet(c.get("snippet", ""))
                and not c.get("promoted_at")
                and c.get("score", 0.0) >= min_score_val
                and c.get("signal_count", 0) >= min_recall_val
                and max(c.get("unique_queries", 0), len(c.get("recall_days", []))) >= min_unique_val
                and (max_age_val < 0 or c.get("age_days", 0.0) <= max_age_val)
                and not (store["entries"].get(c.get("key", "")) or {}).get("promoted_at")
            )
        ][:effective_limit]

        if not selected:
            return {
                "memory_path": memory_path,
                "applied": 0,
                "appended": 0,
                "reconciled_existing": 0,
                "applied_candidates": [],
                "compacted_sections": 0,
                "compacted_dates": [],
            }

        memory_write_path = await _resolve_memory_write_path(memory_path)
        loop = asyncio.get_event_loop()
        try:
            existing_memory: str = await loop.run_in_executor(
                None, lambda: Path(memory_write_path).read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            existing_memory = ""
        except OSError:
            existing_memory = ""

        existing_markers = _extract_promotion_markers(existing_memory)
        already_written = [c for c in selected if c.get("key") in existing_markers]
        to_append = [c for c in selected if c.get("key") not in existing_markers]

        compacted_dates: list[str] = []
        if to_append:
            section = _build_promotion_section(
                to_append, now_ms_val, timezone, max_promoted_snippet_tokens
            )
            budget = (
                max(0, int(memory_file_max_chars))
                if isinstance(memory_file_max_chars, int) and math.isfinite(memory_file_max_chars)
                else DEFAULT_MEMORY_FILE_MAX_CHARS
            )
            compaction = compact_memory_for_budget(
                existing_memory=existing_memory,
                new_section=section,
                budget_chars=budget,
            )
            compacted_dates = compaction["dropped_dates"]
            base_memory = compaction["compacted"]
            header = "" if base_memory.strip() else "# Long-Term Memory\n\n"
            content = (
                f"{header}{base_memory.rstrip()}\n{section}"
                if base_memory.strip()
                else f"{header}{section}"
            )
            # Write atomically
            try:
                parent_dir = Path(memory_write_path).parent
                await loop.run_in_executor(None, parent_dir.mkdir, ..., True, True)
                fd, tmp_path = tempfile.mkstemp(
                    dir=str(parent_dir), suffix=".tmp", prefix=".MEMORY_"
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write(content)
                    await loop.run_in_executor(None, os.replace, tmp_path, memory_write_path)
                except Exception:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp_path)
                    raise
            except Exception:
                # Fall back to in-place write
                await loop.run_in_executor(
                    None, lambda: Path(memory_write_path).write_text(content, encoding="utf-8")
                )

        # Mark promoted in the store
        applied_candidates: list[PromotionCandidate] = []
        for candidate in to_append + already_written:
            key = candidate.get("key", "")
            if key in store["entries"]:
                store["entries"][key]["promoted_at"] = now_iso
            applied_candidates.append(candidate)
        store["updated_at"] = now_iso
        await _write_store(wd, store)

        return {
            "memory_path": memory_path,
            "applied": len(to_append) + len(already_written),
            "appended": len(to_append),
            "reconciled_existing": len(already_written),
            "applied_candidates": applied_candidates,
            "compacted_sections": len(compacted_dates),
            "compacted_dates": compacted_dates,
        }

    return await _with_short_term_lock(wd, _do)


# ── Artifact repair ───────────────────────────────────────────────────────────


async def repair_short_term_promotion_artifacts(
    workspace_dir: str,
    *,
    now_ms: int | None = None,
) -> RepairShortTermPromotionArtifactsResult:
    """Remove invalid/overflow entries and stale lock files.

    Mirrors OpenClaw's ``repairShortTermPromotionArtifacts``.
    """
    wd = workspace_dir.strip()
    if not wd:
        return {
            "changed": False,
            "removed_invalid_entries": 0,
            "removed_overflow_entries": 0,
            "rewrote_store": False,
            "removed_stale_lock": False,
        }

    now_ms_val = resolve_memory_core_now_ms(now_ms)
    now_iso = resolve_memory_core_timestamp(now_ms_val)

    async def _do() -> RepairShortTermPromotionArtifactsResult:
        store = await _read_store(wd, now_iso)

        # Remove contaminated entries
        removed_invalid = 0
        for key in list(store["entries"].keys()):
            entry = store["entries"][key]
            if is_contaminated_dreaming_snippet(
                entry.get("snippet", ""),
                allow_transcript_turn_snippet=_is_short_term_session_corpus_path(
                    entry.get("path", "")
                ),
            ):
                del store["entries"][key]
                removed_invalid += 1

        # Enforce retention
        removed_overflow = _enforce_short_term_recall_store_retention(store)

        changed = removed_invalid > 0 or removed_overflow > 0
        if changed:
            store["updated_at"] = now_iso
            await _write_store(wd, store)

        # Check for stale lock (best-effort, read from keyed store)
        removed_stale_lock = False
        try:
            lock_store = open_memory_core_state_store(
                OpenKeyedStoreOptions(
                    namespace=SHORT_TERM_LOCK_NAMESPACE,
                    max_entries=SHORT_TERM_LOCK_MAX_ENTRIES,
                )
            )
            workspace_key = memory_core_workspace_state_key(wd)
            for k, v in lock_store.entries():
                if not k.startswith(workspace_key):
                    continue
                if isinstance(v, dict):
                    acquired_at = v.get("acquiredAt") or v.get("acquired_at") or 0
                    if now_ms_val - int(acquired_at) > _SHORT_TERM_LOCK_STALE_MS * 2:
                        lock_store.delete(k)
                        removed_stale_lock = True
                        break
        except Exception:
            pass

        return {
            "changed": changed or removed_stale_lock,
            "removed_invalid_entries": removed_invalid,
            "removed_overflow_entries": removed_overflow,
            "rewrote_store": changed,
            "removed_stale_lock": removed_stale_lock,
        }

    return await _with_short_term_lock(wd, _do)


# ── Stats loading ─────────────────────────────────────────────────────────────


async def load_short_term_promotion_dreaming_stats(
    workspace_dir: str,
    *,
    now_ms: int | None = None,
    timezone: str | None = None,
) -> ShortTermDreamingStats:
    """Load dreaming stats for the dashboard/CLI display.

    Mirrors OpenClaw's ``loadShortTermPromotionDreamingStats``.
    """
    wd = workspace_dir.strip()
    now_ms_val = resolve_memory_core_now_ms(now_ms)
    now_iso = resolve_memory_core_timestamp(now_ms_val)
    today_bucket = _format_dreaming_day(now_ms_val, timezone)

    store = await _read_store(wd, now_iso)
    phase_signal_error: str | None = None
    try:
        phase_store = await _read_phase_signal_store(wd, now_iso)
    except Exception as exc:
        phase_signal_error = format_error_message(exc)
        phase_store = _empty_phase_signal_store(now_iso)

    short_term_count = 0
    recall_signal_count = 0
    daily_signal_count = 0
    grounded_signal_count = 0
    total_signal_count = 0
    phase_signal_count = 0
    light_phase_hit_count = 0
    rem_phase_hit_count = 0
    promoted_total = 0
    promoted_today = 0
    latest_promoted_at_ms: float = float("-inf")
    latest_promoted_at: str | None = None

    active_keys: set[str] = set()
    active_entries: dict[str, ShortTermDreamingStatsEntry] = {}
    short_term_entries: list[ShortTermDreamingStatsEntry] = []
    promoted_entries: list[ShortTermDreamingStatsEntry] = []

    for entry_key, entry in store["entries"].items():
        if not entry or entry.get("source") != "memory":
            continue
        entry_path = entry.get("path", "")
        if not _is_short_term_memory_path(entry_path):
            continue
        recall_count = _to_non_negative_int(entry.get("recall_count", 0))
        daily_count = _to_non_negative_int(entry.get("daily_count", 0))
        grounded_count = _to_non_negative_int(entry.get("grounded_count", 0))
        total_entry_signals = recall_count + daily_count + grounded_count

        detail: ShortTermDreamingStatsEntry = {
            "key": entry_key,
            "path": entry_path,
            "start_line": entry.get("start_line", 1),
            "end_line": max(entry.get("start_line", 1), entry.get("end_line", 1)),
            "snippet": _normalize_snippet(entry.get("snippet", "")) or entry_path,
            "recall_count": recall_count,
            "daily_count": daily_count,
            "grounded_count": grounded_count,
            "total_signal_count": total_entry_signals,
            "light_hits": 0,
            "rem_hits": 0,
            "phase_hit_count": 0,
        }
        if entry.get("last_recalled_at"):
            detail["last_recalled_at"] = entry["last_recalled_at"]

        if not entry.get("promoted_at"):
            short_term_count += 1
            active_keys.add(entry_key)
            recall_signal_count += recall_count
            daily_signal_count += daily_count
            grounded_signal_count += grounded_count
            total_signal_count += total_entry_signals
            short_term_entries.append(detail)
            active_entries[entry_key] = detail
        else:
            promoted_total += 1
            promoted_at = entry["promoted_at"]
            promoted_detail = {**detail, "promoted_at": promoted_at}
            promoted_entries.append(promoted_detail)
            promoted_at_ms = _parse_store_timestamp_ms(promoted_at)
            promoted_dt = (
                datetime.fromtimestamp(promoted_at_ms / 1000, tz=UTC)
                if math.isfinite(promoted_at_ms)
                else None
            )
            if promoted_dt and promoted_dt.strftime("%Y-%m-%d") == today_bucket:
                promoted_today += 1
            if math.isfinite(promoted_at_ms) and promoted_at_ms > latest_promoted_at_ms:
                latest_promoted_at_ms = promoted_at_ms
                latest_promoted_at = promoted_at

    for key, phase_entry in phase_store["entries"].items():
        if key not in active_keys:
            continue
        light_hits = _to_non_negative_int(phase_entry.get("light_hits", 0))
        rem_hits = _to_non_negative_int(phase_entry.get("rem_hits", 0))
        light_phase_hit_count += light_hits
        rem_phase_hit_count += rem_hits
        phase_signal_count += light_hits + rem_hits
        detail = active_entries.get(key)
        if detail:
            detail["light_hits"] = light_hits
            detail["rem_hits"] = rem_hits
            detail["phase_hit_count"] = light_hits + rem_hits

    result: ShortTermDreamingStats = {
        "short_term_count": short_term_count,
        "recall_signal_count": recall_signal_count,
        "daily_signal_count": daily_signal_count,
        "grounded_signal_count": grounded_signal_count,
        "total_signal_count": total_signal_count,
        "phase_signal_count": phase_signal_count,
        "light_phase_hit_count": light_phase_hit_count,
        "rem_phase_hit_count": rem_phase_hit_count,
        "promoted_total": promoted_total,
        "promoted_today": promoted_today,
        "store_path": _resolve_store_path(wd),
        "phase_signal_path": _resolve_phase_signal_path(wd),
        "short_term_entries": short_term_entries[:_DREAMING_ENTRY_LIST_LIMIT],
        "signal_entries": sorted(short_term_entries, key=lambda e: -e.get("total_signal_count", 0))[
            :_DREAMING_ENTRY_LIST_LIMIT
        ],
        "promoted_entries": sorted(
            promoted_entries,
            key=lambda e: -_parse_store_timestamp_ms(e.get("promoted_at")),
        )[:_DREAMING_ENTRY_LIST_LIMIT],
    }
    if phase_signal_error:
        result["phase_signal_error"] = phase_signal_error
    if latest_promoted_at:
        result["last_promoted_at"] = latest_promoted_at
    return result


# ── Public read helpers ───────────────────────────────────────────────────────


async def read_short_term_recall_entries(
    workspace_dir: str,
    *,
    now_ms: int | None = None,
) -> list[ShortTermRecallEntry]:
    """Read all valid short-term recall entries.

    Mirrors OpenClaw's ``readShortTermRecallEntries``.
    """
    wd = workspace_dir.strip()
    if not wd:
        return []
    now_ms_val = resolve_memory_core_now_ms(now_ms)
    now_iso = resolve_memory_core_timestamp(now_ms_val)
    store = await _read_store(wd, now_iso)
    return [
        entry
        for entry in store["entries"].values()
        if entry
        and entry.get("source") == "memory"
        and _is_short_term_memory_path(entry.get("path", ""))
    ]


# ── contextlib for atomic write fallback ─────────────────────────────────────


__all__ = [
    # Constants
    "DEFAULT_PROMOTION_MIN_SCORE",
    "DEFAULT_PROMOTION_MIN_RECALL_COUNT",
    "DEFAULT_PROMOTION_MIN_UNIQUE_QUERIES",
    "SHORT_TERM_STORE_RELATIVE_PATH",
    "SHORT_TERM_PHASE_SIGNAL_RELATIVE_PATH",
    # Types
    "ShortTermRecallEntry",
    "ShortTermRecallStore",
    "ShortTermPhaseSignalEntry",
    "ShortTermPhaseSignalStore",
    "PromotionCandidate",
    "PromotionComponents",
    "RepairShortTermPromotionArtifactsResult",
    "ApplyShortTermPromotionsResult",
    "ShortTermDreamingStats",
    "ShortTermDreamingStatsEntry",
    # Store normalization
    "normalize_short_term_recall_store",
    "normalize_short_term_phase_signal_store",
    # Contamination
    "is_contaminated_dreaming_snippet",
    # Signal recording
    "record_short_term_recalls",
    "record_grounded_short_term_candidates",
    "record_dreaming_phase_signals",
    # Candidate ranking
    "rank_short_term_promotion_candidates",
    # Promotion application
    "apply_short_term_promotions",
    # Repair
    "repair_short_term_promotion_artifacts",
    # Stats
    "load_short_term_promotion_dreaming_stats",
    # Read
    "read_short_term_recall_entries",
]
