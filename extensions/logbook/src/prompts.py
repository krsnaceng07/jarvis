"""Logbook prompt builders.

Two-stage pipeline (observe frames, then revise timeline cards) adapted
from the approach popularized by Dayflow (MIT).

Mirrors OpenClaw's ``extensions/logbook/src/prompts.ts``.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Sequence

from .logbook_types import LogbookCard, LogbookObservation

CARD_MIN_MINUTES = 10
CARD_MAX_MINUTES = 60
CARD_CATEGORIES: tuple[str, ...] = (
    "coding",
    "review",
    "writing",
    "research",
    "comms",
    "meetings",
    "design",
    "ops",
    "browsing",
    "media",
    "other",
)


def format_clock(ms: int) -> str:
    """Format epoch millisecond timestamp as local HH:MM:SS."""
    dt = datetime.datetime.fromtimestamp(ms / 1000.0)
    return f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"


OBSERVATION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["segments"],
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["start", "end", "description"],
                "properties": {
                    "start": {
                        "type": "string",
                        "description": "HH:MM:SS within the covered window",
                    },
                    "end": {
                        "type": "string",
                        "description": "HH:MM:SS within the covered window",
                    },
                    "description": {"type": "string"},
                },
            },
        },
    },
}


def build_observation_instructions(params: dict[str, Any] | None = None, **kwargs: Any) -> str:
    """Build instruction string for the vision model extracting segments.

    Mirrors OpenClaw's ``buildObservationInstructions``.
    Accepts params dict or keyword arguments:
    frame_times (or frameTimes), start_ms (or startMs), end_ms (or endMs).
    """
    opts = {**(params or {}), **kwargs}
    frame_times: list[int] = opts.get("frameTimes") or opts.get("frame_times") or []
    start_ms: int = opts.get("startMs") or opts.get("start_ms") or 0
    end_ms: int = opts.get("endMs") or opts.get("end_ms") or 0

    start = format_clock(start_ms)
    end = format_clock(end_ms)
    times = ", ".join(format_clock(t) for t in frame_times)

    return "\n".join([
        f"These are {len(frame_times)} screenshots of one computer screen, captured in order between {start} and {end} (local time).",
        f"Capture timestamps: {times}.",
        "",
        "Write an activity log detailed enough that the user could reconstruct what they did.",
        'For each segment ask: "What EXACTLY did they do? What SPECIFIC things are visible?"',
        "Capture exact app/site names, file names, URLs, page or PR titles, usernames, search queries, and numbers when readable.",
        "",
        "Bad: \"Checked email\". Good: \"Gmail: read 'Budget approval' from dana@acme.com, replied briefly\".",
        "Bad: \"Working on code\". Good: \"VS Code: editing store.ts, fixing a type error in replaceCardsInWindow\".",
        "",
        "Return 2-8 segments covering the whole window in order, no gaps, no overlaps.",
        "If the screen barely changes, return one segment describing the sustained activity.",
        "Group by GOAL, not app: debugging across editor, terminal, and browser is one segment.",
        f"Timestamps must be HH:MM:SS between {start} and {end}.",
    ])


def build_cards_prompt(params: dict[str, Any] | None = None, **kwargs: Any) -> str:
    """Build synthesis prompt to generate/revise timeline cards.

    Mirrors OpenClaw's ``buildCardsPrompt``.
    """
    opts = {**(params or {}), **kwargs}
    day: str = opts.get("day") or ""
    observations: Sequence[LogbookObservation] = opts.get("observations") or []
    previous_cards: Sequence[LogbookCard] = opts.get("previousCards") or opts.get("previous_cards") or []
    window_start_ms: int = opts.get("windowStartMs") or opts.get("window_start_ms") or 0
    window_end_ms: int = opts.get("windowEndMs") or opts.get("window_end_ms") or 0

    transcript = "\n".join(
        f"[{format_clock(obs['startMs'])} - {format_clock(obs['endMs'])}] {obs['text']}"
        for obs in observations
    )

    rendered_previous = []
    for card in previous_cards:
        rendered_previous.append({
            "startTime": format_clock(card["startMs"]),
            "endTime": format_clock(card["endMs"]),
            "category": card.get("category", "other"),
            "title": card.get("title", ""),
            "summary": card.get("summary", ""),
            "detailedSummary": card.get("detail", ""),
            "distractions": [
                {
                    "startTime": format_clock(d["startMs"]),
                    "endTime": format_clock(d["endMs"]),
                    "title": d.get("title", ""),
                }
                for d in card.get("distractions", [])
            ],
            "appSites": {
                "primary": card.get("appPrimary") or "",
                "secondary": card.get("appSecondary") or "",
            },
        })
    previous = json.dumps(rendered_previous, indent=2)

    categories_str = ", ".join(CARD_CATEGORIES)
    example_shape = (
        '[\n'
        '  {\n'
        '    "startTime": "13:12:00",\n'
        '    "endTime": "13:41:00",\n'
        '    "category": "coding",\n'
        '    "title": "",\n'
        '    "summary": "",\n'
        '    "detailedSummary": "",\n'
        '    "distractions": [{ "startTime": "13:15:00", "endTime": "13:18:00", "title": "" }],\n'
        '    "appSites": { "primary": "", "secondary": "" }\n'
        '  }\n'
        ']'
    )

    return "\n".join([
        "You are synthesizing a user's screen activity log into timeline cards. Each card is one coherent activity.",
        "",
        "CORE PRINCIPLE:",
        f"Each card = one main thing the user did. Time is a constraint ({CARD_MIN_MINUTES}-{CARD_MAX_MINUTES} min per card), not a goal.",
        "",
        "SPLIT into a new card only when the user's GOAL changes, not just the tool. MERGE when consecutive activities serve the same goal (app switches, debugging across editor + terminal + browser, iterating on the same document). Default to merging: fewer rich cards beat many granular ones.",
        "",
        "DISTRACTIONS: a brief (<5 min) unrelated interruption inside a card. Anything sustained (>10 min) is its own card.",
        "",
        "CONTINUITY: adjacent cards meet cleanly; never introduce gaps or overlaps. Preserve genuine idle gaps from the source data.",
        "",
        f"CATEGORY: one of {categories_str}.",
        "",
        'APP SITES: identify the main app or site per card as a canonical lower-case domain (figma.com, docs.google.com, github.com). Use "terminal" for terminals. Omit secondary when unclear. Never invent brands.',
        "",
        "REVISION CONTRACT:",
        "\"Previous cards\" is a draft you are revising and extending with the new observations. Your output must cover the union of the previous cards' time range and the new observations' range; you may restructure freely inside it, but do not drop covered time. The final card may be shorter than the minimum.",
        "",
        f"Day: {day}. Window under revision: {format_clock(window_start_ms)} to {format_clock(window_end_ms)}.",
        "",
        "Previous cards:",
        previous,
        "",
        "New observations:",
        transcript or "(none)",
        "",
        "Return ONLY a raw JSON array, no code fences, in this exact shape:",
        example_shape,
    ])


def build_cards_correction_prompt(validation_error: str) -> str:
    """Build repair prompt when card synthesis output fails schema/coverage validation.

    Mirrors OpenClaw's ``buildCardsCorrectionPrompt``.
    """
    return "\n".join([
        "The previous JSON output failed validation:",
        validation_error,
        "",
        "Return the FULL corrected JSON array (not a diff). Same coverage, no gaps or overlaps, JSON only.",
    ])


def build_standup_prompt(params: dict[str, Any] | None = None, **kwargs: Any) -> str:
    """Build daily standup summary prompt.

    Mirrors OpenClaw's ``buildStandupPrompt``.
    """
    opts = {**(params or {}), **kwargs}
    day: str = opts.get("day") or ""
    cards: Sequence[LogbookCard] = opts.get("cards") or []
    previous_day_cards: Sequence[LogbookCard] = opts.get("previousDayCards") or opts.get("previous_day_cards") or []

    def _render(card_list: Sequence[LogbookCard]) -> str:
        lines = [
            f"- {format_clock(c['startMs'])}-{format_clock(c['endMs'])} [{c.get('category', 'other')}] {c.get('title', '')}: {c.get('summary', '')}"
            for c in card_list
        ]
        return "\n".join(lines) if lines else "(no tracked activity)"

    return "\n".join([
        f"Write a concise daily standup for {day} based on the user's tracked screen activity.",
        "",
        "Yesterday's timeline:",
        _render(previous_day_cards),
        "",
        "Today's timeline so far:",
        _render(cards),
        "",
        "Output markdown with exactly three sections: '## Done' (yesterday's concrete accomplishments, merged and deduplicated), '## Today' (in-progress threads worth continuing), '## Blockers' (only if evidence shows something stuck; otherwise write 'None observed').",
        "Keep it under 150 words. No preamble.",
    ])


def build_ask_prompt(params: dict[str, Any] | None = None, **kwargs: Any) -> str:
    """Build prompt for answering free-form questions about tracked activity.

    Mirrors OpenClaw's ``buildAskPrompt``.
    """
    opts = {**(params or {}), **kwargs}
    day: str = opts.get("day") or ""
    cards: Sequence[LogbookCard] = opts.get("cards") or []
    observations: Sequence[LogbookObservation] = opts.get("observations") or []
    question: str = opts.get("question") or ""

    cards_text = "\n".join(
        f"- {format_clock(c['startMs'])}-{format_clock(c['endMs'])} [{c.get('category', 'other')}] {c.get('title', '')}: {c.get('summary', '')} {c.get('detail', '')}".strip()
        for c in cards
    ) or "(none)"

    obs_text = "\n".join(
        f"- {format_clock(o['startMs'])}-{format_clock(o['endMs'])}: {o.get('text', '')}"
        for o in observations
    ) or "(none)"

    return "\n".join([
        f"Answer the user's question about their tracked day ({day}) using ONLY the evidence below.",
        "If the evidence does not contain the answer, say so plainly. Reference times like 14:05 when useful.",
        "",
        "Timeline cards:",
        cards_text,
        "",
        "Detailed observations:",
        obs_text,
        "",
        f"Question: {question}",
        "",
        "Answer in 1-4 sentences.",
    ])


__all__ = [
    "CARD_CATEGORIES",
    "CARD_MAX_MINUTES",
    "CARD_MIN_MINUTES",
    "OBSERVATION_JSON_SCHEMA",
    "build_ask_prompt",
    "build_cards_correction_prompt",
    "build_cards_prompt",
    "build_observation_instructions",
    "build_standup_prompt",
    "format_clock",
]
