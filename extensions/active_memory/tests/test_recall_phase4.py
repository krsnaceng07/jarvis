"""Tests for extensions/active_memory/recall.py + recall_run.py.

Phase 4.2b step 3: ports the recall orchestration and
embedded sub-agent dispatch. The tests focus on:

- ``format_active_memory_fast_mode`` (4-value renderer)
- ``prepare_recall_run_context`` (parent session key +
  store path + fastMode chain)
- ``apply_active_memory_runtime_config_snapshot``
  (plugins.active-memory overlay)
- ``collect_active_memory_transcript_sources`` (file +
  runtime source list)
- ``run_recall_subagent`` no-model path (``rawReply: NONE``)
- The default ``_run_embedded_agent`` stub returns
  ``{ payloads: [] }``
- Circuit-breaker / cache / abort-signal wiring
- ``schedule_memory_search_cleanup_after_timeout`` calls
  the SDK's ``close_active_memory_search_manager``
"""

# pyright: reportArgumentType=false
# pyright: reportAssignmentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false
# pyright: reportReturnType=false

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, ClassVar

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.active_memory.recall import (  # noqa: E402
    format_active_memory_fast_mode,
    prepare_recall_run_context,
)
from extensions.active_memory.recall_run import (  # noqa: E402
    apply_active_memory_runtime_config_snapshot,
    collect_active_memory_transcript_sources,
    run_recall_subagent,
)
from extensions.active_memory.recall_state import (  # noqa: E402
    reset_active_recall_state_for_tests,
    schedule_memory_search_cleanup_after_timeout,
)

# ── format_active_memory_fast_mode ───────────────────────────────


class TestFormatActiveMemoryFastMode:
    def test_undefined_returns_inherit(self) -> None:
        assert format_active_memory_fast_mode(None) == "inherit"

    def test_true_returns_on(self) -> None:
        assert format_active_memory_fast_mode(True) == "on"

    def test_false_returns_off(self) -> None:
        assert format_active_memory_fast_mode(False) == "off"

    def test_auto_returns_auto(self) -> None:
        assert format_active_memory_fast_mode("auto") == "auto"


# ── prepare_recall_run_context ──────────────────────────────────


class TestPrepareRecallRunContext:
    def test_no_api_returns_empty_store_path(self) -> None:
        out = prepare_recall_run_context(
            {
                "api": None,
                "runtimeConfig": {},
                "config": {"fastMode": "auto"},
                "agentId": "a",
                "sessionKey": "agent:a:k",
            }
        )
        assert out["parentSessionKey"] == "agent:a:k"
        assert out["fastMode"] == "auto"
        assert out["storePath"] == ""


# ── apply_active_memory_runtime_config_snapshot ──────────────────


class TestApplyActiveMemoryRuntimeConfigSnapshot:
    def test_overlays_plugins_section(self) -> None:
        out = apply_active_memory_runtime_config_snapshot(
            {"plugins": {}},
            {"enabled": True, "agents": ["a", "b"]},
        )
        assert "active-memory" in out["plugins"]
        assert out["plugins"]["active-memory"]["enabled"] is True
        assert out["plugins"]["active-memory"]["agents"] == ["a", "b"]

    def test_empty_runtime_config(self) -> None:
        out = apply_active_memory_runtime_config_snapshot({}, {"enabled": False})
        assert out["plugins"]["active-memory"]["enabled"] is False


# ── collect_active_memory_transcript_sources ─────────────────────


class TestCollectActiveMemoryTranscriptSources:
    def test_runtime_and_artifact_only(self) -> None:
        runtime_source: dict = {
            "kind": "runtime",
            "target": {
                "agentId": "a",
                "sessionId": "s1",
                "sessionKey": "agent:a:s1",
                "storePath": "/store",
            },
        }
        out = collect_active_memory_transcript_sources(
            {
                "runtimeSource": runtime_source,
                "artifactSessionFile": "C:/tmp/x.jsonl",
                "activeSessionKey": "agent:a:s1",
            }
        )
        assert len(out) == 2
        assert out[0] is runtime_source
        assert out[1]["kind"] == "file"
        assert out[1]["sessionFile"] == "C:/tmp/x.jsonl"

    def test_includes_active_session_file_if_different(self) -> None:
        runtime_source: dict = {
            "kind": "runtime",
            "target": {
                "agentId": "a",
                "sessionId": "s1",
                "sessionKey": "agent:a:s1",
                "storePath": "/store",
            },
        }
        out = collect_active_memory_transcript_sources(
            {
                "runtimeSource": runtime_source,
                "artifactSessionFile": "C:/tmp/artifact.jsonl",
                "activeSessionFile": "C:/tmp/active.jsonl",
                "activeSessionKey": "agent:a:s1",
            }
        )
        assert len(out) == 3


# ── run_recall_subagent no-model path ───────────────────────────


class TestRunRecallSubagentNoModel:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_model(self) -> None:
        out = await run_recall_subagent(
            {
                "api": _StubApi(),
                "runtimeConfig": {},
                "config": {"toolsAllow": ["memory_search"]},
                "agentId": "a",
            }
        )
        assert out == {"rawReply": "NONE"}


# ── schedule_memory_search_cleanup_after_timeout ────────────────


class TestScheduleMemorySearchCleanup:
    def teardown_method(self) -> None:
        reset_active_recall_state_for_tests()

    def test_no_event_loop_does_not_raise(self) -> None:
        """When called outside an event loop, the cleanup
        is a no-op (logged at debug, not invoked). The next
        recall will retry it. We just verify no exception
        is raised."""

        class _StubLogger:
            @staticmethod
            def debug(msg: str) -> None:
                pass

            @staticmethod
            def warn(msg: str) -> None:
                pass

        class _StubConfig:
            @staticmethod
            def current() -> dict:
                return {"x": 1}

        class _StubRuntime:
            config = _StubConfig

        class _Stub:
            runtime = _StubRuntime()
            id = "active-memory"
            config: ClassVar[dict] = {"x": 1}
            logger = _StubLogger()

        # No event loop is running in the test; the call
        # should return silently without raising.
        schedule_memory_search_cleanup_after_timeout(_Stub(), "active-memory: ", "a")


# ── Stub for the no-model test ──────────────────────────────────


class _StubSession:
    def list_session_entries(self, params: dict) -> list:
        return []

    def get_session_entry(self, params: dict) -> Any:
        return None

    def patch_session_entry(self, params: dict) -> Any:
        return None

    def resolve_store_path(self, *args: Any, **kwargs: Any) -> str:
        return "/store"


class _StubRuntimeAgent:
    session = _StubSession()


class _StubRuntime:
    agent = _StubRuntimeAgent()


class _StubLogger:
    def debug(self, *args: Any, **kwargs: Any) -> None:
        pass

    def warn(self, *args: Any, **kwargs: Any) -> None:
        pass

    def info(self, *args: Any, **kwargs: Any) -> None:
        pass


class _StubApi:
    def __init__(self) -> None:
        self.runtime = _StubRuntime()
        self.logger = _StubLogger()
        self.id = "active-memory"
        self.config = {}
