"""Unit tests for Agent-to-Agent (A2A) extension."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from extensions.a2a.src.protocol import create_task_envelope
from extensions.a2a.src.client import A2AClient
from extensions.a2a.plugin import a2a_plugin


def test_create_task_envelope() -> None:
    env = create_task_envelope(
        source_agent="agent_alpha",
        target_agent="agent_beta",
        action="summarize_document",
        payload={"doc_id": "123"},
    )
    assert env.source_agent == "agent_alpha"
    assert env.target_agent == "agent_beta"
    assert env.action == "summarize_document"
    assert env.payload["doc_id"] == "123"
    assert env.task_id.startswith("task_")

    data = env.to_dict()
    assert data["task_id"] == env.task_id


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    with patch.object(
        A2AClient, "dispatch_task", return_value={"status": "dispatched", "task_id": "task_123"}
    ):
        res = await a2a_plugin.send("agent_beta", {"action": "query", "payload": {"q": "weather"}})
        assert res.is_ok
        assert res.unwrap()["status"] == "dispatched"
