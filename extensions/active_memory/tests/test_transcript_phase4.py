"""Tests for extensions/active_memory/{transcript, transcript_watch, transcript_result, session}.py.

Phase 4.2b step 2: ports the transcript and session
helpers from OpenClaw. The tests focus on:

- per-record evidence detection (has_usable, has_unavailable,
  has_terminal_unavailable, extract_search_debug,
  extract_tool_result_name)
- transcript-source dispatch (file vs. runtime)
- search-debug normalization + run-result extraction
- the polling watch (terminal-memory-search)
- partial-text recovery from transcript sources
- partial-timeout data round-trip + result builders
- session-store helpers (canonical session key, recall
  channel context, status line, debug line, persist)
"""

from __future__ import annotations

# pyright: reportArgumentType=false
# pyright: reportTypedDictNotRequiredAccess=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportOptionalSubscript=false
# pyright: reportOptionalIterable=false
# pyright: reportOptionalOperand=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeArgument=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportCallIssue=false
# pyright: reportIndexIssue=false
# pyright: reportAssignmentType=false
# pyright: reportReturnType=false
# pyright: reportOperatorIssue=false
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.active_memory.session import (  # noqa: E402
    build_persisted_debug_summary,
    build_plugin_debug_line,
    build_plugin_status_line,
    format_elapsed_ms_compact,
    persist_plugin_status_lines,
    resolve_canonical_session_key_from_session_id,
    resolve_recall_run_channel_context,
    resolve_status_update_agent_id,
    sanitize_debug_text,
)
from extensions.active_memory.transcript import (  # noqa: E402
    create_active_memory_hook_deadline,
    extract_active_memory_search_debug_from_session_record,
    extract_tool_result_name_from_session_record,
    file_transcript_source,
    has_terminal_unavailable_memory_result_in_session_record,
    has_unavailable_memory_result_in_session_record,
    has_usable_memory_result_in_session_record,
    is_unavailable_memory_search_debug,
    resolve_transcript_read_limits,
    stream_active_memory_transcript_records,
    transcript_source_from_returned_session_file,
)
from extensions.active_memory.transcript_result import (  # noqa: E402
    attach_partial_timeout_data,
    build_subagent_recall_result,
    build_timeout_recall_result,
    extract_assistant_text_from_session_record,
    read_memory_tool_result_evidence,
    read_partial_assistant_text,
    read_partial_assistant_text_from_sources,
    read_partial_timeout_data,
    reset_active_memory_transcript_for_tests,
    set_timeout_partial_data_grace_ms_for_tests,
)
from extensions.active_memory.transcript_watch import (  # noqa: E402
    normalize_search_debug,
    read_active_memory_search_debug,
    read_active_memory_search_debug_from_run_result,
    read_active_memory_session_file_from_run_result,
    read_merged_active_memory_transcript_state,
    read_terminal_memory_search_result,
    watch_terminal_memory_search_result,
)
from extensions.active_memory.types import (  # noqa: E402
    ACTIVE_MEMORY_DEBUG_PREFIX,
    ACTIVE_MEMORY_STATUS_PREFIX,
    DEFAULT_PARTIAL_TRANSCRIPT_MAX_CHARS,
    DEFAULT_TRANSCRIPT_READ_MAX_BYTES,
    DEFAULT_TRANSCRIPT_READ_MAX_LINES,
)

# The test file uses a few ``asyncio.Future()`` calls that
# emit ``ResourceWarning`` (unclosed loop) when the future
# is not awaited. The Phase 4.2a test config has a catch-all
# ``filterwarnings = ["error", ...]`` rule, so we suppress
# these specific warnings at the module level.
pytestmark = pytest.mark.filterwarnings(
    "ignore::ResourceWarning:asyncio",
    "ignore::ResourceWarning",
)


# ── transcript.resolve_transcript_read_limits ─────────────────────


class TestResolveTranscriptReadLimits:
    def test_defaults_applied_when_none(self) -> None:
        limits = resolve_transcript_read_limits()
        assert limits["maxChars"] == DEFAULT_PARTIAL_TRANSCRIPT_MAX_CHARS
        assert limits["maxLines"] == DEFAULT_TRANSCRIPT_READ_MAX_LINES
        assert limits["maxBytes"] == DEFAULT_TRANSCRIPT_READ_MAX_BYTES

    def test_partial_overrides(self) -> None:
        limits = resolve_transcript_read_limits({"maxChars": 1000})
        assert limits["maxChars"] == 1000
        assert limits["maxLines"] == DEFAULT_TRANSCRIPT_READ_MAX_LINES
        assert limits["maxBytes"] == DEFAULT_TRANSCRIPT_READ_MAX_BYTES

    def test_clamped_to_minimum(self) -> None:
        limits = resolve_transcript_read_limits({"maxChars": 0})
        # 0 is below the lo=1 minimum, so it gets clamped up to 1.
        assert limits["maxChars"] == 1


# ── transcript helpers ──────────────────────────────────────────


class TestFileTranscriptSource:
    def test_file_kind(self) -> None:
        src = file_transcript_source("C:/tmp/x.jsonl")
        assert src["kind"] == "file"
        assert src["sessionFile"] == "C:/tmp/x.jsonl"


