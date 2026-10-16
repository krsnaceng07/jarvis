"""Tests for workboard store, lifecycle, tools, and CLI."""

from __future__ import annotations

import pytest

from extensions.workboard.src.cli import handle_workboard_cli
from extensions.workboard.src.store import WorkboardStore
from extensions.workboard.src.tools import (
    _handle_workboard_claim,
    _handle_workboard_comment,
    _handle_workboard_complete,
    _handle_workboard_create,
    _handle_workboard_heartbeat,
    _handle_workboard_list,
    _handle_workboard_move,
    _handle_workboard_proof,
    _handle_workboard_read,
    _handle_workboard_stats,
)


def test_board_lifecycle() -> None:
    store = WorkboardStore(":memory:")
    boards = store.list_boards()
    assert len(boards) == 1
    assert boards[0].id == "default"

    new_board = store.create_board("sprint-1", "Sprint 1", "Active sprint board")
    assert new_board.id == "sprint-1"
    assert len(store.list_boards()) == 2

    assert store.archive_board("sprint-1") is True
    assert len(store.list_boards(include_archived=False)) == 1
    assert len(store.list_boards(include_archived=True)) == 2


def test_card_lifecycle() -> None:
    store = WorkboardStore(":memory:")
    card = store.create_card(
        title="Implement feature", notes="Write code", priority="high", labels=["core"]
    )
    assert card.title == "Implement feature"
    assert card.status == "todo"
    assert card.priority == "high"

    # Move card
    moved = store.move_card(card.id, to_status="ready")
    assert moved is not None
    assert moved.status == "ready"
    assert len(moved.events) == 2

    # Claim card
    success, token, claimed = store.claim_card(
        card.id, owner_id="agent-worker-1", timeout_seconds=600
    )
    assert success is True
    assert token is not None
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.claim is not None
    assert claimed.claim.owner_id == "agent-worker-1"

    # Heartbeat
    hb = store.heartbeat_card(card.id, owner_id="agent-worker-1", token=token)
    assert hb is True

    # Complete card
    comp = store.complete_card(card.id, owner_id="agent-worker-1", token=token)
    assert comp is True

    final_card = store.get_card(card.id)
    assert final_card is not None
    assert final_card.status == "done"
    assert final_card.claim is None
    assert final_card.completed_at is not None


def test_card_block_and_unblock() -> None:
    store = WorkboardStore(":memory:")
    card = store.create_card(title="Blocked task")
    blocked = store.block_card(card.id, reason="Missing API key")
    assert blocked is not None
    assert blocked.status == "blocked"
    assert blocked.metadata["blockReason"] == "Missing API key"

    unblocked = store.unblock_card(card.id)
    assert unblocked is not None
    assert unblocked.status == "ready"
    assert "blockReason" not in unblocked.metadata


def test_card_comments_proof_and_attachments() -> None:
    store = WorkboardStore(":memory:")
    card = store.create_card(title="Artifact task")

    comment = store.add_comment(card.id, body="LGTM")
    assert comment.body == "LGTM"

    proof = store.add_proof(card.id, status="passed", label="CI proof", command="pytest")
    assert proof.status == "passed"
    assert proof.label == "CI proof"

    att = store.add_attachment(
        card.id, file_name="report.pdf", content=b"%PDF-report", mime_type="application/pdf"
    )
    assert att.file_name == "report.pdf"
    assert att.byte_size == len(b"%PDF-report")

    read_att = store.read_attachment(att.id)
    assert read_att is not None
    assert read_att[1] == b"%PDF-report"

    assert store.delete_attachment(att.id) is True
    assert store.read_attachment(att.id) is None


@pytest.mark.asyncio
async def test_tool_handlers() -> None:
    store = WorkboardStore(":memory:")
    create_res = await _handle_workboard_create({"title": "Tool task", "priority": "urgent"}, store)
    card_id = create_res["details"]["cardId"]

    read_res = await _handle_workboard_read({"cardId": card_id}, store)
    assert "Tool task" in read_res["content"][0]["text"]

    list_res = await _handle_workboard_list({}, store)
    assert "Tool task" in list_res["content"][0]["text"]

    claim_res = await _handle_workboard_claim({"cardId": card_id, "ownerId": "worker-1"}, store)
    token = claim_res["details"]["token"]

    hb_res = await _handle_workboard_heartbeat(
        {"cardId": card_id, "ownerId": "worker-1", "token": token}, store
    )
    assert hb_res["details"]["success"] is True

    move_res = await _handle_workboard_move({"cardId": card_id, "toStatus": "review"}, store)
    assert "[review]" in move_res["content"][0]["text"]

    comment_res = await _handle_workboard_comment({"cardId": card_id, "body": "Checked"}, store)
    assert "Added comment" in comment_res["content"][0]["text"]

    proof_res = await _handle_workboard_proof(
        {"cardId": card_id, "status": "passed", "label": "Unit tests"}, store
    )
    assert "Attached PASSED proof" in proof_res["content"][0]["text"]

    comp_res = await _handle_workboard_complete(
        {"cardId": card_id, "ownerId": "worker-1", "token": token}, store
    )
    assert "DONE" in comp_res["content"][0]["text"]

    stats_res = await _handle_workboard_stats({}, store)
    assert stats_res["details"]["total"] == 1
    assert stats_res["details"]["done"] == 1


def test_cli_output() -> None:
    store = WorkboardStore(":memory:")
    store.create_card("CLI Task")
    status_out = handle_workboard_cli(["status"], store)
    assert "Total cards: 1" in status_out

    list_out = handle_workboard_cli(["list"], store)
    assert "CLI Task" in list_out
