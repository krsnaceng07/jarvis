"""Tests for Phase 3 Gateway RPC methods: chat.*, cron.*, sessions.*, tasks.*."""

from __future__ import annotations

import time
import pytest
from typing import Any

from jarvis_gateway_protocol import RPCRequest, GatewayRequest
from src.gateway import (
    Gateway,
    RPCDispatcher,
    RPCDispatchError,
    make_chat_handlers,
    make_cron_handlers,
    make_sessions_handlers,
    make_tasks_handlers,
)
from src.sessions.session_store import InMemorySessionStore
from src.cron import CronRunner
from src.automation.task_registry import upsert_task, get_task_by_id
from src.automation.task_types import TaskRecord


@pytest.fixture
def session_store() -> InMemorySessionStore:
    store = InMemorySessionStore()
    return store


@pytest.fixture
def cron_runner() -> CronRunner:
    runner = CronRunner()
    return runner


class TestChatHandlers:
    def test_chat_send_success(self, session_store: InMemorySessionStore) -> None:
        handlers = make_chat_handlers(session_store=session_store)
        res = handlers["chat.send"]({
            "message": "Hello Jarvis",
            "sessionKey": "test-session-1",
            "model": "gpt-4o",
        })
        assert res["ok"] is True
        assert res["status"] == "started"
        assert res["sessionKey"] == "test-session-1"
        assert "runId" in res

        # Verify session entry was created in session_store
        session = session_store.get("test-session-1")
        assert session is not None
        assert session.model_ref == "gpt-4o"
        assert len(session.entries) == 1
        assert session.entries[0]["kind"] == "user_message"
        assert session.entries[0]["payload"]["text"] == "Hello Jarvis"

    def test_chat_send_empty_message_raises(self, session_store: InMemorySessionStore) -> None:
        handlers = make_chat_handlers(session_store=session_store)
        with pytest.raises(RPCDispatchError) as exc_info:
            handlers["chat.send"]({"message": "  ", "sessionKey": "s1"})
        assert exc_info.value.code == -32602

    def test_chat_abort(self, session_store: InMemorySessionStore) -> None:
        handlers = make_chat_handlers(session_store=session_store)
        # Abort nonexistent run
        res = handlers["chat.abort"]({"runId": "nonexistent-run-id"})
        assert res["ok"] is True
        assert res["aborted"] is False

        # Send a message and abort its session
        send_res = handlers["chat.send"]({
            "message": "Long running turn",
            "sessionKey": "abort-session",
        })
        run_id = send_res["runId"]

        # Abort by run_id
        abort_res = handlers["chat.abort"]({"runId": run_id})
        assert abort_res["ok"] is True

        # Abort by sessionKey
        abort_sess_res = handlers["chat.abort"]({"sessionKey": "abort-session"})
        assert abort_sess_res["ok"] is True

    def test_chat_history(self, session_store: InMemorySessionStore) -> None:
        handlers = make_chat_handlers(session_store=session_store)
        # Seed user and assistant entries
        session_store.get_or_create(session_key="hist-session", agent_id="local", kind="direct")
        session_store.append_entry("hist-session", {
            "id": "m1",
            "kind": "user_message",
            "payload": {"text": "What is the weather?", "role": "user", "timestamp": 1000},
        })
        session_store.append_entry("hist-session", {
            "id": "m2",
            "kind": "assistant_message",
            "payload": {"text": "It is sunny.", "role": "assistant", "timestamp": 2000},
        })

        res = handlers["chat.history"]({"sessionKey": "hist-session"})
        assert res["sessionKey"] == "hist-session"
        assert res["total"] == 2
        assert len(res["messages"]) == 2
        assert res["messages"][0]["role"] == "user"
        assert res["messages"][0]["content"] == "What is the weather?"
        assert res["messages"][1]["role"] == "assistant"
        assert res["messages"][1]["content"] == "It is sunny."

        # Pagination test
        paginated = handlers["chat.history"]({"sessionKey": "hist-session", "limit": 1, "offset": 1})
        assert len(paginated["messages"]) == 1
        assert paginated["messages"][0]["id"] == "m2"

    def test_chat_history_missing_session_key(self, session_store: InMemorySessionStore) -> None:
        handlers = make_chat_handlers(session_store=session_store)
        with pytest.raises(RPCDispatchError) as exc_info:
            handlers["chat.history"]({})
        assert exc_info.value.code == -32602


class TestCronHandlers:
    def test_cron_crud_lifecycle(self, cron_runner: CronRunner) -> None:
        handlers = make_cron_handlers(runner=cron_runner)

        # 1. Initially empty
        initial = handlers["cron.list"]()
        assert initial["total"] == 0

        # 2. Add job
        executed = []

        def dummy_handler() -> None:
            executed.append(True)

        add_res = handlers["cron.add"]({
            "id": "job-1",
            "schedule": "*/5 * * * *",
            "description": "Every 5 mins test job",
            "handler": dummy_handler,
        })
        assert add_res["ok"] is True
        assert add_res["job"]["id"] == "job-1"
        assert add_res["job"]["schedule"] == "*/5 * * * *"

        # 3. List contains job
        listed = handlers["cron.list"]()
        assert listed["total"] == 1
        assert listed["jobs"][0]["id"] == "job-1"

        # 4. Get job
        get_res = handlers["cron.get"]({"id": "job-1"})
        assert get_res["ok"] is True
        assert get_res["job"]["description"] == "Every 5 mins test job"

        # 5. Run job manually
        run_res = handlers["cron.run"]({"id": "job-1"})
        assert run_res["ok"] is True
        assert run_res["ran"] is True
        assert len(executed) == 1

        # 6. Status
        status_res = handlers["cron.status"]()
        assert status_res["ok"] is True
        assert status_res["job_count"] == 1

        # 7. Remove job
        del_res = handlers["cron.delete"]({"id": "job-1"})
        assert del_res["ok"] is True
        assert del_res["removed"] is True

        # Verify removal
        assert handlers["cron.list"]()["total"] == 0

    def test_cron_add_invalid_schedule(self, cron_runner: CronRunner) -> None:
        handlers = make_cron_handlers(runner=cron_runner)
        with pytest.raises(RPCDispatchError) as exc_info:
            handlers["cron.add"]({"schedule": ""})
        assert exc_info.value.code == -32602

    def test_cron_run_nonexistent(self, cron_runner: CronRunner) -> None:
        handlers = make_cron_handlers(runner=cron_runner)
        with pytest.raises(RPCDispatchError) as exc_info:
            handlers["cron.run"]({"id": "no-such-job"})
        assert exc_info.value.code == 404


