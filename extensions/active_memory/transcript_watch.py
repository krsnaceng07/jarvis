"""transcript_watch — transcript state merging + terminal-memory-search watch.

OpenClaw parity: mirrors
``extensions/active-memory/transcript-watch.ts``.

Phase 4.2b step 2: ports the transcript-state aggregation
helpers and the polling ``TerminalMemorySearchWatch``
used by the recall loop to bail out early on definitive
memory-tool unavailability.

Surface
-------
- ``read_active_memory_transcript_state`` — walk one
  source, aggregate ``searchDebug``,
  ``hasUsableMemoryResult``, and
  ``hasUnavailableMemorySearchResult``.
- ``read_active_memory_search_debug`` — convenience
  wrapper that returns just the debug dict.
- ``read_merged_active_memory_transcript_state`` — walk
  multiple sources, dedup by ``agentId/sessionId/sessionKey/storePath/threadId``
  for runtime and by ``sessionFile`` for file.
- ``read_terminal_memory_search_result`` — for one source,
  return ``{"status": "unavailable", "hasUsableMemoryResult", "searchDebug"}``
  if *every* recall-path tool in ``tools_allow`` (minus
  ``memory_get``) has hit a terminal unavailability.
- ``read_terminal_memory_search_result_from_sources`` —
  same, walking each source in order.
- ``watch_terminal_memory_search_result`` — start a
  background poll, return a ``TerminalMemorySearchWatch``
  with ``promise`` and ``stop()``. The poll runs every
  ``TERMINAL_MEMORY_SEARCH_POLL_INTERVAL_MS`` until the
  abort signal fires or the watch is stopped.
- ``normalize_search_debug`` / ``read_active_memory_search_debug_from_run_result``
  / ``read_active_memory_session_file_from_run_result`` —
  extract the search debug + session file path from a
  sub-agent run result.

Dependencies
============
- ``extensions.active_memory.transcript`` — the
  record-streaming + per-record evidence probes.
- ``extensions.active_memory.types`` — recall-flow types
  and constants.
- ``jarvis_sdk.as_optional_record`` +
  ``normalize_optional_string`` (string-coerce).
"""

from __future__ import annotations

import asyncio
import contextlib
import math
from typing import Any, cast

from jarvis_sdk import (
    as_optional_record,
    normalize_lowercase_string_or_empty,
    normalize_optional_string,
)

from .transcript import (
    extract_active_memory_search_debug_from_session_record,
    extract_tool_result_name_from_session_record,
    file_transcript_source,
    has_terminal_unavailable_memory_result_in_session_record,
    has_unavailable_memory_result_in_session_record,
    has_usable_memory_result_in_session_record,
    stream_active_memory_transcript_records,
)
from .types import (
    TERMINAL_MEMORY_SEARCH_POLL_INTERVAL_MS,
    ActiveMemorySearchDebug,
    ActiveMemoryTranscriptSource,
    TerminalMemorySearchResult,
    TerminalMemorySearchWatch,
    TranscriptReadLimits,
)

# ── Single-source state ──────────────────────────────────────────


