"""Phase 7.2c-2 tests — compact_queued + compact (direct)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.runs import (
    ACTIVE_EMBEDDED_RUNS,
    ACTIVE_EMBEDDED_RUNS_BY_RUN_ID,
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE,
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY,
    ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID,
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE,
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY,
    RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS,
)


@pytest.fixture(autouse=True)
def _reset_embedded_run_state() -> None:
    ACTIVE_EMBEDDED_RUNS.clear()
    ACTIVE_EMBEDDED_RUNS_BY_RUN_ID.clear()
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE.clear()
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY.clear()
    ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID.clear()
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE.clear()
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY.clear()
    RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS.clear()


from src.agents.embedded_agent_runner.compact import (
    compact_embedded_agent_session_direct,
    register_testing_helpers,
    set_direct_compaction_handler,
    set_has_compaction_model_fallback_candidates,
    set_resolve_agent_run_session_target,
    testing,
)
from src.agents.embedded_agent_runner.compact_queued import (
    COMPACTION_ABORTED_REASON,
    MANUAL_COMPACTION_ACTIVE_RUN_REASON,
    build_context_engine_compaction_session_target,
    compact_embedded_agent_session,
    create_compaction_aborted_result,
    defer_owning_context_engine_budget_compaction,
    dispose_context_engine,
    locked_compaction_runtime_failure,
    merge_secondary_native_harness_compaction_details,
    resolve_manual_compaction_active_run_session_id,
    set_deferred_maintenance_hook,
    set_queued_compaction_handler,
    set_sqlite_session_file_marker_parser,
    should_defer_owning_context_engine_budget_compaction,
)
from src.agents.embedded_agent_runner.compact_types import (
    CompactEmbeddedAgentSessionParams,
)


# ============================================================================
# compact_queued.py — helpers
# ============================================================================


class TestLockedCompactionRuntimeFailure:
    def test_with_runtime(self) -> None:
        result = locked_compaction_runtime_failure("codex")
        assert result["ok"] is False
        assert result["compacted"] is False
        assert "codex" in result["reason"]
        assert result["failure"] == {"reason": "model_selection_locked"}

    def test_without_runtime(self) -> None:
        result = locked_compaction_runtime_failure()
        assert result["ok"] is False
        assert "persisted agent harness" in result["reason"]


class TestCreateCompactionAbortedResult:
    def test_shape(self) -> None:
        result = create_compaction_aborted_result()
        assert result["ok"] is False
        assert result["compacted"] is False
        assert result["reason"] == COMPACTION_ABORTED_REASON


class TestResolveManualCompactionActiveRunSessionId:
    def test_no_active_run(self) -> None:
        params: CompactEmbeddedAgentSessionParams = {
            "sessionId": "sess-1",
            "sessionKey": "key-1",
            "sessionFile": "/tmp/s.jsonl",
        }
        result = resolve_manual_compaction_active_run_session_id(params)
        assert result is None

    def test_session_id_active(self) -> None:
        from src.agents.embedded_agent_runner.runs import (
            register_active_embedded_run,
        )

        handle = {"kind": "embedded"}
        register_active_embedded_run(
            session_id="sess-1",
            handle=handle,
        )
        try:
            result = resolve_manual_compaction_active_run_session_id(
                {"sessionId": "sess-1", "sessionKey": "k", "sessionFile": "/f"}
            )
            assert result == "sess-1"
        finally:
            from src.agents.embedded_agent_runner.runs import (
                unregister_active_embedded_run,
            )

            unregister_active_embedded_run(
                session_id="sess-1",
                handle=handle,
            )

    def test_session_key_active(self) -> None:
        from src.agents.embedded_agent_runner.runs import (
            register_active_embedded_run,
            unregister_active_embedded_run,
        )

        handle = {"kind": "embedded"}
        register_active_embedded_run(
            session_id="sess-other",
            handle=handle,
            session_key="key-1",
        )
        try:
            result = resolve_manual_compaction_active_run_session_id(
                {"sessionId": "different", "sessionKey": "key-1", "sessionFile": "/f"}
            )
            assert result == "sess-other"
        finally:
            unregister_active_embedded_run(
                session_id="sess-other",
                handle=handle,
                session_key="key-1",
            )

    def test_session_file_active(self) -> None:
        from src.agents.embedded_agent_runner.runs import (
            register_active_embedded_run,
            unregister_active_embedded_run,
        )

        handle = {"kind": "embedded"}
        register_active_embedded_run(
            session_id="sess-f",
            handle=handle,
            session_file="/f",
        )
        try:
            result = resolve_manual_compaction_active_run_session_id(
                {
                    "sessionId": "different",
                    "sessionKey": "different",
                    "sessionFile": "/f",
                }
            )
            assert result == "sess-f"
        finally:
            unregister_active_embedded_run(
                session_id="sess-f",
                handle=handle,
                session_file="/f",
            )


class TestShouldDeferOwningContextEngineBudgetCompaction:
    def test_defer_when_owns_and_background(self) -> None:
        params: CompactEmbeddedAgentSessionParams = {
            "deferOwningContextEngineCompaction": True,
            "trigger": "budget",
        }
        engine = {
            "info": {
                "ownsCompaction": True,
                "turnMaintenanceMode": "background",
            },
            "maintain": lambda **kwargs: None,
        }
        assert should_defer_owning_context_engine_budget_compaction(
            compact_params=params, context_engine=engine
        ) is True

    def test_no_defer_when_not_budget_trigger(self) -> None:
        params: CompactEmbeddedAgentSessionParams = {
            "deferOwningContextEngineCompaction": True,
            "trigger": "manual",
        }
        engine = {
            "info": {"ownsCompaction": True, "turnMaintenanceMode": "background"},
            "maintain": lambda **kwargs: None,
        }
        assert (
            should_defer_owning_context_engine_budget_compaction(
                compact_params=params, context_engine=engine
            )
            is False
        )

    def test_no_defer_when_engine_does_not_own(self) -> None:
        params: CompactEmbeddedAgentSessionParams = {
            "deferOwningContextEngineCompaction": True,
            "trigger": "budget",
        }
        engine = {
            "info": {"ownsCompaction": False, "turnMaintenanceMode": "background"},
            "maintain": lambda **kwargs: None,
        }
        assert (
            should_defer_owning_context_engine_budget_compaction(
                compact_params=params, context_engine=engine
            )
            is False
        )

    def test_no_defer_when_maintenance_mode_synchronous(self) -> None:
        params: CompactEmbeddedAgentSessionParams = {
            "deferOwningContextEngineCompaction": True,
            "trigger": "budget",
        }
        engine = {
            "info": {"ownsCompaction": True, "turnMaintenanceMode": "synchronous"},
            "maintain": lambda **kwargs: None,
        }
        assert (
            should_defer_owning_context_engine_budget_compaction(
                compact_params=params, context_engine=engine
            )
            is False
        )

    def test_no_defer_when_no_maintain_function(self) -> None:
        params: CompactEmbeddedAgentSessionParams = {
            "deferOwningContextEngineCompaction": True,
            "trigger": "budget",
        }
        engine = {
            "info": {"ownsCompaction": True, "turnMaintenanceMode": "background"},
        }
        assert (
            should_defer_owning_context_engine_budget_compaction(
                compact_params=params, context_engine=engine
            )
            is False
        )


class TestBuildContextEngineCompactionSessionTarget:
    def test_basic(self) -> None:
        params: CompactEmbeddedAgentSessionParams = {
            "sessionId": "sess-1",
            "sessionKey": "key-1",
            "agentId": "agent-1",
            "sessionFile": "/tmp/s.jsonl",
        }
        target = build_context_engine_compaction_session_target(params)
        assert target["agentId"] == "agent-1"
        assert target["sessionId"] == "sess-1"
        assert target["sessionKey"] == "key-1"

    def test_explicit_session_target_overrides(self) -> None:
        params: CompactEmbeddedAgentSessionParams = {
            "sessionId": "sess-1",
            "sessionKey": "key-1",
            "agentId": "agent-1",
            "sessionFile": "/tmp/s.jsonl",
            "sessionTarget": {
                "agentId": "agent-x",
                "sessionId": "sess-x",
                "sessionKey": "key-x",
                "storePath": "/tmp/store",
                "threadId": "t-1",
            },
        }
        target = build_context_engine_compaction_session_target(params)
        assert target["agentId"] == "agent-x"
        assert target["sessionId"] == "sess-x"
        assert target["sessionKey"] == "key-x"
        assert target["storePath"] == "/tmp/store"
        assert target["threadId"] == "t-1"

    def test_sqlite_marker_parser(self) -> None:
        set_sqlite_session_file_marker_parser(
            lambda path: {"agentId": "agent-sqlite", "sessionId": "sess-sqlite"}
            if "sqlite" in path
            else None
        )
        try:
            params: CompactEmbeddedAgentSessionParams = {
                "sessionId": "fallback",
                "sessionFile": "/tmp/sqlite.jsonl",
            }
            target = build_context_engine_compaction_session_target(params)
            assert target["agentId"] == "agent-sqlite"
            assert target["sessionId"] == "sess-sqlite"
        finally:
            set_sqlite_session_file_marker_parser(None)


class TestDisposeContextEngine:
    @pytest.mark.asyncio
    async def test_calls_dispose(self) -> None:
        called = []

        class _Engine:
            async def dispose(self) -> None:
                called.append(True)

        await dispose_context_engine(_Engine())
        assert called == [True]

    @pytest.mark.asyncio
    async def test_swallows_exceptions(self) -> None:
        class _Engine:
            async def dispose(self) -> None:
                raise RuntimeError("boom")

        # Should not raise.
        await dispose_context_engine(_Engine())

    @pytest.mark.asyncio
    async def test_missing_dispose_is_noop(self) -> None:
        class _Engine:
            pass

        # Should not raise.
        await dispose_context_engine(_Engine())

    @pytest.mark.asyncio
    async def test_sync_dispose(self) -> None:
        called = []

        class _Engine:
            def dispose(self) -> None:
                called.append(True)

        await dispose_context_engine(_Engine())
        assert called == [True]


class TestDeferOwningContextEngineBudgetCompaction:
    @pytest.mark.asyncio
    async def test_default_no_hook(self) -> None:
        params: CompactEmbeddedAgentSessionParams = {
            "sessionId": "sess-1",
            "sessionKey": "key-1",
            "sessionFile": "/tmp/s.jsonl",
        }
        result = await defer_owning_context_engine_budget_compaction(
            compact_params=params,
            context_engine={},
            context_engine_runtime_context={},
            context_engine_runtime_settings={},
        )
        assert result["ok"] is True
        assert result["compacted"] is False
        assert result["reason"] == "deferred to background context-engine maintenance"

    @pytest.mark.asyncio
    async def test_with_maintenance_hook(self) -> None:
        called: List[Dict[str, Any]] = []

        async def hook(**payload: Any) -> None:
            called.append(payload)

        set_deferred_maintenance_hook(hook)
        try:
            params: CompactEmbeddedAgentSessionParams = {
                "sessionId": "sess-1",
                "sessionKey": "key-1",
                "sessionFile": "/tmp/s.jsonl",
            }
            result = await defer_owning_context_engine_budget_compaction(
                compact_params=params,
                context_engine={},
                context_engine_runtime_context={"r": 1},
                context_engine_runtime_settings={"s": 1},
            )
            assert result["ok"] is True
            assert len(called) == 1
            assert called[0]["compact_params"] == params
        finally:
            set_deferred_maintenance_hook(None)

    @pytest.mark.asyncio
    async def test_with_engine_maintain(self) -> None:
        called: List[Dict[str, Any]] = []

        def maintain(**kwargs: Any) -> None:
            called.append(kwargs)

        engine = {"maintain": maintain}
        params: CompactEmbeddedAgentSessionParams = {
            "sessionId": "sess-1",
            "sessionKey": "key-1",
            "sessionFile": "/tmp/s.jsonl",
        }
        result = await defer_owning_context_engine_budget_compaction(
            compact_params=params,
            context_engine=engine,
            context_engine_runtime_context={},
            context_engine_runtime_settings={},
        )
        assert result["ok"] is True
        assert len(called) == 1
        assert called[0]["reason"] == "turn"

    @pytest.mark.asyncio
    async def test_maintain_failure_captured(self) -> None:
        def maintain(**kwargs: Any) -> None:
            raise RuntimeError("nope")

        engine = {"maintain": maintain}
        params: CompactEmbeddedAgentSessionParams = {
            "sessionId": "sess-1",
            "sessionKey": "key-1",
            "sessionFile": "/tmp/s.jsonl",
        }
        result = await defer_owning_context_engine_budget_compaction(
            compact_params=params,
            context_engine=engine,
            context_engine_runtime_context={},
            context_engine_runtime_settings={},
        )
        assert result["ok"] is True
        details = result["result"]["details"]
        assert details["scheduled"] is False
        assert "nope" in details["scheduleFailure"]


class TestMergeSecondaryNativeHarnessCompactionDetails:
    def test_no_native_result(self) -> None:
        assert (
            merge_secondary_native_harness_compaction_details(
                details={"a": 1}, native_result=None, details_key="codexNativeCompaction"
            )
            == {"a": 1}
        )

    def test_dict_details_merges(self) -> None:
        merged = merge_secondary_native_harness_compaction_details(
            details={"a": 1},
            native_result={"ok": True},
            details_key="codexNativeCompaction",
        )
        assert merged == {"a": 1, "codexNativeCompaction": {"ok": True}}

    def test_non_dict_details_wraps(self) -> None:
        merged = merge_secondary_native_harness_compaction_details(
            details="raw",
            native_result={"ok": True},
            details_key="codexNativeCompaction",
        )
        assert merged == {
            "contextEngine": "raw",
            "codexNativeCompaction": {"ok": True},
        }

    def test_undefined_details(self) -> None:
        merged = merge_secondary_native_harness_compaction_details(
            details=None,
            native_result={"ok": True},
            details_key="codexNativeCompaction",
        )
        assert merged == {"codexNativeCompaction": {"ok": True}}


# ============================================================================
# compact_embedded_agent_session — public entry
# ============================================================================


class TestCompactEmbeddedAgentSession:
    @pytest.mark.asyncio
    async def test_no_handler_returns_no_handler_result(self) -> None:
        set_queued_compaction_handler(None)
        # Non-manual trigger bypasses the active-run guard and goes
        # straight to the handler (default no-op).
        result = await compact_embedded_agent_session(
            {"trigger": "budget", "sessionId": "sess-1"}
        )
        assert result["ok"] is False
        assert "no queued compaction handler installed" in result["reason"]

    @pytest.mark.asyncio
    async def test_non_manual_invokes_handler(self) -> None:
        called: List[Dict[str, Any]] = []

        async def handler(params: Dict[str, Any]) -> Dict[str, Any]:
            called.append(dict(params))
            return {"ok": True, "compacted": True}

        set_queued_compaction_handler(handler)
        try:
            params = {"trigger": "budget", "sessionId": "sess-1"}
            result = await compact_embedded_agent_session(params)
            assert result["ok"] is True
            assert result["compacted"] is True
            assert len(called) == 1
            assert called[0]["sessionId"] == "sess-1"
        finally:
            set_queued_compaction_handler(None)

    @pytest.mark.asyncio
    async def test_manual_blocked_by_active_run(self) -> None:
        from src.agents.embedded_agent_runner.runs import (
            register_active_embedded_run,
            unregister_active_embedded_run,
        )

        handle = {"kind": "embedded"}
        register_active_embedded_run(
            session_id="sess-1",
            handle=handle,
        )
        try:
            result = await compact_embedded_agent_session(
                {"trigger": "manual", "sessionId": "sess-1", "sessionKey": "k", "sessionFile": "/f"}
            )
            assert result["ok"] is False
            assert result["reason"] == MANUAL_COMPACTION_ACTIVE_RUN_REASON
            assert result["failure"] == {"reason": "active_run"}
        finally:
            unregister_active_embedded_run(
                session_id="sess-1",
                handle=handle,
            )

    @pytest.mark.asyncio
    async def test_manual_passes_through_handler(self) -> None:
        from src.agents.embedded_agent_runner.runs import unregister_active_embedded_run

        called: List[Dict[str, Any]] = []

        async def handler(params: Dict[str, Any]) -> Dict[str, Any]:
            called.append(dict(params))
            return {"ok": True, "compacted": True}

        set_queued_compaction_handler(handler)
        try:
            result = await compact_embedded_agent_session(
                {
                    "trigger": "manual",
                    "sessionId": "sess-manual",
                    "sessionKey": "k",
                    "sessionFile": "/f",
                }
            )
            assert result["ok"] is True
            assert "abortSignal" in called[0]
            # Ensure the run handle is cleared on exit.
            assert (
                resolve_manual_compaction_active_run_session_id(
                    {"sessionId": "sess-manual", "sessionKey": "k", "sessionFile": "/f"}
                )
                is None
            )
        finally:
            set_queued_compaction_handler(None)
            unregister_active_embedded_run(
                session_id="sess-manual",
                handle={"kind": "embedded"},
                session_key="k",
                session_file="/f",
            )


# ============================================================================
# compact.py — direct entry
# ============================================================================


class TestCompactEmbeddedAgentSessionDirect:
    @pytest.mark.asyncio
    async def test_locked_harness_failure(self) -> None:
        result = await compact_embedded_agent_session_direct(
            {
                "modelSelectionLocked": True,
                "agentHarnessId": "codex",
            }
        )
        assert result["ok"] is False
        assert result["failure"] == {"reason": "model_selection_locked"}
        assert "codex" in result["reason"]

    @pytest.mark.asyncio
    async def test_locked_harness_no_runtime(self) -> None:
        result = await compact_embedded_agent_session_direct(
            {
                "modelSelectionLocked": True,
            }
        )
        assert result["ok"] is False
        assert "persisted agent harness" in result["reason"]

    @pytest.mark.asyncio
    async def test_locked_openclaw_falls_through(self) -> None:
        captured: List[Dict[str, Any]] = []

        async def handler(
            params: Dict[str, Any], target: Dict[str, str]
        ) -> Dict[str, Any]:
            captured.append({"params": params, "target": target})
            return {"ok": True, "compacted": True}

        set_direct_compaction_handler(handler)
        try:
            result = await compact_embedded_agent_session_direct(
                {
                    "modelSelectionLocked": True,
                    "agentHarnessId": "openclaw",
                    "sessionId": "sess-1",
                    "sessionFile": "/f",
                }
            )
            assert result["ok"] is True
            assert len(captured) == 1
        finally:
            set_direct_compaction_handler(None)

    @pytest.mark.asyncio
    async def test_default_no_handler(self) -> None:
        set_direct_compaction_handler(None)
        set_resolve_agent_run_session_target(None)
        set_has_compaction_model_fallback_candidates(None)
        result = await compact_embedded_agent_session_direct(
            {
                "sessionId": "sess-1",
                "sessionFile": "/f",
            }
        )
        assert result["ok"] is False
        assert "no direct compaction handler installed" in result["reason"]

    @pytest.mark.asyncio
    async def test_resolves_session_target(self) -> None:
        captured: List[Dict[str, Any]] = []

        async def handler(
            params: Dict[str, Any], target: Dict[str, str]
        ) -> Dict[str, Any]:
            captured.append({"params": params, "target": target})
            return {"ok": True, "compacted": True}

        set_direct_compaction_handler(handler)
        set_resolve_agent_run_session_target(
            lambda params: {
                "agentId": "agent-from-resolver",
                "sessionId": "sess-from-resolver",
                "sessionKey": "key-from-resolver",
                "sessionFile": "/f-from-resolver",
            }
        )
        try:
            result = await compact_embedded_agent_session_direct(
                {
                    "sessionId": "sess-1",
                    "sessionFile": "/f",
                }
            )
            assert result["ok"] is True
            assert captured[0]["target"]["sessionId"] == "sess-from-resolver"
        finally:
            set_direct_compaction_handler(None)
            set_resolve_agent_run_session_target(None)


class TestTestingNamespace:
    def test_static_helpers_present(self) -> None:
        assert testing["estimateTokensAfterCompaction"] is not None
        assert testing["buildBeforeCompactionHookMetrics"] is not None
        assert testing["runBeforeCompactionHooks"] is not None
        assert testing["runAfterCompactionHooks"] is not None
        assert testing["runPostCompactionSideEffects"] is not None
        assert testing["prepareCompactionSessionAgent"] is not None

    def test_optional_helpers_registered(self) -> None:
        def fake_has_real(*args: Any, **kwargs: Any) -> bool:
            return True

        register_testing_helpers(has_real_conversation_content=fake_has_real)
        assert testing["hasRealConversationContent"] is fake_has_real

        # And it can be replaced.
        def fake_has_real2(*args: Any, **kwargs: Any) -> bool:
            return False

        register_testing_helpers(has_real_conversation_content=fake_has_real2)
        assert testing["hasRealConversationContent"] is fake_has_real2
