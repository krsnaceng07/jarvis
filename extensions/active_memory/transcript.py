"""transcript — session-transcript record streaming + evidence detection.

OpenClaw parity: mirrors ``extensions/active-memory/transcript.ts``.

Phase 4.2b step 2: ports the streaming and per-record
evidence helpers. The host's transcript store is consulted
through ``read_session_transcript_raw_delta`` for runtime
sources and through ``read_session_transcript_jsonl`` for
file sources.

Surface
-------
- ``resolve_transcript_read_limits`` — fill in defaults
  for the optional ``TranscriptReadLimits`` dict.
- ``file_transcript_source`` / ``transcript_source_from_returned_session_file``
  — build ``ActiveMemoryTranscriptSource`` values (file
  or runtime). The latter parses a ``"sqlite:..."``
  session-file marker the host returns to plugins.
- ``stream_active_memory_transcript_records`` — top-level
  dispatcher: runtime source uses
  ``read_session_transcript_raw_delta``; file source uses
  the bounded JSONL stream.
- ``is_unavailable_memory_search_debug`` — a search debug
  is "unavailable" iff it has an ``error`` field.
- ``extract_active_memory_search_debug_from_session_record`` /
  ``extract_tool_result_name_from_session_record`` /
  ``has_unavailable_memory_result_in_session_record`` /
  ``has_terminal_unavailable_memory_result_in_session_record`` /
  ``has_usable_memory_result_in_session_record`` — per-record
  probes that detect whether a tool call in the session
  transcript is a memory tool and whether its result
  represents a successful / failed / disabled / unavailable
  state.
- ``create_active_memory_hook_deadline`` — a small promise
  + setTimeout pair used by the recall flow to enforce a
  maximum wall-clock duration for the sub-agent hook.

Dependencies
============
- ``jarvis_sdk.read_session_transcript_raw_delta`` +
  ``SessionTranscriptTargetParams`` + ``parse_sqlite_session_file_marker``
  (session-transcript runtime).
- ``jarvis_sdk.as_optional_record`` +
  ``normalize_lowercase_string_or_empty`` +
  ``normalize_optional_string`` (string-coerce).
- ``extensions.active_memory.types`` — recall-flow types
  and constants.
- ``extensions.active_memory.prompt`` — the structured-memory
  probes (re-used here so transcript.py doesn't re-implement
  the same JSON-walk).
- ``extensions.active_memory.query`` — ``extract_text_content``
  for the text-walking probes.
- ``extensions.active_memory.config`` — ``clamp_int`` helper
  (mirrors OpenClaw's ``clampInt``).
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import re
from typing import Any, cast

from jarvis_sdk import (
    as_optional_record,
    normalize_lowercase_string_or_empty,
    normalize_optional_string,
    read_session_transcript_raw_delta,
)
from jarvis_sdk.text_utility import truncate_utf16_safe

from .config import _clamp_int
from .prompt import (
    read_explicit_memory_evidence,
    read_structured_memory_evidence_from_content,
    read_structured_memory_failure,
    read_structured_memory_failure_from_content,
)
from .query import extract_text_content
from .types import (
    DEFAULT_ACTIVE_MEMORY_TOOLS_ALLOW,
    DEFAULT_PARTIAL_TRANSCRIPT_MAX_CHARS,
    DEFAULT_TRANSCRIPT_READ_MAX_BYTES,
    DEFAULT_TRANSCRIPT_READ_MAX_LINES,
    LANCEDB_ACTIVE_MEMORY_TOOLS_ALLOW,
    ActiveMemorySearchDebug,
    ActiveMemoryTranscriptSource,
    TranscriptReadLimits,
)

# Pre-compiled regexes used by the per-record evidence probes.
# These match the OpenClaw source verbatim.
_RESULTS_ARRAY_PRESENT_RE = re.compile(r'"results"\s*:\s*\[\s*([^\s\]])')
_LCM_GREP_RESULTS_RE = re.compile(
    r"^## LCM Grep Results[\s\S]*^\*\*Total matches:\*\*\s+[1-9]\d*$",
    re.MULTILINE,
)
_LCM_SUMMARY_RE = re.compile(r"^LCM_SUMMARY \S+", re.MULTILINE)
_LCM_FILE_RE = re.compile(r"^## LCM File: \S+", re.MULTILINE)
_MEMORY_RECALL_PREFIX_RE = re.compile(r"^Found [1-9]\d* memories:")
_MEMORY_GET_TEXT_RE = re.compile(r'"text"\s*:\s*"(?!")')


def is_unavailable_memory_search_debug(debug: ActiveMemorySearchDebug | None) -> bool:
    """Return ``True`` iff the search debug has an ``error`` field.

    Mirrors OpenClaw's ``isUnavailableMemorySearchDebug``.
    """
    return bool(debug and debug.get("error"))


def resolve_transcript_read_limits(
    limits: TranscriptReadLimits | None = None,
) -> dict[str, int]:
    """Fill in defaults for the optional transcript-read limits.

    Mirrors OpenClaw's ``resolveTranscriptReadLimits``.
    Returns a dict with ``maxChars``, ``maxLines``,
    ``maxBytes`` (all guaranteed positive integers).
    """
    return {
        "maxChars": _clamp_int(
            limits.get("maxChars") if limits else None,
            DEFAULT_PARTIAL_TRANSCRIPT_MAX_CHARS,
            lo=1,
            hi=DEFAULT_PARTIAL_TRANSCRIPT_MAX_CHARS,
        ),
        "maxLines": _clamp_int(
            limits.get("maxLines") if limits else None,
            DEFAULT_TRANSCRIPT_READ_MAX_LINES,
            lo=1,
            hi=DEFAULT_TRANSCRIPT_READ_MAX_LINES,
        ),
        "maxBytes": _clamp_int(
            limits.get("maxBytes") if limits else None,
            DEFAULT_TRANSCRIPT_READ_MAX_BYTES,
            lo=1,
            hi=DEFAULT_TRANSCRIPT_READ_MAX_BYTES,
        ),
    }


def file_transcript_source(session_file: str) -> ActiveMemoryTranscriptSource:
    """Build a file-backed transcript source."""
    return {"kind": "file", "sessionFile": session_file}


def transcript_source_from_returned_session_file(
    params: dict[str, Any],
) -> ActiveMemoryTranscriptSource:
    """Decode a returned ``sessionFile`` into a transcript source.

    Mirrors OpenClaw's ``transcriptSourceFromReturnedSessionFile``.
    A ``"sqlite:..."`` marker is parsed into a runtime
    source; anything else is treated as a file path.
    """
    from jarvis_sdk import parse_sqlite_session_file_marker

    session_file = normalize_optional_string(params.get("sessionFile"))
    if not session_file:
        return file_transcript_source(str(params.get("sessionFile", "")))
    marker = parse_sqlite_session_file_marker(session_file)
    if not marker:
        return file_transcript_source(session_file)
    return {
        "kind": "runtime",
        "target": {
            "agentId": marker.agent_id,
            "sessionId": marker.session_id,
            "sessionKey": str(params.get("sessionKey", "")),
            "storePath": marker.store_path,
        },
    }


async def _stream_bounded_transcript_jsonl(params: dict[str, Any]) -> None:
    """Stream records from a bounded JSONL session file.

    Mirrors OpenClaw's ``streamBoundedTranscriptJsonl``.
    Skips files larger than ``maxBytes``; stops after
    ``maxLines``; each non-empty line is JSON-parsed and
    passed to ``on_record``. JSON parse errors are
    silently skipped (best-effort recovery on timeout).
    Uses the stdlib ``asyncio`` + ``thread`` helpers
    (no ``aiofiles`` dependency) to keep the plugin
    extension lightweight.
    """
    import asyncio as _asyncio
    from pathlib import Path

    session_file = params["sessionFile"]
    limits = resolve_transcript_read_limits(params.get("limits"))
    path = Path(session_file)
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size > limits["maxBytes"]:
        return

    def _read_lines() -> list[str]:
        with path.open(encoding="utf-8", errors="replace") as f:
            return f.readlines()

    try:
        lines = await _asyncio.to_thread(_read_lines)
    except OSError:
        return
    seen_lines = 0
    for raw_line in lines:
        seen_lines += 1
        if seen_lines > limits["maxLines"]:
            break
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = _json_loads(line)
        except ValueError:
            continue
        if params["onRecord"](record):
            break


def _json_loads(line: str) -> Any:
    import json as _json

    return _json.loads(line)


async def _stream_runtime_transcript_events(params: dict[str, Any]) -> None:
    """Stream events from a runtime transcript source.

    Mirrors OpenClaw's ``streamRuntimeTranscriptEvents``.
    Reads via ``read_session_transcript_raw_delta``; on
    ``"page"`` result, iterates ``page.events`` and yields
    each ``event`` to ``on_record``.
    """
    target = params["target"]
    limits = resolve_transcript_read_limits(params.get("limits"))
    try:
        page = read_session_transcript_raw_delta(
            target,
            max_bytes=limits["maxBytes"],
            max_events=limits["maxLines"],
        )
    except Exception:
        return
    if page.kind != "page":
        return
    for item in page.events:
        event = item.get("event") if isinstance(item, dict) else None
        if event is None:
            continue
        try:
            if params["onRecord"](event):
                break
        except Exception as exc:
            # The transcript walker is opportunistic; a callback
            # that raises on one event shouldn't abort the
            # whole walk.
            import logging

            logging.getLogger(__name__).debug("active-memory transcript callback raised: %s", exc)
            continue


async def stream_active_memory_transcript_records(params: dict[str, Any]) -> None:
    """Top-level dispatcher for streaming transcript records.

    Mirrors OpenClaw's ``streamActiveMemoryTranscriptRecords``.
    Runtime sources use ``read_session_transcript_raw_delta``;
    file sources use ``stream_bounded_transcript_jsonl``.
    """
    source = params["source"]
    if source.get("kind") == "runtime":
        await _stream_runtime_transcript_events(
            {
                "target": source.get("target"),
                "limits": params.get("limits"),
                "onRecord": params["onRecord"],
            }
        )
        return
    await _stream_bounded_transcript_jsonl(
        {
            "sessionFile": source.get("sessionFile", ""),
            "limits": params.get("limits"),
            "onRecord": params["onRecord"],
        }
    )


# ── Per-record evidence probes ─────────────────────────────────────


def _resolve_session_message(value: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Pick the inner ``message`` from a session record.

    Returns ``(message, top_level_tool_name)``. The message
    may live under ``record.message`` (canonical) or directly
    on the record (when the record *is* a tool-result). The
    top-level tool name is used to short-circuit on
    memory-only record shapes.
    """
    record = as_optional_record(value)
    nested = as_optional_record((record or {}).get("message"))
    record_tool_name = normalize_lowercase_string_or_empty((record or {}).get("toolName"))
    top_level = (
        record
        if (record or {}).get("role") == "toolResult"
        or record_tool_name
        in (
            "memory_search",
            "memory_recall",
        )
        else None
    )
    message = nested or top_level
    return message, record_tool_name or None


