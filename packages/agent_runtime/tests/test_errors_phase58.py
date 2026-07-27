"""Tests for ``jarvis_agent.errors``.

OpenClaw source: ``packages/agent-core/src/errors.ts`` (14 lines). Upstream
has no ``errors.test.ts``, so every case here is derived from the source
directly: the constructor interpolates the role into the message, pins
``name``, and exposes a stable ``code``.
"""

from __future__ import annotations

import pytest

from jarvis_agent.errors import (
    TRANSCRIPT_NOT_CONTINUABLE_ERROR_CODE,
    TranscriptNotContinuableError,
)


class TestErrorCode:
    def test_code_value_is_wire_stable(self) -> None:
        # The openclaw_ prefix is deliberate: this string appears in
        # persisted sessions, so it must match the TS constant byte for byte.
        assert TRANSCRIPT_NOT_CONTINUABLE_ERROR_CODE == "openclaw_transcript_not_continuable"

    def test_class_attribute_mirrors_constant(self) -> None:
        assert TranscriptNotContinuableError.code is TRANSCRIPT_NOT_CONTINUABLE_ERROR_CODE


class TestTranscriptNotContinuableError:
    def test_message_interpolates_role(self) -> None:
        # TS: super(`Cannot continue from message role: ${role}`)
        error = TranscriptNotContinuableError("user")
        assert str(error) == "Cannot continue from message role: user"

    @pytest.mark.parametrize(
        "role",
        ["user", "assistant", "toolResult", "custom", "notification"],
    )
    def test_role_is_kept_for_branching_callers(self, role: str) -> None:
        error = TranscriptNotContinuableError(role)
        assert error.role == role
        assert role in str(error)

    def test_name_matches_ts_class_name(self) -> None:
        # TS: this.name = "TranscriptNotContinuableError"
        assert TranscriptNotContinuableError("user").name == "TranscriptNotContinuableError"

    def test_instance_code_matches(self) -> None:
        assert TranscriptNotContinuableError("user").code == (
            "openclaw_transcript_not_continuable"
        )

    def test_is_an_exception_and_raisable(self) -> None:
        with pytest.raises(TranscriptNotContinuableError) as exc_info:
            raise TranscriptNotContinuableError("toolResult")
        assert exc_info.value.role == "toolResult"

    def test_empty_role_still_formats(self) -> None:
        # TS template literal never throws on empty input; neither do we.
        error = TranscriptNotContinuableError("")
        assert str(error) == "Cannot continue from message role: "
        assert error.role == ""
