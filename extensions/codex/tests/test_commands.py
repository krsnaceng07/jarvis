"""Tests for `/codex` command surface handlers.

OpenClaw parity: ``extensions/codex/src/commands.test.ts``.
"""

from __future__ import annotations

import asyncio

from extensions.codex.src.commands import (
    CodexCommandContext,
    handle_codex_command,
)
from extensions.codex.src.conversation_store import CodexConversationStore


def test_command_help():
    ctx = CodexCommandContext(args="help")
    res = asyncio.run(handle_codex_command(ctx))
    assert "Codex Plugin Commands" in res.text
    assert "/codex status" in res.text


def test_command_status():
    ctx = CodexCommandContext(args="status")

    def mock_req(verb: str, payload: dict | None = None):
        if verb == "plugin/list":
            return {"plugins": []}
        return {}

    res = asyncio.run(handle_codex_command(ctx, request_fn=mock_req))
    assert "Codex Harness Status" in res.text
    assert "OpenAI Codex" in res.text


def test_command_models():
    ctx = CodexCommandContext(args="models")
    res = asyncio.run(handle_codex_command(ctx))
    assert "openai/gpt-5.6-sol" in res.text


def test_command_binding():
    ctx = CodexCommandContext(args="binding", binding_thread_id="th_test_123")
    res = asyncio.run(handle_codex_command(ctx))
    assert "th_test_123" in res.text
    assert "openai/gpt-5.6-sol" in res.text


def test_command_computer_use_status():
    ctx = CodexCommandContext(args="computer-use status")

    def mock_req(verb: str, payload: dict | None = None):
        if verb == "plugin/list":
            return {"plugins": []}
        return {}

    res = asyncio.run(handle_codex_command(ctx, request_fn=mock_req))
    assert "Codex Computer Use Status" in res.text


def test_read_only_commands_use_live_app_server_control_methods():
    calls: list[tuple[str, dict | None]] = []

    def mock_req(verb: str, payload: dict | None = None):
        calls.append((verb, payload))
        responses = {
            "model/list": {"models": [{"id": "gpt-live", "isDefault": True}]},
            "thread/list": {"data": [{"threadId": "thread-live", "title": "Current work"}]},
            "account/read": {"email": "owner@example.test"},
            "account/rateLimits/read": {"primary": {"usedPercent": 2}},
            "mcpServerStatus/list": {"data": [{"name": "filesystem"}]},
            "skills/list": {"data": [{"skills": [{"name": "review"}]}]},
        }
        return responses.get(verb, {})

    for args, expected in (
        ("models", "gpt-live"),
        ("threads current", "thread-live"),
        ("account", "owner@example.test"),
        ("mcp", "filesystem"),
        ("skills", "review"),
    ):
        result = asyncio.run(
            handle_codex_command(
                CodexCommandContext(args=args, is_admin=True),
                request_fn=mock_req,
            )
        )
        assert expected in result.text

    assert [method for method, _ in calls] == [
        "model/list",
        "thread/list",
        "account/read",
        "account/rateLimits/read",
        "mcpServerStatus/list",
        "skills/list",
    ]


def test_plugin_commands_use_native_catalog_and_install_methods():
    calls: list[tuple[str, dict | None]] = []

    def mock_req(verb: str, payload: dict | None = None):
        calls.append((verb, payload))
        return {"plugins": [{"name": "review-tools"}]}

    for args, expected in (
        ("plugins list", "Installed plugins"),
        ("plugins available", "Available plugins"),
        ("plugins install review-tools@official", "Plugin installed"),
    ):
        result = asyncio.run(
            handle_codex_command(
                CodexCommandContext(args=args, is_admin=True),
                request_fn=mock_req,
            )
        )
        assert expected in result.text

    assert [method for method, _ in calls] == [
        "plugin/installed",
        "plugin/list",
        "plugin/install",
    ]
    assert calls[2][1] == {"pluginName": "review-tools", "marketplace": "official"}


def test_active_turn_commands_use_native_control_methods():
    calls: list[tuple[str, dict | None]] = []

    def mock_req(verb: str, payload: dict | None = None):
        calls.append((verb, payload))
        return {}

    for args, expected in (
        ("stop", "Codex stop requested"),
        ("steer continue", "steered"),
        ("review", "Started Codex review"),
    ):
        result = asyncio.run(
            handle_codex_command(
                CodexCommandContext(
                    args=args,
                    is_admin=True,
                    binding_thread_id="thread-1",
                    active_turn_id="turn-1",
                ),
                request_fn=mock_req,
            )
        )
        assert expected in result.text

    assert [method for method, _ in calls] == ["turn/interrupt", "turn/steer", "review/start"]
    assert calls[0][1] == {"threadId": "thread-1", "turnId": "turn-1"}
    assert calls[1][1]["expectedTurnId"] == "turn-1"
    assert calls[2][1] == {
        "threadId": "thread-1",
        "target": {"type": "uncommittedChanges"},
    }


