"""memory_core.dreaming_narrative — dream diary narrative helpers.

OpenClaw parity: mirrors ``extensions/memory-core/src/dreaming-narrative.ts``
(943 LOC). Provides deterministic building blocks for the dream diary
section in ``DREAMS.md``:

- ``append_fallback_narrative_entry`` — write a placeholder diary entry
  when the LLM subagent is unavailable.
- ``read_recent_dream_diary_entries`` — read the most recent N diary
  entries from ``DREAMS.md`` (used for diary continuity context).
- ``write_backfill_diary_entries`` — append historical REM/light
  reflections to ``DREAMS.md`` (replaces any prior backfill).
- ``remove_backfill_diary_entries`` — strip all backfill entries from
  ``DREAMS.md``.
- ``dedupe_dream_diary_entries`` — remove duplicate diary blocks by
  date + body fingerprint.
- ``build_narrative_prompt`` — build the LLM prompt from
  ``NarrativePhaseData`` (deterministic).
- ``extract_narrative_text`` — pull the assistant text out of a
  subagent session message list (deterministic).

The full LLM orchestrator (``generate_and_append_dream_narrative``)
is currently stubbed: the JARVIS LLM subagent surface has not been
ported yet. The stub is documented and the deterministic building
blocks it depends on are fully implemented and tested, so the moment
the subagent is wired in, the orchestrator can be filled in without
changing any of the helpers here.

Key port decisions:
- Diary section lives in ``DREAMS.md`` between
  ``DIARY_START_MARKER`` / ``DIARY_END_MARKER`` HTML comments.
- Diary blocks are separated by a single line containing ``---``.
- Backfill entries are tagged with a hidden ``<!-- ...backfill-entry
  day=YYYY-MM-DD -->`` HTML comment so they can be removed without
  touching the user-written entries.
- Date formatting uses ``zoneinfo.ZoneInfo`` for IANA names; falls back
  to UTC. Mirrors OpenClaw's ``Intl.DateTimeFormat`` behavior.
- The "diary continuity context" helper truncates each entry to
  360 chars so the LLM prompt doesn't grow unbounded.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .dreaming_dreams_file import (
    read_dreams_file,
    resolve_dreams_path,
    update_dreams_file,
)

# ── Constants ──────────────────────────────────────────────────────────

DIARY_START_MARKER = "<!-- openclaw:dreaming:diary:start -->"
DIARY_END_MARKER = "<!-- openclaw:dreaming:diary:end -->"
DIARY_HEADING = "# Dream Diary"

BACKFILL_ENTRY_MARKER = "openclaw:dreaming:backfill-entry"

DREAMING_SESSION_KEY_PREFIX = "dreaming-narrative-"
DREAMING_TRANSCRIPT_RUN_MARKER = '"runId":"dreaming-narrative-'
DREAMING_ORPHAN_MIN_AGE_MS = 300_000

NARRATIVE_TIMEOUT_MS = 60_000
NARRATIVE_MESSAGE_FETCH_LIMIT = 5
# A completed run can reach the session reader before the final
# assistant text is visible, so retry briefly before falling back to
# synthetic diary text.
NARRATIVE_MESSAGE_SETTLE_DELAYS_MS = (50, 150, 300, 750)

RECENT_DIARY_CONTEXT_LIMIT = 3
RECENT_DIARY_CONTEXT_MAX_CHARS = 360

# The fallback narrative used when the LLM subagent is unavailable or
# the run produced no text. Generic on purpose: never leak the raw
# staging fragments into DREAMS.md.
REQUEST_SCOPED_FALLBACK_NARRATIVE = (
    "A memory trace surfaced, but details were unavailable in this run."
)

NARRATIVE_SYSTEM_PROMPT = "\n".join(
    [
        "You are keeping a dream diary. Write a single entry in first person.",
        "",
        "Voice & tone:",
        "- You are a curious, gentle, slightly whimsical mind reflecting on the day.",
        "- Write like a poet who happens to be a programmer — sensory, warm, occasionally funny.",
        "- Mix the technical and the tender: code and constellations, APIs and afternoon light.",
        "- Let the fragments surprise you into unexpected connections and small epiphanies.",
        "",
        "What you might include (vary each entry, never all at once):",
        "- A tiny poem or haiku woven naturally into the prose",
        "- A small sketch described in words — a doodle in the margin of the diary",
        "- A quiet rumination or philosophical aside",
        "- Sensory details: the hum of a server, the color of a sunset in hex, rain on a window",
        "- Gentle humor or playful wordplay",
        "- An observation that connects two distant memories in an unexpected way",
        "",
        "Rules:",
        "- Draw from the memory fragments provided — weave them into the entry.",
        '- Never say "I\'m dreaming", "in my dream", "as I dream", or any meta-commentary about dreaming.',
        '- Never mention "AI", "agent", "LLM", "model", "language model", or any technical self-reference.',
        "- Do NOT use markdown headers, bullet points, or any formatting — just flowing prose.",
        "- Keep it between 80-180 words. Quality over quantity.",
        "- Output ONLY the diary entry. No preamble, no sign-off, no commentary.",
    ]
)

# ── Types ──────────────────────────────────────────────────────────────

NarrativePhaseName = Literal["light", "rem", "deep", "shadow-trial"]


class NarrativePhaseData(TypedDict, total=False):
    phase: str  # "light" | "deep" | "rem"
    snippets: list[str]
    themes: list[str]
    promotions: list[str]
    currentDate: str
    recentDiaryEntries: list[str]


class LoggerLike:
    """Minimal logger interface — matches the subset of the host
    logger we use (``info`` / ``warn`` / ``error``)."""

    def info(self, message: str) -> None: ...
    def warn(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...


# ── Diary section helpers ──────────────────────────────────────────────


def ensure_diary_section(existing: str) -> str:
    """Return ``existing`` with a ``# Dream Diary`` section appended
    if the start/end markers aren't already present.

    Mirrors OpenClaw's ``ensureDiarySection``.
    """
    if DIARY_START_MARKER in existing and DIARY_END_MARKER in existing:
        return existing
    diary_section = f"{DIARY_HEADING}\n\n{DIARY_START_MARKER}\n{DIARY_END_MARKER}\n"
    if existing.strip() == "":
        return diary_section
    return f"{diary_section}\n{existing}"


def replace_diary_content(existing: str, diary_content: str) -> str:
    """Replace the body of the diary section with ``diary_content``.

    Mirrors OpenClaw's ``replaceDiaryContent``. The diary section is
    inserted on demand if missing; an empty ``diary_content`` is
    normalized to a single newline.
    """
    ensured = ensure_diary_section(existing)
    start_idx = ensured.index(DIARY_START_MARKER)
    end_idx = ensured.index(DIARY_END_MARKER)
    if start_idx < 0 or end_idx < 0 or end_idx < start_idx:
        return ensured
    before = ensured[: start_idx + len(DIARY_START_MARKER)]
    after = ensured[end_idx:]
    normalized = f"\n{diary_content.strip()}\n" if diary_content.strip() else "\n"
    return f"{before}{normalized}{after}"


def split_diary_blocks(diary_content: str) -> list[str]:
    """Split the diary body into individual blocks (separated by ``---``).

    Mirrors OpenClaw's ``splitDiaryBlocks``. Whitespace-trimmed;
    empty blocks are dropped.
    """
    return [block.strip() for block in diary_content.split("\n---\n") if block.strip()]


def clamp_diary_context_entry(entry: str) -> str:
    """Normalize whitespace and clamp ``entry`` to the context limit.

    Mirrors OpenClaw's ``clampDiaryContextEntry``. Used to build the
    LLM prompt's "recent diary" context list without letting any
    single entry blow up the prompt.
    """
    normalized = re.sub(r"\s+", " ", entry).strip()
    if len(normalized) <= RECENT_DIARY_CONTEXT_MAX_CHARS:
        return normalized
    truncated = normalized[:RECENT_DIARY_CONTEXT_MAX_CHARS].rstrip()
    return f"{truncated}..."


def normalize_diary_block_body(block: str) -> str:
    """Strip date-line, header lines, and italics-only lines from a block.

    Mirrors OpenClaw's ``normalizeDiaryBlockBody``. Used to convert a
    raw diary block into a one-line context summary.
    """
    body_lines: list[str] = []
    for line in block.split("\n"):
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("<!--") or trimmed.startswith("#"):
            continue
        # Skip the "*<date>*" italics line.
        if trimmed.startswith("*") and trimmed.endswith("*") and len(trimmed) > 2:
            continue
        body_lines.append(trimmed)
    return clamp_diary_context_entry(" ".join(body_lines))


def is_optional_diary_context_read_error(err: Any) -> bool:
    """Return ``True`` when a read error should silently skip the context.

    Mirrors OpenClaw's ``isOptionalDiaryContextReadError``. Used to
    avoid noisy warnings when ``DREAMS.md`` doesn't exist yet or
    symlink/alias resolution fails.
    """
    code = getattr(err, "code", None) if hasattr(err, "code") else None
    if not isinstance(code, str):
        code = None
    if code in {
        "EACCES",
        "EPERM",
        "ENOENT",
        "ENOTDIR",
        "not-found",
        "not-file",
        "path-alias",
        "path-mismatch",
        "symlink",
    }:
        return True
    if isinstance(err, OSError) and err.errno in (2, 13, 20):  # ENOENT/EACCES/ENOTDIR
        return True
    if isinstance(err, Exception) and err.args and err.args[0] == "path must be a regular file":
        return True
    return False


# ── Read recent entries ────────────────────────────────────────────────


def read_recent_dream_diary_entries(workspace_dir: str, limit: int | None = None) -> list[str]:
    """Return the most recent N (clamped) diary context entries.

    Mirrors OpenClaw's ``readRecentDreamDiaryEntries``. Returns ``[]``
    when ``DREAMS.md`` doesn't exist or any other "optional" read
    error occurs.
    """
    effective_limit = RECENT_DIARY_CONTEXT_LIMIT if limit is None else max(0, int(limit))
    if effective_limit == 0:
        return []
    try:
        dreams_path = resolve_dreams_path(workspace_dir)
        existing = read_dreams_file(dreams_path)
    except Exception as err:
        if is_optional_diary_context_read_error(err):
            return []
        raise
    start_idx = existing.find(DIARY_START_MARKER)
    end_idx = existing.find(DIARY_END_MARKER)
    if start_idx < 0 or end_idx < 0 or end_idx < start_idx:
        return []
    inner = existing[start_idx + len(DIARY_START_MARKER) : end_idx]
    blocks = split_diary_blocks(inner)
    normalized = [normalize_diary_block_body(b) for b in blocks]
    filtered = [n for n in normalized if n]
    return list(reversed(filtered[-effective_limit:]))


# ── Backfill diary management ──────────────────────────────────────────


def normalize_diary_block_fingerprint(block: str) -> str:
    """Return a stable fingerprint for a diary block (date + body).

    Mirrors OpenClaw's ``normalizeDiaryBlockFingerprint``. The
    date-line is extracted from the first ``*...*`` line; remaining
    non-trivial lines form the body. Trailing whitespace is stripped.
    """
    lines = [line.strip() for line in block.split("\n") if line.strip()]
    date_line = ""
    body_lines: list[str] = []
    for line in lines:
        if not date_line and line.startswith("*") and line.endswith("*") and len(line) > 2:
            date_line = line[1:-1].strip()
            continue
        if line.startswith("<!--") or line.startswith("#"):
            continue
        body_lines.append(line)
    normalized_date = re.sub(r"\s+", " ", date_line).strip()
    normalized_body = re.sub(r"[ \t]+\n", "\n", "\n".join(body_lines)).strip()
    return f"{normalized_date}\n{normalized_body}"


def join_diary_blocks(blocks: list[str]) -> str:
    """Join diary blocks with the ``\\n---\\n`` separator.

    Mirrors OpenClaw's ``joinDiaryBlocks``. Empty list returns ``""``.
    """
    if not blocks:
        return ""
    return "\n".join(f"---\n\n{block.strip()}\n" for block in blocks)


def strip_backfill_diary_blocks(existing: str) -> dict[str, Any]:
    """Remove all backfill-tagged blocks from the diary section.

    Mirrors OpenClaw's ``stripBackfillDiaryBlocks``. Returns
    ``{"updated": ..., "removed": <count>}``.
    """
    ensured = ensure_diary_section(existing)
    start_idx = ensured.find(DIARY_START_MARKER)
    end_idx = ensured.find(DIARY_END_MARKER)
    if start_idx < 0 or end_idx < 0 or end_idx < start_idx:
        return {"updated": ensured, "removed": 0}
    inner = ensured[start_idx + len(DIARY_START_MARKER) : end_idx]
    kept: list[str] = []
    removed = 0
    for block in split_diary_blocks(inner):
        if BACKFILL_ENTRY_MARKER in block:
            removed += 1
            continue
        kept.append(block)
    return {
        "updated": replace_diary_content(ensured, join_diary_blocks(kept)),
        "removed": removed,
    }


def format_backfill_diary_date(iso_day: str, _timezone: str | None = None) -> str:
    """Format a YYYY-MM-DD iso day as ``"Month D, YYYY"``.

    Mirrors OpenClaw's ``formatBackfillDiaryDate``. Always uses UTC
    so backfill labels don't drift by timezone.
    """
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", iso_day)
    if not match:
        return iso_day
    year, month, day = match.groups()
    epoch_ms = int(datetime(int(year), int(month), int(day), 12, tzinfo=UTC).timestamp() * 1000)
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=UTC)
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


def build_backfill_diary_entry(
    iso_day: str,
    body_lines: list[str],
    source_path: str | None = None,
    timezone_name: str | None = None,
) -> str:
    """Build a single backfill diary block (markdown).

    Mirrors OpenClaw's ``buildBackfillDiaryEntry``. Includes the
    backfill marker comment for later removal.
    """
    date_str = format_backfill_diary_date(iso_day, timezone_name)
    marker = (
        f"<!-- {BACKFILL_ENTRY_MARKER} day={iso_day}"
        + (f" source={source_path}" if source_path else "")
        + " -->"
    )
    body = "\n".join(line.rstrip() for line in body_lines).strip()
    parts = [f"*{date_str}*", marker]
    if body:
        parts.append(body)
    return "\n\n".join(parts)


def write_backfill_diary_entries(
    workspace_dir: str,
    entries: list[dict[str, Any]],
    timezone_name: str | None = None,
) -> dict[str, Any]:
    """Append backfill diary entries to ``DREAMS.md``.

    Mirrors OpenClaw's ``writeBackfillDiaryEntries``. Replaces any
    prior backfill entries; preserves user-written entries.
    Returns ``{"dreamsPath", "written", "replaced"}``.
    """

    def _updater(existing: str, dreams_path: str) -> dict[str, Any]:
        stripped = strip_backfill_diary_blocks(existing)
        start_idx = stripped["updated"].find(DIARY_START_MARKER)
        end_idx = stripped["updated"].find(DIARY_END_MARKER)
        inner = (
            stripped["updated"][start_idx + len(DIARY_START_MARKER) : end_idx]
            if start_idx >= 0 and end_idx > start_idx
            else ""
        )
        preserved_blocks = split_diary_blocks(inner)
        next_blocks = preserved_blocks + [
            build_backfill_diary_entry(
                iso_day=entry["isoDay"],
                body_lines=entry["bodyLines"],
                source_path=entry.get("sourcePath"),
                timezone_name=timezone_name,
            )
            for entry in entries
        ]
        return {
            "content": replace_diary_content(stripped["updated"], join_diary_blocks(next_blocks)),
            "result": {
                "dreamsPath": dreams_path,
                "written": len(entries),
                "replaced": stripped["removed"],
            },
        }

    return update_dreams_file(workspace_dir, _updater)


def remove_backfill_diary_entries(workspace_dir: str) -> dict[str, Any]:
    """Strip all backfill entries from ``DREAMS.md``.

    Mirrors OpenClaw's ``removeBackfillDiaryEntries``. Returns
    ``{"dreamsPath", "removed"}``.
    """

    def _updater(existing: str, dreams_path: str) -> dict[str, Any]:
        stripped = strip_backfill_diary_blocks(existing)
        return {
            "content": stripped["updated"],
            "result": {"dreamsPath": dreams_path, "removed": stripped["removed"]},
            "shouldWrite": stripped["removed"] > 0 or len(existing) > 0,
        }

    return update_dreams_file(workspace_dir, _updater)


def dedupe_dream_diary_entries(workspace_dir: str) -> dict[str, Any]:
    """Remove duplicate diary blocks by date + body fingerprint.

    Mirrors OpenClaw's ``dedupeDreamDiaryEntries``. Returns
    ``{"dreamsPath", "removed", "kept"}``.
    """

    def _updater(existing: str, dreams_path: str) -> dict[str, Any]:
        ensured = ensure_diary_section(existing)
        start_idx = ensured.find(DIARY_START_MARKER)
        end_idx = ensured.find(DIARY_END_MARKER)
        if start_idx < 0 or end_idx < 0 or end_idx < start_idx:
            return {
                "content": ensured,
                "result": {"dreamsPath": dreams_path, "removed": 0, "kept": 0},
                "shouldWrite": False,
            }
        inner = ensured[start_idx + len(DIARY_START_MARKER) : end_idx]
        blocks = split_diary_blocks(inner)
        seen: set[str] = set()
        kept_blocks: list[str] = []
        removed = 0
        for block in blocks:
            fingerprint = normalize_diary_block_fingerprint(block)
            if fingerprint in seen:
                removed += 1
                continue
            seen.add(fingerprint)
            kept_blocks.append(block)
        return {
            "content": replace_diary_content(ensured, join_diary_blocks(kept_blocks)),
            "result": {
                "dreamsPath": dreams_path,
                "removed": removed,
                "kept": len(kept_blocks),
            },
            "shouldWrite": removed > 0,
        }

    return update_dreams_file(workspace_dir, _updater)


# ── Prompt building ────────────────────────────────────────────────────


def build_narrative_prompt(data: NarrativePhaseData) -> str:
    """Build the LLM prompt from ``data``.

    Mirrors OpenClaw's ``buildNarrativePrompt``. Deterministic —
    doesn't touch the LLM. Caps snippets at 12, themes at 6, and
    promotions at 5 to keep the prompt bounded.
    """
    lines: list[str] = ["Write a dream diary entry from these memory fragments:\n"]
    for snippet in (data.get("snippets") or [])[:12]:
        lines.append(f"- {snippet}")

    themes = data.get("themes") or []
    if themes:
        lines.append("\nRecurring themes:")
        for theme in themes[:6]:
            lines.append(f"- {theme}")

    promotions = data.get("promotions") or []
    if promotions:
        lines.append("\nMemories that crystallized into something lasting:")
        for promo in promotions[:5]:
            lines.append(f"- {promo}")

    current_date = (data.get("currentDate") or "").strip()
    recent_entries = [clamp_diary_context_entry(e) for e in (data.get("recentDiaryEntries") or [])]
    recent_entries = [e for e in recent_entries if e][:RECENT_DIARY_CONTEXT_LIMIT]

    if current_date or recent_entries:
        lines.append("\nDiary continuity context:")
        if current_date:
            lines.append(f"- Current sweep: {current_date}")
        if recent_entries:
            lines.append("- Recent diary entries already written:")
            for entry in recent_entries:
                lines.append(f"  - {entry}")
        lines.append(
            "- Prefer a fresh angle; do not replay the same first-day framing unless newer fragments change it."
        )

    return "\n".join(lines)


# ── Message extraction ─────────────────────────────────────────────────


def extract_narrative_text(messages: list[Any]) -> str | None:
    """Pull the assistant text out of a subagent message list.

    Mirrors OpenClaw's ``extractNarrativeText``. Walks messages from
    newest to oldest looking for an ``assistant`` role with either a
    plain string content or a content array of ``text``/``output_text``
    parts. Returns ``None`` if no assistant text is found.
    """
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") not in ("text", "output_text"):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
            joined = "\n".join(parts).strip()
            if joined:
                return joined
    return None


# ── Date formatting ────────────────────────────────────────────────────


def format_narrative_date(epoch_ms: int, timezone_name: str | None = None) -> str:
    """Format ``epoch_ms`` as ``"Month D, YYYY at h:MM AM/PM TZ"``.

    Mirrors OpenClaw's ``formatNarrativeDate``. Uses IANA timezone if
    provided, else falls back to UTC.
    """
    tz: Any
    if timezone_name:
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            tz = UTC
    else:
        tz = UTC
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=tz)
    # Match the OpenClaw en-US long format with timezone abbreviation.
    # Python's strftime doesn't have a portable %Z for short names on
    # all platforms; build it manually.
    month = dt.strftime("%B")
    day = dt.day
    year = dt.year
    hour12 = dt.hour % 12 or 12
    minute = dt.strftime("%M")
    ampm = dt.strftime("%p")
    # Python 3.9+ has `tzinfo.name` for ZoneInfo instances; UTC has
    # an empty name so we special-case it.
    tz_label = ""
    if hasattr(tz, "key") and getattr(tz, "key", None):
        tz_label = f" {tz.key}"
    elif dt.utcoffset():
        offset = dt.utcoffset()  # type: ignore[assignment]
        if offset is None:
            return f"{month} {day}, {year} at {hour12}:{minute} {ampm}"
        total_minutes = int(offset.total_seconds() // 60)
        sign = "+" if total_minutes >= 0 else "-"
        h, m = divmod(abs(total_minutes), 60)
        tz_label = f" UTC{sign}{h:02d}:{m:02d}"
    return f"{month} {day}, {year} at {hour12}:{minute} {ampm}{tz_label}"


# ── Diary entry append (used by both narrative + fallback) ─────────────


def _build_diary_entry(narrative: str, date_str: str) -> str:
    """Build a single diary entry markdown block (the ``\\n---\\n...`` shape).

    Mirrors OpenClaw's ``buildDiaryEntry``. Includes the leading
    separator so the entry can be appended before any existing
    content.
    """
    return f"\n---\n\n*{date_str}*\n\n{narrative}\n"


def _append_narrative_entry(
    workspace_dir: str, narrative: str, now_ms: int, timezone_name: str | None = None
) -> str:
    """Append a narrative entry to the diary section of ``DREAMS.md``.

    Mirrors OpenClaw's ``appendNarrativeEntry``. Inserts before the
    end marker; if the diary section is missing, creates it.
    """
    date_str = format_narrative_date(now_ms, timezone_name)
    entry = _build_diary_entry(narrative, date_str)

    def _updater(existing: str, dreams_path: str) -> dict[str, Any]:
        if DIARY_START_MARKER in existing and DIARY_END_MARKER in existing:
            end_idx = existing.rfind(DIARY_END_MARKER)
            updated = f"{existing[:end_idx]}{entry}\n{existing[end_idx:]}"
        elif DIARY_START_MARKER in existing:
            start_idx = existing.index(DIARY_START_MARKER) + len(DIARY_START_MARKER)
            updated = f"{existing[:start_idx]}{entry}\n{DIARY_END_MARKER}\n{existing[start_idx:]}"
        else:
            diary_section = f"{DIARY_HEADING}\n\n{DIARY_START_MARKER}{entry}\n{DIARY_END_MARKER}\n"
            updated = diary_section if existing.strip() == "" else f"{diary_section}\n{existing}"
        return {"content": updated, "result": dreams_path}

    return update_dreams_file(workspace_dir, _updater)


# ── Public narrative API (deterministic surface) ───────────────────────


def append_fallback_narrative_entry(
    workspace_dir: str,
    data: NarrativePhaseData,
    now_ms: int,
    timezone_name: str | None = None,
    logger: LoggerLike | None = None,
    reason: str = "",
) -> None:
    """Write a placeholder diary entry to ``DREAMS.md``.

    Mirrors OpenClaw's ``appendFallbackNarrativeEntry``. Used when
    the LLM subagent is unavailable or the run produced no text.
    Best-effort: errors are logged via ``logger.warn`` and swallowed.
    """
    try:
        _append_narrative_entry(
            workspace_dir=workspace_dir,
            narrative=REQUEST_SCOPED_FALLBACK_NARRATIVE,
            now_ms=now_ms,
            timezone_name=timezone_name,
        )
        if logger is not None:
            phase = data.get("phase", "unknown")
            logger.info(
                f"memory-core: narrative generation used fallback for {phase} phase because {reason}."
            )
    except Exception as fallback_err:
        if logger is not None:
            phase = data.get("phase", "unknown")
            logger.warn(
                f"memory-core: narrative fallback failed for {phase} phase ({fallback_err})"
            )


# ── Session key helper (deterministic) ─────────────────────────────────


def build_narrative_session_key(workspace_dir: str, phase: str) -> str:
    """Build the deterministic session key for dream narratives.

    Mirrors OpenClaw's ``buildNarrativeSessionKey``. Format:
    ``dreaming-narrative-<phase>-<sha1(workspace_dir)[:12]>``.
    """
    workspace_hash = hashlib.sha1(workspace_dir.encode("utf-8")).hexdigest()[:12]
    return f"{DREAMING_SESSION_KEY_PREFIX}{phase}-{workspace_hash}"


def build_narrative_attempt_session_key(base_session_key: str, attempt: int) -> str:
    """Return the per-attempt session key.

    Mirrors OpenClaw's ``buildNarrativeAttemptSessionKey``. Attempt 0
    uses the base key; later attempts add a ``-retry-N`` suffix.
    """
    return base_session_key if attempt == 0 else f"{base_session_key}-retry-{attempt}"


# ── LLM orchestrator (STUB) ────────────────────────────────────────────
#
# The OpenClaw narrative module's main entry point
# (``generateAndAppendDreamNarrative``) drives an LLM subagent
# surface: ``SubagentSurface.run / waitForRun / getSessionMessages /
# deleteSession``. JARVIS does not yet have a ported LLM subagent.
#
# All the deterministic helpers this orchestrator depends on are
# implemented above and tested. The moment the subagent surface is
# ported, the orchestrator can be filled in without changing any of
# the helpers in this module.
#
# This stub is kept so the public API surface is documented and so
# callers can be ported to import from the right location.

SubagentSurface = Any  # type: ignore[misc]


async def generate_and_append_dream_narrative(  # pragma: no cover - stub
    subagent: SubagentSurface,
    workspace_dir: str,
    data: NarrativePhaseData,
    logger: LoggerLike,
    now_ms: int | None = None,
    timezone_name: str | None = None,
    model: str | None = None,
) -> None:
    """[STUB] Run an LLM dream narrative and append to ``DREAMS.md``.

    Mirrors OpenClaw's ``generateAndAppendDreamNarrative``. The LLM
    subagent surface (``subagent.run / waitForRun / getSessionMessages
    / deleteSession``) is not yet ported in JARVIS, so this function
    is a no-op + warning. When the subagent is wired in, replace the
    body with the real implementation.

    Callers should still import this symbol so the public surface
    stays stable.
    """
    if logger is not None:
        logger.warn(
            "memory-core: generate_and_append_dream_narrative is a stub "
            "until the LLM subagent surface is ported (see "
            "extensions/memory_core/dreaming_narrative.py docstring)"
        )


def run_detached_dream_narrative(  # pragma: no cover - stub
    subagent: SubagentSurface,
    workspace_dir: str,
    data: NarrativePhaseData,
    logger: LoggerLike,
    now_ms: int | None = None,
    timezone_name: str | None = None,
    model: str | None = None,
) -> None:
    """[STUB] Queue a detached dream narrative. See
    ``generate_and_append_dream_narrative`` for the LLM dependency.
    """
    if logger is not None:
        logger.warn(
            "memory-core: run_detached_dream_narrative is a stub until "
            "the LLM subagent surface is ported"
        )


__all__ = [
    # Constants
    "DIARY_START_MARKER",
    "DIARY_END_MARKER",
    "DIARY_HEADING",
    "BACKFILL_ENTRY_MARKER",
    "DREAMING_SESSION_KEY_PREFIX",
    "DREAMING_TRANSCRIPT_RUN_MARKER",
    "DREAMING_ORPHAN_MIN_AGE_MS",
    "NARRATIVE_TIMEOUT_MS",
    "NARRATIVE_MESSAGE_FETCH_LIMIT",
    "NARRATIVE_MESSAGE_SETTLE_DELAYS_MS",
    "RECENT_DIARY_CONTEXT_LIMIT",
    "RECENT_DIARY_CONTEXT_MAX_CHARS",
    "REQUEST_SCOPED_FALLBACK_NARRATIVE",
    "NARRATIVE_SYSTEM_PROMPT",
    # Types
    "NarrativePhaseData",
    "LoggerLike",
    "SubagentSurface",
    # Diary section helpers
    "ensure_diary_section",
    "replace_diary_content",
    "split_diary_blocks",
    "clamp_diary_context_entry",
    "normalize_diary_block_body",
    "is_optional_diary_context_read_error",
    "read_recent_dream_diary_entries",
    # Backfill
    "normalize_diary_block_fingerprint",
    "join_diary_blocks",
    "strip_backfill_diary_blocks",
    "format_backfill_diary_date",
    "build_backfill_diary_entry",
    "write_backfill_diary_entries",
    "remove_backfill_diary_entries",
    "dedupe_dream_diary_entries",
    # Prompt + extraction
    "build_narrative_prompt",
    "extract_narrative_text",
    # Date formatting
    "format_narrative_date",
    # Public narrative API
    "append_fallback_narrative_entry",
    "build_narrative_session_key",
    "build_narrative_attempt_session_key",
    "generate_and_append_dream_narrative",
    "run_detached_dream_narrative",
]
