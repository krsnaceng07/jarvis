"""tests.test_channel_agent_tool_pipeline — Integration tests for channel tool execution.

Verifies OpenClaw-parity channel agent tool calling, multi-turn loops,
slash command routing, and session transcript persistence.
"""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

SimpleNamespace = types.SimpleNamespace

import pytest

from src.agents.task.session_transcript_store import SessionTranscriptStore
from src.channels.channel_agent_pipeline import ChannelAgentPipeline


@pytest.fixture
def clean_transcript_store(tmp_path: Path):
    db_path = str(tmp_path / "test_agent.sqlite")
    store = SessionTranscriptStore(db_path=db_path)
    return store


@pytest.mark.asyncio
async def test_channel_slash_command_dispatch():
    """Verify channel messages starting with / are routed through CommandRouter."""
    pipeline = ChannelAgentPipeline.get_instance()

    # Test unknown command produces guidance
    res = await pipeline._dispatch_slash_command(
        command_text="/unknown_command_xyz",
        channel_id="telegram",
        sender_id="user123",
    )
    assert res is not None
    assert "Unknown command: /unknown_command_xyz" in res

    # Test empty command name
    res_empty = await pipeline._dispatch_slash_command(
        command_text="/",
        channel_id="telegram",
        sender_id="user123",
    )
    assert res_empty == "Empty command name."


@pytest.mark.asyncio
async def test_channel_tool_execution_filesystem_tools(tmp_path: Path):
    """Verify coding/filesystem tools (mkdir, write, read, ls) execute cleanly from channel context."""
    pipeline = ChannelAgentPipeline.get_instance()
    pipeline._ensure_tools_loaded()

    test_dir = tmp_path / "channel_test_dir"
    test_file = test_dir / "test.txt"

    # 1. mkdir tool
    mkdir_res = await pipeline._execute_channel_tool(
        tool_name="mkdir",
        args={"path": str(test_dir)},
        channel_id="telegram",
    )
    assert test_dir.exists()
    assert "created" in mkdir_res.lower() or "ok" in mkdir_res.lower() or str(test_dir) in mkdir_res

    # 2. write tool
    write_res = await pipeline._execute_channel_tool(
        tool_name="write",
        args={"path": str(test_file), "content": "Hello from Telegram channel turn!"},
        channel_id="telegram",
    )
    assert test_file.exists()
    assert "wrote" in write_res.lower() or "ok" in write_res.lower() or "channel" in test_file.read_text()

    # 3. read tool
    read_res = await pipeline._execute_channel_tool(
        tool_name="read",
        args={"path": str(test_file)},
        channel_id="telegram",
    )
    assert "Hello from Telegram channel turn!" in read_res

    # 4. ls tool
    ls_res = await pipeline._execute_channel_tool(
        tool_name="ls",
        args={"path": str(test_dir)},
        channel_id="telegram",
    )
    assert "test.txt" in ls_res


@pytest.mark.asyncio
async def test_channel_save_memory_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify save_memory tool called from channel updates long-term memory."""
    from apps.desktop.src.jarvis_desktop.memory_bridge import load_memory

    # The save path falls back to the active workspace (the repo root) and would
    # append a duplicate directive to the real USER.md; keep it in tmp_path.
    monkeypatch.setenv("JARVIS_WORKSPACE", str(tmp_path))
    pipeline = ChannelAgentPipeline.get_instance()
    mem_res = await pipeline._execute_channel_tool(
        tool_name="save_memory",
        args={
            "category": "preferences",
            "key": "channel_fav_editor",
            "value": "Neovim via Telegram",
        },
        channel_id="telegram",
    )
    assert "successfully saved" in mem_res.lower()

    mem = load_memory()
    assert mem.get("preferences", {}).get("channel_fav_editor", {}).get("value") == "Neovim via Telegram"


@pytest.mark.asyncio
async def test_channel_shutdown_blocked_from_channel():
    """Verify remote shutdown command via channel is blocked for host security."""
    pipeline = ChannelAgentPipeline.get_instance()
    res = await pipeline._execute_channel_tool(
        tool_name="shutdown_jarvis",
        args={"user_command": "shutdown jarvis", "confirmed": True},
        channel_id="telegram",
    )
    assert "blocked" in res.lower() or "security" in res.lower()


@pytest.mark.asyncio
async def test_channel_process_open_path_delegation():
    """Verify process(action='open_path') delegates to open_path tool without errors."""
    pipeline = ChannelAgentPipeline.get_instance()
    pipeline._ensure_tools_loaded()

    # Mock open_path handler in coding tools
    mock_open_path = AsyncMock(return_value={"result": "Successfully opened notepad"})
    pipeline._coding_tools["open_path"] = {"execute": mock_open_path}

    res = await pipeline._execute_channel_tool(
        tool_name="process",
        args={"action": "open_path", "target": "notepad.exe"},
        channel_id="telegram",
    )
    assert "notepad" in res.lower()
    mock_open_path.assert_called_once()


@pytest.mark.asyncio
async def test_channel_agent_turn_multi_turn_tool_loop(tmp_path: Path):
    """Verify agent multi-turn tool calling loop: generate_content -> tool -> reply -> transcript."""
    pipeline = ChannelAgentPipeline.get_instance()
    test_file = tmp_path / "created_by_channel.txt"

    assembled = SimpleNamespace(
        turn_id="turn_test_100",
        message=SimpleNamespace(
            channel_id="telegram",
            sender_id="tg_user_42",
            text="Create file created_by_channel.txt with content 'OpenClaw Parity'",
        ),
        session=SimpleNamespace(
            session_key="telegram:chat_999",
        ),
    )

    # Mock GenAI responses:
    # Turn 1: Model requests write tool call
    # Turn 2: Model returns final assistant text reply
    fc = SimpleNamespace(
        name="write",
        args={"path": str(test_file), "content": "OpenClaw Parity"},
    )
    resp_turn_1 = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    role="model",
                    parts=[SimpleNamespace(function_call=fc, text=None)],
                )
            )
        ],
        function_calls=[fc],
        text=None,
    )

    resp_turn_2 = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    role="model",
                    parts=[SimpleNamespace(function_call=None, text="File created successfully, sir.")],
                )
            )
        ],
        function_calls=None,
        text="File created successfully, sir.",
    )

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [resp_turn_1, resp_turn_2]

    # Patch client and transcript store
    db_path = str(tmp_path / "agent.sqlite")
    mock_store = SessionTranscriptStore(db_path=db_path)

    with (
        patch("src.channels.channel_agent_pipeline._read_gemini_api_key", return_value="fake_api_key"),
        patch("src.channels.channel_agent_pipeline.genai.Client", return_value=mock_client),
        patch("src.agents.task.session_transcript_store.SessionTranscriptStore", return_value=mock_store),
    ):
        reply = await pipeline.dispatch_turn(assembled)

    assert reply == "File created successfully, sir."
    assert test_file.exists()
    assert test_file.read_text() == "OpenClaw Parity"

    # Verify session transcript persistence
    entries = mock_store.get_recent_entries("telegram:chat_999")
    entry_types = [e["entry_type"] for e in entries]
    assert "user_turn" in entry_types
    assert "tool_executions" in entry_types
    assert "assistant_reply" in entry_types
