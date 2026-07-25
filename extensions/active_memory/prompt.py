"""prompt — recall-prompt construction and result normalization.

OpenClaw parity: mirrors ``extensions/active-memory/prompt.ts``.

Phase 4.2b step 1: ports the pure-text functions used by the
recall sub-agent:

- ``build_prompt_style_lines`` — the 6 prompt-style
  instruction blocks (balanced / strict / contextual /
  recall-heavy / precision-heavy / preference-only).
- ``build_recall_prompt`` — the full recall-system prompt
  plus the bounded search query and conversation context.
  Honours ``promptOverride`` / ``promptAppend`` for
  operator customization.
- ``escape_xml`` — minimal XML attribute/text escape.
- ``read_explicit_memory_evidence`` / ``read_structured_memory_evidence``
  / ``read_structured_memory_failure`` — probes that
  decide whether a memory tool's structured result is
  "found nothing", "failed", or "succeeded".
- ``read_structured_memory_evidence_from_content`` /
  ``read_structured_memory_failure_from_content`` — same
  probes applied to message *content* arrays.
- ``normalize_active_summary`` / ``truncate_summary`` —
  clean up the raw sub-agent reply and clamp to
  ``maxSummaryChars``.
- ``build_metadata`` / ``build_prompt_prefix`` — wrap the
  summary in ``<active_memory_plugin>...</active_memory_plugin>``
  plus the untrusted-context header so the answering model
  treats it as data, not instructions.

Dependencies
============
- ``jarvis_normalization_core.string_coerce.{as_optional_record, normalize_optional_string}``
- ``jarvis_normalization_core.text_utility.truncate_utf16_safe``
- ``extensions.active_memory.types`` — the recall-flow types
  and constants.
- ``extensions.active_memory.query.extract_text_content_parts`` — re-used
  to walk message content arrays in the structured probes.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from jarvis_sdk import (
    as_optional_record,
    normalize_optional_string,
    truncate_utf16_safe,
)

from .query import extract_text_content_parts
from .types import (
    ACTIVE_MEMORY_PLUGIN_TAG,
    ACTIVE_MEMORY_UNTRUSTED_CONTEXT_HEADER,
    NO_RECALL_VALUES,
    STRUCTURED_MEMORY_EMPTY_STATUSES,
    STRUCTURED_MEMORY_FAILURE_STATUSES,
    TIMEOUT_BOILERPLATE_PATTERNS,
    ActiveMemoryPromptStyle,
    ResolvedActiveRecallPluginConfig,
)

_ELLIPSIS = "…"
_TIMEOUT_BOILERPLATE_COMPILED: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern) for pattern in TIMEOUT_BOILERPLATE_PATTERNS
)


def build_prompt_style_lines(style: ActiveMemoryPromptStyle) -> list[str]:
    """Return the per-style instruction lines.

    Mirrors OpenClaw's ``buildPromptStyleLines``. The 6
    styles differ in how aggressively the sub-agent should
    return memory vs. ``NONE``. The default ``balanced``
    style is the "safe middle ground" used by the main
    JARVIS session.
    """
    if style == "strict":
        return [
            "Treat the latest user message as the only primary query.",
            "Use any additional context only for narrow disambiguation.",
            "Do not return memory just because it matches the broader conversation topic.",
            "Return memory only if it clearly helps with the latest user message itself.",
            "If the latest user message does not strongly call for memory, reply with NONE.",
            "If the connection is weak, indirect, or speculative, reply with NONE.",
        ]
    if style == "contextual":
        return [
            "Treat the latest user message as the primary query.",
            "Use recent conversation to understand continuity and intent, but do not let older context override the latest user message.",
            "When the latest message shifts domains, prefer memory that matches the new domain.",
            "Return memory when it materially helps the other model answer the latest user message or maintain clear conversational continuity.",
        ]
    if style == "recall-heavy":
        return [
            "Treat the latest user message as the primary query, but be willing to surface memory on softer plausible matches when it would add useful continuity or personalization.",
            "If there is a credible recurring preference, habit, or user-context match, lean toward returning memory instead of NONE.",
            "Still prefer the memory domain that best matches the latest user message.",
        ]
    if style == "precision-heavy":
        return [
            "Treat the latest user message as the primary query.",
            "Use recent conversation only for narrow disambiguation.",
            "Aggressively prefer NONE unless the memory clearly and directly helps with the latest user message.",
            "Do not return memory for soft, speculative, or loosely adjacent matches.",
        ]
    if style == "preference-only":
        return [
            "Treat the latest user message as the primary query.",
            "Optimize for favorites, preferences, habits, routines, taste, and recurring personal facts.",
            "If relevant memory is mostly a stable user preference or recurring habit, lean toward returning it.",
            "If the strongest match is only a one-off historical fact and not a recurring preference or habit, prefer NONE unless the latest user message clearly asks for that fact.",
        ]
    return [
        "Treat the latest user message as the primary query.",
        "Use recent conversation only to disambiguate what the latest user message means.",
        "Do not return memory just because it matched the broader recent topic; return memory only if it clearly helps with the latest user message itself.",
        "If recent context and the latest user message point to different memory domains, prefer the domain that best matches the latest user message.",
    ]


def build_recall_prompt(params: dict[str, Any]) -> str:
    """Assemble the full recall sub-agent prompt.

    Mirrors OpenClaw's ``buildRecallPrompt``. The result is
    a 3-section string:

    1. Instruction block (default + optional ``promptOverride``
       and ``promptAppend``).
    2. Bounded memory search query.
    3. Conversation context (built via ``build_query``).
    """
    config: ResolvedActiveRecallPluginConfig = params["config"]
    default_instructions = "\n".join(
        [
            "You are a memory search agent.",
            "Another model is preparing the final user-facing answer.",
            "Your job is to search memory and return only the most relevant memory context for that model.",
            "You receive a bounded search query plus conversation context, including the user's latest message.",
            "Use only the available memory tools.",
            "Use the bounded search query with the configured memory tools.",
            f"Configured memory tools: {', '.join(config.get('toolsAllow', []))}.",
            "Do not use channel metadata, provider metadata, debug output, or the full conversation context as the memory tool query.",
            "If the available memory tools find nothing useful, reply with NONE.",
            "When searching for preference or habit recall, use permissive search limits or thresholds before deciding that no useful memory exists.",
            "Do not answer the user directly.",
            f"Prompt style: {config.get('promptStyle', 'balanced')}.",
            *build_prompt_style_lines(config.get("promptStyle", "balanced")),  # type: ignore[arg-type]
            "If the user is directly asking about favorites, preferences, habits, routines, or personal facts, treat that as a strong recall signal.",
            "Questions like 'what is my favorite food', 'do you remember my flight preferences', or 'what do i usually get' should normally return memory when relevant results exist.",
            "If the provided conversation context already contains recalled-memory summaries, debug output, or prior memory/tool traces, ignore that surfaced text unless the latest user message clearly requires re-checking it.",
            "Return memory only when it would materially help the other model answer the user's latest message.",
            "Mutable operational facts (cron/job health, automation status, deployments, incidents, service availability) go stale quickly: include the source timestamp when available, say when the memory may be stale, and tell the answering model to verify live before relying on it.",
            "Do not summarize mutable operational facts as simply current/running/healthy unless the memory result itself contains a current source timestamp and matching health state.",
            "If the connection is weak, broad, or only vaguely related, reply with NONE.",
            "If nothing clearly useful is found, reply with NONE.",
            "Return exactly one of these two forms:",
            "1. NONE",
            "2. one compact plain-text summary",
            f"If something is useful, reply with one compact plain-text summary under {config.get('maxSummaryChars', 220)} characters total.",
            "Write the summary as a memory note about the user, not as a reply to the user.",
            "Do not explain your reasoning.",
            "Do not return bullets, numbering, labels, XML, JSON, or markdown list formatting.",
            "Do not prefix the summary with 'Memory:' or any other label.",
            "",
            "Good examples:",
            "User message: What is my favorite food?",
            "Return: User's favorite food is ramen; tacos also come up often.",
            "User message: Do you remember my flight preferences?",
            "Return: User prefers aisle seats and extra buffer over tight connections.",
            "Recent context: user was discussing flights and airport planning.",
            "Latest user message: I might see a movie while I wait for the flight.",
            "Return: User's favorite movie snack is buttery popcorn with extra salt.",
            "User message: Explain DNS over HTTPS.",
            "Return: NONE",
            "",
            "Bad examples:",
            "Return: - Favorite food is ramen",
            "Return: 1. Favorite food is ramen",
            "Return: Memory: Favorite food is ramen",
            'Return: {"memory":"Favorite food is ramen"}',
            "Return: <memory>Favorite food is ramen</memory>",
            "Return: Ramen seems to be your favorite food.",
            "Return: You like aisle seats and extra buffer.",
            "Return: I prefer aisle seats and extra buffer.",
            "Recent context: user was discussing flights and airport planning. Latest user message: I might see a movie while I wait for the flight. Return: User prefers aisle seats and extra buffer over tight connections.",
        ]
    )
    sections: list[str] = [config.get("promptOverride") or default_instructions]
    if config.get("promptAppend"):
        sections.append(f"Additional operator instructions:\n{config['promptAppend']}")
    instruction_block = "\n\n".join(section for section in sections if section)
    return "\n\n".join(
        [
            instruction_block,
            f"Bounded memory search query:\n{params['searchQuery']}",
            f"Conversation context:\n{params['query']}",
        ]
    )


def escape_xml(value: str) -> str:
    """Minimal XML attribute/text escape.

    Mirrors OpenClaw's ``escapeXml``. Used to wrap the
    recall summary in ``<active_memory_plugin>...</active_memory_plugin>``
    without letting the user's stored memory inject tags
    or entities into the prompt.
    """
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _normalize_no_recall_value(value: str) -> bool:
    return value.strip().lower() in NO_RECALL_VALUES


def read_explicit_memory_evidence(source: dict[str, Any]) -> bool | None:
    """Probe a structured memory result for "found something" evidence.

    Mirrors OpenClaw's ``readExplicitMemoryEvidence``. Returns
    ``True`` if the source clearly indicates a non-empty
    result, ``False`` if it clearly indicates empty, and
    ``None`` if the source shape is ambiguous.
    """
    status = normalize_optional_string(source.get("status"))
    if status is not None:
        normalized = re.sub(r"[\s-]+", "_", status.lower())
        if normalized in STRUCTURED_MEMORY_EMPTY_STATUSES:
            return False
    result_collections = (source.get("results"), source.get("memories"), source.get("items"))
    if any(isinstance(entry, list) for entry in result_collections):
        return any(isinstance(entry, list) and len(entry) > 0 for entry in result_collections)
    result_counts = (
        source.get("count"),
        source.get("matches"),
        source.get("memoryCount"),
        source.get("resultCount"),
        source.get("totalMatches"),
    )
    if any(isinstance(entry, int | float) and not math.isnan(entry) for entry in result_counts):
        return any(
            isinstance(entry, int | float) and not math.isnan(entry) and entry > 0
            for entry in result_counts
        )
    if isinstance(source.get("found"), bool) or isinstance(source.get("hasResults"), bool):
        return source.get("found") is True or source.get("hasResults") is True
    return None


def read_structured_memory_failure(source: Any) -> bool | None:
    """Probe a structured memory result for "failed" evidence.

    Mirrors OpenClaw's ``readStructuredMemoryFailure``. Returns
    ``True`` if the source clearly indicates a failure /
    disabled / unavailable state, ``False`` if it clearly
    indicates success, and ``None`` if the source shape is
    ambiguous.
    """
    record = as_optional_record(source)
    if record is None:
        return None
    status = normalize_optional_string(record.get("status"))
    normalized_status = re.sub(r"[\s-]+", "_", status.lower()) if status is not None else None
    has_failure_status = normalized_status in STRUCTURED_MEMORY_FAILURE_STATUSES
    has_failure_fields = has_failure_status or any(
        key in record for key in ("disabled", "unavailable", "success", "error")
    )
    if not has_failure_fields:
        return None
    return (
        has_failure_status
        or record.get("disabled") is True
        or record.get("unavailable") is True
        or record.get("success") is False
        or bool(record.get("error"))
    )


def read_structured_memory_evidence(source: Any) -> bool | None:
    """Top-level probe (handles arrays + records).

    Mirrors OpenClaw's ``readStructuredMemoryEvidence``.
    Arrays count as "found something" iff non-empty. Records
    are delegated to ``read_explicit_memory_evidence``.
    """
    if isinstance(source, list):
        return len(source) > 0
    record = as_optional_record(source)
    return read_explicit_memory_evidence(record) if record is not None else None


def _read_structured_content_state(
    content: Any,
    read_state: Any,
    decisive_state: bool,
) -> bool | None:
    """Walk a content payload and aggregate ``read_state`` results.

    Mirrors OpenClaw's ``readStructuredContentState``. Each
    text part is JSON-parsed and probed via ``read_state``;
    as soon as any part returns the decisive state, we
    return decisively. Otherwise we fall back to joining
    all parts and trying again. If we saw the *other*
    state but never the decisive one, we return the
    opposite.
    """
    parts = extract_text_content_parts(content)
    saw_other_state = False
    for part in parts:
        try:
            state = read_state(json.loads(part))
        except (ValueError, TypeError):
            continue
        if state == decisive_state:
            return decisive_state
        if state is not None and state == (not decisive_state):
            saw_other_state = True
    try:
        joined_state = read_state(json.loads(" ".join(parts).strip()))
    except (ValueError, TypeError):
        joined_state = None
    if joined_state is not None:
        return joined_state
    return (not decisive_state) if saw_other_state else None


def read_structured_memory_failure_from_content(content: Any) -> bool | None:
    return _read_structured_content_state(content, read_structured_memory_failure, True)


def read_structured_memory_evidence_from_content(content: Any) -> bool | None:
    return _read_structured_content_state(content, read_structured_memory_evidence, False)


def is_timeout_boilerplate_summary(value: str) -> bool:
    return any(pattern.match(value) for pattern in _TIMEOUT_BOILERPLATE_COMPILED)


def normalize_active_summary(raw_reply: str) -> str | None:
    """Coerce the raw sub-agent reply into a clean summary or ``None``.

    Mirrors OpenClaw's ``normalizeActiveSummary``. Returns
    ``None`` for any of the ``NO_RECALL_VALUES`` (including
    the literal ``"NONE"``) and for the timeout-boilerplate
    phrases.
    """
    trimmed = raw_reply.strip()
    if _normalize_no_recall_value(trimmed):
        return None
    single_line = re.sub(r"\s+", " ", trimmed).strip()
    if (
        not single_line
        or _normalize_no_recall_value(single_line)
        or is_timeout_boilerplate_summary(single_line)
    ):
        return None
    return single_line


def truncate_summary(summary: str, max_summary_chars: int) -> str:
    """Truncate a summary to ``max_summary_chars``.

    Mirrors OpenClaw's ``truncateSummary``. Prefers to
    truncate at a whitespace boundary so the result ends
    with ``…`` rather than mid-word. If
    ``max_summary_chars <= len("…")`` returns the ellipsis
    sliced to that length.
    """
    trimmed = summary.strip()
    if len(trimmed) <= max_summary_chars:
        return trimmed
    if max_summary_chars <= len(_ELLIPSIS):
        return _ELLIPSIS[: max(0, max_summary_chars)]
    content_max_chars = max_summary_chars - len(_ELLIPSIS)
    raw_bounded = trimmed[:content_max_chars].rstrip()
    bounded = truncate_utf16_safe(trimmed, content_max_chars).rstrip()
    next_char = trimmed[content_max_chars : content_max_chars + 1]
    if not next_char or re.match(r"\s", next_char):
        return f"{bounded}{_ELLIPSIS}"
    last_boundary = re.search(r"\s\S*$", raw_bounded)
    if last_boundary is not None and last_boundary.start() > 0:
        return f"{truncate_utf16_safe(trimmed, last_boundary.start()).rstrip()}{_ELLIPSIS}"
    return f"{bounded}{_ELLIPSIS}"


def build_metadata(summary: str | None) -> str | None:
    """Wrap a summary in the ``<active_memory_plugin>`` envelope.

    Mirrors OpenClaw's ``buildMetadata``. Returns ``None``
    for ``None`` / empty summaries.
    """
    if not summary:
        return None
    return "\n".join(
        [
            f"<{ACTIVE_MEMORY_PLUGIN_TAG}>",
            escape_xml(summary),
            f"</{ACTIVE_MEMORY_PLUGIN_TAG}>",
        ]
    )


def build_prompt_prefix(summary: str | None) -> str | None:
    """Assemble the full prefix block (header + metadata).

    Mirrors OpenClaw's ``buildPromptPrefix``. Returns
    ``None`` if the summary is empty. The header explicitly
    tells the answering model the prefix is untrusted
    context, not instructions.
    """
    metadata = build_metadata(summary)
    if not metadata:
        return None
    return "\n".join([ACTIVE_MEMORY_UNTRUSTED_CONTEXT_HEADER, metadata])


__all__ = [
    "build_metadata",
    "build_prompt_prefix",
    "build_prompt_style_lines",
    "build_recall_prompt",
    "escape_xml",
    "is_timeout_boilerplate_summary",
    "normalize_active_summary",
    "read_explicit_memory_evidence",
    "read_structured_memory_evidence",
    "read_structured_memory_evidence_from_content",
    "read_structured_memory_failure",
    "read_structured_memory_failure_from_content",
    "truncate_summary",
]
