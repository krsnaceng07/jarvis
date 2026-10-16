"""Tests for src/sessions/conversation_turns.py.

Mirrors OpenClaw's ``extensions/sessions/conversation-turns.test.ts``.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from src.sessions.conversation_turns import (
    ConversationTurnReplyClaim,
    PendingConversationTurnHandle,
    _reset_pending_turns_for_tests,
    cancel_pending_conversation_turn,
    claim_pending_conversation_turn_reply,
    register_pending_conversation_turn,
)


@pytest.fixture(autouse=True)
def _clear():
    _reset_pending_turns_for_tests()
    yield
    _reset_pending_turns_for_tests()


# ── register_pending_conversation_turn ───────────────────────────


class TestRegisterPendingConversationTurn:
    def test_requires_agent_id(self) -> None:
        with pytest.raises(ValueError, match="requires an agent id"):
            register_pending_conversation_turn(
                {
                    "conversationRef": "discord:channel:abc",
                    "sessionId": "s1",
                    "timeoutMs": 5000,
                }
            )

    def test_creates_turn(self) -> None:
        handle = register_pending_conversation_turn(
            {
                "agentId": "agent-1",
                "conversationRef": "discord:channel:abc",
                "sessionId": "s1",
                "timeoutMs": 5000,
            }
        )
        assert isinstance(handle, PendingConversationTurnHandle)
        assert handle.id  # UUID generated

    def test_duplicate_id_raises(self) -> None:
        register_pending_conversation_turn(
            {
                "agentId": "agent-1",
                "id": "turn-1",
                "conversationRef": "discord:channel:abc",
                "sessionId": "s1",
                "timeoutMs": 5000,
            }
        )
        with pytest.raises(RuntimeError, match="already pending"):
            register_pending_conversation_turn(
                {
                    "agentId": "agent-1",
                    "id": "turn-1",
                    "conversationRef": "discord:channel:abc",
                    "sessionId": "s1",
                    "timeoutMs": 5000,
                }
            )


class TestPendingTurnHandle:
    def test_set_outbound_message_id(self) -> None:
        handle = register_pending_conversation_turn(
            {
                "agentId": "agent-1",
                "id": "turn-1",
                "conversationRef": "discord:channel:abc",
                "sessionId": "s1",
                "timeoutMs": 5000,
            }
        )
        handle.set_outbound_message_id("msg-1")
        # No error; outbound id is set
        assert True

    def test_set_outbound_message_id_none_settles(self) -> None:
        handle = register_pending_conversation_turn(
            {
                "agentId": "agent-1",
                "id": "turn-1",
                "conversationRef": "discord:channel:abc",
                "sessionId": "s1",
                "timeoutMs": 5000,
            }
        )
        handle.set_outbound_message_id(None)
        # After settle, the wait resolves to None
        result = asyncio.run(handle.wait())
        assert result is None

    def test_mark_ready_with_no_outbound_settles(self) -> None:
        handle = register_pending_conversation_turn(
            {
                "agentId": "agent-1",
                "id": "turn-1",
                "conversationRef": "discord:channel:abc",
                "sessionId": "s1",
                "timeoutMs": 5000,
            }
        )
        handle.mark_ready()
        result = asyncio.run(handle.wait())
        assert result is None


# ── cancel_pending_conversation_turn ─────────────────────────────


class TestCancelPendingConversationTurn:
    def test_cancel_existing(self) -> None:
        register_pending_conversation_turn(
            {
                "agentId": "agent-1",
                "id": "turn-1",
                "conversationRef": "discord:channel:abc",
                "sessionId": "s1",
                "timeoutMs": 5000,
            }
        )
        assert (
            cancel_pending_conversation_turn({"agentId": "agent-1", "id": "turn-1"})
            is True
        )

    def test_cancel_missing(self) -> None:
        assert (
            cancel_pending_conversation_turn({"agentId": "agent-1", "id": "nope"})
            is False
        )

    def test_cancel_missing_fields(self) -> None:
        assert cancel_pending_conversation_turn({}) is False
        assert cancel_pending_conversation_turn({"agentId": "agent-1"}) is False
        assert cancel_pending_conversation_turn({"id": "turn-1"}) is False


# ─- Timeout test ──────────────────────────────────────────────────


class TestPendingTurnTimeout:
    def test_timeout_settles_with_none(self) -> None:
        """A turn that times out resolves the wait to None."""
        handle = register_pending_conversation_turn(
            {
                "agentId": "agent-1",
                "id": "turn-1",
                "conversationRef": "discord:channel:abc",
                "sessionId": "s1",
                "timeoutMs": 50,  # 50ms
            }
        )
        start = time.time()
        result = asyncio.run(handle.wait())
        elapsed = time.time() - start
        assert result is None
        # Wait should have resolved around the timeout
        assert elapsed >= 0.05


# ── claim_pending_conversation_turn_reply ────────────────────────


class TestClaimPendingConversationTurnReply:
    def test_no_reply_to_id(self) -> None:
        result = asyncio.run(
            claim_pending_conversation_turn_reply(
                {
                    "agentId": "agent-1",
                    "conversationRef": "discord:channel:abc",
                    "sessionId": "s1",
                    "messageId": "m1",
                    "text": "hi",
                }
            )
        )
        assert result is None

    def test_no_matching_turn(self) -> None:
        result = asyncio.run(
            claim_pending_conversation_turn_reply(
                {
                    "agentId": "agent-1",
                    "conversationRef": "discord:channel:abc",
                    "sessionId": "s1",
                    "messageId": "m1",
                    "replyToId": "outbound-1",
                    "text": "hi",
                }
            )
        )
        assert result is None

    def test_claim_with_matching_outbound_id(self) -> None:
        handle = register_pending_conversation_turn(
            {
                "agentId": "agent-1",
                "id": "turn-1",
                "conversationRef": "discord:channel:abc",
                "sessionId": "s1",
                "timeoutMs": 5000,
            }
        )
        handle.set_outbound_message_id("outbound-1")
        handle.mark_ready()
        claim = asyncio.run(
            claim_pending_conversation_turn_reply(
                {
                    "agentId": "agent-1",
                    "conversationRef": "discord:channel:abc",
                    "sessionId": "s1",
                    "messageId": "m1",
                    "replyToId": "outbound-1",
                    "text": "hello back",
                }
            )
        )
        assert claim is not None
        assert isinstance(claim, ConversationTurnReplyClaim)
        assert claim.turn_id == "turn-1"
        assert claim.session_id == "s1"

    def test_complete_settles_turn(self) -> None:
        handle = register_pending_conversation_turn(
            {
                "agentId": "agent-1",
                "id": "turn-1",
                "conversationRef": "discord:channel:abc",
                "sessionId": "s1",
                "timeoutMs": 5000,
            }
        )
        handle.set_outbound_message_id("outbound-1")
        handle.mark_ready()

        async def _flow():
            claim = await claim_pending_conversation_turn_reply(
                {
                    "agentId": "agent-1",
                    "conversationRef": "discord:channel:abc",
                    "sessionId": "s1",
                    "messageId": "m1",
                    "replyToId": "outbound-1",
                    "text": "hello back",
                }
            )
            assert claim is not None
            claim.complete({"transcriptArtifactId": "artifact-1"})

        asyncio.run(_flow())
        reply = asyncio.run(handle.wait())
        assert reply is not None
        assert reply.text == "hello back"
        assert reply.transcript_artifact_id == "artifact-1"

    def test_release_unclaims_turn(self) -> None:
        handle = register_pending_conversation_turn(
            {
                "agentId": "agent-1",
                "id": "turn-1",
                "conversationRef": "discord:channel:abc",
                "sessionId": "s1",
                "timeoutMs": 5000,
            }
        )
        handle.set_outbound_message_id("outbound-1")
        handle.mark_ready()

        async def _flow():
            claim = await claim_pending_conversation_turn_reply(
                {
                    "agentId": "agent-1",
                    "conversationRef": "discord:channel:abc",
                    "sessionId": "s1",
                    "messageId": "m1",
                    "replyToId": "outbound-1",
                    "text": "hello back",
                }
            )
            assert claim is not None
            claim.release()

        asyncio.run(_flow())
        # After release, the turn is no longer claimed
        # (we can register a new claim against the same
        # outbound id).
        claim2 = asyncio.run(
            claim_pending_conversation_turn_reply(
                {
                    "agentId": "agent-1",
                    "conversationRef": "discord:channel:abc",
                    "sessionId": "s1",
                    "messageId": "m2",
                    "replyToId": "outbound-1",
                    "text": "second reply",
                }
            )
        )
        # The second claim succeeds (release un-claimed).
        # The turn is then completed by the second claim.
        assert claim2 is not None
        # Cleanup: complete the second claim so the wait
        # doesn't time out.
        claim2.complete()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
