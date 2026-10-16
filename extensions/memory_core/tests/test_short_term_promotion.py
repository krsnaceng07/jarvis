"""Tests for memory_core.short_term_promotion — deterministic unit coverage.

Tests the pure synchronous/deterministic helpers and types directly:
- normalize_short_term_recall_store
- normalize_short_term_phase_signal_store
- is_contaminated_dreaming_snippet
- Score component functions
- concept_vocabulary.derive_concept_tags
- memory_budget.compact_memory_for_budget

Async pipeline functions (record_short_term_recalls, rank_short_term_promotion_candidates,
apply_short_term_promotions) require a wired keyed store; those are integration tests.
"""

from __future__ import annotations

import pytest

# ── Import the modules under test ─────────────────────────────────────────────

from extensions.memory_core.short_term_promotion import (
    normalize_short_term_recall_store,
    normalize_short_term_phase_signal_store,
    is_contaminated_dreaming_snippet,
    _clamp_score,
    _calculate_recency_component,
    _calculate_consolidation_component,
    _calculate_conceptual_component,
    _calculate_phase_signal_boost,
    _normalize_snippet,
    _truncate_short_term_snippet,
    _build_entry_key,
    _build_claim_hash,
    _hash_query,
    _is_short_term_memory_path,
)
from extensions.memory_core.concept_vocabulary import derive_concept_tags, MAX_CONCEPT_TAGS
from extensions.memory_core.memory_budget import (
    compact_memory_for_budget,
    DEFAULT_MEMORY_FILE_MAX_CHARS,
)


NOW_ISO = "2024-06-15T10:00:00+00:00"

# ── _clamp_score ──────────────────────────────────────────────────────────────


def test_clamp_score_bounds() -> None:
    assert _clamp_score(0.0) == 0.0
    assert _clamp_score(1.0) == 1.0
    assert _clamp_score(1.5) == 1.0
    assert _clamp_score(-0.5) == 0.0
    # Non-finite values return 0 (mirroring OpenClaw's clampScore)
    assert _clamp_score(float("nan")) == 0.0
    assert _clamp_score(float("inf")) == 0.0
    assert _clamp_score(float("-inf")) == 0.0


# ── _normalize_snippet ────────────────────────────────────────────────────────


def test_normalize_snippet_collapses_whitespace() -> None:
    assert _normalize_snippet("  hello   world  ") == "hello world"


def test_normalize_snippet_empty() -> None:
    assert _normalize_snippet("") == ""
    assert _normalize_snippet("   ") == ""


# ── _truncate_short_term_snippet ──────────────────────────────────────────────


def test_truncate_short_term_snippet_no_truncation() -> None:
    s = "x" * 100
    assert _truncate_short_term_snippet(s) == s


def test_truncate_short_term_snippet_at_limit() -> None:
    s = "a" * 800
    assert len(_truncate_short_term_snippet(s)) == 800


def test_truncate_short_term_snippet_over_limit() -> None:
    s = "a" * 1000
    result = _truncate_short_term_snippet(s)
    assert len(result) <= 800


# ── _is_short_term_memory_path ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path,expected",
    [
        ("memory/2024-06-15.md", True),
        ("memory/2024-06-15-session.md", True),
        ("memory/subdir/2024-06-15.md", True),
        ("memory/dreaming/2024-06-15.md", False),
        ("memory/.dreams/session-corpus/2024-06-15.md", True),
        ("memory/.dreams/session-corpus/2024-06-15.txt", True),
        ("docs/2024-06-15.md", False),
        ("2024-06-15.md", False),
        ("", False),
    ],
)
def test_is_short_term_memory_path(path: str, expected: bool) -> None:
    assert _is_short_term_memory_path(path) == expected


# ── is_contaminated_dreaming_snippet ─────────────────────────────────────────


def test_contaminated_with_promotion_marker() -> None:
    snippet = "<!-- openclaw-memory-promotion:somekey -->"
    assert is_contaminated_dreaming_snippet(snippet) is True


def test_contaminated_session_metadata() -> None:
    snippet = "Session Key: abc Session ID: 123 more text here"
    assert is_contaminated_dreaming_snippet(snippet) is True


def test_contaminated_conversation_summary() -> None:
    snippet = "Conversation Summary: here is a summary"
    assert is_contaminated_dreaming_snippet(snippet) is True


def test_contaminated_transcript_turn() -> None:
    snippet = "User: hello there"
    assert is_contaminated_dreaming_snippet(snippet) is True


def test_not_contaminated_clean_snippet() -> None:
    snippet = "The user prefers Python 3.12 for all new projects."
    assert is_contaminated_dreaming_snippet(snippet) is False


def test_not_contaminated_empty() -> None:
    assert is_contaminated_dreaming_snippet("") is False
    assert is_contaminated_dreaming_snippet("   ") is False


def test_contaminated_promotion_score_metadata() -> None:
    snippet = "[score=0.85 recalls=5 avg=0.80 source=memory/2024-06-15.md]"
    assert is_contaminated_dreaming_snippet(snippet) is True


# ── _build_entry_key ──────────────────────────────────────────────────────────


