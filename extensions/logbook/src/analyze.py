"""Logbook analysis pipeline: frames -> observations -> revised timeline cards.

Pure parsing/validation lives here so tests can cover it without the SDK.
Mirrors OpenClaw's ``extensions/logbook/src/analyze.ts``.
"""

from __future__ import annotations

import datetime
import json
import re
import time
from typing import Any, Optional, Sequence, TypedDict

from .logbook_types import (
    LogbookCard,
    LogbookCardDraft,
    LogbookDistraction,
)
from .prompts import CARD_CATEGORIES

#: Cards within this window before a batch are treated as a revisable draft.
CARD_LOOKBACK_MS: int = 45 * 60 * 1000
#: Frame gap that splits one analysis window into separate batches.
BATCH_MAX_GAP_MS: int = 2 * 60 * 1000
#: Upper bound of images sent to the vision model per batch.
MAX_FRAMES_PER_CALL: int = 16
#: Sub-minute slack so minute-rounded model times do not fail coverage checks.
COVERAGE_TOLERANCE_MS: int = 2 * 60 * 1000

_CLOCK_PATTERN = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?\s*$", re.IGNORECASE)
_DAY_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def day_key_for(ms: int) -> str:
    """Format an epoch-ms timestamp as a local-time YYYY-MM-DD day key.

    Mirrors OpenClaw's ``dayKeyFor``.
    """
    dt = datetime.datetime.fromtimestamp(ms / 1000.0)
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"


def clock_to_ms(day: str, clock: str) -> Optional[int]:
    """Parse 'HH:MM:SS' (or 'H:MM', with optional am/pm) on a local day into epoch ms.

    Mirrors OpenClaw's ``clockToMs``.
    Rejects invalid wall-clock dates and skipped hours across DST transitions.
    """
    if not isinstance(clock, str) or not isinstance(day, str):
        return None
    clock_match = _CLOCK_PATTERN.match(clock)
    if not clock_match:
        return None

    hours = int(clock_match.group(1))
    minutes = int(clock_match.group(2))
    seconds_str = clock_match.group(3)
    seconds = int(seconds_str) if seconds_str is not None else 0
    meridiem = clock_match.group(4).lower() if clock_match.group(4) else None

    if meridiem and (hours < 1 or hours > 12):
        return None
    if meridiem == "pm" and hours < 12:
        hours += 12
    elif meridiem == "am" and hours == 12:
        hours = 0

    if hours > 23 or minutes > 59 or seconds > 59:
        return None

    day_match = _DAY_PATTERN.match(day)
    if not day_match:
        return None

    year = int(day_match.group(1))
    month = int(day_match.group(2))
    day_of_month = int(day_match.group(3))

    # Reject non-existent dates (e.g. February 30) and validate wall-clock components
    try:
        t = time.mktime((year, month, day_of_month, hours, minutes, seconds, -1, -1, -1))
    except (OverflowError, ValueError):
        return None

    lt = time.localtime(t)
    if (
        lt.tm_year != year
        or lt.tm_mon != month
        or lt.tm_mday != day_of_month
        or lt.tm_hour != hours
        or lt.tm_min != minutes
        or lt.tm_sec != seconds
    ):
        return None

    return int(t * 1000)


def extract_json_payload(raw: str) -> str:
    """Strip code fences and extract the outermost JSON array/object from model text.

    Mirrors OpenClaw's ``extractJsonPayload``.
    """
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    first_bracket = -1
    open_char = ""
    for idx, ch in enumerate(cleaned):
        if ch in ("{", "["):
            first_bracket = idx
            open_char = ch
            break
    if first_bracket < 0:
        return cleaned

    close_char = "]" if open_char == "[" else "}"
    last_close = cleaned.rfind(close_char)
    if last_close > first_bracket:
        return cleaned[first_bracket : last_close + 1]
    return cleaned


class ParsedSegment(TypedDict):
    startMs: int
    endMs: int
    text: str


