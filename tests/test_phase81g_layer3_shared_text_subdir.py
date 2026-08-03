"""Tests for Phase 8.1g — src/shared/text/ subdir (12 files) + chat-message-content + others."""
from __future__ import annotations

import json

import pytest

from src.shared.text.assistant_transcript_role_headers import (
    detect_assistant_transcript_role_header_text,
)
from src.shared.text.assistant_visible_text import extract_assistant_visible_text
from src.shared.text.auto_linked_file_ref import (
    FILE_REF_EXTENSIONS,
    is_auto_linked_file_ref,
)
from src.shared.text.citation_control_markers import (
    strip_unsupported_citation_control_markers,
)
from src.shared.text.code_regions import find_code_regions, is_inside_code
from src.shared.text.final_tags import find_final_tag_matches, strip_final_tags
from src.shared.text.formatted_reasoning_message import (
    strip_formatted_reasoning_message,
)
from src.shared.text.join_segments import (
    concat_optional_text_segments,
    join_present_text_segments,
)
from src.shared.text.model_special_tokens import strip_model_special_tokens
from src.shared.text.reasoning_tags import (
    has_orphan_reasoning_close_boundary,
    strip_reasoning_tags_from_text,
)
from src.shared.text.strip_markdown import strip_markdown
from src.shared.text.tool_call_shaped_text import detect_tool_call_shaped_text


# ============================================================================
# assistant-transcript-role-headers
# ============================================================================


class TestAssistantTranscriptRoleHeaders:
    def test_angle_header(self) -> None:
        out = detect_assistant_transcript_role_header_text("<assistant> hello")
        assert out == {"kind": "angle_role_header", "role": "assistant"}

    def test_bracket_header(self) -> None:
        out = detect_assistant_transcript_role_header_text("[assistant 12:34] hello")
        assert out is not None
        assert out["role"] == "assistant"
        assert out["kind"] == "role_timestamp_bracket"

    def test_colon_header(self) -> None:
        out = detect_assistant_transcript_role_header_text("user: hello")
        assert out is not None
        assert out["role"] == "user"

    def test_no_header(self) -> None:
        assert detect_assistant_transcript_role_header_text("hello") is None

    def test_annotations_path(self) -> None:
        annotations = [
            {"type": "assistant_transcript_role", "kind": "angle_role_header", "role": "developer"},
        ]
        out = detect_assistant_transcript_role_header_text("ignored", annotations)
        assert out == {"kind": "angle_role_header", "role": "developer"}


# ============================================================================
# auto-linked-file-ref
# ============================================================================


class TestAutoLinkedFileRef:
    def test_python_ref(self) -> None:
        assert is_auto_linked_file_ref("https://example/path/foo.py", "example/path/foo.py") is True

    def test_md_ref(self) -> None:
        assert is_auto_linked_file_ref("https://x/y/README.md", "x/y/README.md") is True

    def test_unknown_ext(self) -> None:
        assert is_auto_linked_file_ref("https://x/y/file.txt", "x/y/file.txt") is False

    def test_no_ext(self) -> None:
        assert is_auto_linked_file_ref("https://x/y/file", "x/y/file") is False

    def test_mismatch(self) -> None:
        assert is_auto_linked_file_ref("https://x/y/foo.py", "different") is False

    def test_intermediate_dot_in_path(self) -> None:
        assert is_auto_linked_file_ref("https://x/y.dir/foo.py", "x/y.dir/foo.py") is False

    def test_constants(self) -> None:
        assert "py" in FILE_REF_EXTENSIONS
        assert "md" in FILE_REF_EXTENSIONS


# ============================================================================
# citation-control-markers
# ============================================================================


class TestCitationControlMarkers:
    def test_no_markers(self) -> None:
        assert strip_unsupported_citation_control_markers("hello") == "hello"

    def test_strips_marker(self) -> None:
        # The marker chars are fullwidth angle brackets.
        text = "before\u3008cite\u3009after"
        out = strip_unsupported_citation_control_markers(text)
        assert "after" in out
        assert "\u3008cite" not in out