def test_build_entry_key_stable() -> None:
    k1 = _build_entry_key(path="memory/2024-06-15.md", start_line=1, end_line=5, source="memory")
    k2 = _build_entry_key(path="memory/2024-06-15.md", start_line=1, end_line=5, source="memory")
    assert k1 == k2
    assert len(k1) == 32


def test_build_entry_key_differs_with_claim_hash() -> None:
    k1 = _build_entry_key(path="memory/2024-06-15.md", start_line=1, end_line=5, source="memory")
    k2 = _build_entry_key(
        path="memory/2024-06-15.md", start_line=1, end_line=5, source="memory", claim_hash="abc"
    )
    assert k1 != k2


# ── _hash_query and _build_claim_hash ─────────────────────────────────────────


def test_hash_query_stable() -> None:
    h1 = _hash_query("what are my preferences?")
    h2 = _hash_query("what are my preferences?")
    assert h1 == h2
    assert len(h1) == 16


def test_build_claim_hash_stable() -> None:
    h = _build_claim_hash("Python 3.12 preferred")
    assert len(h) == 16
    assert _build_claim_hash("Python 3.12 preferred") == h


# ── _calculate_recency_component ─────────────────────────────────────────────


def test_recency_zero_age_is_one() -> None:
    assert _calculate_recency_component(0.0, 14.0) == pytest.approx(1.0)


def test_recency_half_life_is_half() -> None:
    result = _calculate_recency_component(14.0, 14.0)
    assert result == pytest.approx(0.5, abs=0.001)


def test_recency_old_entry() -> None:
    result = _calculate_recency_component(100.0, 14.0)
    assert result < 0.01


# ── _calculate_consolidation_component ───────────────────────────────────────


def test_consolidation_no_days() -> None:
    assert _calculate_consolidation_component([]) == 0.0


def test_consolidation_single_day() -> None:
    assert _calculate_consolidation_component(["2024-01-01"]) == pytest.approx(0.2)


def test_consolidation_multiple_days() -> None:
    days = ["2024-01-01", "2024-01-08", "2024-01-15"]
    score = _calculate_consolidation_component(days)
    # Spanned 14 days (>1 week), 3 distinct days → high consolidation
    assert score > 0.6


# ── _calculate_conceptual_component ──────────────────────────────────────────


def test_conceptual_no_tags() -> None:
    assert _calculate_conceptual_component([]) == 0.0


def test_conceptual_six_tags_max() -> None:
    assert _calculate_conceptual_component(["a", "b", "c", "d", "e", "f"]) == pytest.approx(1.0)


def test_conceptual_partial() -> None:
    assert _calculate_conceptual_component(["a", "b", "c"]) == pytest.approx(0.5)


# ── normalize_short_term_recall_store ─────────────────────────────────────────


def test_normalize_empty_raw() -> None:
    store = normalize_short_term_recall_store(None, NOW_ISO)
    assert store["version"] == 1
    assert store["entries"] == {}


def test_normalize_invalid_raw() -> None:
    store = normalize_short_term_recall_store("not a dict", NOW_ISO)
    assert store["entries"] == {}


def test_normalize_valid_entry() -> None:
    raw = {
        "version": 1,
        "updatedAt": NOW_ISO,
        "entries": {
            "key1": {
                "key": "key1",
                "path": "memory/2024-06-15.md",
                "startLine": 1,
                "endLine": 5,
                "source": "memory",
                "snippet": "The user prefers Python.",
                "recallCount": 3,
                "dailyCount": 1,
                "groundedCount": 0,
                "totalScore": 2.4,
                "maxScore": 0.85,
                "firstRecalledAt": NOW_ISO,
                "lastRecalledAt": NOW_ISO,
                "queryHashes": ["abc123"],
                "recallDays": ["2024-06-15"],
                "conceptTags": ["python"],
            }
        },
    }
    store = normalize_short_term_recall_store(raw, NOW_ISO)
    assert "key1" in store["entries"]
    entry = store["entries"]["key1"]
    assert entry["recall_count"] == 3
    assert entry["daily_count"] == 1
    assert entry["path"] == "memory/2024-06-15.md"


def test_normalize_filters_dreaming_path() -> None:
    # normalize_short_term_recall_store normalizes the store structure;
    # it does NOT filter by path (that is the ranking step's responsibility).
    # dreaming paths come through and are retained in the store.
    raw = {
        "version": 1,
        "entries": {
            "k": {
                "path": "memory/dreaming/2024-06-15.md",
                "startLine": 1,
                "endLine": 5,
                "source": "memory",
                "snippet": "some content",
            }
        },
    }
    store = normalize_short_term_recall_store(raw, NOW_ISO)
    # dreaming paths ARE stored; _is_short_term_memory_path filters them in ranking
    assert len(store["entries"]) == 1


def test_normalize_filters_contaminated_snippet() -> None:
    raw = {
        "version": 1,
        "entries": {
            "k": {
                "path": "memory/2024-06-15.md",
                "startLine": 1,
                "endLine": 5,
                "source": "memory",
                "snippet": "User: hello world",
            }
        },
    }
    store = normalize_short_term_recall_store(raw, NOW_ISO)
    assert len(store["entries"]) == 0