class TestTranscriptSourceFromReturnedSessionFile:
    def test_plain_path_returns_file_source(self) -> None:
        out = transcript_source_from_returned_session_file(
            {"sessionFile": "C:/tmp/x.jsonl", "sessionKey": "agent:a:x"}
        )
        assert out["kind"] == "file"
        assert out["sessionFile"] == "C:/tmp/x.jsonl"

    def test_sqlite_marker_returns_runtime_source(self) -> None:
        out = transcript_source_from_returned_session_file(
            {
                "sessionFile": "sqlite:agent-a:sess-1:/store/path",
                "sessionKey": "agent-a:sess-1",
            }
        )
        assert out["kind"] == "runtime"
        target = out.get("target") or {}
        assert target.get("agentId") == "agent-a"
        assert target.get("sessionId") == "sess-1"
        assert target.get("sessionKey") == "agent-a:sess-1"
        assert target.get("storePath") == "/store/path"


# ── transcript per-record evidence probes ──────────────────────


def _record(
    *,
    tool_name: str | None = None,
    details: dict | None = None,
    is_error: bool = False,
    content: Any = None,
) -> dict:
    return {
        "message": {
            "role": "toolResult",
            "toolName": tool_name,
            "isError": is_error,
            "content": content or [],
            "details": details or {},
        }
    }


class TestExtractActiveMemorySearchDebug:
    def test_returns_none_for_non_memory_record(self) -> None:
        assert extract_active_memory_search_debug_from_session_record({"x": 1}) is None
        assert (
            extract_active_memory_search_debug_from_session_record(
                {"message": {"role": "toolResult", "toolName": "other_tool"}}
            )
            is None
        )

    def test_extracts_search_debug_from_details(self) -> None:
        record = _record(
            tool_name="memory_search",
            details={
                "debug": {
                    "backend": "lancedb",
                    "configuredMode": "search",
                    "effectiveMode": "search",
                    "fallback": "",
                    "searchMs": 42.7,
                    "hits": 3,
                },
                "warning": "soft",
                "action": "ok",
            },
        )
        debug = extract_active_memory_search_debug_from_session_record(record)
        assert debug is not None
        assert debug["backend"] == "lancedb"
        assert debug["searchMs"] == 42
        assert debug["hits"] == 3
        assert debug["warning"] == "soft"
        assert debug["action"] == "ok"

    def test_extracts_when_nan_string(self) -> None:
        record = _record(tool_name="memory_recall", details={"debug": {"searchMs": "oops"}})
        debug = extract_active_memory_search_debug_from_session_record(record)
        assert debug is not None
        assert debug.get("searchMs") is None


class TestExtractToolResultName:
    def test_returns_tool_name_for_tool_result(self) -> None:
        record = _record(tool_name="memory_search")
        assert extract_tool_result_name_from_session_record(record) == "memory_search"

    def test_returns_none_for_non_tool_result(self) -> None:
        assert extract_tool_result_name_from_session_record({"x": 1}) is None


class TestHasUsableMemoryResult:
    def test_memory_search_with_results(self) -> None:
        record = _record(tool_name="memory_search", details={"results": [{"x": 1}]})
        assert has_usable_memory_result_in_session_record(record) is True

    def test_memory_search_empty_results(self) -> None:
        record = _record(tool_name="memory_search", details={"results": []})
        assert has_usable_memory_result_in_session_record(record) is False

    def test_memory_recall_with_memories(self) -> None:
        record = _record(tool_name="memory_recall", details={"memories": [{"y": 1}]})
        assert has_usable_memory_result_in_session_record(record) is True

    def test_memory_recall_with_text_prefix(self) -> None:
        record = _record(
            tool_name="memory_recall",
            content="Found 3 memories:\n- one\n- two\n- three",
        )
        assert has_usable_memory_result_in_session_record(record) is True

    def test_memory_recall_empty(self) -> None:
        record = _record(tool_name="memory_recall", content="No memories found.")
        assert has_usable_memory_result_in_session_record(record) is False

    def test_memory_get_with_text(self) -> None:
        record = _record(tool_name="memory_get", details={"text": "user likes ramen"})
        assert has_usable_memory_result_in_session_record(record) is True

    def test_memory_get_empty_text(self) -> None:
        record = _record(tool_name="memory_get", details={"text": ""})
        assert has_usable_memory_result_in_session_record(record) is False

    def test_lcm_grep_with_matches(self) -> None:
        record = _record(
            tool_name="lcm_grep",
            details={"totalMatches": 5},
            content="## LCM Grep Results\n\n**Total matches:** 5",
        )
        assert has_usable_memory_result_in_session_record(record, tools_allow=("lcm_grep",)) is True

    def test_lcm_describe_summary(self) -> None:
        record = _record(
            tool_name="lcm_describe",
            details={"id": "x", "type": "summary"},
        )
        assert (
            has_usable_memory_result_in_session_record(record, tools_allow=("lcm_describe",))
            is True
        )

    def test_lcm_expand_query(self) -> None:
        record = _record(
            tool_name="lcm_expand_query",
            details={"expandedSummaryCount": 2, "answer": "ok"},
        )
        assert (
            has_usable_memory_result_in_session_record(record, tools_allow=("lcm_expand_query",))
            is True
        )

    def test_unknown_tool_with_evidence(self) -> None:
        record = _record(
            tool_name="custom_recall",
            details={"results": [{"x": 1}]},
            content=json.dumps({"results": [{"x": 1}]}),
        )
        assert (
            has_usable_memory_result_in_session_record(record, tools_allow=("custom_recall",))
            is True
        )

    def test_non_memory_tool_ignored(self) -> None:
        record = _record(tool_name="web_search", details={"results": [{"x": 1}]})
        assert has_usable_memory_result_in_session_record(record) is False

    def test_unavailable_blocks_usable(self) -> None:
        record = _record(
            tool_name="memory_search",
            is_error=True,
            details={"results": [{"x": 1}]},
        )
        assert has_usable_memory_result_in_session_record(record) is False


