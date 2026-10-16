"""memory_core.short_term_scoring — scoring and contamination detection helpers.

OpenClaw parity: mirrors scoring formulas, decay functions, and contamination
rules from ``extensions/memory-core/src/short-term-promotion.ts``.
"""

from __future__ import annotations

from datetime import UTC, datetime
import math
import re
from typing import Any, TypedDict

# ── Numeric / Time constants ──────────────────────────────────────────────────

DAY_MS = 24 * 60 * 60 * 1000

_PHASE_SIGNAL_LIGHT_BOOST_MAX = 0.06
_PHASE_SIGNAL_REM_BOOST_MAX = 0.09
_PHASE_SIGNAL_HALF_LIFE_DAYS = 14

# ── Regexes ───────────────────────────────────────────────────────────────────

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
_PROMOTION_MARKER_RE = re.compile(
    r"<!--\s*openclaw-memory-promotion:([^\n]*?)\s*-->", re.IGNORECASE
)


class _PromotionWeights(TypedDict):
    frequency: float
    relevance: float
    diversity: float
    recency: float
    consolidation: float
    conceptual: float


_DEFAULT_WEIGHTS: _PromotionWeights = {
    "frequency": 0.24,
    "relevance": 0.3,
    "diversity": 0.15,
    "recency": 0.15,
    "consolidation": 0.1,
    "conceptual": 0.06,
}


def _clamp_score(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


def _normalize_snippet(raw: str) -> str:
    trimmed = raw.strip()
    if not trimmed:
        return ""
    return re.sub(r"\s+", " ", trimmed)


def _has_dreaming_narrative_lead(snippet: str) -> bool:
    """Return True if the snippet starts with a dreaming narrative marker."""
    stripped = snippet
    stripped = _DREAMING_DIFF_PREFIX_RE.sub("", stripped).lstrip("[(")
    stripped = re.sub(r"^[-*+>]\s+", "", stripped)
    head = stripped[:200]
    return bool(re.search(r"\b(?:Candidate|Reflections?):(?!\s*\d)", head, re.IGNORECASE))


def is_contaminated_dreaming_snippet(
    raw: str,
    *,
    allow_transcript_turn_snippet: bool = False,
) -> bool:
    """Return True if the snippet is a dreaming artifact that should be excluded."""
    snippet = _normalize_snippet(raw)
    if not snippet:
        return False
    if _PROMOTION_MARKER_RE.search(snippet):
        return True
    if _DREAMING_TRANSCRIPT_PROMPT_LINE_RE.search(snippet):
        return True
    if _RAW_SESSION_METADATA_RE.search(snippet):
        return True
    if _RAW_CONVERSATION_SUMMARY_RE.match(snippet):
        return True
    if not allow_transcript_turn_snippet and _RAW_TRANSCRIPT_TURN_RE.match(snippet):
        return True
    if _MEMORY_FLUSH_PROMPT_RE.search(snippet):
        return True
    if _PROMOTION_SCORE_METADATA_RE.search(snippet):
        return True
    has_narrative_lead = _has_dreaming_narrative_lead(snippet)
    has_confidence = bool(re.search(r"\bconfidence:\s*\d", snippet, re.IGNORECASE))
    has_evidence = bool(
        re.search(
            r"\bevidence:\s*(?:memory/\.dreams/session-corpus/|memory/)",
            snippet,
            re.IGNORECASE,
        )
    )
    has_status = bool(re.search(r"\bstatus:\s*staged\b", snippet, re.IGNORECASE))
    has_recalls = bool(re.search(r"\brecalls:\s*\d+\b", snippet, re.IGNORECASE))
    return has_narrative_lead and has_confidence and has_evidence and has_status and has_recalls


def _calculate_recency_component(age_days: float, half_life_days: float) -> float:
    """Exponential decay recency score."""
    if half_life_days <= 0:
        return 0.0
    return _clamp_score(2 ** (-age_days / half_life_days))


def _calculate_consolidation_component(recall_days: list[str]) -> float:
    if not recall_days:
        return 0.0
    if len(recall_days) == 1:
        return 0.2
    parsed: list[float] = []
    for day in recall_days:
        try:
            ts = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000
            parsed.append(ts)
        except ValueError:
            continue
    if len(parsed) <= 1:
        return 0.2
    parsed.sort()
    first = parsed[0]
    last = parsed[-1]
    span_days = max(0.0, (last - first) / DAY_MS)
    spacing = _clamp_score(math.log1p(len(parsed) - 1) / math.log1p(4))
    span = _clamp_score(span_days / 7)
    return _clamp_score(0.55 * spacing + 0.45 * span)


def _calculate_conceptual_component(concept_tags: list[str]) -> float:
    return _clamp_score(len(concept_tags) / 6)


def _calculate_phase_signal_age_days(last_seen_at: str | None, now_ms: int) -> float | None:
    if not last_seen_at:
        return None
    try:
        dt = datetime.fromisoformat(last_seen_at.replace("Z", "+00:00"))
        ts_ms = dt.timestamp() * 1000
        return max(0.0, (now_ms - ts_ms) / DAY_MS)
    except ValueError:
        return None


def _calculate_phase_signal_boost(
    entry: dict[str, Any] | None,
    now_ms: int,
) -> float:
    if entry is None:
        return 0.0
    light_strength = _clamp_score(math.log1p(max(0, entry.get("light_hits", 0))) / math.log1p(6))
    rem_strength = _clamp_score(math.log1p(max(0, entry.get("rem_hits", 0))) / math.log1p(6))
    light_age = _calculate_phase_signal_age_days(entry.get("last_light_at"), now_ms)
    rem_age = _calculate_phase_signal_age_days(entry.get("last_rem_at"), now_ms)
    light_recency = (
        0.0
        if light_age is None
        else _clamp_score(_calculate_recency_component(light_age, _PHASE_SIGNAL_HALF_LIFE_DAYS))
    )
    rem_recency = (
        0.0
        if rem_age is None
        else _clamp_score(_calculate_recency_component(rem_age, _PHASE_SIGNAL_HALF_LIFE_DAYS))
    )
    return _clamp_score(
        _PHASE_SIGNAL_LIGHT_BOOST_MAX * light_strength * light_recency
        + _PHASE_SIGNAL_REM_BOOST_MAX * rem_strength * rem_recency
    )


def _total_signal_count_for_entry(entry: dict[str, Any]) -> int:
    return (
        max(0, int(entry.get("recall_count", 0) or 0))
        + max(0, int(entry.get("daily_count", 0) or 0))
        + max(0, int(entry.get("grounded_count", 0) or 0))
    )


def _normalize_weights(weights: dict[str, Any] | None) -> _PromotionWeights:
    if not isinstance(weights, dict):
        return _DEFAULT_WEIGHTS
    merged = {**_DEFAULT_WEIGHTS}
    for k in _DEFAULT_WEIGHTS:
        if k in weights:
            try:
                v = float(weights[k])
                if math.isfinite(v) and v >= 0:
                    merged[k] = v
            except (TypeError, ValueError):
                pass
    return merged  # type: ignore[return-value]


# Public aliases
calculate_recency_component = _calculate_recency_component
calculate_consolidation_component = _calculate_consolidation_component
calculate_conceptual_component = _calculate_conceptual_component
calculate_phase_signal_age_days = _calculate_phase_signal_age_days
calculate_phase_signal_boost = _calculate_phase_signal_boost
total_signal_count_for_entry = _total_signal_count_for_entry
normalize_weights = _normalize_weights