def extract_active_memory_search_debug_from_session_record(
    value: Any,
) -> ActiveMemorySearchDebug | None:
    """Extract a normalized ``ActiveMemorySearchDebug`` from a session record.

    Mirrors OpenClaw's
    ``extractActiveMemorySearchDebugFromSessionRecord``.
    Returns ``None`` if the record is not a memory tool
    result, or if no debug-shaped fields are present.
    """
    message, _ = _resolve_session_message(value)
    if not message:
        return None
    role = normalize_optional_string(message.get("role"))
    tool_name = normalize_lowercase_string_or_empty(message.get("toolName"))
    if role != "toolResult" or tool_name not in ("memory_search", "memory_recall"):
        return None
    details = as_optional_record(message.get("details"))
    debug = as_optional_record((details or {}).get("debug"))
    warning = normalize_optional_string((details or {}).get("warning"))
    action = normalize_optional_string((details or {}).get("action"))
    error = normalize_optional_string((details or {}).get("error"))
    if not debug and not warning and not action and not error:
        return None
    search_ms_value = (debug or {}).get("searchMs")
    hits_value = (debug or {}).get("hits")
    search_ms_int: int | None = (
        int(search_ms_value)
        if isinstance(search_ms_value, int | float) and not math.isnan(search_ms_value)
        else None
    )
    hits_int: int | None = (
        int(hits_value)
        if isinstance(hits_value, int | float) and not math.isnan(hits_value)
        else None
    )
    return cast(
        ActiveMemorySearchDebug,
        {
            "backend": normalize_optional_string((debug or {}).get("backend")),
            "configuredMode": normalize_optional_string((debug or {}).get("configuredMode")),
            "effectiveMode": normalize_optional_string((debug or {}).get("effectiveMode")),
            "fallback": normalize_optional_string((debug or {}).get("fallback")),
            "searchMs": search_ms_int,
            "hits": hits_int,
            "warning": warning,
            "action": action,
            "error": error,
        },
    )


