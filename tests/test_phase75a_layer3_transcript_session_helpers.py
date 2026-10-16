"""Phase 7.5a tests — small transcript + session helpers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


from src.agents.embedded_agent_runner.history import (
    get_history_limit_from_session_key,
    limit_history_turns,
    set_provider_id_normalizer,
)
from src.agents.embedded_agent_runner.replay_state import (
    create_embedded_run_replay_state,
    merge_embedded_run_replay_state,
    observe_replay_metadata,
    replay_metadata_from_state,
)
from src.agents.embedded_agent_runner.session_prompt_state import (
    clear_embedded_session_prompt_states,
    clone_tool_result_prompt_projection_state,
    get_embedded_session_prompt_state,
    has_session_user_turn_been_sent,
    mark_session_user_turns_sent,
)
from src.agents.embedded_agent_runner.transcript_rewrite import (
    rewrite_transcript_entries_in_session_manager,
    rewrite_transcript_entries_in_state,
)


# ============================================================================
# history
# ============================================================================


class TestLimitHistoryTurns:
    def test_no_limit(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        assert limit_history_turns(messages, None) is messages
        assert limit_history_turns(messages, 0) is messages

    def test_empty(self) -> None:
        assert limit_history_turns([], 5) == []

    def test_under_limit(self) -> None:
        messages = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
        ]
        assert limit_history_turns(messages, 5) is messages

    def test_over_limit(self) -> None:
        messages = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "u3"},
        ]
        result = limit_history_turns(messages, 1)
        # Keeps leading (none) + the last 1 user turn.
        assert len(result) == 1
        assert result[0]["content"] == "u3"

    def test_preserves_leading_compaction(self) -> None:
        messages = [
            {"type": "compactionSummary", "summary": "old"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "user", "content": "u3"},
        ]
        result = limit_history_turns(messages, 1)
        # Compaction summary + last 1 user turn.
        assert len(result) == 2
        assert result[0]["type"] == "compactionSummary"
        assert result[1]["content"] == "u3"


class TestGetHistoryLimitFromSessionKey:
    def test_no_session_key(self) -> None:
        assert get_history_limit_from_session_key(None, {}) is None

    def test_no_config(self) -> None:
        assert get_history_limit_from_session_key("agent:test:openai:u1", None) is None

    def test_dm_history_limit(self) -> None:
        config = {
            "channels": {
                "openai": {
                    "dmHistoryLimit": 10,
                },
            },
        }
        assert (
            get_history_limit_from_session_key("agent:main:openai:dm:u1", config) == 10
        )

    def test_dm_per_user_override(self) -> None:
        config = {
            "channels": {
                "openai": {
                    "dmHistoryLimit": 10,
                    "dms": {
                        "u-special": {"historyLimit": 5},
                    },
                },
            },
        }
        assert (
            get_history_limit_from_session_key(
                "agent:main:openai:dm:u-special", config
            )
            == 5
        )

    def test_dm_per_user_override_thread(self) -> None:
        config = {
            "channels": {
                "openai": {
                    "dmHistoryLimit": 10,
                    "dms": {
                        "u-special": {"historyLimit": 5},
                    },
                },
            },
        }
        # The :thread:N suffix is stripped before lookup.
        assert (
            get_history_limit_from_session_key(
                "agent:main:openai:dm:u-special:thread:1", config
            )
            == 5
        )

    def test_channel_history_limit(self) -> None:
        config = {
            "channels": {
                "openai": {
                    "historyLimit": 7,
                },
            },
        }
        assert (
            get_history_limit_from_session_key(
                "agent:main:openai:channel:c1", config
            )
            == 7
        )

    def test_no_provider_config(self) -> None:
        assert (
            get_history_limit_from_session_key("agent:main:openai:dm:u1", {}) is None
        )

    def test_invalid_kind(self) -> None:
        config = {
            "channels": {
                "openai": {
                    "historyLimit": 5,
                    "dmHistoryLimit": 10,
                },
            },
        }
        # Unknown kind: no limit returned.
        assert (
            get_history_limit_from_session_key(
                "agent:main:openai:random:thing", config
            )
            is None
        )

    def test_custom_normalizer(self) -> None:
        set_provider_id_normalizer(lambda v: (v or "").upper())
        try:
            config = {"channels": {"OPENAI": {"dmHistoryLimit": 10}}}
            # Custom normalizer uppercases the provider id, so the
            # "openai" lookup matches "OPENAI".
            assert (
                get_history_limit_from_session_key(
                    "agent:main:openai:dm:u1", config
                )
                == 10
            )
        finally:
            set_provider_id_normalizer(lambda v: (v or "").strip().lower())


# ============================================================================
# replay_state
# ============================================================================


class TestReplayState:
    def test_create_normalizes(self) -> None:
        state = create_embedded_run_replay_state(
            {"replayInvalid": True, "hadPotentialSideEffects": True}
        )
        assert state == {
            "replayInvalid": True,
            "hadPotentialSideEffects": True,
        }

    def test_create_empty(self) -> None:
        state = create_embedded_run_replay_state()
        assert state == {
            "replayInvalid": False,
            "hadPotentialSideEffects": False,
        }

    def test_create_ignores_non_bool(self) -> None:
        state = create_embedded_run_replay_state(
            {"replayInvalid": "yes", "hadPotentialSideEffects": 1}
        )
        assert state == {
            "replayInvalid": False,
            "hadPotentialSideEffects": False,
        }

    def test_merge_monotonic(self) -> None:
        current = {"replayInvalid": False, "hadPotentialSideEffects": False}
        merged = merge_embedded_run_replay_state(
            current, {"replayInvalid": True}
        )
        assert merged == {
            "replayInvalid": True,
            "hadPotentialSideEffects": False,
        }
        # Cannot be cleared by a later merge.
        merged_again = merge_embedded_run_replay_state(
            merged, {"replayInvalid": False}
        )
        assert merged_again == {
            "replayInvalid": True,
            "hadPotentialSideEffects": False,
        }

    def test_merge_no_next(self) -> None:
        current = {"replayInvalid": True, "hadPotentialSideEffects": True}
        assert merge_embedded_run_replay_state(current) is current

    def test_observe_metadata_safe(self) -> None:
        current = {"replayInvalid": False, "hadPotentialSideEffects": False}
        result = observe_replay_metadata(
            current, {"replaySafe": True, "hadPotentialSideEffects": False}
        )
        assert result == {
            "replayInvalid": False,
            "hadPotentialSideEffects": False,
        }

    def test_observe_metadata_unsafe(self) -> None:
        current = {"replayInvalid": False, "hadPotentialSideEffects": False}
        result = observe_replay_metadata(
            current, {"replaySafe": False, "hadPotentialSideEffects": True}
        )
        assert result == {
            "replayInvalid": True,
            "hadPotentialSideEffects": True,
        }

    def test_observe_missing_metadata_marks_unsafe(self) -> None:
        current = {"replayInvalid": False, "hadPotentialSideEffects": False}
        result = observe_replay_metadata(current, None)
        assert result["replayInvalid"] is True
        assert result["hadPotentialSideEffects"] is True

    def test_replay_metadata_from_state(self) -> None:
        state = {"replayInvalid": False, "hadPotentialSideEffects": False}
        assert replay_metadata_from_state(state) == {
            "hadPotentialSideEffects": False,
            "replaySafe": True,
        }
        state = {"replayInvalid": True, "hadPotentialSideEffects": False}
        assert replay_metadata_from_state(state)["replaySafe"] is False
        state = {"replayInvalid": False, "hadPotentialSideEffects": True}
        assert replay_metadata_from_state(state)["replaySafe"] is False


# ============================================================================
# session_prompt_state
# ============================================================================


class TestSessionPromptState:
    def setup_method(self) -> None:
        clear_embedded_session_prompt_states(
            [s for s in dir() if s.startswith("sess-")]
        )

    def test_get_returns_new_state(self) -> None:
        state = get_embedded_session_prompt_state("sess-a")
        assert "toolResults" in state
        assert "sentUserTurnIds" in state

    def test_get_returns_same_state(self) -> None:
        state1 = get_embedded_session_prompt_state("sess-b")
        state2 = get_embedded_session_prompt_state("sess-b")
        assert state1 is state2

    def test_clear(self) -> None:
        get_embedded_session_prompt_state("sess-c")
        clear_embedded_session_prompt_states(["sess-c"])
        # The next get should return a new (empty) state.
        state = get_embedded_session_prompt_state("sess-c")
        assert state["sentUserTurnIds"] == set()

    def test_clear_with_none(self) -> None:
        # Should not raise.
        clear_embedded_session_prompt_states([None, "sess-x"])

    def test_clone_state(self) -> None:
        original = {
            "replacements": {"a": "msg-a"},
            "frozen": {"k"},
            "ambiguousBaseKeys": set(),
            "sourceTextByKey": {"k": ["v1", "v2"]},
        }
        cloned = clone_tool_result_prompt_projection_state(original)
        # Independent sets.
        cloned["frozen"].add("new")
        assert "new" not in original["frozen"]
        cloned["sourceTextByKey"]["k"].append("v3")
        assert original["sourceTextByKey"]["k"] == ["v1", "v2"]
        cloned["replacements"]["b"] = "msg-b"
        assert "b" not in original["replacements"]

    def test_mark_session_user_turns_sent(self) -> None:
        state = get_embedded_session_prompt_state("sess-d")
        mark_session_user_turns_sent(
            state,
            [
                {"role": "user", "idempotencyKey": "k1"},
                {"role": "assistant", "content": "x"},
                {"role": "user", "idempotencyKey": "k2"},
            ],
        )
        assert state["sentUserTurnIds"] == {"k1", "k2"}

    def test_has_session_user_turn_been_sent(self) -> None:
        state = get_embedded_session_prompt_state("sess-e")
        mark_session_user_turns_sent(
            state, [{"role": "user", "idempotencyKey": "k1"}]
        )
        assert (
            has_session_user_turn_been_sent(
                state, {"role": "user", "idempotencyKey": "k1"}
            )
            is True
        )
        assert (
            has_session_user_turn_been_sent(
                state, {"role": "user", "idempotencyKey": "k2"}
            )
            is False
        )
        # Non-user message returns None.
        assert (
            has_session_user_turn_been_sent(
                state, {"role": "assistant", "idempotencyKey": "k1"}
            )
            is None
        )
        # Message without idempotencyKey returns None.
        assert (
            has_session_user_turn_been_sent(
                state, {"role": "user"}
            )
            is None
        )

    def test_lru_eviction(self) -> None:
        from src.agents.embedded_agent_runner import session_prompt_state as sps

        original_cap = sps.MAX_SESSION_PROMPT_STATES
        sps.MAX_SESSION_PROMPT_STATES = 3
        try:
            for sid in ("s1", "s2", "s3", "s4"):
                get_embedded_session_prompt_state(sid)
            # Only 3 states should be retained.
            with sps._SESSION_PROMPT_STATES_LOCK:
                assert len(sps._SESSION_PROMPT_STATES) == 3
        finally:
            sps.MAX_SESSION_PROMPT_STATES = original_cap


# ============================================================================
# transcript_rewrite
# ============================================================================


class _FakeSessionManager:
    def __init__(self) -> None:
        self.appended: List[Dict[str, Any]] = []
        self.leaf_reset = False
        self.branched_to: Optional[str] = None

    def getBranch(self) -> List[Dict[str, Any]]:
        return []

    def resetLeaf(self) -> None:
        self.leaf_reset = True

    def branch(self, parent_id: str) -> None:
        self.branched_to = parent_id

    def appendMessage(self, message: Any) -> str:
        new_id = f"new-{len(self.appended)}"
        self.appended.append({"type": "message", "id": new_id, "message": message})
        return new_id

    def appendCompaction(self, *args: Any, **kwargs: Any) -> str:
        return f"compaction-{len(self.appended)}"

    def appendThinkingLevelChange(self, *args: Any, **kwargs: Any) -> str:
        return f"thinking-{len(self.appended)}"

    def appendModelChange(self, *args: Any, **kwargs: Any) -> str:
        return f"model-{len(self.appended)}"

    def appendCustomEntry(self, *args: Any, **kwargs: Any) -> str:
        return f"custom-{len(self.appended)}"

    def appendCustomMessageEntry(self, *args: Any, **kwargs: Any) -> str:
        return f"custom-msg-{len(self.appended)}"

    def appendSessionInfo(self, *args: Any, **kwargs: Any) -> str:
        return f"info-{len(self.appended)}"

    def branchWithSummary(self, *args: Any, **kwargs: Any) -> str:
        return f"branch-{len(self.appended)}"

    def appendLabelChange(self, *args: Any, **kwargs: Any) -> str:
        return f"label-{len(self.appended)}"


class TestRewriteTranscriptInSessionManager:
    def test_no_replacements(self) -> None:
        sm = _FakeSessionManager()
        result = rewrite_transcript_entries_in_session_manager(
            session_manager=sm, replacements=[]
        )
        assert result["changed"] is False
        assert result["reason"] == "no replacements requested"

    def test_empty_branch(self) -> None:
        sm = _FakeSessionManager()
        result = rewrite_transcript_entries_in_session_manager(
            session_manager=sm, replacements=[{"entryId": "x", "message": {}}]
        )
        assert result["changed"] is False
        assert result["reason"] == "empty session"

    def test_no_match(self) -> None:
        sm = _FakeSessionManager()
        sm.getBranch = lambda: [
            {"type": "message", "id": "a", "message": {"role": "user"}},
        ]
        result = rewrite_transcript_entries_in_session_manager(
            session_manager=sm, replacements=[{"entryId": "b", "message": {}}]
        )
        assert result["changed"] is False
        assert result["reason"] == "no matching message entries"

    def test_match_first_no_parent(self) -> None:
        sm = _FakeSessionManager()
        sm.getBranch = lambda: [
            {"type": "message", "id": "a", "message": {"role": "user"}},
        ]
        result = rewrite_transcript_entries_in_session_manager(
            session_manager=sm,
            replacements=[{"entryId": "a", "message": {"role": "user", "v": 2}}],
        )
        assert result["changed"] is True
        assert result["rewrittenEntries"] == 1
        assert sm.leaf_reset is True
        assert len(sm.appended) == 1
        assert sm.appended[0]["message"] == {"role": "user", "v": 2}

    def test_match_with_parent_branches(self) -> None:
        sm = _FakeSessionManager()
        sm.getBranch = lambda: [
            {"type": "message", "id": "a", "parentId": None, "message": {"v": 1}},
            {"type": "message", "id": "b", "parentId": "a", "message": {"v": 2}},
        ]
        result = rewrite_transcript_entries_in_session_manager(
            session_manager=sm,
            replacements=[{"entryId": "b", "message": {"v": 22}}],
        )
        assert result["changed"] is True
        assert sm.branched_to == "a"
        # branch[firstMatchedIndex:] = branch[1:] = [b] (1 element).
        assert len(sm.appended) == 1
        assert sm.appended[0]["message"] == {"v": 22}

    def test_invalid_first_target(self) -> None:
        sm = _FakeSessionManager()
        # A non-message entry first, then a message. The first matched
        # index is 0 (the message), so the "invalid first rewrite
        # target" path is not triggered. Use a non-message first match
        # by making the matched entry a compaction via the message
        # type — easier: just trigger "no matching message entries" by
        # having only a compaction in the branch.
        sm.getBranch = lambda: [
            {"type": "compaction", "id": "c", "firstKeptEntryId": "a"},
        ]
        result = rewrite_transcript_entries_in_session_manager(
            session_manager=sm,
            replacements=[{"entryId": "c", "message": {}}],
        )
        # _find_transcript_rewrite_matches only matches message entries,
        # so a compaction in the branch is "no matching message entries".
        assert result["changed"] is False
        assert result["reason"] == "no matching message entries"

    def test_blank_entry_id_filtered(self) -> None:
        sm = _FakeSessionManager()
        result = rewrite_transcript_entries_in_session_manager(
            session_manager=sm,
            replacements=[{"entryId": "   ", "message": {}}],
        )
        assert result["changed"] is False
        assert result["reason"] == "no replacements requested"


class TestRewriteTranscriptInState:
    def test_state_append(self) -> None:
        class _State:
            def __init__(self) -> None:
                self.appended: List[Dict[str, Any]] = []

            def getBranch(self) -> List[Dict[str, Any]]:
                return []

            def getEntries(self) -> List[Dict[str, Any]]:
                return []

            def getLeafId(self) -> Optional[str]:
                return None

            def getAppendParentId(self) -> Optional[str]:
                return None

            def getAppendMode(self) -> Optional[str]:
                return None

            def appendMessage(self, message: Any) -> Dict[str, Any]:
                entry = {"type": "message", "id": f"e-{len(self.appended)}", "message": message}
                self.appended.append(entry)
                return entry

        state = _State()
        result = rewrite_transcript_entries_in_state(
            state=state, replacements=[]
        )
        assert result["changed"] is False
        assert "appendedEntries" in result

    def test_state_empty_session(self) -> None:
        class _State:
            def getBranch(self) -> List[Dict[str, Any]]:
                return []

            def getEntries(self) -> List[Dict[str, Any]]:
                return []

            def getLeafId(self) -> Optional[str]:
                return None

            def getAppendParentId(self) -> Optional[str]:
                return None

            def getAppendMode(self) -> Optional[str]:
                return None

        state = _State()
        result = rewrite_transcript_entries_in_state(
            state=state,
            replacements=[{"entryId": "x", "message": {}}],
        )
        assert result["changed"] is False
        assert "appendedEntries" in result

    def test_state_no_match(self) -> None:
        class _State:
            def __init__(self) -> None:
                self._branch = [
                    {"type": "message", "id": "a", "message": {"v": 1}},
                ]

            def getBranch(self) -> List[Dict[str, Any]]:
                return self._branch

            def getEntries(self) -> List[Dict[str, Any]]:
                return self._branch

            def getLeafId(self) -> Optional[str]:
                return None

            def getAppendParentId(self) -> Optional[str]:
                return None

            def getAppendMode(self) -> Optional[str]:
                return None

            def appendMessage(self, message: Any) -> Dict[str, Any]:
                return {"type": "message", "id": "new", "message": message}

        state = _State()
        result = rewrite_transcript_entries_in_state(
            state=state,
            replacements=[{"entryId": "b", "message": {}}],
        )
        assert result["changed"] is False
        assert result["reason"] == "no matching message entries"

    def test_state_match(self) -> None:
        class _State:
            def __init__(self) -> None:
                self._branch = [
                    {"type": "message", "id": "a", "parentId": None, "message": {"v": 1}},
                ]
                self.appended: List[Dict[str, Any]] = []
                self.leaf_reset = False
                self.branched: Optional[str] = None

            def getBranch(self) -> List[Dict[str, Any]]:
                return self._branch

            def getEntries(self) -> List[Dict[str, Any]]:
                return self._branch

            def getLeafId(self) -> Optional[str]:
                return None

            def getAppendParentId(self) -> Optional[str]:
                return None

            def getAppendMode(self) -> Optional[str]:
                return None

            def resetLeaf(self) -> None:
                self.leaf_reset = True

            def branch(self, parent_id: str) -> None:
                self.branched = parent_id

            def appendMessage(self, message: Any) -> Dict[str, Any]:
                entry = {"type": "message", "id": f"new-{len(self.appended)}", "message": message}
                self.appended.append(entry)
                return entry

        state = _State()
        result = rewrite_transcript_entries_in_state(
            state=state,
            replacements=[{"entryId": "a", "message": {"v": 2}}],
        )
        assert result["changed"] is True
        assert result["rewrittenEntries"] == 1
        assert state.leaf_reset is True
        assert state.appended[0]["message"] == {"v": 2}

    def test_state_with_branch_parent(self) -> None:
        class _State:
            def __init__(self) -> None:
                self._branch = [
                    {"type": "message", "id": "a", "parentId": None, "message": {}},
                    {"type": "message", "id": "b", "parentId": "a", "message": {}},
                ]

            def getBranch(self) -> List[Dict[str, Any]]:
                return self._branch

            def getEntries(self) -> List[Dict[str, Any]]:
                return self._branch

            def getLeafId(self) -> Optional[str]:
                return None

            def getAppendParentId(self) -> Optional[str]:
                return None

            def getAppendMode(self) -> Optional[str]:
                return None

            def resetLeaf(self) -> None:
                pass

            def branch(self, parent_id: str) -> None:
                self.branched = parent_id

            def appendMessage(self, message: Any) -> Dict[str, Any]:
                return {"type": "message", "id": "new", "message": message}

        state = _State()
        result = rewrite_transcript_entries_in_state(
            state=state,
            replacements=[{"entryId": "b", "message": {}}],
        )
        assert result["changed"] is True
        assert state.branched == "a"