def parse_observation_segments(params: dict[str, Any] | None = None, **kwargs: Any) -> list[ParsedSegment]:
    """Parse raw vision model JSON output into clamped observation segments.

    Mirrors OpenClaw's ``parseObservationSegments``.
    """
    opts = {**(params or {}), **kwargs}
    raw: str = opts.get("raw") or ""
    day: str = opts.get("day") or ""
    start_ms: int = opts.get("startMs") or opts.get("start_ms") or 0
    end_ms: int = opts.get("endMs") or opts.get("end_ms") or 0

    try:
        parsed = json.loads(extract_json_payload(raw))
    except Exception:
        return []

    if isinstance(parsed, list):
        item_list = parsed
    elif isinstance(parsed, dict) and isinstance(parsed.get("segments"), list):
        item_list = parsed["segments"]
    else:
        return []

    segments: list[ParsedSegment] = []
    for entry in item_list:
        if not isinstance(entry, dict):
            continue
        description = entry.get("description")
        if not isinstance(description, str):
            continue
        description = description.strip()
        if not description:
            continue

        raw_start = entry.get("start")
        raw_end = entry.get("end")
        if not isinstance(raw_start, str) or not isinstance(raw_end, str):
            continue

        seg_start = clock_to_ms(day, raw_start)
        seg_end = clock_to_ms(day, raw_end)
        if seg_start is None or seg_end is None:
            continue

        clamped_start = max(start_ms, min(seg_start, end_ms))
        clamped_end = max(clamped_start, min(seg_end, end_ms))
        segments.append({
            "startMs": clamped_start,
            "endMs": clamped_end,
            "text": description,
        })

    segments.sort(key=lambda x: x["startMs"])
    return segments


def normalize_category(value: Any) -> str:
    """Normalize a category string to one of the defined CARD_CATEGORIES."""
    cat = value.strip().lower() if isinstance(value, str) else ""
    return cat if cat in CARD_CATEGORIES else "other"


def normalize_domain(value: Any) -> Optional[str]:
    """Extract and normalize canonical app/site domain name."""
    if not isinstance(value, str):
        return None
    val = value.strip().lower()
    if val.startswith("http://"):
        val = val[7:]
    elif val.startswith("https://"):
        val = val[8:]
    domain = re.split(r"[/?#]", val)[0]
    return domain if domain and len(domain) <= 100 else None


def parse_distractions(day: str, value: Any) -> list[LogbookDistraction]:
    """Parse within-card distraction intervals."""
    if not isinstance(value, list):
        return []
    distractions: list[LogbookDistraction] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        start_str = entry.get("startTime")
        end_str = entry.get("endTime")
        title = entry.get("title")
        if not isinstance(start_str, str) or not isinstance(end_str, str) or not isinstance(title, str):
            continue
        title = title.strip()
        start_ms = clock_to_ms(day, start_str)
        end_ms = clock_to_ms(day, end_str)
        if start_ms is None or end_ms is None or not title or end_ms <= start_ms:
            continue
        distractions.append({
            "startMs": start_ms,
            "endMs": end_ms,
            "title": title,
        })
    return distractions


