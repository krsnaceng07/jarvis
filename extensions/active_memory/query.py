"""query — query and search-query construction for the recall sub-agent.

OpenClaw parity: mirrors ``extensions/active-memory/query.ts``.

Phase 4.2b step 1: ports the pure-text functions. The
model-resolution chain (``getModelRef``) is included so
the recall flow can resolve which model the sub-agent
should run on, using the agent's effective primary model
or the operator's ``config.model`` / ``config.modelFallback``.

Surface
-------
- ``build_query`` — assemble the conversation context that
  the recall sub-agent sees (``queryMode``: message / recent
  / full). Truncates per-turn text using ``truncateUtf16Safe``
  to honour ``recentUserChars`` / ``recentAssistantChars``.
- ``build_search_query`` — assemble the *bounded* search
  query that the sub-agent feeds to the configured memory
  tools. Strips untrusted-content fences, JSON code fences,
  and the active-memory XML block so a poisoned conversation
  history cannot inject tool-query text.
- ``strip_recalled_context_noise`` — remove the previous
  turn's prompt prefix lines (and any active-memory XML
  block) before re-feeding assistant history to the
  sub-agent. Otherwise the agent sees its own prior
  summary and biases toward NO_RECALL.
- ``strip_injected_active_memory_prefix_only`` — same as
  above but for the *user* side, keeping the user's actual
  message intact except for the active-memory prefix that
  was injected by the host.
- ``extract_recent_turns`` — pull ``{ role, text }`` pairs
  out of a list of message envelopes.
- ``extract_text_content`` / ``extract_text_content_parts``
  — handle both string and ``[{ type, text }]`` content
  shapes; OpenClaw's content blocks may be either.
- ``get_model_ref`` — model resolution chain:
  ``config.model`` → current run's model → agent's effective
  primary → ``config.modelFallback``.

Dependencies
============
- ``jarvis_sdk.text_utility.truncate_utf16_safe``
- ``jarvis_sdk.agent_runtime.{DEFAULT_PROVIDER, parse_model_ref,
  resolve_agent_effective_model_primary,
  resolve_default_model_for_agent}``
- ``extensions.active_memory.types`` — the recall-flow types
  added in Phase 4.2b.
"""

from __future__ import annotations

import re
from typing import Any

from jarvis_sdk import (
    DEFAULT_PROVIDER,
    parse_model_ref,
    resolve_agent_effective_model_primary,
    resolve_default_model_for_agent,
    truncate_utf16_safe,
)

from .types import (
    ACTIVE_MEMORY_CLOSE_TAG,
    ACTIVE_MEMORY_OPEN_TAG,
    ACTIVE_MEMORY_UNTRUSTED_CONTEXT_HEADER,
    MAX_ACTIVE_MEMORY_SEARCH_QUERY_CHARS,
    RECALLED_CONTEXT_LINE_PATTERNS,
    ActiveRecallRecentTurn,
    ResolvedActiveRecallPluginConfig,
)