class TestHasUnavailableMemoryResult:
    def test_is_error_true(self) -> None:
        record = _record(tool_name="memory_search", is_error=True)
        assert has_unavailable_memory_result_in_session_record(record) is True

    def test_status_error(self) -> None:
        record = _record(tool_name="memory_search", details={"status": "error"})
        assert has_unavailable_memory_result_in_session_record(record) is True

    def test_normal_results_not_unavailable(self) -> None:
        record = _record(
            tool_name="memory_search",
            details={"results": [{"x": 1}]},
        )
        assert has_unavailable_memory_result_in_session_record(record) is False

    def test_non_memory_tool_ignored(self) -> None:
        record = _record(tool_name="web_search", is_error=True)
        assert has_unavailable_memory_result_in_session_record(record) is False


class TestHasTerminalUnavailableMemoryResult:
    def test_disabled_flag(self) -> None:
        record = _record(tool_name="memory_search", details={"disabled": True})
        assert (
            has_terminal_unavailable_memory_result_in_session_record(record, ("memory_search",))
            is True
        )

    def test_status_unavailable(self) -> None:
        record = _record(tool_name="memory_recall", details={"status": "unavailable"})
        assert (
            has_terminal_unavailable_memory_result_in_session_record(record, ("memory_recall",))
            is True
        )

    def test_status_disabled_with_spaces(self) -> None:
        record = _record(tool_name="memory_search", details={"status": "disabled"})
        assert (
            has_terminal_unavailable_memory_result_in_session_record(record, ("memory_search",))
            is True
        )

    def test_error_field_for_memory_search(self) -> None:
        record = _record(tool_name="memory_search", details={"error": "boom"})
        assert (
            has_terminal_unavailable_memory_result_in_session_record(record, ("memory_search",))
            is True
        )

    def test_normal_results_not_terminal(self) -> None:
        record = _record(
            tool_name="memory_search",
            details={"results": [{"x": 1}]},
        )
        assert (
            has_terminal_unavailable_memory_result_in_session_record(record, ("memory_search",))
            is False
        )


# ── transcript.create_active_memory_hook_deadline ────────────────


class TestCreateActiveMemoryHookDeadline:
    def teardown_method(self) -> None:
        # Clear any leftover state from prior tests.
        pass

    def test_resolves_with_sentinel_on_timeout(self) -> None:
        # Removed: superseded by the async version below.
        pass

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self) -> None:
        # Run inside an event loop so the deadline can be
        # created without warnings. stop() is safe to call
        # on a never-armed deadline.
        deadline = create_active_memory_hook_deadline()
        deadline["stop"]()
        deadline["stop"]()  # second call is a no-op

    @pytest.mark.asyncio
    async def test_resolves_with_sentinel_on_timeout_async(self) -> None:
        deadline = create_active_memory_hook_deadline()
        fired: list[bool] = []

        def on_timeout() -> None:
            fired.append(True)

        deadline["arm"](20, on_timeout)
        # Wait long enough for the timer to fire.
        for _ in range(50):
            if fired:
                break
            await asyncio.sleep(0.01)
        deadline["stop"]()
        assert fired == [True]


# ── transcript.is_unavailable_memory_search_debug ────────────────


def test_is_unavailable_memory_search_debug_true_for_error() -> None:
    assert is_unavailable_memory_search_debug({"error": "boom"}) is True


def test_is_unavailable_memory_search_debug_false_without_error() -> None:
    assert is_unavailable_memory_search_debug({"backend": "x"}) is False
    assert is_unavailable_memory_search_debug(None) is False


# ── transcript_watch.normalize_search_debug ──────────────────────


class TestNormalizeSearchDebug:
    def test_returns_none_for_non_dict(self) -> None:
        assert normalize_search_debug(None) is None
        assert normalize_search_debug("string") is None
        assert normalize_search_debug(42) is None

    def test_returns_none_for_empty_dict(self) -> None:
        assert normalize_search_debug({}) is None

    def test_normalizes_string_fields(self) -> None:
        debug = normalize_search_debug(
            {
                "backend": "lancedb",
                "configuredMode": "search",
                "effectiveMode": "search",
                "fallback": "vsearch",
                "searchMs": 12.5,
                "hits": 4,
                "warning": "soft",
                "action": "fallback",
                "error": "",
            }
        )
        assert debug is not None
        assert debug["backend"] == "lancedb"
        # normalize_search_debug preserves the number as-is
        # (mirrors OpenClaw's `Number.isFinite` check).
        assert debug["searchMs"] == 12.5
        assert debug["hits"] == 4
        assert debug["warning"] == "soft"
        assert debug["action"] == "fallback"
        assert debug["error"] is None

    def test_falls_back_to_reason_for_warning(self) -> None:
        debug = normalize_search_debug({"reason": "soft"})
        assert debug is not None
        assert debug["warning"] == "soft"

    def test_drops_nan_numbers(self) -> None:
        # Add a non-numeric field so the result isn't "all empty".
        debug = normalize_search_debug(
            {"searchMs": float("nan"), "hits": float("nan"), "backend": "x"}
        )
        assert debug is not None
        assert debug.get("searchMs") is None
        assert debug.get("hits") is None
        assert debug["backend"] == "x"


