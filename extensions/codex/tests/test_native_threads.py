from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from extensions.codex.src.native_threads import execute_codex_threads


def _config(*, home_scope="agent", supervision=None):
    return SimpleNamespace(
        app_server=SimpleNamespace(home_scope=home_scope),
        supervision=supervision,
    )


def test_native_threads_requires_owner_and_opt_in():
    async def request(_method, _params):
        return {}

    with pytest.raises(PermissionError):
        asyncio.run(
            execute_codex_threads(
                _config(home_scope="user"), {"action": "list"}, request, is_owner=False
            )
        )
    with pytest.raises(PermissionError):
        asyncio.run(execute_codex_threads(_config(), {"action": "list"}, request, is_owner=True))


def test_native_threads_archive_checks_confirmation_and_idle_state():
    calls = []

    async def request(method, params):
        calls.append((method, params))
        if method == "thread/read":
            return {"thread": {"id": "t1", "status": {"type": "idle"}}}
        return {}

    result = asyncio.run(
        execute_codex_threads(
            _config(home_scope="user"),
            {"action": "archive", "thread_id": "t1", "confirm": True},
            request,
            is_owner=True,
            session_id="s1",
        )
    )
    assert result["status"] == "idle"
    assert [method for method, _ in calls] == ["thread/read", "thread/archive"]


def test_supervision_redacts_transcripts_and_disallows_attached_forks():
    async def request(method, _params):
        if method == "thread/read":
            return {"thread": {"id": "t1", "status": {"type": "idle"}, "turns": [1]}}
        return {"thread": {"id": "t2", "turns": [1]}}

    config = _config(
        supervision={"enabled": True, "allowRawTranscripts": False, "allowWriteControls": True}
    )
    result = asyncio.run(
        execute_codex_threads(
            config,
            {"action": "read", "thread_id": "t1"},
            request,
            is_owner=True,
        )
    )
    assert "turns" not in result["thread"]
    with pytest.raises(PermissionError, match="stay detached"):
        asyncio.run(
            execute_codex_threads(
                config,
                {"action": "fork", "thread_id": "t1", "attach": True},
                request,
                is_owner=True,
            )
        )
