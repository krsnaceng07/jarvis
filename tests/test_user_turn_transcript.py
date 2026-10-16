"""Tests for src/sessions/user_turn_transcript.py.

Mirrors a focused subset of OpenClaw's
``src/sessions/user-turn-transcript.test.ts`` — the parts
that exercise the public surface (text resolver, media
field assembly, message builder, runtime merge, recorder
state machine). The recorder tests use an in-memory
``persist_turn_callback`` stub instead of the real
``persistSessionTranscriptTurn`` store writer.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest

from src.sessions.user_turn_transcript import (
    build_persisted_user_turn_media_inputs_from_fields,
    build_persisted_user_turn_message,
    build_run_user_turn_idempotency_key,
    create_user_turn_transcript_recorder,
    merge_prepared_user_turn_message_for_runtime,
    resolve_persisted_user_turn_text,
    restore_prepared_user_turn_operational_meta_for_runtime,
)
from src.sessions.user_turn_transcript_types import (
    UserTurnTranscriptPersistResult,
    UserTurnTranscriptTarget,
)


# ── Text resolver ──────────────────────────────────────────


class TestResolvePersistedUserTurnText:
    def test_plain_text_passes_through(self) -> None:
        assert resolve_persisted_user_turn_text("hello") == "hello"

    def test_trims_whitespace(self) -> None:
        assert resolve_persisted_user_turn_text("  hello  ") == "hello"

    def test_none_returns_none(self) -> None:
        assert resolve_persisted_user_turn_text(None) is None

    def test_empty_returns_none(self) -> None:
        assert resolve_persisted_user_turn_text("") is None
        assert resolve_persisted_user_turn_text("   ") is None

    def test_drops_placeholder_when_media_present(self) -> None:
        assert (
            resolve_persisted_user_turn_text("<media:image>", has_media=True)
            is None
        )
        assert (
            resolve_persisted_user_turn_text(
                "<media:image> (caption)", has_media=True
            )
            is None
        )

    def test_keeps_placeholder_when_no_media(self) -> None:
        # Without structured media, channel placeholders
        # survive into the transcript as plain text.
        assert (
            resolve_persisted_user_turn_text("<media:image>", has_media=False)
            == "<media:image>"
        )


# ── Media fields ──────────────────────────────────────────


class TestBuildPersistedUserTurnMediaInputsFromFields:
    def test_returns_empty_for_none(self) -> None:
        assert build_persisted_user_turn_media_inputs_from_fields(None) == []

    def test_single_media_path_with_type(self) -> None:
        fields = {
            "MediaPath": "/tmp/a.png",
            "MediaType": "image/png",
        }
        media = build_persisted_user_turn_media_inputs_from_fields(fields)
        assert len(media) == 1
        assert media[0]["path"] == "/tmp/a.png"
        assert media[0]["contentType"] == "image/png"

    def test_single_media_path_infers_type_from_extension(self) -> None:
        fields = {"MediaPath": "/tmp/photo.jpg"}
        media = build_persisted_user_turn_media_inputs_from_fields(fields)
        assert media[0]["contentType"] == "image/jpeg"

    def test_parallel_arrays_are_index_aligned(self) -> None:
        fields = {
            "MediaPaths": ["/tmp/a.png", "/tmp/b.mp3"],
            "MediaTypes": ["image/png", None],
        }
        media = build_persisted_user_turn_media_inputs_from_fields(fields)
        assert len(media) == 2
        assert media[0]["contentType"] == "image/png"
        assert media[1]["contentType"] == "audio/mpeg"

    def test_url_field_propagates(self) -> None:
        fields = {"MediaUrl": "https://example.com/img.png"}
        media = build_persisted_user_turn_media_inputs_from_fields(fields)
        assert media[0]["url"] == "https://example.com/img.png"
        # When only URL is set, no path key is present.
        assert "path" not in media[0]

    def test_workspace_dir_anchors_relative_path(self) -> None:
        fields = {
            "MediaPath": "uploads/photo.png",
            "MediaWorkspaceDir": "/workspace",
        }
        media = build_persisted_user_turn_media_inputs_from_fields(fields)
        # On Windows, os.path.join uses backslashes; we
        # check the suffix only to stay portable.
        assert media[0]["path"].endswith("photo.png")
        assert "/workspace" in media[0]["path"].replace("\\", "/")

    def test_url_like_path_is_not_anchored(self) -> None:
        fields = {
            "MediaPath": "https://example.com/photo.png",
            "MediaWorkspaceDir": "/workspace",
        }
        media = build_persisted_user_turn_media_inputs_from_fields(fields)
        assert media[0]["path"] == "https://example.com/photo.png"


# ── Message builder ──────────────────────────────────────


class TestBuildPersistedUserTurnMessage:
    def test_basic_text_message(self) -> None:
        msg = build_persisted_user_turn_message({"text": "hello"})
        assert msg["role"] == "user"
        assert msg["content"] == "hello"
        assert "timestamp" in msg
        assert "__openclaw" not in msg

    def test_idempotency_key_included(self) -> None:
        msg = build_persisted_user_turn_message(
            {"text": "hello", "idempotencyKey": "abc"}
        )
        assert msg["idempotencyKey"] == "abc"

    def test_sender_meta_in_openclaw(self) -> None:
        msg = build_persisted_user_turn_message(
            {
                "text": "hi",
                "sender": {"id": "u-1", "name": "Alice", "username": "alice"},
                "senderIsOwner": True,
            }
        )
        meta = msg["__openclaw"]
        assert meta["senderId"] == "u-1"
        assert meta["senderName"] == "Alice"
        assert meta["senderUsername"] == "alice"
        assert meta["senderIsOwner"] is True

    def test_transport_meta_in_openclaw(self) -> None:
        msg = build_persisted_user_turn_message(
            {
                "text": "hi",
                "transport": {
                    "channel": "discord",
                    "conversationRef": "channel:abc",
                },
            }
        )
        meta = msg["__openclaw"]
        assert meta["transport"]["channel"] == "discord"

    def test_media_included_via_parallel_arrays(self) -> None:
        msg = build_persisted_user_turn_message(
            {
                "text": "see attached",
                "media": [
                    {"path": "/tmp/a.png", "contentType": "image/png"},
                    {"path": "/tmp/b.mp3", "contentType": "audio/mpeg"},
                ],
            }
        )
        assert msg["MediaPath"] == "/tmp/a.png"
        assert msg["MediaPaths"] == ["/tmp/a.png", "/tmp/b.mp3"]
        assert msg["MediaType"] == "image/png"
        assert msg["MediaTypes"] == ["image/png", "audio/mpeg"]


# ── Idempotency key builder ───────────────────────────────


class TestBuildRunUserTurnIdempotencyKey:
    def test_appends_user_suffix(self) -> None:
        assert build_run_user_turn_idempotency_key("run-123") == "run-123:user"


# ── Runtime merge / restore ──────────────────────────────


class TestMergePreparedUserTurnMessageForRuntime:
    def test_returns_runtime_unchanged_when_no_prepared(self) -> None:
        runtime = {"role": "user", "content": "hi"}
        assert (
            merge_prepared_user_turn_message_for_runtime(
                runtime_message=runtime, prepared_message=None
            )
            is runtime
        )

    def test_returns_runtime_unchanged_when_blocked(self) -> None:
        runtime = {
            "role": "user",
            "content": "hi",
            "__openclaw": {"beforeAgentRunBlocked": True},
        }
        prepared = {
            "role": "user",
            "content": "transcript text",
            "__openclaw": {"senderIsOwner": True},
        }
        result = merge_prepared_user_turn_message_for_runtime(
            runtime_message=runtime, prepared_message=prepared
        )
        # Blocked: runtime stays intact.
        assert result is runtime

    def test_merges_prepared_into_runtime(self) -> None:
        runtime = {"role": "user", "content": "hi"}
        prepared = {
            "role": "user",
            "content": "transcript text",
            "idempotencyKey": "abc",
            "__openclaw": {"senderIsOwner": True},
        }
        result = merge_prepared_user_turn_message_for_runtime(
            runtime_message=runtime, prepared_message=prepared
        )
        assert result["content"] == "transcript text"
        assert result["idempotencyKey"] == "abc"
        assert result["__openclaw"]["senderIsOwner"] is True


class TestRestorePreparedUserTurnOperationalMetaForRuntime:
    def test_restores_sender_is_owner(self) -> None:
        runtime = {"role": "user", "content": "hi"}
        prepared = {
            "role": "user",
            "content": "x",
            "__openclaw": {"senderIsOwner": False},
        }
        result = restore_prepared_user_turn_operational_meta_for_runtime(
            runtime_message=runtime, prepared_message=prepared
        )
        assert result["__openclaw"]["senderIsOwner"] is False

    def test_returns_runtime_unchanged_when_sender_is_owner_missing(self) -> None:
        runtime = {"role": "user", "content": "hi"}
        prepared = {
            "role": "user",
            "content": "x",
            "__openclaw": {},
        }
        result = restore_prepared_user_turn_operational_meta_for_runtime(
            runtime_message=runtime, prepared_message=prepared
        )
        assert result is runtime


# ── Recorder ─────────────────────────────────────────────


class _RecorderStub:
    """Stub for the host-supplied ``persist_turn_callback``.

    Captures the persist call payload and returns a
    canned ``UserTurnTranscriptPersistResult`` so the
    recorder state machine can be exercised without a
    real store.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_result: Optional[UserTurnTranscriptPersistResult] = None

    async def __call__(self, payload: dict[str, Any]) -> UserTurnTranscriptPersistResult:
        self.calls.append(payload)
        return self.next_result or {
            "appended": True,
            "sessionFile": "/tmp/session.jsonl",
            "sessionEntry": {"sessionId": "s1", "updatedAt": 0},
            "messageId": f"m{len(self.calls)}",
            "message": payload["message"],
        }