def extract_tool_result_name_from_session_record(value: Any) -> str | None:
    """Return the tool name if the record is a tool-result, else ``None``.

    Mirrors OpenClaw's ``extractToolResultNameFromSessionRecord``.
    """
    message, _ = _resolve_session_message(value)
    if not message:
        return None
    role = normalize_optional_string(message.get("role"))
    tool_name = normalize_lowercase_string_or_empty(message.get("toolName"))
    if role == "toolResult" and tool_name:
        return tool_name
    return None


def _default_tools_allow() -> tuple[str, ...]:
    return (*DEFAULT_ACTIVE_MEMORY_TOOLS_ALLOW, *LANCEDB_ACTIVE_MEMORY_TOOLS_ALLOW)


def has_unavailable_memory_result_in_session_record(
    value: Any,
    tools_allow: tuple[str, ...] | list[str] | None = None,
) -> bool:
    """Return ``True`` if the record is a memory tool result with no usable data.

    Mirrors OpenClaw's ``hasUnavailableMemoryResultInSessionRecord``.
    The default ``tools_allow`` is the union of the
    ``memory_core`` and ``memory_lancedb`` allow lists.
    """
    tools_allow = tuple(tools_allow) if tools_allow else _default_tools_allow()
    message, _ = _resolve_session_message(value)
    if not message or normalize_optional_string(message.get("role")) != "toolResult":
        return False
    tool_name = _normalize_lowercase_string_empty_safe(message.get("toolName"))
    if not tool_name or tool_name not in tools_allow:
        return False
    details = as_optional_record(message.get("details"))
    unavailable = message.get("isError") is True or read_structured_memory_failure(details) is True
    if unavailable:
        return True
    return read_structured_memory_failure_from_content(message.get("content")) is True


