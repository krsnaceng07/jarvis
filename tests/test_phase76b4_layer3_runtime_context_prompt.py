"""Phase 7.6b-4 tests — runtime-context-prompt."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.run.runtime_context_prompt import (
    INTERNAL_RUNTIME_CONTEXT_BEGIN,
    INTERNAL_RUNTIME_CONTEXT_END,
    OPENCLAW_NEXT_TURN_RUNTIME_CONTEXT_HEADER,
    OPENCLAW_RUNTIME_CONTEXT_CUSTOM_TYPE,
    OPENCLAW_RUNTIME_CONTEXT_NOTICE,
    OPENCLAW_RUNTIME_EVENT_HEADER,
    OPENCLAW_RUNTIME_EVENT_USER_PROMPT,
    build_current_inbound_prompt,
    build_runtime_context_custom_message,
    resolve_runtime_context_prompt_parts,
    set_extract_internal_runtime_context_hook,
)


# ============================================================================
# constants
# ============================================================================


class TestRuntimeContextPromptConstants:
    def test_runtime_event_user_prompt(self) -> None:
        assert OPENCLAW_RUNTIME_EVENT_USER_PROMPT == (
            "Continue the OpenClaw runtime event."
        )

    def test_begin_end_markers(self) -> None:
        assert "BEGIN" in INTERNAL_RUNTIME_CONTEXT_BEGIN
        assert "END" in INTERNAL_RUNTIME_CONTEXT_END

    def test_runtime_context_custom_type(self) -> None:
        assert OPENCLAW_RUNTIME_CONTEXT_CUSTOM_TYPE == "openclaw.runtimeContext"

    def test_headers(self) -> None:
        assert "next-turn" in OPENCLAW_NEXT_TURN_RUNTIME_CONTEXT_HEADER.lower()
        assert "runtime event" in OPENCLAW_RUNTIME_EVENT_HEADER.lower()
        assert "runtime context" in OPENCLAW_RUNTIME_CONTEXT_NOTICE.lower()


# ============================================================================
# buildCurrentInboundPrompt
# ============================================================================


class TestBuildCurrentInboundPrompt:
    def test_no_context(self) -> None:
        assert build_current_inbound_prompt({"prompt": "hi"}) == "hi"

    def test_no_prompt(self) -> None:
        result = build_current_inbound_prompt(
            {"context": {"text": "ctx"}, "prompt": ""}
        )
        assert result == "ctx"

    def test_joiner(self) -> None:
        result = build_current_inbound_prompt(
            {
                "context": {"text": "ctx", "promptJoiner": " | "},
                "prompt": "hi",
            }
        )
        assert result == "ctx | hi"

    def test_default_joiner(self) -> None:
        result = build_current_inbound_prompt(
            {"context": {"text": "ctx"}, "prompt": "hi"}
        )
        assert result == "ctx\n\nhi"

    def test_resumable_text(self) -> None:
        result = build_current_inbound_prompt(
            {
                "context": {
                    "text": "user",
                    "resumableText": "resumed",
                },
                "prompt": "hi",
                "preferResumableText": True,
            }
        )
        assert result == "resumed\n\nhi"

    def test_no_resumable_falls_back_to_text(self) -> None:
        result = build_current_inbound_prompt(
            {
                "context": {
                    "text": "user",
                },
                "prompt": "hi",
                "preferResumableText": True,
            }
        )
        assert result == "user\n\nhi"

    def test_empty_context(self) -> None:
        result = build_current_inbound_prompt(
            {"context": {"text": "  "}, "prompt": "hi"}
        )
        assert result == "hi"

    def test_no_context_dict(self) -> None:
        result = build_current_inbound_prompt(
            {"context": None, "prompt": "hi"}
        )
        assert result == "hi"


# ============================================================================
# resolveRuntimeContextPromptParts
# ============================================================================


class TestResolveRuntimeContextPromptParts:
    def setup_method(self) -> None:
        # Default extract uses the begin/end marker pattern.
        set_extract_internal_runtime_context_hook(_default_extract)

    def test_no_runtime_context(self) -> None:
        result = resolve_runtime_context_prompt_parts({"prompt": "hi"})
        assert result["prompt"] == "hi"
        assert result["runtimeContext"] is None
        assert result["runtimeOnly"] is False

    def test_explicit_runtime_context(self) -> None:
        result = resolve_runtime_context_prompt_parts(
            {"prompt": "hi", "runtimeContext": "ctx"}
        )
        assert INTERNAL_RUNTIME_CONTEXT_BEGIN in result["prompt"]
        assert "ctx" in result["prompt"]
        assert result["runtimeContext"] == "ctx"

    def test_extracted_runtime_context(self) -> None:
        prompt = (
            "hi "
            + INTERNAL_RUNTIME_CONTEXT_BEGIN
            + "\nextracted\n"
            + INTERNAL_RUNTIME_CONTEXT_END
        )
        result = resolve_runtime_context_prompt_parts({"prompt": prompt})
        assert result["runtimeContext"] == "extracted"
        # The extracted context gets re-wrapped into the prompt.
        assert INTERNAL_RUNTIME_CONTEXT_BEGIN in result["prompt"]

    def test_runtime_only(self) -> None:
        result = resolve_runtime_context_prompt_parts(
            {"prompt": "hi", "runtimeContext": "ctx", "runtimeOnly": True}
        )
        assert result["runtimeOnly"] is True
        assert "hi" in result["prompt"]
        assert "ctx" in result["prompt"]

    def test_runtime_only_with_model_prompt(self) -> None:
        result = resolve_runtime_context_prompt_parts(
            {
                "prompt": "user-question",
                "modelPrompt": "wrapped user-question with annotations",
                "runtimeContext": "ctx",
                "runtimeOnly": True,
            }
        )
        # The runtime context is appended after the model prompt.
        assert "user-question" in result["prompt"]
        assert "ctx" in result["prompt"]

    def test_runtime_only_no_user_prompt(self) -> None:
        result = resolve_runtime_context_prompt_parts(
            {"prompt": "", "runtimeContext": "ctx", "runtimeOnly": True}
        )
        assert INTERNAL_RUNTIME_CONTEXT_BEGIN in result["prompt"]
        assert "ctx" in result["prompt"]

    def test_custom_extract_hook(self) -> None:
        set_extract_internal_runtime_context_hook(
            lambda _t: "from-hook"
        )
        result = resolve_runtime_context_prompt_parts({"prompt": "hi"})
        assert result["runtimeContext"] == "from-hook"


def _default_extract(text: str) -> Optional[str]:
    if not isinstance(text, str):
        return None
    begin = "<<<BEGIN_OPENCLAW_RUNTIME_CONTEXT>>>"
    end = "<<<END_OPENCLAW_RUNTIME_CONTEXT>>>"
    if begin not in text or end not in text:
        return None
    start = text.index(begin) + len(begin)
    stop = text.index(end, start)
    return text[start:stop].strip()


# ============================================================================
# buildRuntimeContextCustomMessage
# ============================================================================


class TestBuildRuntimeContextCustomMessage:
    def test_basic(self) -> None:
        result = build_runtime_context_custom_message(
            {"runtimeContext": "ctx", "timestamp": 12345}
        )
        assert result["role"] == "custom"
        assert result["customType"] == OPENCLAW_RUNTIME_CONTEXT_CUSTOM_TYPE
        assert result["content"] == "ctx"
        assert result["display"] is False
        assert result["timestamp"] == 12345
        assert result["details"]["source"] == "openclaw-runtime-context"
        assert result["details"]["runtimeContextCarrier"] is True

    def test_default_timestamp(self) -> None:
        result = build_runtime_context_custom_message(
            {"runtimeContext": "ctx"}
        )
        assert isinstance(result["timestamp"], int)
        assert result["timestamp"] > 0

    def test_empty_runtime_context(self) -> None:
        result = build_runtime_context_custom_message({})
        assert result["content"] == ""


# ============================================================================
# hook setters
# ============================================================================


class TestHookSetters:
    def test_set_extract_hook(self) -> None:
        set_extract_internal_runtime_context_hook(lambda _t: "x")
        result = resolve_runtime_context_prompt_parts({"prompt": "hi"})
        assert result["runtimeContext"] == "x"
        # Reset to default for other tests.
        set_extract_internal_runtime_context_hook(_default_extract)
