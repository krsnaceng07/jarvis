from __future__ import annotations

import asyncio

from extensions.codex.plugin import CodexProvider
from extensions.codex.src.app_server.config import resolve_codex_app_server_runtime_options
from extensions.codex.src.turn import complete_codex_turn


def test_complete_codex_turn_starts_thread_then_submits_user_input():
    calls = []

    async def request(method, params):
        calls.append((method, params))
        if method == "thread/start":
            return {"thread": {"id": "thread-1"}}
        return {"text": "hello from codex"}

    result = asyncio.run(
        complete_codex_turn(
            [{"role": "system", "content": "be concise"}, {"role": "user", "content": "hi"}],
            request,
            model="gpt-test",
        )
    )
    assert result == "hello from codex"
    assert calls == [
        ("thread/start", {"model": "gpt-test"}),
        (
            "turn/start",
            {
                "threadId": "thread-1",
                "input": [{"type": "text", "text": "hi"}],
                "model": "gpt-test",
            },
        ),
    ]


def test_provider_completion_uses_injected_codex_transport():
    async def request(method, _params):
        return {"thread": {"id": "thread-1"}} if method == "thread/start" else {"text": "done"}

    result = asyncio.run(
        CodexProvider().complete([{"role": "user", "content": "run"}], request_fn=request)
    )
    assert result.value == "done"


def test_turn_applies_guardian_posture_to_thread_start():
    calls = []

    async def request(method, params):
        calls.append((method, params))
        return {"thread": {"id": "thread-1"}} if method == "thread/start" else {"text": "ok"}

    options = resolve_codex_app_server_runtime_options(
        {"appServer": {"mode": "guardian", "defaultWorkspaceDir": "/workspace"}}, env={}
    )
    asyncio.run(
        complete_codex_turn(
            [{"role": "user", "content": "hi"}],
            request,
            runtime_options=options,
        )
    )

    assert calls[0][1] == {
        "cwd": "/workspace",
        "approvalPolicy": "on-request",
        "approvalsReviewer": "auto_review",
        "sandbox": "workspace-write",
    }


def test_turn_applies_network_proxy_config_patch_instead_of_sandbox():
    calls = []

    async def request(method, params):
        calls.append((method, params))
        return {"thread": {"id": "thread-1"}} if method == "thread/start" else {"text": "ok"}

    options = resolve_codex_app_server_runtime_options(
        {
            "appServer": {
                "networkProxy": {
                    "enabled": True,
                    "domains": {"api.openai.com": "allow"},
                }
            }
        },
        env={},
    )
    asyncio.run(
        complete_codex_turn(
            [{"role": "user", "content": "hi"}],
            request,
            runtime_options=options,
        )
    )

    assert "config" in calls[0][1]
    assert "default_permissions" in calls[0][1]["config"]
    assert "sandbox" not in calls[0][1]
