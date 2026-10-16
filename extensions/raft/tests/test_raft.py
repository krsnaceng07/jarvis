"""Unit tests for Raft extension."""

from __future__ import annotations

import pytest

from extensions.raft.src.state import RaftNodeState
from extensions.raft.src.rpc import RequestVoteArgs, handle_request_vote
from extensions.raft.plugin import raft_plugin


def test_raft_state_append_log() -> None:
    state = RaftNodeState(node_id="node_1", current_term=2)
    entry1 = state.append_log({"command": "set_key", "k": "a", "v": 1})
    assert entry1.index == 1
    assert entry1.term == 2
    assert len(state.log) == 1

    entry2 = state.append_log({"command": "set_key", "k": "b", "v": 2})
    assert entry2.index == 2
    assert len(state.log) == 2


def test_handle_request_vote() -> None:
    state = RaftNodeState(node_id="node_1", current_term=1)

    # 1. Candidate with lower term is rejected
    r1 = handle_request_vote(
        state, RequestVoteArgs(term=0, candidate_id="node_2", last_log_index=0, last_log_term=0)
    )
    assert r1.vote_granted is False

    # 2. Candidate with higher term is granted vote
    r2 = handle_request_vote(
        state, RequestVoteArgs(term=2, candidate_id="node_2", last_log_index=0, last_log_term=0)
    )
    assert r2.vote_granted is True
    assert state.current_term == 2
    assert state.voted_for == "node_2"


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    res = await raft_plugin.send("peer_node_2", {"action": "sync"})
    assert res.is_ok
    data = res.unwrap()
    assert data["replicated"] is True
    assert data["index"] == 1
