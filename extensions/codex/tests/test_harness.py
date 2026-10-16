"""Tests for Codex agent harness & remote workspace attachment reader.

OpenClaw parity: ``extensions/codex/harness.test.ts``.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from extensions.codex.harness import (
    CODEX_HARNESS_ID,
    RemoteWorkspaceAttachmentReader,
    create_codex_app_server_agent_harness,
)


def test_harness_defaults():
    harness = create_codex_app_server_agent_harness()
    assert harness.id == CODEX_HARNESS_ID
    assert "codex" in harness.provider_ids
    assert "openai" in harness.provider_ids
    assert harness.auth_bootstrap == "harness"
    assert "bootstrap" in harness.context_engine_capabilities
    assert "web_fetch" in harness.safe_deny_tools


def test_harness_custom_config():
    harness = create_codex_app_server_agent_harness(
        config={
            "remoteWorkspaceRoot": "/tmp/remote_ws",
            "fastMode": "on",
        }
    )
    assert harness.plugin_config.remote_workspace_root == "/tmp/remote_ws"
    assert harness.plugin_config.fast_mode == "on"

    reader = harness.get_remote_attachment_reader()
    assert reader is not None
    assert reader.remote_root == "/tmp/remote_ws"


def test_harness_owns_dynamic_tool_and_web_search_projection():
    harness = create_codex_app_server_agent_harness(config={"codexDynamicToolsLoading": "direct"})
    projected = harness.project_dynamic_tools(
        [{"name": "message", "inputSchema": {}}, {"name": "exec", "inputSchema": {}}]
    )
    assert projected["specs"][0]["name"] == "message"
    assert harness.resolve_web_search_plan({"tools": {"web": {"search": {}}}})["kind"] == (
        "native-hosted"
    )


def test_harness_delegates_native_thread_controls():
    harness = create_codex_app_server_agent_harness(config={"appServer": {"homeScope": "user"}})

    async def request(method, _params):
        if method == "thread/list":
            return {"data": [{"id": "t1"}]}
        return {}

    result = asyncio.run(
        harness.execute_native_threads({"action": "list"}, request, is_owner=True, session_id="s1")
    )
    assert result["data"][0]["id"] == "t1"


def test_remote_attachment_reader_path_validation():
    with tempfile.TemporaryDirectory() as tmpdir:
        sub_file = os.path.join(tmpdir, "valid.txt")
        with open(sub_file, "w", encoding="utf-8") as f:
            f.write("content")

        reader = RemoteWorkspaceAttachmentReader(remote_root=tmpdir)
        resolved = reader.validate_and_resolve_remote_path("valid.txt")
        assert os.path.exists(resolved)

        # Path traversal rejection
        with pytest.raises(ValueError, match="Path traversal rejected"):
            reader.validate_and_resolve_remote_path("../outside.txt")
