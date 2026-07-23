"""Tests for memory_core.dreaming_phases — Phase 4.4h.

Mirrors the TypeScript ``test_dreaming-phases.test.ts`` patterns.
The LLM orchestrators are stubbed; we test the deterministic building
blocks (lookback filter, snippet extraction, dedupe, diary coverage,
ingestion state normalizers, session ingestion helpers).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from extensions.memory_core import dreaming_phases as dp


# ── Constants ──────────────────────────────────────────────────────────


def test_constants_present() -> None:
    """All exported constants are present and have expected types."""
    assert dp.DAILY_INGESTION_STATE_RELATIVE_PATH.endswith("daily-ingestion.json")
    assert dp.SESSION_INGESTION_STATE_RELATIVE_PATH.endswith("session-ingestion.json")
    assert dp.DAILY_INGESTION_SCORE == 0.62
    assert dp.SESSION_INGESTION_SCORE == 0.58
    assert dp.DAILY_INGESTION_MAX_SNIPPET_CHARS == 280
    assert dp.SESSION_INGESTION_MAX_TRACKED_MESSAGES_PER_SESSION == 4096
    assert dp.LIGHT_DIARY_SNIPPET_SIMILARITY_THRESHOLD == 0.35


# ── Lookback helpers ──────────────────────────────────────────────────


def test_calculate_lookback_cutoff_ms() -> None:
    """Cutoff = now - days * 86400_000."""
    now = 1_700_000_000_000
    assert dp._calculate_lookback_cutoff_ms(now, 0) == now
    assert dp._calculate_lookback_cutoff_ms(now, 1) == now - 86_400_000
    assert dp._calculate_lookback_cutoff_ms(now, 7) == now - 7 * 86_400_000
    # Negative days clamped to 0
    assert dp._calculate_lookback_cutoff_ms(now, -5) == now


def test_is_day_within_lookback_valid() -> None:
    """Days on or after the cutoff return ``True``."""
    # cutoff = 2023-11-14T22:13:20Z
    cutoff = 1_700_000_000_000
    # 2023-11-15T23:59:59.999Z is later than the cutoff → within lookback
    assert dp._is_day_within_lookback("2023-11-15", cutoff) is True
    # 2023-11-13T23:59:59.999Z is earlier than the cutoff → not within
    assert dp._is_day_within_lookback("2023-11-13", cutoff) is False


def test_is_day_within_lookback_invalid() -> None:
    """Invalid date strings return ``False``."""
    assert dp._is_day_within_lookback("not-a-date", 0) is False
    assert dp._is_day_within_lookback("", 0) is False


def test_entry_within_lookback_uses_recall_days() -> None:
    """``recallDays`` controls inclusion when present."""
    entry: dp.ShortTermRecallEntry = {
        "key": "k",
        "snippet": "s",
        "lastRecalledAt": "2020-01-01T00:00:00Z",
        "recallDays": ["2023-11-15"],
    }
    # Recent day, old lastRecalledAt → still included
    assert dp._entry_within_lookback(entry, 1_700_000_000_000) is True


def test_entry_within_lookback_falls_back_to_last_recalled() -> None:
    """``lastRecalledAt`` is the fallback when ``recallDays`` is empty."""
    entry: dp.ShortTermRecallEntry = {
        "key": "k",
        "snippet": "s",
        "lastRecalledAt": "2023-11-15T12:00:00Z",
        "recallDays": [],
    }
    # 2023-11-15 is on or after cutoff 2023-11-15
    assert dp._entry_within_lookback(entry, 1_700_000_000_000) is True


def test_entry_within_lookback_outside_window() -> None:
    """Entry outside the window returns ``False``."""
    entry: dp.ShortTermRecallEntry = {
        "key": "k",
        "snippet": "s",
        "lastRecalledAt": "2020-01-01T00:00:00Z",
        "recallDays": [],
    }
    assert dp._entry_within_lookback(entry, 1_700_000_000_000) is False


def test_filter_recall_entries_within_lookback_mixed() -> None:
    """Returns only entries within the lookback window."""
    entries: list[dp.ShortTermRecallEntry] = [
        {
            "key": "k1",
            "snippet": "s1",
            "lastRecalledAt": "2023-11-15T00:00:00Z",
            "recallDays": [],
        },
        {
            "key": "k2",
            "snippet": "s2",
            "lastRecalledAt": "2020-01-01T00:00:00Z",
            "recallDays": [],
        },
    ]
    # Use a cutoff that includes 2023-11-15 but excludes 2020-01-01
    cutoff = int(
        datetime(2023, 11, 14, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
    )
    result = dp.filter_recall_entries_within_lookback(entries, now_ms=cutoff + 86_400_000, lookback_days=1)
    assert len(result) == 1
    assert result[0]["key"] == "k1"


# ── Daily snippet extraction ──────────────────────────────────────────


def test_normalize_daily_list_marker() -> None:
    """Strip ``- `` / ``* `` / ``+ `` / ``1. `` markers."""
    assert dp._normalize_daily_list_marker("- hello") == "hello"
    assert dp._normalize_daily_list_marker("* hello") == "hello"
    assert dp._normalize_daily_list_marker("+ hello") == "hello"
    assert dp._normalize_daily_list_marker("1. hello") == "hello"
    assert dp._normalize_daily_list_marker("hello") == "hello"


def test_is_generic_daily_heading_short_labels() -> None:
    """``Today`` / ``Yesterday`` / ``Morning`` etc. are generic."""
    assert dp._is_generic_daily_heading("Today") is True
    assert dp._is_generic_daily_heading("Yesterday") is True
    assert dp._is_generic_daily_heading("morning") is True
    assert dp._is_generic_daily_heading("evening") is True
    assert dp._is_generic_daily_heading("") is True


def test_is_generic_daily_heading_dates() -> None:
    """Date strings are generic."""
    assert dp._is_generic_daily_heading("December 15") is True
    assert dp._is_generic_daily_heading("12/15/2025") is True
    assert dp._is_generic_daily_heading("2025-12-15") is True


def test_is_generic_daily_heading_specific() -> None:
    """Specific section names are not generic."""
    assert dp._is_generic_daily_heading("Project Status") is False
    assert dp._is_generic_daily_heading("Meeting Notes") is False


def test_normalize_daily_heading_valid() -> None:
    """Headings (1-6 ``#``) are extracted and truncated."""
    assert dp._normalize_daily_heading("# Project Status") == "Project Status"
    assert dp._normalize_daily_heading("## Sub Section") == "Sub Section"


def test_normalize_daily_heading_invalid() -> None:
    """Non-headings / generic headings return ``None``."""
    assert dp._normalize_daily_heading("not a heading") is None
    assert dp._normalize_daily_heading("# 2025-12-15") is None  # daily file name
    assert dp._normalize_daily_heading("# Today") is None  # generic
    assert dp._normalize_daily_heading("") is None


def test_normalize_daily_snippet_basic() -> None:
    """Trims + strips list markers."""
    assert dp._normalize_daily_snippet("- hello world") == "hello world"
    assert dp._normalize_daily_snippet("* a longer snippet") == "a longer snippet"


def test_normalize_daily_snippet_rejects_short() -> None:
    """Snippets below the min length are rejected."""
    assert dp._normalize_daily_snippet("hi") is None  # < 8 chars
    assert dp._normalize_daily_snippet("") is None
    assert dp._normalize_daily_snippet("   ") is None


def test_normalize_daily_snippet_rejects_headings() -> None:
    """Heading lines are rejected."""
    assert dp._normalize_daily_snippet("# heading") is None


def test_build_daily_chunk_snippet_list() -> None:
    """List chunks are joined with ``"; "``."""
    result = dp._build_daily_chunk_snippet(None, ["a", "b", "c"], "list")
    assert result == "a; b; c"


def test_build_daily_chunk_snippet_paragraph() -> None:
    """Paragraph chunks are joined with ``" "``."""
    result = dp._build_daily_chunk_snippet(None, ["a", "b", "c"], "paragraph")
    assert result == "a b c"


def test_build_daily_chunk_snippet_with_heading() -> None:
    """A heading is prefixed with ``": "``."""
    result = dp._build_daily_chunk_snippet("Section", ["a", "b"], "list")
    assert result == "Section: a; b"


def test_build_daily_snippet_chunks_basic() -> None:
    """Walk lines + build chunks."""
    lines = [
        "# Top",
        "",
        "first snippet line one",
        "first snippet line two",
        "",
        "second snippet paragraph",
    ]
    chunks = dp.build_daily_snippet_chunks(lines, limit=10)
    assert len(chunks) >= 1
    # All chunks have a snippet
    for chunk in chunks:
        assert "snippet" in chunk
        assert len(chunk["snippet"]) >= dp.DAILY_INGESTION_MIN_SNIPPET_CHARS


def test_build_daily_snippet_chunks_respects_limit() -> None:
    """At most ``limit`` chunks are returned."""
    lines = [f"line number {i} with enough chars" for i in range(20)]
    chunks = dp.build_daily_snippet_chunks(lines, limit=3)
    assert len(chunks) == 3


def test_build_daily_snippet_chunks_strips_managed_block_lines() -> None:
    """``_strip_managed_daily_dreaming_lines`` removes managed blocks; chunks then build from the sanitized lines."""
    lines = [
        "before content",
        "## Light Sleep",
        "<!-- openclaw:dreaming:light:start -->",
        "this is a managed block entry",
        "<!-- openclaw:dreaming:light:end -->",
        "real content line one",
        "real content line two",
    ]
    sanitized = dp._strip_managed_daily_dreaming_lines(lines)
    chunks = dp.build_daily_snippet_chunks(sanitized, limit=10)
    snippets = [c["snippet"] for c in chunks]
    # Real content appears; managed block content does not
    assert any("real content" in s for s in snippets)
    assert not any("managed block" in s for s in snippets)


# ── Daily memory file helpers ─────────────────────────────────────────


def test_parse_daily_memory_file_name_canonical() -> None:
    """``2025-12-15.md`` is canonical."""
    result = dp._parse_daily_memory_file_name("2025-12-15.md")
    assert result is not None
    assert result["day"] == "2025-12-15"
    assert result["canonical"] is True


def test_parse_daily_memory_file_name_with_slug() -> None:
    """``2025-12-15-some-slug.md`` is parsed but not canonical."""
    result = dp._parse_daily_memory_file_name("2025-12-15-extra.md")
    assert result is not None
    assert result["day"] == "2025-12-15"
    assert result["canonical"] is False


def test_parse_daily_memory_file_name_invalid() -> None:
    """Non-matching names return ``None``."""
    assert dp._parse_daily_memory_file_name("not-a-date.md") is None
    assert dp._parse_daily_memory_file_name("2025-12-15.txt") is None
    assert dp._parse_daily_memory_file_name("") is None


def test_compare_daily_memory_files_by_newest_day() -> None:
    """Sorts newest day first; canonical first within same day."""
    a: dp.DailyMemoryFile = {"fileName": "2025-12-14.md", "day": "2025-12-14", "canonical": True}
    b: dp.DailyMemoryFile = {"fileName": "2025-12-15.md", "day": "2025-12-15", "canonical": True}
    c: dp.DailyMemoryFile = {
        "fileName": "2025-12-15-extra.md",
        "day": "2025-12-15",
        "canonical": False,
    }
    assert dp._compare_daily_memory_files_by_newest_day(b, a) < 0  # b is newer
    assert dp._compare_daily_memory_files_by_newest_day(a, b) > 0
    assert dp._compare_daily_memory_files_by_newest_day(b, c) < 0  # canonical first


# ── Managed block stripping ──────────────────────────────────────────


def test_strip_managed_daily_dreaming_lines_light() -> None:
    """Light block is stripped; surrounding content preserved."""
    lines = [
        "before content",
        "## Light Sleep",
        "<!-- openclaw:dreaming:light:start -->",
        "managed content 1",
        "managed content 2",
        "<!-- openclaw:dreaming:light:end -->",
        "after content",
    ]
    result = dp._strip_managed_daily_dreaming_lines(lines)
    assert "before content" in result
    assert "after content" in result
    assert "managed content 1" not in result
    assert "managed content 2" not in result


def test_strip_managed_daily_dreaming_lines_rem() -> None:
    """REM block is also stripped."""
    lines = [
        "before",
        "## REM Sleep",
        "<!-- openclaw:dreaming:rem:start -->",
        "rem content",
        "<!-- openclaw:dreaming:rem:end -->",
        "after",
    ]
    result = dp._strip_managed_daily_dreaming_lines(lines)
    assert "rem content" not in result
    assert "before" in result
    assert "after" in result


def test_strip_managed_daily_dreaming_lines_no_blocks() -> None:
    """No managed blocks → input returned as-is."""
    lines = ["plain content", "more plain"]
    result = dp._strip_managed_daily_dreaming_lines(lines)
    assert result == ["plain content", "more plain"]


# ── Dedupe (Jaccard) ─────────────────────────────────────────────────


def test_text_similarity_jaccard_identical() -> None:
    """Identical strings have similarity 1.0."""
    assert dp._text_similarity_jaccard("hello world", "hello world") == 1.0


def test_text_similarity_jaccard_disjoint() -> None:
    """Disjoint strings have similarity 0.0."""
    assert dp._text_similarity_jaccard("alpha beta", "gamma delta") == 0.0


def test_text_similarity_jaccard_partial() -> None:
    """Partial overlap yields intermediate value."""
    sim = dp._text_similarity_jaccard("a b c", "a b d")
    # Intersection: {a, b} = 2; Union: {a, b, c, d} = 4
    assert sim == 0.5


def test_text_similarity_jaccard_empty() -> None:
    """Empty strings return 0.0."""
    assert dp._text_similarity_jaccard("", "hello") == 0.0
    assert dp._text_similarity_jaccard("hello", "") == 0.0


def test_dedupe_entries_removes_duplicates() -> None:
    """Near-duplicate entries are removed."""
    entries: list[dp.ShortTermRecallEntry] = [
        {"key": "a", "snippet": "the cat sat on the mat"},
        {"key": "b", "snippet": "the cat sat on the mat"},  # duplicate
        {"key": "c", "snippet": "completely different content here"},
    ]
    result = dp.dedupe_entries(entries, threshold=0.9)
    assert len(result) == 2
    assert result[0]["key"] == "a"
    assert result[1]["key"] == "c"


def test_dedupe_entries_keeps_unique() -> None:
    """Distinct entries are kept (similarity below threshold)."""
    entries: list[dp.ShortTermRecallEntry] = [
        {"key": "a", "snippet": "alpha bravo charlie delta echo"},
        {"key": "b", "snippet": "foxtrot golf hotel india juliet"},
    ]
    result = dp.dedupe_entries(entries, threshold=0.9)
    assert len(result) == 2


def test_dedupe_entries_threshold_zero() -> None:
    """Threshold 0.0 → only exact duplicates removed."""
    entries: list[dp.ShortTermRecallEntry] = [
        {"key": "a", "snippet": "hello"},
        {"key": "b", "snippet": "hello world"},
    ]
    # 0.0 threshold: Jaccard of "hello" vs "hello world" = 1/2 = 0.5 > 0.0
    # Wait, threshold means "if similarity >= threshold, drop". So 0.0
    # means even tiny overlap is "duplicate" → b is dropped.
    result = dp.dedupe_entries(entries, threshold=0.0)
    assert len(result) == 1


# ── Diary coverage ───────────────────────────────────────────────────


def test_normalize_diary_coverage_text() -> None:
    """Strips non-alphanumerics + lowercases + collapses whitespace."""
    assert dp.normalize_diary_coverage_text("Hello, World!") == "hello world"
    assert dp.normalize_diary_coverage_text("  Multiple   Spaces  ") == "multiple spaces"
    assert dp.normalize_diary_coverage_text("") == ""


def test_is_entry_covered_by_recent_diary_match() -> None:
    """An entry similar to a recent diary entry returns ``True``."""
    covered = dp.is_entry_covered_by_recent_diary(
        "the cat sat on the mat",
        ["the cat sat on the mat today"],
    )
    assert covered is True


def test_is_entry_covered_by_recent_diary_no_match() -> None:
    """A clearly different entry returns ``False``."""
    covered = dp.is_entry_covered_by_recent_diary(
        "completely unique content here",
        ["totally different diary entry"],
    )
    assert covered is False


def test_is_entry_covered_by_recent_diary_empty() -> None:
    """Empty inputs return ``False``."""
    assert dp.is_entry_covered_by_recent_diary("", ["something"]) is False
    assert dp.is_entry_covered_by_recent_diary("hello", []) is False


def test_prioritize_light_entries_by_diary_coverage() -> None:
    """Uncovered entries come first; covered entries last."""
    entries: list[dp.ShortTermRecallEntry] = [
        {"key": "covered", "snippet": "the cat sat on the mat"},
        {"key": "uncovered", "snippet": "completely unique and different content here"},
    ]
    recent = ["the cat sat on the mat in the dream diary"]
    result = dp.prioritize_light_entries_by_diary_coverage(entries, recent)
    assert result[0]["key"] == "uncovered"
    assert result[1]["key"] == "covered"


# ── Ingestion state normalizers ──────────────────────────────────────


def test_normalize_daily_ingestion_state_valid() -> None:
    """Valid input is preserved."""
    raw = {
        "version": 1,
        "files": {
            "memory/2025-12-15.md": {
                "mtimeMs": 12345.6,
                "size": 1024,
                "lastDreamingDayIngested": "2025-12-15",
            }
        },
    }
    result = dp.normalize_daily_ingestion_state(raw)
    assert result["version"] == 1
    assert "memory/2025-12-15.md" in result["files"]
    file_state = result["files"]["memory/2025-12-15.md"]
    assert file_state["mtimeMs"] == 12345
    assert file_state["size"] == 1024
    assert file_state["lastDreamingDayIngested"] == "2025-12-15"


def test_normalize_daily_ingestion_state_drops_invalid() -> None:
    """Files with negative or non-numeric mtime/size are dropped."""
    raw = {
        "files": {
            "ok.md": {"mtimeMs": 1.0, "size": 1},
            "bad-mtime.md": {"mtimeMs": -1, "size": 1},
            "bad-size.md": {"mtimeMs": 1, "size": "x"},
            "empty-key.md": {"mtimeMs": 1, "size": 1},  # valid; key tested below
        }
    }
    result = dp.normalize_daily_ingestion_state(raw)
    assert "ok.md" in result["files"]
    assert "bad-mtime.md" not in result["files"]
    assert "bad-size.md" not in result["files"]


def test_normalize_daily_ingestion_state_empty() -> None:
    """Empty / invalid input returns a fresh shell."""
    assert dp.normalize_daily_ingestion_state({}) == {"version": 1, "files": {}}
    assert dp.normalize_daily_ingestion_state(None) == {"version": 1, "files": {}}
    assert dp.normalize_daily_ingestion_state("not a dict") == {"version": 1, "files": {}}


def test_normalize_daily_ingestion_state_rejects_invalid_day() -> None:
    """``lastDreamingDayIngested`` that isn't a YYYY-MM-DD is dropped."""
    raw = {
        "files": {
            "a.md": {
                "mtimeMs": 1,
                "size": 1,
                "lastDreamingDayIngested": "not-a-date",
            }
        }
    }
    result = dp.normalize_daily_ingestion_state(raw)
    assert "lastDreamingDayIngested" not in result["files"]["a.md"]


def test_normalize_session_ingestion_state_valid() -> None:
    """Valid input is preserved; version forced to 3."""
    raw = {
        "version": 3,
        "files": {
            "session1": {
                "mtimeMs": 1000.0,
                "size": 2000.0,
                "contentHash": "abc",
                "lineCount": 100,
                "lastContentLine": 50,
            }
        },
        "seenMessages": {
            "scope1": ["h1", "h2", "h1"],  # duplicate "h1" is deduped
        },
    }
    result = dp.normalize_session_ingestion_state(raw)
    assert result["version"] == 3
    assert "session1" in result["files"]
    assert result["seenMessages"]["scope1"] == ["h1", "h2"]


def test_normalize_session_ingestion_state_empty() -> None:
    """Empty / invalid input returns a fresh shell."""
    result = dp.normalize_session_ingestion_state({})
    assert result["version"] == 3
    assert result["files"] == {}
    assert result["seenMessages"] == {}


def test_normalize_session_ingestion_state_caps_seen_messages() -> None:
    """Seen message lists are capped to the per-session max."""
    # Generate a long list of unique hashes
    raw = {
        "files": {},
        "seenMessages": {
            "scope": [f"hash-{i}" for i in range(dp.SESSION_INGESTION_MAX_TRACKED_MESSAGES_PER_SESSION + 100)]
        },
    }
    result = dp.normalize_session_ingestion_state(raw)
    assert len(result["seenMessages"]["scope"]) == dp.SESSION_INGESTION_MAX_TRACKED_MESSAGES_PER_SESSION


def test_normalize_session_ingestion_state_drops_invalid_files() -> None:
    """Files with negative mtime/size are dropped."""
    raw = {
        "files": {
            "ok": {"mtimeMs": 1.0, "size": 1.0, "contentHash": "h", "lineCount": 1, "lastContentLine": 1},
            "bad": {"mtimeMs": -1, "size": 1.0, "contentHash": "h", "lineCount": 1, "lastContentLine": 1},
        },
        "seenMessages": {},
    }
    result = dp.normalize_session_ingestion_state(raw)
    assert "ok" in result["files"]
    assert "bad" not in result["files"]


# ── Session ingestion helpers ────────────────────────────────────────


def test_hash_session_message_id_deterministic() -> None:
    """Same input → same SHA-1 hash."""
    a = dp._hash_session_message_id("session-msg-1")
    b = dp._hash_session_message_id("session-msg-1")
    assert a == b
    assert len(a) == 40  # SHA-1 hex


def test_hash_session_message_id_differs_per_value() -> None:
    """Different inputs → different hashes."""
    a = dp._hash_session_message_id("a")
    b = dp._hash_session_message_id("b")
    assert a != b


def test_normalize_session_corpus_snippet() -> None:
    """Trim + collapse + cap."""
    s = "  hello    world  "
    assert dp._normalize_session_corpus_snippet(s) == "hello world"
    long = "x" * (dp.SESSION_INGESTION_MAX_SNIPPET_CHARS + 50)
    result = dp._normalize_session_corpus_snippet(long)
    assert len(result) == dp.SESSION_INGESTION_MAX_SNIPPET_CHARS


def test_merge_tracked_message_hashes_empty_additions() -> None:
    """No additions → existing returned."""
    existing = ["h1", "h2"]
    assert dp._merge_tracked_message_hashes(existing, []) == existing


def test_merge_tracked_message_hashes_appends_unique() -> None:
    """Unique additions are appended."""
    result = dp._merge_tracked_message_hashes(["h1"], ["h2", "h3"])
    assert result == ["h1", "h2", "h3"]


def test_merge_tracked_message_hashes_skips_duplicates() -> None:
    """Duplicate additions are skipped."""
    result = dp._merge_tracked_message_hashes(["h1", "h2"], ["h2", "h3"])
    assert result == ["h1", "h2", "h3"]


def test_merge_tracked_message_hashes_caps() -> None:
    """Result is capped to the per-session max."""
    long_existing = [f"h{i}" for i in range(dp.SESSION_INGESTION_MAX_TRACKED_MESSAGES_PER_SESSION)]
    result = dp._merge_tracked_message_hashes(long_existing, ["new"])
    assert len(result) == dp.SESSION_INGESTION_MAX_TRACKED_MESSAGES_PER_SESSION


def test_trim_tracked_session_scopes_under_limit() -> None:
    """Under the limit → returned as-is."""
    seen = {f"scope-{i}": ["h"] for i in range(10)}
    assert dp._trim_tracked_session_scopes(seen) == seen


def test_trim_tracked_session_scopes_over_limit() -> None:
    """Over the limit → lexicographically last scopes are kept."""
    over_limit = dp.SESSION_INGESTION_MAX_TRACKED_SCOPES + 5
    seen = {f"scope-{i:05d}": ["h"] for i in range(over_limit)}
    result = dp._trim_tracked_session_scopes(seen)
    assert len(result) == dp.SESSION_INGESTION_MAX_TRACKED_SCOPES
    # The highest-sorted scopes are kept
    assert max(result.keys()) == f"scope-{over_limit - 1:05d}"