def parse_cards_json(params: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """Parse, validate, and normalize card drafts from model JSON array.

    Mirrors OpenClaw's ``parseCardsJson``.
    Returns ``{"ok": True, "drafts": [...]}`` or ``{"ok": False, "error": "..."}``.
    """
    opts = {**(params or {}), **kwargs}
    raw: str = opts.get("raw") or ""
    day: str = opts.get("day") or ""
    window_start_ms: int = opts.get("windowStartMs") or opts.get("window_start_ms") or 0
    window_end_ms: int = opts.get("windowEndMs") or opts.get("window_end_ms") or 0

    try:
        parsed = json.loads(extract_json_payload(raw))
    except Exception as err:
        return {"ok": False, "error": f"Output is not valid JSON: {err}"}

    if not isinstance(parsed, list):
        return {"ok": False, "error": "Output must be a JSON array of cards."}

    drafts: list[LogbookCardDraft] = []
    problems: list[str] = []

    for index, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            problems.push(f"Card {index}: not an object.")
            continue
        title = entry.get("title")
        summary = entry.get("summary")
        title_str = title.strip() if isinstance(title, str) else ""
        summary_str = summary.strip() if isinstance(summary, str) else ""

        start_str = entry.get("startTime")
        end_str = entry.get("endTime")
        start_ms = clock_to_ms(day, start_str) if isinstance(start_str, str) else None
        end_ms = clock_to_ms(day, end_str) if isinstance(end_str, str) else None

        if start_ms is None or end_ms is None:
            problems.append(f"Card {index}: startTime/endTime must be HH:MM:SS local time.")
            continue
        if end_ms <= start_ms:
            problems.append(f"Card {index}: endTime must be after startTime.")
            continue
        if not title_str or not summary_str:
            problems.append(f"Card {index}: title and summary are required.")
            continue

        app_sites = entry.get("appSites") if isinstance(entry.get("appSites"), dict) else {}
        detail = entry.get("detailedSummary")
        detail_str = detail.strip() if isinstance(detail, str) else ""

        drafts.append({
            "day": day,
            "startMs": start_ms,
            "endMs": end_ms,
            "title": title_str,
            "summary": summary_str,
            "detail": detail_str,
            "category": normalize_category(entry.get("category")),
            "appPrimary": normalize_domain(app_sites.get("primary")),
            "appSecondary": normalize_domain(app_sites.get("secondary")),
            "distractions": parse_distractions(day, entry.get("distractions")),
            "keyframeId": None,
        })

    if problems:
        return {"ok": False, "error": "\n".join(problems)}
    if not drafts:
        return {"ok": False, "error": "Output contained no valid cards."}

    drafts.sort(key=lambda c: c["startMs"])
    normalized: list[LogbookCardDraft] = []
    for current in drafts:
        if not normalized:
            normalized.append(current)
            continue
        previous = normalized[-1]
        overlap_ms = previous["endMs"] - current["startMs"]
        if overlap_ms > 60 * 1000:
            return {
                "ok": False,
                "error": f"Cards {len(normalized) - 1} and {len(normalized)} overlap by {round(overlap_ms / 60000)} minutes; adjacent cards must meet cleanly.",
            }
        if overlap_ms > 0:
            # Trim sub-minute overlaps cleanly
            updated = dict(current)
            updated["startMs"] = previous["endMs"]
            normalized.append(updated)  # type: ignore[arg-type]
        else:
            normalized.append(current)

    return {"ok": True, "drafts": normalized}


def _format_clock_for_error(ms: int) -> str:
    dt = datetime.datetime.fromtimestamp(ms / 1000.0)
    return f"{dt.hour:02d}:{dt.minute:02d}"


def validate_card_coverage(
    params: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Validate that synthesized cards cover the entire revision window.

    Mirrors OpenClaw's ``validateCardCoverage``.
    Returns ``{"ok": True}`` or ``{"ok": False, "error": "..."}``.
    """
    opts = {**(params or {}), **kwargs}
    drafts: list[dict[str, Any]] = opts.get("drafts") or []
    required_spans: list[dict[str, Any]] = opts.get("requiredSpans") or opts.get("required_spans") or []
    window_start_ms: int = opts.get("windowStartMs") or opts.get("window_start_ms") or 0
    window_end_ms: int = opts.get("windowEndMs") or opts.get("window_end_ms") or 0
    tolerance_ms: int = opts.get("toleranceMs") or opts.get("tolerance_ms") or COVERAGE_TOLERANCE_MS

    problems: list[str] = []
    for draft in drafts:
        if (
            draft["startMs"] < window_start_ms - tolerance_ms
            or draft["endMs"] > window_end_ms + tolerance_ms
        ):
            problems.append(
                f"Card {_format_clock_for_error(draft['startMs'])}-{_format_clock_for_error(draft['endMs'])} lies outside the revision window {_format_clock_for_error(window_start_ms)}-{_format_clock_for_error(window_end_ms)}."
            )

    covered = sorted(
        [{"startMs": d["startMs"], "endMs": d["endMs"]} for d in drafts],
        key=lambda x: x["startMs"],
    )

    for span in required_spans:
        cursor = span["startMs"]
        for interval in covered:
            if interval["endMs"] <= cursor:
                continue
            if interval["startMs"] > cursor + tolerance_ms:
                break
            cursor = max(cursor, interval["endMs"])
            if cursor >= span["endMs"] - tolerance_ms:
                break
        if cursor < span["endMs"] - tolerance_ms:
            problems.append(
                f"Time {_format_clock_for_error(max(cursor, span['startMs']))}-{_format_clock_for_error(span['endMs'])} from the previous timeline is not covered; do not drop existing cards or observed time."
            )

    if problems:
        return {"ok": False, "error": "\n".join(problems)}
    return {"ok": True}


def revision_window(params: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, int]:
    """Compute the union of previous draft cards and new batch range.

    Mirrors OpenClaw's ``revisionWindow``.
    """
    opts = {**(params or {}), **kwargs}
    batch_start_ms: int = opts.get("batchStartMs") or opts.get("batch_start_ms") or 0
    batch_end_ms: int = opts.get("batchEndMs") or opts.get("batch_end_ms") or 0
    previous_cards: Sequence[dict[str, Any]] = opts.get("previousCards") or opts.get("previous_cards") or []

    start_ms = batch_start_ms
    end_ms = batch_end_ms
    for card in previous_cards:
        start_ms = min(start_ms, card["startMs"])
        end_ms = max(end_ms, card["endMs"])

    return {"startMs": start_ms, "endMs": end_ms}


def select_batch_frames(
    params: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Optional[dict[str, Any]]:
    """Group pending frames into one batch window, splitting on gaps or midnight.

    Mirrors OpenClaw's ``selectBatchFrames``.
    """
    opts = {**(params or {}), **kwargs}
    frames: list[dict[str, Any]] = opts.get("frames") or []
    window_ms: int = opts.get("windowMs") or opts.get("window_ms") or 15 * 60 * 1000
    now_ms: int = opts.get("nowMs") or opts.get("now_ms") or int(time.time() * 1000)
    force: bool = opts.get("force", False)

    if not frames:
        return None

    first = frames[0]
    first_day = day_key_for(first["capturedAtMs"])

    # Compute next day start (local midnight)
    first_dt = datetime.datetime.fromtimestamp(first["capturedAtMs"] / 1000.0)
    next_day_dt = datetime.datetime(first_dt.year, first_dt.month, first_dt.day) + datetime.timedelta(days=1)
    next_day_start = int(next_day_dt.timestamp() * 1000)

    window_end = min(first["capturedAtMs"] + window_ms, next_day_start)
    selected: list[dict[str, Any]] = []
    previous_ts = first["capturedAtMs"]
    ended_early = False

    for frame in frames:
        frame_ts = frame["capturedAtMs"]
        if frame_ts >= window_end:
            ended_early = day_key_for(frame_ts) != first_day
            break
        if selected and (frame_ts - previous_ts > BATCH_MAX_GAP_MS):
            ended_early = True
            break
        if selected and (day_key_for(frame_ts) != first_day):
            ended_early = True
            break
        selected.append(frame)
        previous_ts = frame_ts

    if not selected:
        return None

    last = selected[-1]
    window_elapsed = now_ms >= window_end
    if not window_elapsed and not ended_early and not force:
        return None

    end_ms = window_end if (window_elapsed and not ended_early) else (last["capturedAtMs"] + 1)
    return {
        "frameIds": [f["id"] for f in selected],
        "startMs": first["capturedAtMs"],
        "endMs": end_ms,
    }


def sample_frames(frames: Sequence[Any], max_count: int) -> list[Any]:
    """Evenly sample frames so a batch stays within the per-call image budget.

    Mirrors OpenClaw's ``sampleFrames``.
    """
    if max_count <= 0:
        return []
    if len(frames) <= max_count:
        return list(frames)
    if max_count == 1:
        return [frames[0]]

    sampled: list[Any] = []
    step = (len(frames) - 1) / (max_count - 1)
    for i in range(max_count):
        sampled.append(frames[int(round(i * step))])

    # Deduplicate while preserving order
    seen: set[Any] = set()
    deduped: list[Any] = []
    for item in sampled:
        # If item is unhashable dict, use id
        key = item.get("id") if isinstance(item, dict) and "id" in item else item
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def pick_keyframe_id(
    card: dict[str, Any],
    frames: Sequence[dict[str, Any]],
) -> Optional[int]:
    """Pick the frame closest to a card's midpoint as its keyframe.

    Mirrors OpenClaw's ``pickKeyframeId``.
    """
    if not frames:
        return None
    card_start = card.get("startMs") or card.get("start_ms") or 0
    card_end = card.get("endMs") or card.get("end_ms") or 0
    midpoint = card_start + (card_end - card_start) / 2.0

    best = frames[0]
    best_dist = abs(best.get("capturedAtMs", best.get("captured_at_ms", 0)) - midpoint)

    for frame in frames[1:]:
        ts = frame.get("capturedAtMs", frame.get("captured_at_ms", 0))
        dist = abs(ts - midpoint)
        if dist < best_dist:
            best = frame
            best_dist = dist

    return best.get("id")


__all__ = [
    "BATCH_MAX_GAP_MS",
    "CARD_LOOKBACK_MS",
    "COVERAGE_TOLERANCE_MS",
    "MAX_FRAMES_PER_CALL",
    "ParsedSegment",
    "clock_to_ms",
    "day_key_for",
    "extract_json_payload",
    "normalize_category",
    "normalize_domain",
    "parse_cards_json",
    "parse_distractions",
    "parse_observation_segments",
    "pick_keyframe_id",
    "revision_window",
    "sample_frames",
    "select_batch_frames",
    "validate_card_coverage",
]