def _normalize_lowercase_string_empty_safe(value: Any) -> str:
    return normalize_lowercase_string_or_empty(value)


def has_terminal_unavailable_memory_result_in_session_record(
    value: Any,
    tools_allow: tuple[str, ...] | list[str],
) -> bool:
    """Return ``True`` if the record is a terminal "unavailable" memory result.

    Mirrors OpenClaw's
    ``hasTerminalUnavailableMemoryResultInSessionRecord``.
    "Terminal" means the failure is explicit (disabled,
    unavailable status, or memory_search/recall ``error``);
    used by the watch to bail out early on definitive
    unavailability.
    """
    tools_allow = tuple(tools_allow)
    message, _ = _resolve_session_message(value)
    if not message or normalize_optional_string(message.get("role")) != "toolResult":
        return False
    tool_name = _normalize_lowercase_string_empty_safe(message.get("toolName"))
    if not tool_name or tool_name not in tools_allow:
        return False
    details = as_optional_record(message.get("details"))
    if (details or {}).get("disabled") is True or (details or {}).get("unavailable") is True:
        return True
    status = normalize_optional_string((details or {}).get("status"))
    if status:
        normalized = re.sub(r"[\s-]+", "_", status.lower())
        if normalized in ("disabled", "unavailable"):
            return True
    if tool_name not in ("memory_search", "memory_recall"):
        return False
    debug = extract_active_memory_search_debug_from_session_record(value)
    return bool(debug and debug.get("error")) or bool((details or {}).get("error"))


# ── Hook deadline ──────────────────────────────────────────────────