def _target() -> UserTurnTranscriptTarget:
    return {
        "sessionId": "s1",
        "sessionKey": "agent:main:s1",
        "sessionEntry": {"sessionId": "s1", "updatedAt": 0},
        "agentId": "main",
    }


class TestRecorder:
    def test_create_recorder_has_message(self) -> None:
        rec = create_user_turn_transcript_recorder(
            {
                "input": {"text": "hi"},
                "target": _target,
                "persistTurnCallback": _RecorderStub(),
            }
        )
        assert rec["message"] is not None
        assert rec["message"]["content"] == "hi"

    def test_persist_approved_invokes_callback(self) -> None:
        stub = _RecorderStub()
        rec = create_user_turn_transcript_recorder(
            {
                "input": {"text": "hi"},
                "target": _target,
                "persistTurnCallback": stub,
            }
        )
        result = asyncio.run(rec["persistApproved"]())
        assert result is not None
        assert result["appended"] is True
        assert len(stub.calls) == 1
        assert rec["hasPersisted"]() is True

    def test_blocked_recorder_skips_persist_approved(self) -> None:
        stub = _RecorderStub()
        rec = create_user_turn_transcript_recorder(
            {
                "input": {"text": "hi"},
                "target": _target,
                "persistTurnCallback": stub,
            }
        )
        rec["markBlocked"]()
        result = asyncio.run(rec["persistApproved"]())
        assert result is None
        assert len(stub.calls) == 0
        assert rec["isBlocked"]() is True

    def test_persist_blocked_invokes_callback(self) -> None:
        stub = _RecorderStub()
        rec = create_user_turn_transcript_recorder(
            {
                "input": {"text": "hi"},
                "target": _target,
                "persistTurnCallback": stub,
            }
        )
        result = asyncio.run(
            rec["persistBlocked"](
                {"role": "user", "content": "blocked text", "timestamp": 0}
            )
        )
        assert result is not None
        assert rec["isBlocked"]() is True
        assert len(stub.calls) == 1

    def test_persist_fallback_waits_for_runtime_persistence(self) -> None:
        stub = _RecorderStub()
        rec = create_user_turn_transcript_recorder(
            {
                "input": {"text": "hi"},
                "target": _target,
                "persistTurnCallback": stub,
            }
        )
        # No runtime persistence is pending; persistFallback
        # should still complete the call.
        result = asyncio.run(rec["persistFallback"]())
        assert result is not None
        assert len(stub.calls) == 1

    def test_second_persist_approved_returns_first_result(self) -> None:
        stub = _RecorderStub()
        rec = create_user_turn_transcript_recorder(
            {
                "input": {"text": "hi"},
                "target": _target,
                "persistTurnCallback": stub,
            }
        )
        first = asyncio.run(rec["persistApproved"]())
        second = asyncio.run(rec["persistApproved"]())
        assert first is second
        # Only one persist call.
        assert len(stub.calls) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
