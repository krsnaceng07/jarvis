from pathlib import Path

import pytest

from src.agents.sessions.sdk import create_agent_session


@pytest.mark.asyncio
async def test_factory_uses_per_agent_sqlite_session_store(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agents" / "researcher"
    result = await create_agent_session(
        {"cwd": str(tmp_path), "agentDir": str(agent_dir)}
    )

    session_manager = result["session"].session_manager
    assert session_manager.sqlite_persistence["agent_id"] == "researcher"
    assert session_manager.sqlite_persistence["store_path"] == str(
        agent_dir / "agent.sqlite"
    )
    assert (agent_dir / "agent.sqlite").exists()