def test_goal_commands_use_native_goal_methods():
    calls: list[tuple[str, dict | None]] = []

    def mock_req(verb: str, payload: dict | None = None):
        calls.append((verb, payload))
        if verb == "thread/goal/get":
            return {"goal": {"objective": "ship it", "status": "active", "tokensUsed": 3}}
        return {"goal": {"objective": "ship it", "status": "paused", "tokensUsed": 3}}

    for args, expected in (
        ("goal", "ship it"),
        ("goal pause", "paused"),
        ("goal clear", "No Codex goal"),
    ):
        result = asyncio.run(
            handle_codex_command(
                CodexCommandContext(
                    args=args,
                    is_admin=True,
                    binding_thread_id="thread-1",
                ),
                request_fn=mock_req,
            )
        )
        assert expected in result.text

    assert [method for method, _ in calls] == [
        "thread/goal/get",
        "thread/goal/set",
        "thread/goal/clear",
    ]
    assert calls[1][1] == {"threadId": "thread-1", "status": "paused"}


def test_diagnostics_requires_approval_before_feedback_upload():
    calls: list[tuple[str, dict | None]] = []

    def mock_req(verb: str, payload: dict | None = None):
        calls.append((verb, payload))
        return {"threadId": "thread-1"}

    canceled = asyncio.run(
        handle_codex_command(
            CodexCommandContext(
                args="diagnostics bug note",
                is_admin=True,
                user_id="owner-1",
                session_id="session-1",
                binding_thread_id="thread-1",
                diagnostics_approval_fn=lambda note: False,
            ),
            request_fn=mock_req,
        )
    )
    assert "canceled" in canceled.text
    assert calls == []

    uploaded = asyncio.run(
        handle_codex_command(
            CodexCommandContext(
                args="diagnostics bug note",
                is_admin=True,
                user_id="owner-1",
                session_id="session-1",
                binding_thread_id="thread-1",
                diagnostics_approval_fn=lambda note: True,
            ),
            request_fn=mock_req,
        )
    )
    assert "uploaded" in uploaded.text
    assert calls[0][0] == "feedback/upload"
    assert calls[0][1] == {
        "classification": "bug",
        "threadId": "thread-1",
        "includeLogs": True,
        "tags": {"sessionId": "session-1", "userId": "owner-1"},
        "reason": "bug note",
    }


def test_bind_resume_and_detach_use_host_binding_callback():
    calls: list[tuple[str, dict | None]] = []
    bindings: list[dict | None] = []

    def mock_req(verb: str, payload: dict | None = None):
        calls.append((verb, payload))
        return {"thread": {"id": payload["threadId"], "status": {"type": "idle"}}}

    async def update_binding(value: dict | None):
        bindings.append(value)

    for args in ("bind thread-1 --model gpt-live", "resume thread-2", "detach"):
        result = asyncio.run(
            handle_codex_command(
                CodexCommandContext(
                    args=args,
                    is_admin=True,
                    binding_update_fn=update_binding,
                ),
                request_fn=mock_req,
            )
        )
        assert "Bound" in result.text or "Attached" in result.text or "Detached" in result.text

    assert [method for method, _ in calls] == ["thread/read", "thread/read"]
    assert bindings == [
        {"threadId": "thread-1", "cwd": None, "model": "gpt-live", "provider": "codex"},
        {"threadId": "thread-2", "model": "openai/gpt-5.6-sol", "provider": "codex"},
        None,
    ]


def test_bind_refuses_active_native_thread():
    def mock_req(verb: str, payload: dict | None = None):
        return {"thread": {"id": payload["threadId"], "status": {"type": "inProgress"}}}

    updated: list[dict | None] = []
    result = asyncio.run(
        handle_codex_command(
            CodexCommandContext(
                args="bind thread-1",
                is_admin=True,
                binding_update_fn=updated.append,
            ),
            request_fn=mock_req,
        )
    )

    assert "active or unverified" in result.text
    assert updated == []


def test_model_fast_and_permissions_use_host_state_callbacks():
    updates: list[dict] = []

    async def update_state(value: dict):
        updates.append(value)

    def read_state():
        return {"fast": "off", "permissions": "guarded"}

    for args, expected in (
        ("model gpt-live", "model set"),
        ("fast on", "fast mode set"),
        ("fast status", "fast mode: off"),
        ("permissions default", "permissions set"),
        ("permissions status", "permissions: guarded"),
    ):
        result = asyncio.run(
            handle_codex_command(
                CodexCommandContext(
                    args=args,
                    is_admin=True,
                    state_read_fn=read_state,
                    state_update_fn=update_state,
                )
            )
        )
        assert expected in result.text

    assert updates == [
        {"model": "gpt-live"},
        {"fast": True},
        {"permissions": "default"},
    ]

    denied = asyncio.run(
        handle_codex_command(
            CodexCommandContext(
                args="permissions yolo",
                is_admin=False,
                state_update_fn=update_state,
            )
        )
    )
    assert "operator.admin" in denied.text


def test_command_context_wires_durable_conversation_store(tmp_path):
    store = CodexConversationStore(tmp_path / "jarvis.sqlite")
    bind_result = asyncio.run(
        handle_codex_command(
            CodexCommandContext(
                args="bind thread-persisted",
                session_id="session-1",
                conversation_store=store,
                is_admin=True,
            ),
            request_fn=lambda method, payload: {
                "thread": {"id": payload["threadId"], "status": {"type": "idle"}}
            },
        )
    )
    assert "Bound" in bind_result.text

    asyncio.run(
        handle_codex_command(
            CodexCommandContext(
                args="fast on",
                session_id="session-1",
                conversation_store=store,
                is_admin=True,
            )
        )
    )

    assert store.read_binding("session-1")["threadId"] == "thread-persisted"
    assert store.read_state("session-1") == {"fast": True}