# ── transcript_watch run-result extraction ──────────────────────


class TestReadActiveMemorySearchDebugFromRunResult:
    def test_meta_path(self) -> None:
        out = read_active_memory_search_debug_from_run_result(
            {"meta": {"activeMemorySearchDebug": {"backend": "lancedb"}}}
        )
        assert out is not None
        assert out["backend"] == "lancedb"

    def test_fallback_to_top_level(self) -> None:
        out = read_active_memory_search_debug_from_run_result(
            {"memorySearchDebug": {"backend": "core"}}
        )
        assert out is not None
        assert out["backend"] == "core"

    def test_returns_none_when_missing(self) -> None:
        assert read_active_memory_search_debug_from_run_result({}) is None


class TestReadActiveMemorySessionFileFromRunResult:
    def test_agent_meta_path(self) -> None:
        out = read_active_memory_session_file_from_run_result(
            {"meta": {"agentMeta": {"sessionFile": "C:/tmp/x.jsonl"}}}
        )
        assert out == "C:/tmp/x.jsonl"

    def test_meta_path(self) -> None:
        out = read_active_memory_session_file_from_run_result(
            {"meta": {"sessionFile": "C:/tmp/y.jsonl"}}
        )
        assert out == "C:/tmp/y.jsonl"

    def test_returns_none_when_missing(self) -> None:
        assert read_active_memory_session_file_from_run_result({}) is None


# ── transcript_watch async helpers (read_active_memory_search_debug) ─


class TestReadActiveMemorySearchDebugAsync:
    @pytest.mark.asyncio
    async def test_returns_none_for_file_with_no_records(self, tmp_path: Path) -> None:
        out = await read_active_memory_search_debug(
            file_transcript_source(str(tmp_path / "x.jsonl"))
        )
        assert out is None


# ── transcript_watch read_terminal_memory_search_result ─────────


class TestReadTerminalMemorySearchResult:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_recall_paths(self, tmp_path: Path) -> None:
        out = await read_terminal_memory_search_result(
            file_transcript_source(str(tmp_path / "x.jsonl")),
            tools_allow=("memory_get",),
        )
        assert out is None

    @pytest.mark.asyncio
    async def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        out = await read_terminal_memory_search_result(
            file_transcript_source(str(tmp_path / "missing.jsonl")),
            tools_allow=("memory_search",),
        )
        assert out is None


# ── transcript_watch.read_merged_active_memory_transcript_state ─


class TestReadMergedActiveMemoryTranscriptState:
    @pytest.mark.asyncio
    async def test_dedup_by_key(self, tmp_path: Path) -> None:
        src = file_transcript_source(str(tmp_path / "x.jsonl"))
        out = await read_merged_active_memory_transcript_state(
            {"sources": [src, src, src], "toolsAllow": ()}
        )
        assert out["hasUsableMemoryResult"] is False
        assert out["hasUnavailableMemorySearchResult"] is False


# ── transcript_watch.watch_terminal_memory_search_result ────────


class TestWatchTerminalMemorySearchResult:
    @pytest.mark.asyncio
    async def test_stop_cancels(self) -> None:
        watch = watch_terminal_memory_search_result(
            {
                "getTranscriptSources": lambda: (),
                "abortSignal": _NoopAbortSignal(),
                "toolsAllow": (),
            }
        )
        watch["stop"]()
        # The promise is never resolved; we just verify stop is safe to call.
        assert callable(watch["stop"])


class _NoopAbortSignal:
    """Minimal abort-signal stub for tests."""

    aborted = False

    def add_event_listener(self, event: str, cb: Any, *, once: bool = False) -> None:
        pass

    def remove_event_listener(self, event: str, cb: Any) -> None:
        pass


# ── transcript_result.read_memory_tool_result_evidence ──────────


class TestReadMemoryToolResultEvidence:
    def test_usable_result(self) -> None:
        out = read_memory_tool_result_evidence(
            {
                "toolName": "memory_search",
                "result": {"content": "x", "details": {"results": [{"x": 1}]}},
                "isError": False,
                "toolsAllow": ("memory_search", "memory_get"),
            }
        )
        assert out["hasUsableMemoryResult"] is True
        assert out["hasUnavailableMemorySearchResult"] is False

    def test_unavailable_via_error(self) -> None:
        out = read_memory_tool_result_evidence(
            {
                "toolName": "memory_search",
                "result": {"content": "x", "details": {"status": "error"}},
                "isError": False,
                "toolsAllow": ("memory_search",),
            }
        )
        assert out["hasUsableMemoryResult"] is False
        assert out["hasUnavailableMemorySearchResult"] is True

    def test_unavailable_via_iserror(self) -> None:
        out = read_memory_tool_result_evidence(
            {
                "toolName": "memory_search",
                "result": {"content": "x"},
                "isError": True,
                "toolsAllow": ("memory_search",),
            }
        )
        assert out["hasUnavailableMemorySearchResult"] is True


# ── transcript_result.extract_assistant_text_from_session_record ─