def create_active_memory_hook_deadline() -> dict[str, Any]:
    """Build a small promise + setTimeout pair for the recall hook.

    Mirrors OpenClaw's ``createActiveMemoryHookDeadline``.
    Returns a dict with ``arm(timeout_ms, on_timeout)``,
    ``promise`` (resolves with a sentinel on timeout), and
    ``stop()``.
    """
    timeout_sentinel = object()
    state: dict[str, Any] = {"timeout_id": None, "resolve": lambda *_a, **_k: None}

    def stop() -> None:
        timeout_id = state.get("timeout_id")
        if timeout_id is not None:
            with contextlib.suppress(Exception):
                timeout_id.cancel()
            state["timeout_id"] = None

    def arm(timeout_ms: int, on_timeout: Any) -> None:
        stop()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (e.g. called from a sync test
            # path). Defer to the test's event loop on the
            # next tick via ``asyncio.ensure_future``.
            loop = None
        if loop is None:
            state["timeout_id"] = None
            return

        def _on_timeout() -> None:
            state["timeout_id"] = None
            with contextlib.suppress(Exception):
                on_timeout()
            state["resolve"](timeout_sentinel)

        handle = loop.call_later(max(0, int(timeout_ms)) / 1000.0, _on_timeout)
        state["timeout_id"] = handle

    # Build a future that can be resolved from any thread.
    # We attach to the running loop if one is available;
    # otherwise we fall back to a plain Future (which still
    # works for ``set_result`` but emits a DeprecationWarning
    # in 3.10+). The deadline is only useful inside a running
    # loop, so callers should always invoke us from one.
    try:
        running = asyncio.get_running_loop()
        future: asyncio.Future[Any] = running.create_future()
    except RuntimeError:
        # No running loop — caller will not be able to await
        # ``promise``, but ``set_result`` still works for the
        # ``stop()`` / ``resolve`` side. The deprecation is
        # suppressed at the call site in tests.
        future = asyncio.Future()

    def _resolve(value: Any) -> None:
        if not future.done():
            future.set_result(value)

    state["resolve"] = _resolve
    return {"arm": arm, "promise": future, "stop": stop}


# ── "Usable memory result" probe ───────────────────────────────────


def has_usable_memory_result_in_session_record(  # noqa: PLR0911, PLR0912 — mirrors OpenClaw's per-tool branching
    value: Any,
    tools_allow: tuple[str, ...] | list[str] | None = None,
) -> bool:
    """Return ``True`` if the record is a memory tool result with useful data.

    Mirrors OpenClaw's
    ``hasUsableMemoryResultInSessionRecord``. Handles the
    built-in tool shapes (memory_search / memory_recall /
    memory_get / lcm_*) and falls back to
    ``read_explicit_memory_evidence`` /
    ``read_structured_memory_evidence_from_content`` for
    custom recall tools.
    """
    tools_allow = tuple(tools_allow) if tools_allow else _default_tools_allow()
    if has_unavailable_memory_result_in_session_record(value, tools_allow):
        return False
    message, _ = _resolve_session_message(value)
    if not message or normalize_optional_string(message.get("role")) != "toolResult":
        return False
    tool_name = _normalize_lowercase_string_empty_safe(message.get("toolName"))
    if not tool_name or tool_name not in tools_allow:
        return False
    details = as_optional_record(message.get("details"))
    content = extract_text_content(message.get("content"))
    if tool_name == "memory_search":
        results = (details or {}).get("results") if details else None
        if isinstance(results, list):
            return len(results) > 0
        return bool(_RESULTS_ARRAY_PRESENT_RE.search(content))
    if tool_name == "memory_recall":
        memories = (details or {}).get("memories") if details else None
        if isinstance(memories, list):
            return len(memories) > 0
        return bool(_MEMORY_RECALL_PREFIX_RE.match(content))
    if tool_name == "memory_get":
        text = normalize_optional_string((details or {}).get("text")) if details else None
        if text is not None:
            return len(text) > 0
        return bool(_MEMORY_GET_TEXT_RE.search(content))
    if tool_name == "lcm_grep":
        total_matches = (details or {}).get("totalMatches") if details else None
        if (
            isinstance(total_matches, int | float)
            and not math.isnan(total_matches)
            and total_matches > 0
        ):
            return True
        return bool(_LCM_GREP_RESULTS_RE.search(content))
    if tool_name == "lcm_describe":
        type_value = normalize_optional_string((details or {}).get("type")) if details else None
        if normalize_optional_string(
            (details or {}).get("id") if details else None
        ) and type_value in (
            "summary",
            "file",
        ):
            return True
        return bool(_LCM_SUMMARY_RE.search(content) or _LCM_FILE_RE.search(content))
    if tool_name == "lcm_expand_query":
        expanded = (details or {}).get("expandedSummaryCount") if details else None
        if (
            isinstance(expanded, int | float)
            and not math.isnan(expanded)
            and expanded > 0
            and bool(normalize_optional_string((details or {}).get("answer") if details else None))
        ):
            return True
        try:
            parsed = as_optional_record(_json_loads(content))
        except ValueError:
            parsed = None
        if parsed is None:
            return False
        pexp = parsed.get("expandedSummaryCount")
        return bool(
            isinstance(pexp, int | float)
            and not math.isnan(pexp)
            and pexp > 0
            and bool(normalize_optional_string(parsed.get("answer")))
        )
    normalized_content = normalize_optional_string(content)
    explicit_evidence = read_explicit_memory_evidence(details) if details else None
    structured_evidence = (
        read_structured_memory_evidence_from_content(message.get("content"))
        if normalized_content
        else None
    )
    return (
        bool(normalized_content)
        and explicit_evidence is not False
        and structured_evidence is not False
    )


# Suppress unused import warning while keeping the symbol
# available for explicit per-call overrides.
_ = truncate_utf16_safe


__all__ = [
    "create_active_memory_hook_deadline",
    "extract_active_memory_search_debug_from_session_record",
    "extract_tool_result_name_from_session_record",
    "file_transcript_source",
    "has_terminal_unavailable_memory_result_in_session_record",
    "has_unavailable_memory_result_in_session_record",
    "has_usable_memory_result_in_session_record",
    "is_unavailable_memory_search_debug",
    "resolve_transcript_read_limits",
    "stream_active_memory_transcript_records",
    "transcript_source_from_returned_session_file",
]
