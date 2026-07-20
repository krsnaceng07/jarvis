"""transcript_result — memory tool evidence + partial-timeout + result builders.

OpenClaw parity: mirrors
``extensions/active-memory/transcript-result.ts``.

Phase 4.2b step 2: ports the recall-flow result builders.
The recall loop in ``recall.ts`` calls:

- ``read_memory_tool_result_evidence`` on every tool
  result the sub-agent emits (so the harness knows when
  to short-circuit on a definitive unavailability).
- ``read_partial_assistant_text`` /
  ``read_partial_assistant_text_from_sources`` on a
  timeout to recover whatever the sub-agent had said.
- ``attach_partial_timeout_data`` / ``read_partial_timeout_data``
  to round-trip the partial reply + search debug on the
  timeout error.
- ``build_timeout_recall_result`` /
  ``build_subagent_recall_result`` to assemble the final
  ``ActiveRecallResult`` (ok / failed / unavailable /
  no_relevant_memory / timeout / timeout_partial).

Surface
-------
- ``read_memory_tool_result_evidence`` — given a memory
  tool's ``{toolName, result, isError, toolsAllow}``,
  return ``{hasUsableMemoryResult, hasUnavailableMemorySearchResult}``.
- ``extract_assistant_text_from_session_record`` — pull
  the assistant text from a session record (handles both
  ``{message: {role, content}}`` and ``{role, content}``).
- ``read_partial_assistant_text`` /
  ``read_partial_assistant_text_from_sources`` — bounded
  walk over one / many transcript sources, concatenating
  assistant text chunks (truncated to ``maxChars``).
- ``attach_partial_timeout_data`` /
  ``read_partial_timeout_data`` — round-trip the partial
  reply / search debug / unavailable flag on the timeout
  error.
- ``wait_for_subagent_partial_timeout_data`` — give the
  sub-agent ``TIMEOUT_PARTIAL_DATA_GRACE_MS`` to settle so
  we can capture its attached partial data.
- ``build_timeout_recall_result`` — assemble the
  ``timeout`` or ``timeout_partial`` recall result.
- ``build_subagent_recall_result`` — assemble the
  ``ok`` / ``failed`` / ``unavailable`` /
  ``no_relevant_memory`` recall result from a successful
  sub-agent run.
- ``reset_active_memory_transcript_for_tests`` /
  ``set_timeout_partial_data_grace_ms_for_tests`` — test
  hooks for the ``TIMEOUT_PARTIAL_DATA_GRACE_MS`` global.

Dependencies
============
- ``extensions.active_memory.transcript`` —
  ``file_transcript_source``,
  ``has_unavailable_memory_result_in_session_record``,
  ``has_usable_memory_result_in_session_record``,
  ``is_unavailable_memory_search_debug``,
  ``resolve_transcript_read_limits``,
  ``stream_active_memory_transcript_records``.
- ``extensions.active_memory.transcript_watch`` —
  ``read_merged_active_memory_transcript_state``.
- ``extensions.active_memory.prompt`` —
  ``normalize_active_summary`` / ``truncate_summary``.
- ``extensions.active_memory.query`` —
  ``extract_text_content``.
- ``extensions.active_memory.types`` — recall-flow types
  and constants.
- ``jarvis_sdk.as_optional_record`` +
  ``normalize_optional_string`` (string-coerce).
- ``jarvis_sdk.truncate_utf16_safe`` (text-utility).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, cast

from jarvis_sdk import (
    as_optional_record,
    normalize_optional_string,
    truncate_utf16_safe,
)

from .prompt import normalize_active_summary, truncate_summary
from .query import extract_text_content
from .transcript import (
    file_transcript_source,
    has_unavailable_memory_result_in_session_record,
    has_usable_memory_result_in_session_record,
    is_unavailable_memory_search_debug,
    resolve_transcript_read_limits,
    stream_active_memory_transcript_records,
)
from .transcript_watch import read_merged_active_memory_transcript_state
from .types import (
    TIMEOUT_PARTIAL_DATA_GRACE_MS,
    ActiveMemorySearchDebug,
    ActiveMemoryTranscriptSource,
    ActiveRecallResult,
    RecallSubagentResult,
    TranscriptReadLimits,
)

# Mutable test hook for the timeout-grace global.
_timeout_partial_data_grace_ms = TIMEOUT_PARTIAL_DATA_GRACE_MS


# ── Memory tool evidence (live tool result) ──────────────────────


def read_memory_tool_result_evidence(params: dict[str, Any]) -> dict[str, bool]:
    """Probe a live memory tool result for usable / unavailable state.

    Mirrors OpenClaw's ``readMemoryToolResultEvidence``.
    """
    result = as_optional_record(params.get("result"))
    raw_content = (result or {}).get("content") if result else None
    detailed = normalize_optional_string((result or {}).get("detailedContent"))
    text_content = detailed or (
        normalize_optional_string(raw_content) if isinstance(raw_content, str) else None
    )
    record = {
        "message": {
            "role": "toolResult",
            "toolName": params.get("toolName", ""),
            "isError": bool(params.get("isError")),
            "content": (
                raw_content
                if isinstance(raw_content, list)
                else ([{"type": "text", "text": text_content}] if text_content else [])
            ),
            "details": (result or {}).get("details"),
        }
    }
    return {
        "hasUsableMemoryResult": has_usable_memory_result_in_session_record(
            record, params.get("toolsAllow")
        ),
        "hasUnavailableMemorySearchResult": has_unavailable_memory_result_in_session_record(
            record, params.get("toolsAllow")
        ),
    }


# ── Partial assistant text (transcript recovery) ──────────────────


def extract_assistant_text_from_session_record(value: Any) -> str:
    """Return the assistant text from a session record (or ``""``)."""
    record = as_optional_record(value)
    if not record:
        return ""
    nested = as_optional_record(record.get("message"))
    top_level = record if normalize_optional_string(record.get("role")) == "assistant" else None
    message = nested or top_level
    if not message or normalize_optional_string(message.get("role")) != "assistant":
        return ""
    return extract_text_content(message.get("content")).strip()


async def read_partial_assistant_text(
    source: ActiveMemoryTranscriptSource | str | None,
    limits: TranscriptReadLimits | None = None,
) -> str | None:
    """Read the partial assistant text from one transcript source.

    Mirrors OpenClaw's ``readPartialAssistantText``. Returns
    the concatenated assistant text chunks (truncated to
    ``maxChars``) or ``None`` if no assistant text was
    found.
    """
    if not source:
        return None
    resolved_source = file_transcript_source(source) if isinstance(source, str) else source
    resolved_limits = resolve_transcript_read_limits(limits)
    texts: list[str] = []
    collected_chars = 0

    def _on_record(record: Any) -> bool:
        nonlocal collected_chars
        text = extract_assistant_text_from_session_record(record)
        if not text:
            return False
        separator = 1 if texts else 0
        remaining = resolved_limits["maxChars"] - collected_chars - separator
        if remaining <= 0:
            return True
        next_text = truncate_utf16_safe(text, remaining)
        if not next_text:
            return True
        texts.append(next_text)
        collected_chars += separator + len(next_text)
        return len(next_text) < len(text) or collected_chars >= resolved_limits["maxChars"]

    await stream_active_memory_transcript_records(
        {
            "source": resolved_source,
            "limits": resolved_limits,
            "onRecord": _on_record,
        }
    )
    joined = "\n".join(texts).strip()
    return joined or None


async def read_partial_assistant_text_from_sources(
    sources: tuple[ActiveMemoryTranscriptSource, ...] | list[ActiveMemoryTranscriptSource],
    limits: TranscriptReadLimits | None = None,
) -> str | None:
    """Walk sources in order, returning the first non-empty partial text."""
    for source in sources:
        text = await read_partial_assistant_text(source, limits)
        if text:
            return text
    return None


# ── Partial-timeout data round-trip ───────────────────────────────


def attach_partial_timeout_data(
    error: Any,
    partial_reply: str | None,
    search_debug: ActiveMemorySearchDebug | None,
    has_unavailable_memory_search_result: bool,
) -> None:
    """Attach the partial reply / debug to the timeout error.

    Mirrors OpenClaw's ``attachPartialTimeoutData``. Mutates
    ``error`` in place. No-op if ``error`` is ``None`` or
    not an object.
    """
    if not error or not isinstance(error, dict) and not hasattr(error, "__dict__"):
        return
    if partial_reply:
        with contextlib.suppress(Exception):
            error.active_memory_partial_reply = partial_reply
    if search_debug:
        with contextlib.suppress(Exception):
            error.active_memory_search_debug = search_debug
    if has_unavailable_memory_search_result:
        with contextlib.suppress(Exception):
            error.active_memory_unavailable_memory_search = True


def read_partial_timeout_data(error: Any) -> dict[str, Any]:
    """Read the partial reply / debug off the timeout error.

    Mirrors OpenClaw's ``readPartialTimeoutData``. Returns
    an empty dict if ``error`` is ``None`` / not an object.
    """
    if not error or not isinstance(error, dict | BaseException):
        return {}
    partial = getattr(error, "active_memory_partial_reply", None) or (
        error.get("activeMemoryPartialReply") if isinstance(error, dict) else None
    )
    debug = getattr(error, "active_memory_search_debug", None) or (
        error.get("activeMemorySearchDebug") if isinstance(error, dict) else None
    )
    unavailable = getattr(error, "active_memory_unavailable_memory_search", None)
    if unavailable is None and isinstance(error, dict):
        unavailable = error.get("activeMemoryUnavailableMemorySearch")
    return {
        "rawReply": normalize_optional_string(partial),
        "searchDebug": debug,
        "hasUnavailableMemorySearchResult": unavailable is True,
    }


async def wait_for_subagent_partial_timeout_data(
    subagent_promise: Any,
) -> dict[str, Any]:
    """Wait up to ``TIMEOUT_PARTIAL_DATA_GRACE_MS`` for the sub-agent.

    Mirrors OpenClaw's ``waitForSubagentPartialTimeoutData``.
    Returns the partial data from the resolved sub-agent (or
    the attached error data on rejection). ``settled`` is
    ``True`` if the sub-agent settled within the grace
    window.
    """
    if not subagent_promise:
        return {"settled": True}

    async def _settled() -> dict[str, Any]:
        try:
            await subagent_promise
            return {"settled": True}
        except Exception as exc:
            data = read_partial_timeout_data(exc)
            data["settled"] = True
            return data

    async def _timed_out() -> dict[str, Any]:
        return {"settled": False}

    try:
        return await asyncio.wait_for(
            _settled(), timeout=max(0, _timeout_partial_data_grace_ms) / 1000.0
        )
    except TimeoutError:
        return await _timed_out()


# ── Result builders ───────────────────────────────────────────────


async def build_timeout_recall_result(params: dict[str, Any]) -> ActiveRecallResult:
    """Assemble the ``timeout`` or ``timeout_partial`` recall result.

    Mirrors OpenClaw's ``buildTimeoutRecallResult``. If the
    sub-agent has not yet settled, the function gives it a
    grace window (``TIMEOUT_PARTIAL_DATA_GRACE_MS``) to
    surface partial data, then reads partial assistant text
    from the transcript sources.
    """
    if params.get("rawReply"):
        subagent_partial_data: dict[str, Any] = {"settled": True}
    else:
        subagent_partial_data = await wait_for_subagent_partial_timeout_data(
            params.get("subagentPromise")
        )
    raw_reply = (
        params.get("rawReply")
        or subagent_partial_data.get("rawReply")
        or await read_partial_assistant_text_from_sources(params.get("transcriptSources") or ())
    )
    summary = truncate_summary(
        normalize_active_summary(raw_reply or "") or "",
        params.get("maxSummaryChars", 0),
    )
    transcript_state: dict[str, Any] | None = None
    if params.get("transcriptSources"):
        transcript_state = await read_merged_active_memory_transcript_state(
            {
                "sources": params.get("transcriptSources") or (),
                "toolsAllow": params.get("toolsAllow") or (),
            }
        )
    search_debug = (
        params.get("searchDebug")
        or subagent_partial_data.get("searchDebug")
        or (transcript_state or {}).get("searchDebug")
    )
    if (
        len(summary) == 0
        or is_unavailable_memory_search_debug(search_debug)
        or not subagent_partial_data.get("settled", False)
        or bool(params.get("hasUnavailableMemorySearchResult"))
        or bool(subagent_partial_data.get("hasUnavailableMemorySearchResult"))
        or bool((transcript_state or {}).get("hasUnavailableMemorySearchResult"))
    ):
        return cast(
            ActiveRecallResult,
            {
                "status": "timeout",
                "elapsedMs": params.get("elapsedMs", 0),
                "summary": None,
                "searchDebug": search_debug,
            },
        )
    return cast(
        ActiveRecallResult,
        {
            "status": "timeout_partial",
            "elapsedMs": params.get("elapsedMs", 0),
            "summary": summary,
            "searchDebug": search_debug,
        },
    )


def build_subagent_recall_result(params: dict[str, Any]) -> ActiveRecallResult:
    """Assemble the final recall result from a successful sub-agent run.

    Mirrors OpenClaw's ``buildSubagentRecallResult``. Maps
    to ``ok`` / ``failed`` / ``unavailable`` /
    ``no_relevant_memory`` based on the sub-agent's
    ``rawReply`` + ``resultStatus`` + ``hasUsableMemoryResult``
    + ``hasUnavailableMemorySearchResult``.
    """
    subagent: RecallSubagentResult = params["subagentResult"]
    raw_reply = subagent.get("rawReply", "")
    result_status = subagent.get("resultStatus")
    search_debug = subagent.get("searchDebug") or params.get("fallbackSearchDebug")
    summary = truncate_summary(
        normalize_active_summary(raw_reply) or "",
        params.get("maxSummaryChars", 0),
    )
    has_usable = (
        subagent.get("hasUsableMemoryResult") is True
        or params.get("fallbackHasUsableMemoryResult") is True
    )
    has_unavailable = subagent.get("hasUnavailableMemorySearchResult") is True
    can_use_summary = has_usable
    if summary and can_use_summary:
        return cast(
            ActiveRecallResult,
            {
                "status": "ok",
                "elapsedMs": params.get("elapsedMs", 0),
                "rawReply": raw_reply,
                "summary": summary,
                "searchDebug": search_debug,
            },
        )
    if result_status == "failed":
        return cast(
            ActiveRecallResult,
            {
                "status": "failed",
                "elapsedMs": params.get("elapsedMs", 0),
                "summary": None,
                "searchDebug": search_debug,
            },
        )
    if (
        result_status == "unavailable"
        or is_unavailable_memory_search_debug(search_debug)
        or has_unavailable
    ):
        return cast(
            ActiveRecallResult,
            {
                "status": "unavailable",
                "elapsedMs": params.get("elapsedMs", 0),
                "summary": None,
                "searchDebug": search_debug,
            },
        )
    return cast(
        ActiveRecallResult,
        {
            "status": "no_relevant_memory",
            "elapsedMs": params.get("elapsedMs", 0),
            "summary": None,
            "searchDebug": search_debug,
        },
    )


# ── Test hooks ────────────────────────────────────────────────────


def reset_active_memory_transcript_for_tests() -> None:
    global _timeout_partial_data_grace_ms  # noqa: PLW0603 — test hook
    _timeout_partial_data_grace_ms = TIMEOUT_PARTIAL_DATA_GRACE_MS


def set_timeout_partial_data_grace_ms_for_tests(value: int) -> None:
    global _timeout_partial_data_grace_ms  # noqa: PLW0603 — test hook
    _timeout_partial_data_grace_ms = max(0, int(value))


__all__ = [
    "attach_partial_timeout_data",
    "build_subagent_recall_result",
    "build_timeout_recall_result",
    "extract_assistant_text_from_session_record",
    "read_memory_tool_result_evidence",
    "read_partial_assistant_text",
    "read_partial_assistant_text_from_sources",
    "read_partial_timeout_data",
    "reset_active_memory_transcript_for_tests",
    "set_timeout_partial_data_grace_ms_for_tests",
    "wait_for_subagent_partial_timeout_data",
]