# ============================================================================
# code-regions
# ============================================================================


class TestCodeRegions:
    def test_no_code(self) -> None:
        assert find_code_regions("hello world") == []

    def test_fenced(self) -> None:
        regions = find_code_regions("hello\n```py\nx = 1\n```\nworld")
        assert len(regions) == 1
        assert regions[0]["start"] == 6

    def test_inline(self) -> None:
        regions = find_code_regions("use `foo` here")
        assert len(regions) == 1

    def test_inline_inside_fenced_skipped(self) -> None:
        regions = find_code_regions("```\n`inline`\n```")
        # Only the fenced region, no inline.
        assert len(regions) == 1

    def test_is_inside_code(self) -> None:
        regions = find_code_regions("hi `code` end")
        assert is_inside_code(4, regions) is True
        assert is_inside_code(0, regions) is False


# ============================================================================
# final-tags
# ============================================================================


class TestFinalTags:
    def test_basic(self) -> None:
        matches = find_final_tag_matches("hello <final>world</final>")
        assert len(matches) == 2
        assert matches[0]["isClose"] is False
        assert matches[1]["isClose"] is True

    def test_self_closing(self) -> None:
        matches = find_final_tag_matches("text <final/> more")
        assert len(matches) == 1
        assert matches[0]["isSelfClosing"] is True

    def test_with_attrs(self) -> None:
        matches = find_final_tag_matches('<final key="x">body</final>')
        assert len(matches) == 2

    def test_lookalike_rejected(self) -> None:
        # "finally" should not match.
        assert find_final_tag_matches("finally done") == []

    def test_strip(self) -> None:
        out = strip_final_tags("hello <final>world</final> bye")
        assert "<final>" not in out
        assert "world" in out


# ============================================================================
# formatted-reasoning-message
# ============================================================================


class TestFormattedReasoningMessage:
    def test_no_preamble(self) -> None:
        assert strip_formatted_reasoning_message("hello world") == "hello world"

    def test_reasoning_preamble(self) -> None:
        # OpenClaw strips the preamble only when the first line is exactly
        # "Reasoning:" (not "Reasoning: …") and the next non-blank line
        # begins the substantive answer.
        text = "Reasoning:\nhidden thought\nthe answer is 42"
        out = strip_formatted_reasoning_message(text)
        assert "the answer is 42" in out
        assert "Reasoning:" not in out

    def test_reasoning_no_strip_with_inline_body(self) -> None:
        # When the first line is "Reasoning: foo" (not bare "Reasoning:"),
        # OpenClaw leaves the text unchanged.
        text = "Reasoning: hidden thought\nthe answer is 42"
        out = strip_formatted_reasoning_message(text)
        assert out == text

    def test_thinking_italic_preamble(self) -> None:
        text = "Thinking.\n_some italic_\nthe answer is 42"
        out = strip_formatted_reasoning_message(text)
        assert "the answer is 42" in out

    def test_thinking_without_italic(self) -> None:
        text = "Thinking.\nthe answer is 42"
        out = strip_formatted_reasoning_message(text)
        # Without italic, no stripping.
        assert "Thinking" in out


# ============================================================================
# join-segments
# ============================================================================


class TestJoinSegments:
    def test_concat_both(self) -> None:
        out = concat_optional_text_segments({"left": "a", "right": "b"})
        assert out == "a\n\nb"

    def test_concat_only_left(self) -> None:
        assert concat_optional_text_segments({"left": "a"}) == "a"

    def test_concat_only_right(self) -> None:
        assert concat_optional_text_segments({"right": "b"}) == "b"

    def test_concat_empty(self) -> None:
        assert concat_optional_text_segments({}) is None

    def test_concat_custom_separator(self) -> None:
        out = concat_optional_text_segments({"left": "a", "right": "b", "separator": ", "})
        assert out == "a, b"

    def test_concat_right_empty_string_preserved(self) -> None:
        # Per spec, right's explicit empty string is preserved.
        assert concat_optional_text_segments({"left": "a", "right": ""}) == ""

    def test_join_present(self) -> None:
        out = join_present_text_segments(["a", None, "", "b", "c"])
        assert out == "a\n\nb\n\nc"

    def test_join_present_trim(self) -> None:
        out = join_present_text_segments(["  a  ", "  "], trim=True)
        assert out == "a"

    def test_join_present_all_empty(self) -> None:
        # trim=False default: only the literal empty string is filtered, not whitespace.
        assert join_present_text_segments(["", None]) is None

    def test_join_present_whitespace_with_trim(self) -> None:
        # With trim=True, whitespace-only segments are dropped.
        assert join_present_text_segments(["", None, "  "], trim=True) is None