class TestSessionHandlersPhase3:
    def test_sessions_patch(self) -> None:
        handlers = make_sessions_handlers()
        created = handlers["sessions.create"]({"session_key": "patch-session", "agent_id": "test-agent"})
        assert created["session"]["session_key"] == "patch-session"

        # Patch metadata / model
        patched = handlers["sessions.patch"]({
            "key": "patch-session",
            "model": "claude-3-7-sonnet",
            "kind": "channel",
            "title": "Renamed Chat",
        })
        assert patched["ok"] is True
        assert patched["session"]["model_ref"] == "claude-3-7-sonnet"
        assert patched["session"]["kind"] == "channel"

        # Fetch session and verify title entry was recorded
        fetched = handlers["sessions.get"]({"session_key": "patch-session"})
        assert fetched["session"]["model_ref"] == "claude-3-7-sonnet"

    def test_sessions_patch_not_found(self) -> None:
        handlers = make_sessions_handlers()
        with pytest.raises(RPCDispatchError) as exc_info:
            handlers["sessions.patch"]({"key": "missing-session", "model": "test"})
        assert exc_info.value.code == 404

    def test_sessions_delete(self) -> None:
        handlers = make_sessions_handlers()
        handlers["sessions.create"]({"session_key": "delete-me"})
        
        del_res = handlers["sessions.delete"]({"key": "delete-me"})
        assert del_res["ok"] is True
        assert del_res["deleted"] is True

        # Ensure it no longer exists
        with pytest.raises(RPCDispatchError) as exc_info:
            handlers["sessions.get"]({"session_key": "delete-me"})
        assert exc_info.value.code == 404

    def test_sessions_recover(self) -> None:
        handlers = make_sessions_handlers()
        # Recover an uncommitted session key
        rec_res = handlers["sessions.recover"]({"key": "uncommitted-sess-123", "agent_id": "local"})
        assert rec_res["ok"] is True
        assert rec_res["recovered"] is True
        assert rec_res["key"] == "uncommitted-sess-123"

        # Session should now be queryable
        get_res = handlers["sessions.get"]({"session_key": "uncommitted-sess-123"})
        assert get_res["session"]["session_key"] == "uncommitted-sess-123"


class TestTaskHandlersPhase3:
    def test_tasks_retry_and_dismiss(self) -> None:
        now_ms = int(time.time() * 1000)
        task = TaskRecord(
            task_id="task-retry-test-1",
            runtime="subagent",
            requester_session_key="test-owner",
            owner_key="test-owner",
            scope_kind="session",
            task="Test subagent task",
            status="failed",
            delivery_status="failed",
            notify_policy="done_only",
            created_at=float(now_ms - 10000),
            last_event_at=float(now_ms - 5000),
            error="timed out",
        )
        upsert_task(task)

        handlers = make_tasks_handlers()

        # Retry failed task
        retry_res = handlers["tasks.retry"]({"taskId": "task-retry-test-1"})
        assert retry_res["ok"] is True
        assert len(retry_res["results"]) == 1
        assert retry_res["results"][0]["taskId"] == "task-retry-test-1"
        assert retry_res["results"][0]["ok"] is True

        # Dismiss task
        dismiss_res = handlers["tasks.dismiss"]({"taskId": "task-retry-test-1"})
        assert dismiss_res["ok"] is True
        assert len(dismiss_res["results"]) == 1
        assert dismiss_res["results"][0]["taskId"] == "task-retry-test-1"

        updated = get_task_by_id("task-retry-test-1")
        assert updated is not None
        assert updated.delivery_status == "dismissed"


class TestGatewayDispatcherMount:
    def test_dispatcher_routes_all_new_methods(self) -> None:
        gateway = Gateway()
        dispatcher = gateway._dispatcher

        # Check registered methods
        registered = dispatcher.registered_methods()
        expected = [
            "chat.send", "chat.abort", "chat.history",
            "cron.list", "cron.add", "cron.create", "cron.remove", "cron.delete", "cron.run",
            "sessions.patch", "sessions.delete", "sessions.recover",
            "tasks.retry", "tasks.dismiss",
        ]
        for m in expected:
            assert m in registered, f"Missing method in dispatcher: {m}"

        # Dispatch via RPCRequest
        req = RPCRequest(method="cron.list", id="req-1", params={})
        resp = dispatcher.dispatch(req)
        assert resp.error is None
        assert "jobs" in resp.result

        # Dispatch via GatewayRequest
        gw_req = GatewayRequest(type="req", method="sessions.list", id="req-2", params={})
        gw_resp = dispatcher.dispatch(gw_req)
        assert gw_resp.error is None
        assert "sessions" in gw_resp.payload
