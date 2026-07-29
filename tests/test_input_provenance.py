"""Tests for src/sessions/input_provenance.py.

Mirrors OpenClaw's ``extensions/sessions/input-provenance.test.ts``.
"""
from __future__ import annotations

import pytest

from src.sessions.input_provenance import (
    INTER_SESSION_PROMPT_EXPLANATION,
    INTER_SESSION_PROMPT_PREFIX_BASE,
    InputProvenance,
    MAIN_SESSION_RESTART_RECOVERY_SOURCE_TOOL,
    annotate_inter_session_prompt_text,
    apply_input_provenance_to_user_message,
    has_inter_session_user_provenance,
    is_agent_mediated_completion_source_tool,
    is_completion_report_input_provenance,
    is_inter_session_input_provenance,
    is_main_session_restart_recovery_input_provenance,
    normalize_input_provenance,
    should_preserve_user_facing_session_state_for_input_provenance,
    strip_inter_session_prompt_prefix_for_display,
)

# Mirror of the private frozenset inside the module (kept
# private because callers should use the predicate, not the
# set). Used in test_is_agent_mediated_completion_source_tool
# to enumerate every value the predicate accepts.
_AGENT_MEDIATED_COMPLETION_SOURCE_TOOLS = frozenset(
    {
        "agent_harness_task",
        "image_generate",
        "music_generate",
        "video_generate",
    }
)


# ── normalize_input_provenance ───────────────────────────────────


class TestNormalizeInputProvenance:
    def test_external_user(self) -> None:
        result = normalize_input_provenance({"kind": "external_user"})
        assert result == InputProvenance(kind="external_user")

    def test_inter_session_full(self) -> None:
        result = normalize_input_provenance(
            {
                "kind": "inter_session",
                "originSessionId": "s1",
                "sourceSessionKey": "agent:1:discord:channel:abc",
                "sourceChannel": "discord",
                "sourceTool": "agent_harness_task",
            }
        )
        assert result is not None
        assert result.kind == "inter_session"
        assert result.origin_session_id == "s1"
        assert result.source_session_key == "agent:1:discord:channel:abc"
        assert result.source_channel == "discord"
        assert result.source_tool == "agent_harness_task"

    def test_invalid_kind(self) -> None:
        assert normalize_input_provenance({"kind": "invalid"}) is None

    def test_missing_kind(self) -> None:
        assert normalize_input_provenance({"sourceChannel": "discord"}) is None

    def test_non_object(self) -> None:
        assert normalize_input_provenance("string") is None
        assert normalize_input_provenance(None) is None
        assert normalize_input_provenance([]) is None

    def test_trims_string_fields(self) -> None:
        result = normalize_input_provenance(
            {"kind": "external_user", "sourceChannel": "  discord  "}
        )
        assert result is not None
        assert result.source_channel == "discord"


# ── Kind predicates ──────────────────────────────────────────────


class TestKindPredicates:
    def test_is_inter_session(self) -> None:
        assert is_inter_session_input_provenance({"kind": "inter_session"}) is True
        assert is_inter_session_input_provenance({"kind": "external_user"}) is False
        assert is_inter_session_input_provenance({"kind": "invalid"}) is False
        assert is_inter_session_input_provenance(None) is False

    def test_is_main_session_restart_recovery(self) -> None:
        provenance = {
            "kind": "internal_system",
            "sourceTool": MAIN_SESSION_RESTART_RECOVERY_SOURCE_TOOL,
        }
        assert is_main_session_restart_recovery_input_provenance(provenance) is True
        # Case-insensitive
        assert is_main_session_restart_recovery_input_provenance(
            {"kind": "internal_system", "sourceTool": "Main_Session_Restart_Recovery"}
        ) is True
        # Different tool → False
        assert is_main_session_restart_recovery_input_provenance(
            {"kind": "internal_system", "sourceTool": "other"}
        ) is False
        # Different kind → False
        assert is_main_session_restart_recovery_input_provenance(
            {"kind": "inter_session", "sourceTool": MAIN_SESSION_RESTART_RECOVERY_SOURCE_TOOL}
        ) is False

    def test_is_agent_mediated_completion_source_tool(self) -> None:
        for tool in _AGENT_MEDIATED_COMPLETION_SOURCE_TOOLS:
            assert is_agent_mediated_completion_source_tool(tool) is True
            assert is_agent_mediated_completion_source_tool(tool.upper()) is True
        assert is_agent_mediated_completion_source_tool("subagent_announce") is False
        assert is_agent_mediated_completion_source_tool("") is False
        assert is_agent_mediated_completion_source_tool(None) is False

    def test_is_completion_report_input_provenance(self) -> None:
        # subagent_announce + inter_session → True
        assert is_completion_report_input_provenance(
            {"kind": "inter_session", "sourceTool": "subagent_announce"}
        ) is True
        # Agent-mediated completion tools + inter_session → True
        assert is_completion_report_input_provenance(
            {"kind": "inter_session", "sourceTool": "image_generate"}
        ) is True
        # Non-inter-session → False
        assert is_completion_report_input_provenance(
            {"kind": "external_user", "sourceTool": "subagent_announce"}
        ) is False
        # Other tool → False
        assert is_completion_report_input_provenance(
            {"kind": "inter_session", "sourceTool": "other"}
        ) is False

    def test_should_preserve_user_facing_session_state(self) -> None:
        for tool in (
            "agent_harness_task",
            "image_generate",
            "music_generate",
            "video_generate",
            "subagent_announce",
            "subagent_interrupted_resume",
        ):
            assert should_preserve_user_facing_session_state_for_input_provenance(
                {"kind": "inter_session", "sourceTool": tool}
            ) is True
        # Non-inter-session → False
        assert should_preserve_user_facing_session_state_for_input_provenance(
            {"kind": "external_user", "sourceTool": "subagent_announce"}
        ) is False
        # Other tool → False
        assert should_preserve_user_facing_session_state_for_input_provenance(
            {"kind": "inter_session", "sourceTool": "random_tool"}
        ) is False