# ============================================================================
# model-special-tokens
# ============================================================================


class TestModelSpecialTokens:
    def test_no_tokens(self) -> None:
        assert strip_model_special_tokens("hello world") == "hello world"

    def test_strips_ascii(self) -> None:
        out = strip_model_special_tokens("hello <|assistant|> world")
        assert "<|assistant|>" not in out

    def test_preserves_code(self) -> None:
        out = strip_model_special_tokens("use `<|tool|>` in code")
        assert "<|tool|>" in out

    def test_fullwidth_pipe(self) -> None:
        out = strip_model_special_tokens("hello <\uff5ctoken\uff5c> world")
        assert "<" not in out or "\uff5c" not in out

    def test_empty(self) -> None:
        assert strip_model_special_tokens("") == ""


# ============================================================================
# reasoning-tags
# ============================================================================


class TestReasoningTags:
    def test_no_tags(self) -> None:
        assert strip_reasoning_tags_from_text("hello world") == "hello world"

    def test_strips_thinking(self) -> None:
        out = strip_reasoning_tags_from_text("<think>hidden</think>visible")
        assert "visible" in out
        assert "hidden" not in out

    def test_strips_antml(self) -> None:
        out = strip_reasoning_tags_from_text("<antml:think>x</antml:think>visible")
        assert "visible" in out

    def test_strips_mm(self) -> None:
        out = strip_reasoning_tags_from_text("<mm:think>x</mm:think>visible")
        assert "visible" in out

    def test_preserve_mode(self) -> None:
        # preserve mode keeps the unclosed thinking content.
        out = strip_reasoning_tags_from_text("<think>hidden content", mode="preserve")
        assert "hidden content" in out

    def test_strict_unclosed_drops_content(self) -> None:
        # strict mode falls through to the unclosed content index.
        out = strip_reasoning_tags_from_text("<think>hidden content", mode="strict")
        assert "hidden content" in out

    def test_strict_unclosed_falls_through(self) -> None:
        # In strict mode with unclosed thinking, fall through to first content.
        out = strip_reasoning_tags_from_text("<think>hidden content")
        assert "hidden content" in out

    def test_orphan_close(self) -> None:
        out = strip_reasoning_tags_from_text("before</think>after")
        # The preamble "before" is dropped.
        assert "after" in out

    def test_has_orphan_boundary(self) -> None:
        assert has_orphan_reasoning_close_boundary({"before": "a", "after": "b"}) is True
        assert has_orphan_reasoning_close_boundary({"before": "", "after": "b"}) is False
        assert has_orphan_reasoning_close_boundary({"before": "a", "after": ""}) is False

    def test_scope_leading(self) -> None:
        # Non-leading think with no close → return as-is.
        out = strip_reasoning_tags_from_text("text<think>hidden", scope="leading")
        assert "text" in out

    def test_inside_code_preserved(self) -> None:
        out = strip_reasoning_tags_from_text("```\n<think>hidden\n```\nvisible")
        assert "visible" in out


# ============================================================================
# strip-markdown
# ============================================================================