async def read_active_memory_transcript_state(
    source: ActiveMemoryTranscriptSource | str,
    limits: TranscriptReadLimits | None = None,
    tools_allow: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Walk one transcript source and aggregate memory-tool evidence.

    Mirrors OpenClaw's ``readActiveMemoryTranscriptState``.
    """
    search_debug: ActiveMemorySearchDebug | None = None
    has_usable = False
    has_unavailable = False

    def _on_record(record: Any) -> bool:
        nonlocal search_debug, has_usable, has_unavailable
        debug = extract_active_memory_search_debug_from_session_record(record)
        if debug:
            search_debug = debug
        has_unavailable = has_unavailable or has_unavailable_memory_result_in_session_record(
            record, tools_allow
        )
        has_usable = has_usable or has_usable_memory_result_in_session_record(record, tools_allow)
        return False

    resolved_source = file_transcript_source(source) if isinstance(source, str) else source
    await stream_active_memory_transcript_records(
        {
            "source": resolved_source,
            "limits": limits,
            "onRecord": _on_record,
        }
    )
    return {
        "searchDebug": search_debug,
        "hasUsableMemoryResult": has_usable,
        "hasUnavailableMemorySearchResult": has_unavailable,
    }


async def read_active_memory_search_debug(
    source: ActiveMemoryTranscriptSource | str,
    limits: TranscriptReadLimits | None = None,
) -> ActiveMemorySearchDebug | None:
    """Return the search-debug dict from a single source (or ``None``)."""
    state = await read_active_memory_transcript_state(source, limits)
    return state.get("searchDebug")


# ── Merged multi-source state ─────────────────────────────────────


def _source_key(source: ActiveMemoryTranscriptSource) -> str:
    if source.get("kind") == "runtime":
        target = source.get("target", {}) or {}
        return (
            f"runtime:{target.get('agentId', '')}:{target.get('sessionId', '')}:"
            f"{target.get('sessionKey', '')}:{target.get('storePath', '')}:"
            f"{target.get('threadId', '')}"
        )
    return f"file:{source.get('sessionFile', '')}"


async def read_merged_active_memory_transcript_state(
    params: dict[str, Any],
) -> dict[str, Any]:
    """Walk a list of sources, deduping by key, merging the state.

    Mirrors OpenClaw's ``readMergedActiveMemoryTranscriptState``.
    """
    search_debug: ActiveMemorySearchDebug | None = None
    has_usable = False
    has_unavailable = False
    seen: set[str] = set()
    tools_allow = params.get("toolsAllow") or ()
    for source in params.get("sources") or ():
        key = _source_key(source)
        if key in seen:
            continue
        seen.add(key)
        state = await read_active_memory_transcript_state(
            source, limits=None, tools_allow=tools_allow
        )
        if state.get("searchDebug") and not search_debug:
            search_debug = state["searchDebug"]
        has_usable = has_usable or bool(state.get("hasUsableMemoryResult"))
        has_unavailable = has_unavailable or bool(state.get("hasUnavailableMemorySearchResult"))
    return {
        "searchDebug": search_debug,
        "hasUsableMemoryResult": has_usable,
        "hasUnavailableMemorySearchResult": has_unavailable,
    }


# ── Terminal-memory-search detection ─────────────────────────────


async def read_terminal_memory_search_result(
    source: ActiveMemoryTranscriptSource,
    limits: TranscriptReadLimits | None = None,
    tools_allow: tuple[str, ...] | list[str] | None = None,
) -> TerminalMemorySearchResult | None:
    """Return ``{"status": "unavailable", ...}`` if every recall path is dead.

    Mirrors OpenClaw's ``readTerminalMemorySearchResult``.
    The "recall path" tools are the ones in ``tools_allow``
    except ``memory_get`` (which consumes a path discovered
    by another tool). When every recall-path tool has
    reported a terminal unavailability, the watch resolves
    so the recall loop can short-circuit the wait.
    """
    recall_path_names: set[str] = {
        name
        for name in (normalize_lowercase_string_or_empty(t) for t in (tools_allow or ()))
        if name and name != "memory_get"
    }
    if not recall_path_names:
        return None
    unavailable_path_names: set[str] = set()
    has_usable = False
    search_debug: ActiveMemorySearchDebug | None = None
    tools_allow_list = list(tools_allow) if tools_allow else []

    def _on_record(record: Any) -> bool:
        nonlocal has_usable, search_debug
        has_usable = has_usable or has_usable_memory_result_in_session_record(
            record, tools_allow_list
        )
        debug = extract_active_memory_search_debug_from_session_record(record)
        if debug and not search_debug:
            search_debug = debug
        tool_name = extract_tool_result_name_from_session_record(record)
        if not tool_name or tool_name not in recall_path_names:
            return False
        if has_terminal_unavailable_memory_result_in_session_record(record, tools_allow_list):
            unavailable_path_names.add(tool_name)
        else:
            unavailable_path_names.discard(tool_name)
        return False

    await stream_active_memory_transcript_records(
        {"source": source, "limits": limits, "onRecord": _on_record}
    )
    if len(unavailable_path_names) != len(recall_path_names):
        return None
    return cast(
        TerminalMemorySearchResult,
        {
            "status": "unavailable",
            "hasUsableMemoryResult": has_usable,
            "searchDebug": search_debug,
        },
    )


async def read_terminal_memory_search_result_from_sources(
    sources: tuple[ActiveMemoryTranscriptSource, ...] | list[ActiveMemoryTranscriptSource],
    limits: TranscriptReadLimits | None,
    tools_allow: tuple[str, ...] | list[str],
) -> TerminalMemorySearchResult | None:
    """Walk sources in order, returning the first terminal result."""
    for source in sources:
        result = await read_terminal_memory_search_result(source, limits, tools_allow)
        if result:
            return result
    return None


def watch_terminal_memory_search_result(
    params: dict[str, Any],
) -> TerminalMemorySearchWatch:
    """Start a background poll for terminal-memory-search state.

    Mirrors OpenClaw's ``watchTerminalMemorySearchResult``.
    Returns a ``TerminalMemorySearchWatch`` with ``promise``
    (resolves with a ``TerminalMemorySearchResult``) and
    ``stop()`` (cancels the poll and the abort listener).
    The poll runs every
    ``TERMINAL_MEMORY_SEARCH_POLL_INTERVAL_MS`` until the
    abort signal fires or the watch is stopped.
    """
    get_sources = params["getTranscriptSources"]
    abort_signal: Any = params["abortSignal"]
    tools_allow: list[str] = list(params.get("toolsAllow") or ())
    state: dict[str, Any] = {
        "stopped": False,
        "timeout_id": None,
        "in_flight": False,
        "resolve": lambda *_a, **_k: None,
    }
    future: asyncio.Future[TerminalMemorySearchResult] = asyncio.Future()

    def _resolve(value: TerminalMemorySearchResult) -> None:
        if not future.done():
            future.set_result(value)

    state["resolve"] = _resolve

    def stop() -> None:
        if state["stopped"]:
            return
        state["stopped"] = True
        timeout_id = state.get("timeout_id")
        if timeout_id is not None:
            with contextlib.suppress(Exception):
                timeout_id.cancel()
            state["timeout_id"] = None
        with contextlib.suppress(ValueError, NotImplementedError):  # pragma: no cover
            abort_signal.remove_event_listener("abort", on_abort)

    def on_abort() -> None:
        stop()

    def finish(result: TerminalMemorySearchResult) -> None:
        stop()
        state["resolve"](result)

    async def tick() -> None:
        if state["stopped"] or state["in_flight"]:
            return
        if abort_signal.aborted:
            stop()
            return
        state["in_flight"] = True
        try:
            result = await read_terminal_memory_search_result_from_sources(
                get_sources(), None, tools_allow
            )
            if result:
                finish(result)
                return
        except Exception as exc:
            # The transcript poll is best-effort; a single failure
            # shouldn't abort the watch.
            import logging

            logging.getLogger(__name__).debug("active-memory terminal-search poll failed: %s", exc)
        finally:
            state["in_flight"] = False
        schedule()

    def schedule() -> None:
        if state["stopped"]:
            return
        loop = asyncio.get_event_loop()
        handle = loop.call_later(
            TERMINAL_MEMORY_SEARCH_POLL_INTERVAL_MS / 1000.0,
            lambda: asyncio.ensure_future(tick()),
        )
        state["timeout_id"] = handle

    with contextlib.suppress(NotImplementedError, TypeError):  # pragma: no cover
        abort_signal.add_event_listener("abort", on_abort, once=True)  # type: ignore[arg-type]
    _tick_task = asyncio.ensure_future(tick())
    _ = _tick_task  # RUF006 — keep the future alive
    return {"promise": future, "stop": stop}


# ── Run-result extraction ─────────────────────────────────────────


def normalize_search_debug(value: Any) -> ActiveMemorySearchDebug | None:
    """Normalize a search-debug dict to the recall-flow shape.

    Mirrors OpenClaw's ``normalizeSearchDebug``. Returns
    ``None`` if the input doesn't have any recognized
    fields.
    """
    record = as_optional_record(value)
    if record is None:
        return None
    search_ms_value = record.get("searchMs")
    hits_value = record.get("hits")
    normalized = cast(
        ActiveMemorySearchDebug,
        {
            "backend": normalize_optional_string(record.get("backend")),
            "configuredMode": normalize_optional_string(record.get("configuredMode")),
            "effectiveMode": normalize_optional_string(record.get("effectiveMode")),
            "fallback": normalize_optional_string(record.get("fallback")),
            "searchMs": (
                search_ms_value
                if isinstance(search_ms_value, int | float) and not math.isnan(search_ms_value)
                else None
            ),
            "hits": (
                hits_value
                if isinstance(hits_value, int | float) and not math.isnan(hits_value)
                else None
            ),
            "warning": normalize_optional_string(record.get("warning"))
            or normalize_optional_string(record.get("reason")),
            "action": normalize_optional_string(record.get("action")),
            "error": normalize_optional_string(record.get("error")),
        },
    )
    if any(
        [
            normalized.get("backend"),
            normalized.get("configuredMode"),
            normalized.get("effectiveMode"),
            normalized.get("fallback"),
            isinstance(normalized.get("searchMs"), int | float),
            isinstance(normalized.get("hits"), int | float),
            normalized.get("warning"),
            normalized.get("action"),
            normalized.get("error"),
        ]
    ):
        return cast(ActiveMemorySearchDebug, normalized)
    return None


def read_active_memory_search_debug_from_run_result(result: Any) -> ActiveMemorySearchDebug | None:
    """Extract the search debug from a sub-agent run result.

    Mirrors OpenClaw's ``readActiveMemorySearchDebugFromRunResult``.
    Looks in four places (in order): ``result.meta.activeMemorySearchDebug``,
    ``result.meta.memorySearchDebug``, ``result.activeMemorySearchDebug``,
    ``result.memorySearchDebug``.
    """
    record = as_optional_record(result)
    meta = as_optional_record((record or {}).get("meta"))
    return (
        normalize_search_debug((meta or {}).get("activeMemorySearchDebug"))
        or normalize_search_debug((meta or {}).get("memorySearchDebug"))
        or normalize_search_debug((record or {}).get("activeMemorySearchDebug"))
        or normalize_search_debug((record or {}).get("memorySearchDebug"))
    )


def read_active_memory_session_file_from_run_result(result: Any) -> str | None:
    """Extract the session-file path from a sub-agent run result.

    Mirrors OpenClaw's ``readActiveMemorySessionFileFromRunResult``.
    """
    record = as_optional_record(result)
    meta = as_optional_record((record or {}).get("meta"))
    agent_meta = as_optional_record((meta or {}).get("agentMeta"))
    return normalize_optional_string(
        (agent_meta or {}).get("sessionFile")
    ) or normalize_optional_string((meta or {}).get("sessionFile"))


__all__ = [
    "normalize_search_debug",
    "read_active_memory_search_debug",
    "read_active_memory_search_debug_from_run_result",
    "read_active_memory_session_file_from_run_result",
    "read_merged_active_memory_transcript_state",
    "read_terminal_memory_search_result",
    "read_terminal_memory_search_result_from_sources",
    "watch_terminal_memory_search_result",
]
