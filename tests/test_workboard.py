"""Tests for src/plugins/workboard.py.

Mirrors tests of extensions/workboard/src/store-constants.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.workboard import (
    DEFAULT_CLAIM_TTL_MS,
    MAX_ATTACHMENT_BYTES,
    MAX_CARDS,
    WORKBOARD_AGENT_TOOLS,
    WORKBOARD_CARD_PRIORITIES,
    WORKBOARD_CARD_STATUSES,
    WorkboardCard,
)


def test_workboard_constants():
    assert "triage" in WORKBOARD_CARD_STATUSES
    assert "running" in WORKBOARD_CARD_STATUSES
    assert "done" in WORKBOARD_CARD_STATUSES
    assert len(WORKBOARD_CARD_STATUSES) == 9

    assert "low" in WORKBOARD_CARD_PRIORITIES
    assert "urgent" in WORKBOARD_CARD_PRIORITIES
    assert len(WORKBOARD_CARD_PRIORITIES) == 4

    assert MAX_CARDS == 2000
    assert MAX_ATTACHMENT_BYTES == 256 * 1024
    assert DEFAULT_CLAIM_TTL_MS == 30 * 60 * 1000


def test_workboard_agent_tools():
    assert "workboard_list" in WORKBOARD_AGENT_TOOLS
    assert "workboard_read" in WORKBOARD_AGENT_TOOLS
    assert "workboard_claim" in WORKBOARD_AGENT_TOOLS
    assert "workboard_dispatch" in WORKBOARD_AGENT_TOOLS


def test_workboard_card_defaults():
    card = WorkboardCard(id="card_101", title="Fix bug")
    assert card.board_id == "default"
    assert card.status == "todo"
    assert card.priority == "normal"
    assert card.labels == []
    assert card.agent_id is None