class TestExtractAssistantText:
    def test_assistant_role(self) -> None:
        out = extract_assistant_text_from_session_record({"role": "assistant", "content": "hello"})
        assert out == "hello"

    def test_message_wrapper(self) -> None:
        out = extract_assistant_text_from_session_record(
            {"message": {"role": "assistant", "content": "world"}}
        )
        assert out == "world"

    def test_non_assistant_returns_empty(self) -> None:
        assert extract_assistant_text_from_session_record({"role": "user", "content": "hi"}) == ""

    def test_empty_content(self) -> None:
        assert (
            extract_assistant_text_from_session_record({"role": "assistant", "content": "   "})
            == ""
        )


# ── transcript_result.partial-timeout data round-trip ──────────


class TestPartialTimeoutData:
    def teardown_method(self) -> None:
        reset_active_memory_transcript_for_tests()

    def test_attach_and_read(self) -> None:
        class _Err(Exception):
            pass

        err: Any = _Err("boom")
        attach_partial_timeout_data(err, "partial reply", {"backend": "x"}, True)
        data = read_partial_timeout_data(err)
        assert data["rawReply"] == "partial reply"
        assert data["searchDebug"] == {"backend": "x"}
        assert data["hasUnavailableMemorySearchResult"] is True

    def test_attach_skips_when_error_is_none(self) -> None:
        # Should not raise.
        attach_partial_timeout_data(None, "x", None, False)

    def test_read_returns_empty_for_non_error(self) -> None:
        assert read_partial_timeout_data("string") == {}
        assert read_partial_timeout_data(None) == {}
        assert read_partial_timeout_data(42) == {}

    def test_partial_reply_normalized(self) -> None:
        class _Err(Exception):
            pass

        err: Any = _Err("boom")
        attach_partial_timeout_data(err, "  trimmed  ", None, False)
        assert read_partial_timeout_data(err)["rawReply"] == "trimmed"

    def test_set_grace_for_tests(self) -> None:
        set_timeout_partial_data_grace_ms_for_tests(123)
        set_timeout_partial_data_grace_ms_for_tests(-50)
        set_timeout_partial_data_grace_ms_for_tests(10.7)
        reset_active_memory_transcript_for_tests()


# ── transcript_result.build_timeout_recall_result ─────────────