class TestStripMarkdown:
    def test_plain(self) -> None:
        assert strip_markdown("hello world") == "hello world"

    def test_heading(self) -> None:
        assert strip_markdown("# Title") == "Title"
        assert strip_markdown("### Sub") == "Sub"

    def test_bold_italic(self) -> None:
        out = strip_markdown("**bold** and *italic*")
        assert "bold" in out
        assert "italic" in out

    def test_link_label(self) -> None:
        out = strip_markdown("[text](https://x.com)", {"linkStyle": "label"})
        assert out == "text"

    def test_link_label_and_url(self) -> None:
        out = strip_markdown("[text](https://x.com)", {"linkStyle": "label-and-url"})
        assert "text" in out
        assert "https://x.com" in out

    def test_code_block_stripped(self) -> None:
        out = strip_markdown("before\n```py\nx = 1\n```\nafter")
        assert "after" in out
        assert "before" in out

    def test_speech_mode(self) -> None:
        out = strip_markdown("Hello!!!! World", {"mode": "speech"})
        # Repeated punctuation collapses to a single occurrence.
        assert "Hello!" in out
        assert "!!!!" not in out

    def test_blockquote(self) -> None:
        assert strip_markdown("> quote") == "quote"

    def test_image(self) -> None:
        out = strip_markdown("text ![alt](https://x.com/i.png) more")
        assert "more" in out
        assert "text" in out


# ============================================================================
# tool-call-shaped-text
# ============================================================================


class TestToolCallShapedText:
    def test_no_tool_text(self) -> None:
        assert detect_tool_call_shaped_text("hello world") is None

    def test_json_tool_call_fenced(self) -> None:
        text = '```json\n{"name": "search", "arguments": {"q": "hi"}}\n```'
        out = detect_tool_call_shaped_text(text)
        assert out is not None
        assert out["kind"] == "json_tool_call"
        assert out.get("toolName") == "search"

    def test_json_tool_call_inline(self) -> None:
        text = '{"name": "search", "arguments": {"q": "hi"}}'
        out = detect_tool_call_shaped_text(text)
        assert out is not None
        assert out["kind"] == "json_tool_call"

    def test_xml_tool_call(self) -> None:
        text = '<tool_call>\n<function=search>\n</tool_call>'
        out = detect_tool_call_shaped_text(text)
        assert out is not None
        assert out["kind"] == "xml_tool_call"

    def test_bracketed_tool_call(self) -> None:
        text = "[search] query here [END_TOOL_REQUEST]"
        out = detect_tool_call_shaped_text(text)
        assert out is not None
        assert out["kind"] == "bracketed_tool_call"
        assert out.get("toolName") == "search"

    def test_react_action(self) -> None:
        text = "Action: search\n\nAction Input: hello"
        out = detect_tool_call_shaped_text(text)
        assert out is not None
        assert out["kind"] == "react_action"
        assert out.get("toolName") == "search"

    def test_tool_calls_array(self) -> None:
        text = '{"tool_calls": [{"name": "search", "arguments": {}}]}'
        out = detect_tool_call_shaped_text(text)
        assert out is not None
        assert out["kind"] == "json_tool_call"

    def test_function_nested(self) -> None:
        text = '{"function": {"name": "search", "arguments": {}}}'
        out = detect_tool_call_shaped_text(text)
        assert out is not None
        assert out["kind"] == "json_tool_call"
        assert out.get("toolName") == "search"

    def test_prefilter_short_circuit(self) -> None:
        # Text without any tool-call signature.
        assert detect_tool_call_shaped_text("just a normal response") is None

    def test_empty(self) -> None:
        assert detect_tool_call_shaped_text("") is None


# ============================================================================
# assistant-visible-text
# ============================================================================


class TestAssistantVisibleText:
    def test_strip_thinking(self) -> None:
        out = extract_assistant_visible_text("<think>hidden</think>visible")
        assert "visible" in out
        assert "hidden" not in out

    def test_strip_final(self) -> None:
        out = extract_assistant_visible_text("hello <final/> world")
        assert "hello" in out
        assert "world" in out

    def test_custom_stripper(self) -> None:
        out = extract_assistant_visible_text("hello", stripper=lambda s: s.upper())
        assert out == "HELLO"

    def test_empty(self) -> None:
        assert extract_assistant_visible_text("") == ""