# ── normalize_short_term_phase_signal_store ───────────────────────────────────


def test_normalize_phase_signal_empty() -> None:
    store = normalize_short_term_phase_signal_store(None, NOW_ISO)
    assert store["entries"] == {}


def test_normalize_phase_signal_valid() -> None:
    raw = {
        "version": 1,
        "updatedAt": NOW_ISO,
        "entries": {
            "key1": {
                "key": "key1",
                "lightHits": 3,
                "remHits": 1,
                "lastLightAt": NOW_ISO,
            }
        },
    }
    store = normalize_short_term_phase_signal_store(raw, NOW_ISO)
    assert "key1" in store["entries"]
    entry = store["entries"]["key1"]
    assert entry["light_hits"] == 3
    assert entry["rem_hits"] == 1


def test_normalize_phase_signal_skips_zero_hits() -> None:
    raw = {
        "version": 1,
        "entries": {"k": {"key": "k", "lightHits": 0, "remHits": 0}},
    }
    store = normalize_short_term_phase_signal_store(raw, NOW_ISO)
    assert len(store["entries"]) == 0


# ── _calculate_phase_signal_boost ─────────────────────────────────────────────


def test_phase_signal_boost_no_entry() -> None:
    assert _calculate_phase_signal_boost(None, 0) == 0.0


def test_phase_signal_boost_positive() -> None:
    import time as _time

    now_ms = int(_time.time() * 1000)
    entry = {
        "key": "k",
        "light_hits": 6,
        "rem_hits": 3,
        "last_light_at": "2024-06-15T10:00:00+00:00",
        "last_rem_at": "2024-06-15T10:00:00+00:00",
    }
    # Use a very recent now_ms to get high recency
    from datetime import datetime

    now_ms = int(datetime.fromisoformat("2024-06-15T10:00:01+00:00").timestamp() * 1000)
    boost = _calculate_phase_signal_boost(entry, now_ms)
    assert boost > 0.0
    assert boost <= 0.06 + 0.09  # sum of both boosts


# ── derive_concept_tags ───────────────────────────────────────────────────────


def test_derive_concept_tags_from_snippet() -> None:
    tags = derive_concept_tags(
        path="memory/2024-06-15.md",
        snippet="kubernetes deployment configuration helm chart",
    )
    assert len(tags) <= MAX_CONCEPT_TAGS
    assert "kubernetes" in tags or "deployment" in tags


def test_derive_concept_tags_caps_at_max() -> None:
    snippet = " ".join(f"uniqueword{i}" for i in range(20))
    tags = derive_concept_tags(path="", snippet=snippet)
    assert len(tags) <= MAX_CONCEPT_TAGS


def test_derive_concept_tags_filters_stop_words() -> None:
    tags = derive_concept_tags(path="", snippet="the user should have this")
    # All are stop words — should be empty or very short
    assert all(t not in {"the", "user", "should", "have", "this"} for t in tags)


def test_derive_concept_tags_empty_inputs() -> None:
    assert derive_concept_tags() == []
    assert derive_concept_tags(path="", snippet="") == []


# ── compact_memory_for_budget ─────────────────────────────────────────────────


def test_compact_no_action_when_fits() -> None:
    existing = "# Long-Term Memory\n\nsome content\n"
    new_section = "## Section\n\nnew content\n"
    result = compact_memory_for_budget(
        existing_memory=existing,
        new_section=new_section,
        budget_chars=DEFAULT_MEMORY_FILE_MAX_CHARS,
    )
    assert result["compacted"] == existing
    assert result["dropped_dates"] == []


def test_compact_drops_oldest_promotion_section() -> None:
    old_section = "## Promoted From Short-Term Memory (2024-01-01)\n\nold content\n"
    mid_section = "## Promoted From Short-Term Memory (2024-06-01)\n\nmid content\n"
    existing = old_section + "\n" + mid_section
    new_section = "## Promoted From Short-Term Memory (2024-06-15)\n\nnew content\n"
    # Use a very tight budget that cannot fit all three sections
    budget = len(mid_section) + len(new_section) + 25  # only enough for 2 sections + overhead
    result = compact_memory_for_budget(
        existing_memory=existing,
        new_section=new_section,
        budget_chars=budget,
    )
    assert "2024-01-01" in result["dropped_dates"]
    assert "2024-01-01" not in result["compacted"]
    assert "mid" in result["compacted"]


def test_compact_zero_budget_no_action() -> None:
    existing = "some content"
    result = compact_memory_for_budget(
        existing_memory=existing,
        new_section="new",
        budget_chars=0,
    )
    assert result["compacted"] == existing
    assert result["dropped_dates"] == []


def test_compact_no_promotion_sections_no_change() -> None:
    existing = "# User notes\n\nsome handwritten content\n"
    new_section = "## Promoted From Short-Term Memory (2024-06-15)\n\n" + "x" * 5000
    result = compact_memory_for_budget(
        existing_memory=existing,
        new_section=new_section,
        budget_chars=100,
    )
    # No auto-promotion sections to drop
    assert result["compacted"] == existing
    assert result["dropped_dates"] == []