class TestBuildTimeoutRecallResult:
    @pytest.mark.asyncio
    async def test_returns_timeout_when_no_partial(self) -> None:
        out = await build_timeout_recall_result(
            {
                "elapsedMs": 1000,
                "maxSummaryChars": 200,
                "transcriptSources": (),
                "toolsAllow": ("memory_search",),
            }
        )
        assert out["status"] == "timeout"
        assert out["summary"] is None

    @pytest.mark.asyncio
    async def test_returns_timeout_when_raw_reply_no_recall(self) -> None:
        out = await build_timeout_recall_result(
            {
                "elapsedMs": 1000,
                "maxSummaryChars": 200,
                "transcriptSources": (),
                "rawReply": "NONE",
                "toolsAllow": ("memory_search",),
            }
        )
        assert out["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_returns_timeout_when_unavailable(self) -> None:
        out = await build_timeout_recall_result(
            {
                "elapsedMs": 1000,
                "maxSummaryChars": 200,
                "transcriptSources": (),
                "rawReply": "User likes ramen",
                "hasUnavailableMemorySearchResult": True,
                "toolsAllow": ("memory_search",),
            }
        )
        assert out["status"] == "timeout"


# ── transcript_result.build_subagent_recall_result ────────────


class TestBuildSubagentRecallResult:
    def test_ok_with_usable_memory(self) -> None:
        out = build_subagent_recall_result(
            {
                "subagentResult": {
                    "rawReply": "User prefers aisle seats",
                    "hasUsableMemoryResult": True,
                },
                "elapsedMs": 500,
                "maxSummaryChars": 200,
            }
        )
        assert out["status"] == "ok"
        assert out["summary"] == "User prefers aisle seats"

    def test_no_relevant_memory(self) -> None:
        out = build_subagent_recall_result(
            {
                "subagentResult": {"rawReply": "NONE"},
                "elapsedMs": 500,
                "maxSummaryChars": 200,
            }
        )
        assert out["status"] == "no_relevant_memory"
        assert out["summary"] is None

    def test_failed_status(self) -> None:
        out = build_subagent_recall_result(
            {
                "subagentResult": {
                    "rawReply": "NONE",
                    "resultStatus": "failed",
                },
                "elapsedMs": 500,
                "maxSummaryChars": 200,
            }
        )
        assert out["status"] == "failed"

    def test_unavailable_status(self) -> None:
        out = build_subagent_recall_result(
            {
                "subagentResult": {
                    "rawReply": "NONE",
                    "resultStatus": "unavailable",
                },
                "elapsedMs": 500,
                "maxSummaryChars": 200,
            }
        )
        assert out["status"] == "unavailable"

    def test_unavailable_via_search_debug_error(self) -> None:
        out = build_subagent_recall_result(
            {
                "subagentResult": {
                    "rawReply": "NONE",
                    "searchDebug": {"error": "boom"},
                },
                "elapsedMs": 500,
                "maxSummaryChars": 200,
            }
        )
        assert out["status"] == "unavailable"

    def test_fallback_usable_keeps_summary(self) -> None:
        out = build_subagent_recall_result(
            {
                "subagentResult": {"rawReply": "User likes ramen"},
                "fallbackHasUsableMemoryResult": True,
                "elapsedMs": 500,
                "maxSummaryChars": 200,
            }
        )
        assert out["status"] == "ok"

    def test_usable_flag_required_for_ok(self) -> None:
        # A non-empty summary alone is not enough; the harness must
        # report a usable memory result (so a hallucinated
        # "ramen" reply can't bypass the gate).
        out = build_subagent_recall_result(
            {
                "subagentResult": {"rawReply": "User likes ramen"},
                "elapsedMs": 500,
                "maxSummaryChars": 200,
            }
        )
        assert out["status"] == "no_relevant_memory"


# ── transcript_result.read_partial_assistant_text ────────────


class TestReadPartialAssistantText:
    @pytest.mark.asyncio
    async def test_returns_none_for_none_source(self) -> None:
        out = await read_partial_assistant_text(None)
        assert out is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "x.jsonl"
        path.write_text("", encoding="utf-8")
        out = await read_partial_assistant_text(str(path))
        assert out is None

    @pytest.mark.asyncio
    async def test_returns_concatenated_assistant_text(self, tmp_path: Path) -> None:
        path = tmp_path / "x.jsonl"
        path.write_text(
            json.dumps({"role": "assistant", "content": "first"})
            + "\n"
            + json.dumps({"role": "assistant", "content": "second"})
            + "\n",
            encoding="utf-8",
        )
        out = await read_partial_assistant_text(str(path))
        assert out == "first\nsecond"

    @pytest.mark.asyncio
    async def test_skips_non_assistant_records(self, tmp_path: Path) -> None:
        path = tmp_path / "x.jsonl"
        path.write_text(
            json.dumps({"role": "user", "content": "hello"})
            + "\n"
            + json.dumps({"role": "assistant", "content": "world"})
            + "\n",
            encoding="utf-8",
        )
        out = await read_partial_assistant_text(str(path))
        assert out == "world"


class TestReadPartialAssistantTextFromSources:
    @pytest.mark.asyncio
    async def test_walks_sources_in_order(self, tmp_path: Path) -> None:
        empty = file_transcript_source(str(tmp_path / "empty.jsonl"))
        (tmp_path / "empty.jsonl").write_text("", encoding="utf-8")
        path2 = tmp_path / "filled.jsonl"
        path2.write_text(
            json.dumps({"role": "assistant", "content": "second"}) + "\n",
            encoding="utf-8",
        )
        out = await read_partial_assistant_text_from_sources(
            [empty, file_transcript_source(str(path2))]
        )
        assert out == "second"


# ── session helpers ──────────────────────────────────────────


class TestFormatElapsedMsCompact:
    def test_zero_or_negative(self) -> None:
        assert format_elapsed_ms_compact(0) == "0ms"
        assert format_elapsed_ms_compact(-1) == "0ms"

    def test_milliseconds(self) -> None:
        assert format_elapsed_ms_compact(120) == "120ms"
        assert format_elapsed_ms_compact(999) == "999ms"

    def test_seconds(self) -> None:
        assert format_elapsed_ms_compact(1000) == "1s"
        assert format_elapsed_ms_compact(1500) == "1.5s"
        assert format_elapsed_ms_compact(2000) == "2s"

    def test_nan_returns_zero(self) -> None:
        assert format_elapsed_ms_compact(float("nan")) == "0ms"


class TestResolveCanonicalSessionKeyFromSessionId:
    def test_no_api_returns_none(self) -> None:
        assert (
            resolve_canonical_session_key_from_session_id(
                {"api": None, "agentId": "a", "sessionId": "s1"}
            )
            is None
        )

    def test_no_session_id_returns_none(self) -> None:
        assert (
            resolve_canonical_session_key_from_session_id({"api": _StubApi(), "agentId": "a"})
            is None
        )

    def test_no_match_returns_none(self) -> None:
        api = _StubApi()
        out = resolve_canonical_session_key_from_session_id(
            {"api": api, "agentId": "a", "sessionId": "missing"}
        )
        assert out is None

    def test_match_returns_session_key(self) -> None:
        api = _StubApi()
        out = resolve_canonical_session_key_from_session_id(
            {"api": api, "agentId": "a", "sessionId": "s2"}
        )
        assert out == "agent:a:s2"

    def test_chooses_most_recently_updated(self) -> None:
        api = _StubApi()
        out = resolve_canonical_session_key_from_session_id(
            {"api": api, "agentId": "a", "sessionId": "s1"}
        )
        # Both entries have sessionId="s1"; the one with updatedAt=2 wins.
        assert out == "agent:a:s1b"

    def test_api_raises_returns_none(self) -> None:
        class _RaisingApi(_StubApi):
            def __init__(self) -> None:
                pass

        class _Registry:
            def list_session_entries(self, params: dict) -> list:
                raise RuntimeError("boom")

        api = type(
            "Api",
            (),
            {"runtime": type("R", (), {"agent": type("A", (), {"session": _Registry()})()})()},
        )()
        out = resolve_canonical_session_key_from_session_id(
            {"api": api, "agentId": "a", "sessionId": "s1"}
        )
        assert out is None


class TestResolveRecallRunChannelContext:
    def test_no_session_key_no_provider(self) -> None:
        api = _StubApi()
        out = resolve_recall_run_channel_context(
            {"api": api, "agentId": "a", "sessionKey": "agent:a:k"}
        )
        assert out["messageChannel"] is not None
        assert out["messageProvider"] is not None

    def test_explicit_provider_wins(self) -> None:
        api = _StubApi()
        out = resolve_recall_run_channel_context(
            {
                "api": api,
                "agentId": "a",
                "sessionKey": "agent:a:k",
                "messageProvider": "telegram",
            }
        )
        assert out["messageProvider"] == "telegram"

    def test_scoped_channel_id_skipped(self) -> None:
        """Channel IDs with ":" or "/" are not runnable channel names."""
        api = _StubApi()
        out = resolve_recall_run_channel_context(
            {
                "api": api,
                "agentId": "a",
                "sessionKey": "agent:a:k",
                "messageProvider": "telegram",
                "channelId": "spaces/ABC",
            }
        )
        # Scoped id is filtered out, so explicit provider "telegram" wins.
        assert out["messageProvider"] == "telegram"


class TestResolveStatusUpdateAgentId:
    def test_explicit(self) -> None:
        assert resolve_status_update_agent_id({"agentId": "  my-agent  "}) == "my-agent"

    def test_parsed_from_session_key(self) -> None:
        assert resolve_status_update_agent_id({"sessionKey": "agent:foo:bar"}) == "foo"

    def test_empty_returns_empty(self) -> None:
        assert resolve_status_update_agent_id({}) == ""


class TestSanitizeDebugText:
    def test_strips_control_chars(self) -> None:
        assert sanitize_debug_text("hello\x00world") == "helloworld"

    def test_collapses_whitespace(self) -> None:
        assert sanitize_debug_text("hello\n\n   world") == "hello world"

    def test_empty(self) -> None:
        assert sanitize_debug_text("") == ""


class TestBuildPluginStatusLine:
    def test_minimal(self) -> None:
        line = build_plugin_status_line(
            {
                "result": {"status": "ok", "elapsedMs": 200, "summary": "User likes ramen"},
                "config": {"queryMode": "recent"},
            }
        )
        assert ACTIVE_MEMORY_STATUS_PREFIX in line
        assert "status=ok" in line
        assert "elapsed=200ms" in line
        assert "query=recent" in line
        # "User likes ramen" is 16 chars.
        assert "summary=16 chars" in line

    def test_no_summary(self) -> None:
        line = build_plugin_status_line(
            {
                "result": {"status": "failed", "elapsedMs": 0, "summary": None},
                "config": {"queryMode": "message"},
            }
        )
        assert "summary=" not in line
        assert "elapsed=0ms" in line


class TestBuildPersistedDebugSummary:
    def test_timeout_partial_marker(self) -> None:
        out = build_persisted_debug_summary(
            {"status": "timeout_partial", "summary": "abc", "elapsedMs": 100}
        )
        assert out == "timeout_partial: 3 chars recovered (not persisted)"

    def test_other_returns_summary(self) -> None:
        out = build_persisted_debug_summary(
            {"status": "ok", "summary": "User likes ramen", "elapsedMs": 100}
        )
        assert out == "User likes ramen"

    def test_no_summary(self) -> None:
        out = build_persisted_debug_summary({"status": "failed", "summary": None, "elapsedMs": 100})
        assert out is None


class TestBuildPluginDebugLine:
    def test_with_summary(self) -> None:
        out = build_plugin_debug_line({"summary": "User likes ramen"})
        assert out is not None
        assert ACTIVE_MEMORY_DEBUG_PREFIX in out
        assert "User likes ramen" in out

    def test_with_backend_and_metrics(self) -> None:
        out = build_plugin_debug_line(
            {"searchDebug": {"backend": "lancedb", "searchMs": 12.5, "hits": 3}}
        )
        assert out is not None
        assert "backend=lancedb" in out
        assert "searchMs=12" in out
        assert "hits=3" in out

    def test_with_warning(self) -> None:
        out = build_plugin_debug_line({"searchDebug": {"warning": "soft", "error": "boom"}})
        assert out is not None
        assert "soft" in out

    def test_no_info_returns_none(self) -> None:
        assert build_plugin_debug_line({}) is None


class TestPersistPluginStatusLines:
    @pytest.mark.asyncio
    async def test_no_session_key_returns(self) -> None:
        await persist_plugin_status_lines(
            {"api": _StubApi(), "agentId": "a", "sessionKey": None}
        )  # no error

    @pytest.mark.asyncio
    async def test_no_agent_id_no_lines_returns(self) -> None:
        await persist_plugin_status_lines(
            {
                "api": _StubApi(),
                "agentId": "",
                "sessionKey": "agent:a:k",
                "statusLine": None,
            }
        )  # no error

    @pytest.mark.asyncio
    async def test_no_lines_no_existing_returns(self) -> None:
        api = _StubApi()
        await persist_plugin_status_lines(
            {
                "api": api,
                "agentId": "a",
                "sessionKey": "agent:a:k",
                "statusLine": None,
            }
        )
        assert api.runtime.agent.session.patch_calls == 0

    @pytest.mark.asyncio
    async def test_writes_lines_to_session(self) -> None:
        api = _StubApi()
        await persist_plugin_status_lines(
            {
                "api": api,
                "agentId": "a",
                "sessionKey": "agent:a:k",
                "statusLine": "🧩 status=ok",
                "searchDebug": {"backend": "lancedb"},
            }
        )
        assert api.runtime.agent.session.patch_calls == 1
        last = api.runtime.agent.session.last_patch_update({})
        assert "pluginDebugEntries" in last
        entries = last["pluginDebugEntries"]
        assert len(entries) == 1
        assert entries[0]["pluginId"] == "active-memory"
        assert len(entries[0]["lines"]) == 2

    @pytest.mark.asyncio
    async def test_preserves_other_plugin_entries(self) -> None:
        api = _StubApi()
        api.runtime.agent.session.set_existing_entries(
            "agent:a:k",
            [
                {"pluginId": "other", "lines": ["x"]},
                {"pluginId": "active-memory", "lines": ["old"]},
            ],
        )
        await persist_plugin_status_lines(
            {
                "api": api,
                "agentId": "a",
                "sessionKey": "agent:a:k",
                "statusLine": "🧩 status=ok",
            }
        )
        last = api.runtime.agent.session.last_patch_update({})
        entries = last["pluginDebugEntries"]
        ids = {entry["pluginId"] for entry in entries}
        assert ids == {"other", "active-memory"}


# ── Stub for session tests ──────────────────────────────────────


class _StubSessionRegistry:
    def __init__(self) -> None:
        self._entries: list[tuple[str, Any]] = [
            ("agent:a:s1", {"sessionId": "s1", "updatedAt": 1}),
            ("agent:a:s1b", {"sessionId": "s1", "updatedAt": 2}),
            ("agent:a:s2", {"sessionId": "s2", "updatedAt": 3}),
        ]
        self._existing: dict[str, dict] = {}
        self.patch_calls = 0
        self._last_update: Any = None

    def list_session_entries(self, params: dict) -> list:
        agent_id = params.get("agentId", "")
        return [(k, v) for (k, v) in self._entries if k.startswith(f"agent:{agent_id}:")]

    def get_session_entry(self, params: dict) -> Any:
        session_key = params.get("sessionKey", "")
        if session_key in self._existing:
            return self._existing[session_key]
        return {
            "lastChannel": "telegram",
            "channel": "telegram",
            "origin": {"provider": "telegram"},
        }

    def set_existing_entries(self, session_key: str, entries: list) -> None:
        """Test hook: pre-populate the session's existing entries."""
        self._existing[session_key] = {"pluginDebugEntries": entries}

    def patch_session_entry(self, params: dict) -> Any:
        self.patch_calls += 1
        update = params.get("update")
        self._last_update = update
        if callable(update):
            existing = self._existing.get(params.get("sessionKey", ""), {})
            self._last_update = update(existing)
        return {
            "pluginDebugEntries": (
                self._last_update.get("pluginDebugEntries")
                if isinstance(self._last_update, dict)
                else None
            )
        }

    def last_patch_update(self, existing: dict) -> Any:
        if self._last_update is None:
            return {}
        if callable(self._last_update):
            return self._last_update(existing)
        return self._last_update


class _StubRuntimeAgent:
    def __init__(self) -> None:
        self.session = _StubSessionRegistry()


class _StubRuntime:
    def __init__(self) -> None:
        self.agent = _StubRuntimeAgent()


class _StubApi:
    def __init__(self) -> None:
        self.runtime = _StubRuntime()
        self.logger = _StubLogger()


class _StubLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        pass

    def warn(self, *args: Any, **kwargs: Any) -> None:
        pass

    def debug(self, *args: Any, **kwargs: Any) -> None:
        pass

    def error(self, *args: Any, **kwargs: Any) -> None:
        pass


# Wire up the existing-entries field for the test.
_StubSessionRegistry._existing = {}  # type: ignore[attr-defined]


# Fix the patch_session_entry to honour the existingEntries param.
_original_patch = _StubSessionRegistry.patch_session_entry


def _patch_with_existing(self: Any, params: dict) -> Any:
    existing_entries = params.pop("existingEntries", None) if isinstance(params, dict) else None
    if existing_entries is not None:
        self._existing[params["sessionKey"]] = {
            "pluginDebugEntries": existing_entries,
        }
    result = _original_patch(self, params)
    if existing_entries is not None:
        self._existing.pop(params["sessionKey"], None)
    return result


_StubSessionRegistry.patch_session_entry = _patch_with_existing  # type: ignore[assignment]


# ── Smoke test for stream_active_memory_transcript_records ─────


class TestStreamActiveMemoryTranscriptRecords:
    @pytest.mark.asyncio
    async def test_file_source_reads_records(self, tmp_path: Path) -> None:
        path = tmp_path / "x.jsonl"
        path.write_text(
            json.dumps({"a": 1}) + "\n" + json.dumps({"b": 2}) + "\n",
            encoding="utf-8",
        )
        seen: list[Any] = []

        def on_record(record: Any) -> bool:
            seen.append(record)
            return False

        await stream_active_memory_transcript_records(
            {
                "source": file_transcript_source(str(path)),
                "onRecord": on_record,
            }
        )
        assert seen == [{"a": 1}, {"b": 2}]

    @pytest.mark.asyncio
    async def test_missing_file_no_records(self, tmp_path: Path) -> None:
        seen: list[Any] = []

        def on_record(record: Any) -> bool:
            seen.append(record)
            return False

        await stream_active_memory_transcript_records(
            {
                "source": file_transcript_source(str(tmp_path / "missing.jsonl")),
                "onRecord": on_record,
            }
        )
        assert seen == []

    @pytest.mark.asyncio
    async def test_runtime_source_no_pages(self) -> None:
        # The default stub returns an empty page.
        seen: list[Any] = []

        def on_record(record: Any) -> bool:
            seen.append(record)
            return False

        await stream_active_memory_transcript_records(
            {
                "source": {
                    "kind": "runtime",
                    "target": {
                        "agentId": "a",
                        "sessionId": "s1",
                        "sessionKey": "agent:a:s1",
                        "storePath": "/store",
                    },
                },
                "onRecord": on_record,
            }
        )
        assert seen == []