# Pre-compile the regexes used by the text-stripping pipeline.
# These mirror query.ts:
#   /<<<EXTERNAL_UNTRUSTED_CONTENT\b[^>]*>>>[\s\S]*?<<<END_EXTERNAL_UNTRUSTED_CONTENT\b[^>]*>>>/g
_EXTERNAL_UNTRUSTED_RE = re.compile(
    r"<<<EXTERNAL_UNTRUSTED_CONTENT\b[^>]*>>>[\s\S]*?"
    r"<<<END_EXTERNAL_UNTRUSTED_CONTENT\b[^>]*>>>",
    re.IGNORECASE,
)
#   /```(?:json)?\s*[\s\S]*?```/gi
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*[\s\S]*?```", re.IGNORECASE)
#   /<active_memory_plugin>[\s\S]*?<\/active_memory_plugin>/gi
_ACTIVE_MEMORY_BLOCK_RE = re.compile(
    r"<active_memory_plugin>[\s\S]*?</active_memory_plugin>",
    re.IGNORECASE,
)

# Lines we drop from the search query because they're noise
# labels rather than user content. Mirrors query.ts's
# normalizeSearchQueryText filter.
_DROP_PREFIX_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(conversation info|sender|untrusted context)\b", re.IGNORECASE),
    re.compile(r"^(source: external|---|untrusted discord message body)$", re.IGNORECASE),
    re.compile(r"^⚠️?\s*Agent couldn't generate a response", re.IGNORECASE),
    re.compile(r"^Please try again\.?$", re.IGNORECASE),
)

# Compile the recalled-context line patterns at module load.
# The OpenClaw surface stores them as regex source strings
# (``RECALLED_CONTEXT_LINE_PATTERNS``); we keep that
# contract for ``types.py`` parity but pre-compile here.
_RECALLED_CONTEXT_LINE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern) for pattern in RECALLED_CONTEXT_LINE_PATTERNS
)


def build_query(params: dict[str, Any]) -> str:
    """Assemble the conversation context for the recall sub-agent.

    Mirrors OpenClaw's ``buildQuery``. Dispatches on
    ``params.config.queryMode``:

    - ``"message"`` — just the latest user message.
    - ``"full"`` — every turn (user + assistant) plus the
      latest user message.
    - ``"recent"`` (default) — the last N user + assistant
      turns, controlled by ``recentUserTurns`` /
      ``recentAssistantTurns``, with per-turn text
      truncated to ``recentUserChars`` / ``recentAssistantChars``.
    """
    latest = params["latestUserMessage"].strip()
    config: ResolvedActiveRecallPluginConfig = params["config"]
    if config.get("queryMode") == "message":
        return latest
    if config.get("queryMode") == "full":
        all_turns = [
            f"{turn['role']}: {turn['text'].strip().replace(chr(10), ' ').replace(chr(13), ' ')}".strip().replace(
                r"\s+", " "
            )
            for turn in (params.get("recentTurns") or [])
        ]
        all_turns = [t for t in all_turns if t]
        if not all_turns:
            return latest
        return "\n".join(
            [
                "Full conversation context:",
                *all_turns,
                "",
                "Latest user message:",
                latest,
            ]
        )

    # "recent" mode (default)
    remaining_user = config.get("recentUserTurns", 0)
    remaining_assistant = config.get("recentAssistantTurns", 0)
    recent_turns: list[ActiveRecallRecentTurn] = list(params.get("recentTurns") or [])
    selected: list[ActiveRecallRecentTurn] = []
    for index in range(len(recent_turns) - 1, -1, -1):
        turn = recent_turns[index]
        if turn["role"] == "user":
            if remaining_user <= 0:
                continue
            remaining_user -= 1
            selected.append(
                {
                    "role": "user",
                    "text": truncate_utf16_safe(
                        re.sub(r"\s+", " ", turn["text"].strip()),
                        config.get("recentUserChars", 0),
                    ),
                }
            )
            continue
        if remaining_assistant <= 0:
            continue
        remaining_assistant -= 1
        selected.append(
            {
                "role": "assistant",
                "text": truncate_utf16_safe(
                    re.sub(r"\s+", " ", turn["text"].strip()),
                    config.get("recentAssistantChars", 0),
                ),
            }
        )
    ordered = list(reversed(selected))
    ordered = [turn for turn in ordered if turn["text"]]
    if not ordered:
        return latest
    return "\n".join(
        [
            "Recent conversation tail:",
            *(f"{turn['role']}: {turn['text']}" for turn in ordered),
            "",
            "Latest user message:",
            latest,
        ]
    )


def _strip_external_untrusted_blocks(text: str) -> str:
    return _EXTERNAL_UNTRUSTED_RE.sub(" ", text)


def _strip_json_fences(text: str) -> str:
    return _JSON_FENCE_RE.sub(" ", text)


def _strip_active_memory_xml_blocks(text: str) -> str:
    return _ACTIVE_MEMORY_BLOCK_RE.sub(" ", text)


def _normalize_search_query_text(text: str) -> str:
    kept: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if any(pattern.match(line) for pattern in _DROP_PREFIX_PATTERNS):
            continue
        kept.append(line)
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def _clamp_search_query(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) > MAX_ACTIVE_MEMORY_SEARCH_QUERY_CHARS:
        normalized = truncate_utf16_safe(normalized, MAX_ACTIVE_MEMORY_SEARCH_QUERY_CHARS).strip()
    return normalized


def build_search_query(params: dict[str, Any]) -> str:
    """Assemble the *bounded* search query for the memory tools.

    Mirrors OpenClaw's ``buildSearchQuery``. Strips
    untrusted-content fences, JSON code fences, and the
    active-memory XML block, then normalizes and clamps the
    result. If the latest user message is short (< 12 chars)
    and there is previous context, blends the previous user
    turn in for recall disambiguation.
    """
    latest = _clamp_search_query(
        _normalize_search_query_text(
            _strip_active_memory_xml_blocks(
                _strip_json_fences(_strip_external_untrusted_blocks(params["latestUserMessage"]))
            )
        )
    )
    recent_turns = params.get("recentTurns") or []
    if len(latest) >= 12 or not recent_turns:
        return latest or _clamp_search_query(params["latestUserMessage"])
    latest_stripped = params["latestUserMessage"].strip()
    previous_user = next(
        (
            turn
            for turn in reversed(list(recent_turns))
            if turn["role"] == "user" and turn["text"].strip() != latest_stripped
        ),
        None,
    )
    if not previous_user:
        return latest or _clamp_search_query(params["latestUserMessage"])
    context = truncate_utf16_safe(
        _clamp_search_query(
            _normalize_search_query_text(strip_recalled_context_noise(previous_user["text"]))
        ),
        120,
    ).strip()
    return _clamp_search_query(f"{context} {latest}" if context else latest)


def extract_text_content_parts(content: Any) -> list[str]:
    """Return the text parts of a content payload.

    Mirrors OpenClaw's ``extractTextContentParts``. Handles:

    - ``"some text"`` → ``["some text"]`` (trimmed, non-empty).
    - ``[{ type: "text", text: "..." }, ...]`` → the trimmed
      text of each entry with a string ``text`` or a
      ``type="text"`` + string ``content`` pair.
    - Anything else → ``[]``.
    """
    if isinstance(content, str):
        return [content.strip()] if content.strip() else []
    if not isinstance(content, list):
        return []
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        text_value = item.get("text")
        if isinstance(text_value, str):
            parts.append(text_value)
            continue
        if item.get("type") == "text" and isinstance(item.get("content"), str):
            parts.append(item["content"])
    return [part.strip() for part in parts if part.strip()]


def extract_text_content(content: Any) -> str:
    return " ".join(extract_text_content_parts(content)).strip()


def strip_recalled_context_noise(text: str) -> str:
    """Strip prompt-prefix lines and the active-memory XML block.

    Mirrors OpenClaw's ``stripRecalledContextNoise``. Used on
    *assistant* turns before re-feeding them to the recall
    sub-agent, so the agent doesn't see its own prior
    ``<active_memory_plugin>...</active_memory_plugin>``
    block and bias toward ``NONE``.
    """
    lines = text.split("\n")
    cleaned: list[str] = []
    index = 0
    while index < len(lines):
        line = (lines[index] or "").strip()
        if not line:
            index += 1
            continue
        if line == ACTIVE_MEMORY_UNTRUSTED_CONTEXT_HEADER:
            index += 1
            continue
        if line == ACTIVE_MEMORY_OPEN_TAG:
            close_index = -1
            for probe in range(index + 1, len(lines)):
                if (lines[probe] or "").strip() == ACTIVE_MEMORY_CLOSE_TAG:
                    close_index = probe
                    break
            if close_index != -1:
                index = close_index + 1
                continue
        if line == ACTIVE_MEMORY_CLOSE_TAG:
            index += 1
            continue
        if any(pattern.match(line) for pattern in _RECALLED_CONTEXT_LINE_PATTERNS):
            index += 1
            continue
        cleaned.append(line)
        index += 1
    return re.sub(r"\s+", " ", " ".join(cleaned)).strip()


def strip_injected_active_memory_prefix_only(text: str) -> str:
    """Strip the active-memory prefix from a *user* turn.

    Mirrors OpenClaw's ``stripInjectedActiveMemoryPrefixOnly``.
    The user turn is otherwise preserved verbatim; we only
    remove the active-memory block if the user's text starts
    with the untrusted-context header followed by the
    ``<active_memory_plugin>...</active_memory_plugin>``
    envelope (the host may have re-injected the previous
    recall summary into the user side as part of the
    conversation tail).
    """
    lines = text.split("\n")
    cleaned: list[str] = []
    index = 0
    while index < len(lines):
        line = (lines[index] or "").strip()
        if not line:
            index += 1
            continue
        if line == ACTIVE_MEMORY_UNTRUSTED_CONTEXT_HEADER:
            next_line = (lines[index + 1] or "").strip() if index + 1 < len(lines) else ""
            if next_line == ACTIVE_MEMORY_OPEN_TAG:
                close_index = -1
                for probe in range(index + 2, len(lines)):
                    if (lines[probe] or "").strip() == ACTIVE_MEMORY_CLOSE_TAG:
                        close_index = probe
                        break
                if close_index != -1:
                    index = close_index + 1
                    continue
        cleaned.append(line)
        index += 1
    return re.sub(r"\s+", " ", " ".join(cleaned)).strip()


def extract_recent_turns(messages: list[Any]) -> list[ActiveRecallRecentTurn]:
    """Extract ``{ role, text }`` pairs from a list of message envelopes.

    Mirrors OpenClaw's ``extractRecentTurns``. Only messages
    with ``role in {"user", "assistant"}`` and non-empty text
    are returned; the assistant side gets
    ``strip_recalled_context_noise`` and the user side gets
    ``strip_injected_active_memory_prefix_only``.
    """
    turns: list[ActiveRecallRecentTurn] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        raw_text = extract_text_content(message.get("content"))
        text = (
            strip_recalled_context_noise(raw_text)
            if role == "assistant"
            else strip_injected_active_memory_prefix_only(raw_text)
        )
        if not text:
            continue
        turns.append({"role": role, "text": text})  # type: ignore[typeddict-item]
    return turns


def _parse_model_candidate(
    model_ref: str | None,
    default_provider: str = DEFAULT_PROVIDER,
) -> dict[str, str] | None:
    if not model_ref:
        return None
    parsed = parse_model_ref(model_ref, default_provider)
    if parsed is not None:
        return parsed
    return {"provider": default_provider, "model": model_ref}


def get_model_ref(
    runtime_config: Any,
    agent_id: str,
    config: ResolvedActiveRecallPluginConfig,
    ctx: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Resolve which model the recall sub-agent should use.

    Mirrors OpenClaw's ``getModelRef``. Resolution chain:

    1. ``config.model`` (operator-pinned)
    2. current run's model (``ctx.modelProviderId`` +
       ``ctx.modelId``)
    3. agent's effective primary model
       (``resolveDefaultModelForAgent``)
    4. ``config.modelFallback``
    """
    ctx = ctx or {}
    current_run_model = (
        f"{ctx['modelProviderId']}/{ctx['modelId']}"
        if ctx.get("modelProviderId") and ctx.get("modelId")
        else None
    )
    configured_default_model = (
        resolve_default_model_for_agent({"cfg": runtime_config, "agentId": agent_id})
        if resolve_agent_effective_model_primary(runtime_config, agent_id)
        else None
    )
    default_provider = (
        configured_default_model.get("provider", DEFAULT_PROVIDER)
        if configured_default_model
        else DEFAULT_PROVIDER
    )
    candidates = [
        config.get("model"),
        current_run_model,
        (
            f"{configured_default_model['provider']}/{configured_default_model['model']}"
            if configured_default_model
            else None
        ),
        config.get("modelFallback"),
    ]
    for candidate in candidates:
        parsed = _parse_model_candidate(candidate, default_provider)
        if parsed is not None:
            return parsed
    return None


__all__ = [
    "build_query",
    "build_search_query",
    "extract_recent_turns",
    "extract_text_content",
    "extract_text_content_parts",
    "get_model_ref",
    "strip_injected_active_memory_prefix_only",
    "strip_recalled_context_noise",
]