# ── apply_input_provenance_to_user_message ──────────────────────


class TestApplyInputProvenance:
    def test_attaches_to_user_role(self) -> None:
        msg = {"role": "user", "content": "hi"}
        provenance = InputProvenance(kind="external_user")
        result = apply_input_provenance_to_user_message(msg, provenance)
        assert result["provenance"] is provenance

    def test_skips_non_user_role(self) -> None:
        msg = {"role": "assistant", "content": "hi"}
        provenance = InputProvenance(kind="external_user")
        result = apply_input_provenance_to_user_message(msg, provenance)
        assert "provenance" not in result
        assert result is msg  # unchanged

    def test_no_provenance_returns_unchanged(self) -> None:
        msg = {"role": "user", "content": "hi"}
        result = apply_input_provenance_to_user_message(msg, None)
        assert result is msg

    def test_preserves_existing_provenance(self) -> None:
        existing = InputProvenance(kind="external_user", source_channel="discord")
        msg = {"role": "user", "content": "hi", "provenance": existing}
        new = InputProvenance(kind="inter_session")
        result = apply_input_provenance_to_user_message(msg, new)
        # Existing provenance wins
        assert result["provenance"] is existing

    def test_user_facing_state_preservation(self) -> None:
        """Marker reflects: for inter-session + subagent, keep user state."""
        msg = {"role": "user", "content": "hi"}
        result = apply_input_provenance_to_user_message(
            msg,
            InputProvenance(
                kind="inter_session", source_tool="subagent_announce"
            ),
        )
        assert result["provenance"].source_tool == "subagent_announce"


# ── has_inter_session_user_provenance ───────────────────────────


class TestHasInterSessionUserProvenance:
    def test_user_with_inter_session(self) -> None:
        msg = {
            "role": "user",
            "provenance": {"kind": "inter_session"},
        }
        assert has_inter_session_user_provenance(msg) is True

    def test_user_with_other_provenance(self) -> None:
        msg = {
            "role": "user",
            "provenance": {"kind": "external_user"},
        }
        assert has_inter_session_user_provenance(msg) is False

    def test_assistant_role(self) -> None:
        msg = {
            "role": "assistant",
            "provenance": {"kind": "inter_session"},
        }
        assert has_inter_session_user_provenance(msg) is False

    def test_no_message(self) -> None:
        assert has_inter_session_user_provenance(None) is False
        assert has_inter_session_user_provenance({}) is False


# ── Inter-session prompt text ────────────────────────────────────


class TestInterSessionPromptText:
    def test_strip_round_trip(self) -> None:
        """Annotated text → stripped text returns the original."""
        original = "Hello world"
        annotated = annotate_inter_session_prompt_text(
            original,
            InputProvenance(kind="inter_session", source_channel="discord"),
        )
        # Annotation should add the prefix
        assert INTER_SESSION_PROMPT_PREFIX_BASE in annotated
        assert INTER_SESSION_PROMPT_EXPLANATION in annotated
        # Strip should recover the original
        stripped = strip_inter_session_prompt_prefix_for_display(annotated)
        assert stripped == original

    def test_strip_round_trip_with_details(self) -> None:
        original = "Hello world"
        annotated = annotate_inter_session_prompt_text(
            original,
            InputProvenance(
                kind="inter_session",
                source_session_key="agent:1:discord:channel:abc",
                source_channel="discord",
                source_tool="agent_harness_task",
            ),
        )
        assert "sourceSession=agent:1:discord:channel:abc" in annotated
        assert "sourceChannel=discord" in annotated
        assert "sourceTool=agent_harness_task" in annotated
        assert "isUser=false" in annotated
        stripped = strip_inter_session_prompt_prefix_for_display(annotated)
        assert stripped == original

    def test_idempotent(self) -> None:
        text = "Body"
        provenance = InputProvenance(kind="inter_session")
        once = annotate_inter_session_prompt_text(text, provenance)
        twice = annotate_inter_session_prompt_text(once, provenance)
        assert once == twice

    def test_no_provenance_returns_unchanged(self) -> None:
        text = "Body"
        assert annotate_inter_session_prompt_text(text, None) == text

    def test_non_inter_session_returns_unchanged(self) -> None:
        text = "Body"
        provenance = InputProvenance(kind="external_user")
        assert annotate_inter_session_prompt_text(text, provenance) == text

    def test_empty_text_returns_unchanged(self) -> None:
        """Empty text doesn't get a prefix (it would create a header-only)."""
        provenance = InputProvenance(kind="inter_session")
        assert annotate_inter_session_prompt_text("", provenance) == ""
        assert annotate_inter_session_prompt_text("   ", provenance) == "   "

    def test_strip_no_prefix_returns_unchanged(self) -> None:
        """Text without a prefix returns as-is."""
        text = "Plain text with no prefix"
        assert strip_inter_session_prompt_prefix_for_display(text) == text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
