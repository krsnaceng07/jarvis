"""Raft RPC payload models and voting evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import LogEntry, RaftNodeState


@dataclass(slots=True)
class RequestVoteArgs:
    term: int
    candidate_id: str
    last_log_index: int
    last_log_term: int


@dataclass(slots=True)
class RequestVoteReply:
    term: int
    vote_granted: bool


@dataclass(slots=True)
class AppendEntriesArgs:
    term: int
    leader_id: str
    prev_log_index: int
    prev_log_term: int
    entries: list[LogEntry] = field(default_factory=list)
    leader_commit: int = 0


@dataclass(slots=True)
class AppendEntriesReply:
    term: int
    success: bool


def handle_request_vote(state: RaftNodeState, args: RequestVoteArgs) -> RequestVoteReply:
    """Evaluate incoming RequestVote RPC."""
    if args.term < state.current_term:
        return RequestVoteReply(term=state.current_term, vote_granted=False)

    if args.term > state.current_term:
        state.current_term = args.term
        state.role = "follower"
        state.voted_for = None

    can_vote = state.voted_for is None or state.voted_for == args.candidate_id
    if can_vote:
        state.voted_for = args.candidate_id
        return RequestVoteReply(term=state.current_term, vote_granted=True)

    return RequestVoteReply(term=state.current_term, vote_granted=False)
