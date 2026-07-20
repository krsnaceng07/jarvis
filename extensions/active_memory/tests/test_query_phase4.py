"""Tests for extensions/active_memory/query.py + prompt.py.

Phase 4.2b step 1: ported ``query.ts`` and ``prompt.ts`` to
Python. The functions here are pure text transformations —
no LLM, no filesystem, no async — so tests are cheap and
deterministic.

Coverage
========
- ``build_query`` — message / recent / full modes.
- ``build_search_query`` — strip untrusted fences, JSON
  fences, active-memory XML block; clamp to
  ``MAX_ACTIVE_MEMORY_SEARCH_QUERY_CHARS``; blend previous
  user turn when latest is short.
- ``extract_recent_turns`` — string + content-block content;
  user vs. assistant stripping.
- ``extract_text_content`` / ``extract_text_content_parts``.
- ``get_model_ref`` — operator config / current run / agent
  primary / fallback chain.
- ``strip_recalled_context_noise`` — drops header + open
  tag + recalled-context line patterns; collapses
  whitespace.
- ``strip_injected_active_memory_prefix_only`` — drops the
  untrusted header + open/close block; preserves the rest.
- ``build_recall_prompt`` — three-section prompt with
  default instructions; honours promptOverride and
  promptAppend.
- ``build_prompt_style_lines`` — covers all 6 styles.
- ``read_explicit_memory_evidence`` / ``read_structured_memory_evidence`` /
  ``read_structured_memory_failure`` / the ``*_from_content``
  variants.
- ``normalize_active_summary`` — maps NO_RECALL_VALUES to
  None; collapses whitespace; rejects timeout boilerplate.
- ``truncate_summary`` — whitespace boundary preference;
  ellipsis slicing when cap is too small.
- ``build_metadata`` / ``build_prompt_prefix`` — XML
  escaping + untrusted-context header.
"""

from __future__ import annotations

# pyright: reportArgumentType=false
# pyright: reportTypedDictNotRequiredAccess=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportOptionalSubscript=false
# pyright: reportOptionalIterable=false
# pyright: reportOptionalOperand=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeArgument=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportCallIssue=false
# pyright: reportIndexIssue=false
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.active_memory.prompt import (  # noqa: E402
    build_metadata,
    build_prompt_prefix,
    build_prompt_style_lines,
    build_recall_prompt,
    escape_xml,
    is_timeout_boilerplate_summary,
    normalize_active_summary,
    read_explicit_memory_evidence,
    read_structured_memory_evidence,
    read_structured_memory_evidence_from_content,
    read_structured_memory_failure,
    read_structured_memory_failure_from_content,
    truncate_summary,
)
from extensions.active_memory.query import (  # noqa: E402
    build_query,
    build_search_query,
    extract_recent_turns,
    extract_text_content,
    extract_text_content_parts,
    get_model_ref,
    strip_injected_active_memory_prefix_only,
    strip_recalled_context_noise,
)
from extensions.active_memory.types import (  # noqa: E402
    ACTIVE_MEMORY_CLOSE_TAG,
    ACTIVE_MEMORY_OPEN_TAG,
    ACTIVE_MEMORY_UNTRUSTED_CONTEXT_HEADER,
    DEFAULT_RECENT_ASSISTANT_CHARS,
    DEFAULT_RECENT_ASSISTANT_TURNS,
    DEFAULT_RECENT_USER_CHARS,
    DEFAULT_RECENT_USER_TURNS,
    MAX_ACTIVE_MEMORY_SEARCH_QUERY_CHARS,
    NO_RECALL_VALUES,
)

# ── build_query ─────────────────────────────────────────────────────


class TestBuildQuery:
    def test_message_mode_returns_latest_only(self) -> None:
        cfg = {"queryMode": "message"}
        assert build_query({"latestUserMessage": "  hello  ", "config": cfg}) == "hello"

    def test_recent_mode_returns_latest_when_no_history(self) -> None:
        cfg = {
            "queryMode": "recent",
            "recentUserTurns": DEFAULT_RECENT_USER_TURNS,
            "recentAssistantTurns": DEFAULT_RECENT_ASSISTANT_TURNS,
            "recentUserChars": DEFAULT_RECENT_USER_CHARS,
            "recentAssistantChars": DEFAULT_RECENT_ASSISTANT_CHARS,
        }
        assert build_query({"latestUserMessage": "hi", "config": cfg}) == "hi"

    def test_recent_mode_keeps_user_and_assistant_tail(self) -> None:
        cfg = {
            "queryMode": "recent",
            "recentUserTurns": 1,
            "recentAssistantTurns": 1,
            "recentUserChars": 100,
            "recentAssistantChars": 100,
        }
        out = build_query(
            {
                "latestUserMessage": "What's my favorite food?",
                "config": cfg,
                "recentTurns": [
                    {"role": "user", "text": "Earlier I said something."},
                    {"role": "assistant", "text": "And you replied."},
                    {"role": "user", "text": "Then I asked again."},
                ],
            }
        )
        assert "Recent conversation tail:" in out
        assert "assistant: And you replied." in out
        assert "user: Then I asked again." in out
        assert "Latest user message:" in out
        assert out.endswith("What's my favorite food?")

    def test_recent_mode_respects_turn_caps(self) -> None:
        cfg = {
            "queryMode": "recent",
            "recentUserTurns": 1,
            "recentAssistantTurns": 0,
            "recentUserChars": 200,
            "recentAssistantChars": 200,
        }
        out = build_query(
            {
                "latestUserMessage": "Now",
                "config": cfg,
                "recentTurns": [
                    {"role": "user", "text": "u1"},
                    {"role": "user", "text": "u2"},
                ],
            }
        )
        # Only the most recent user turn survives.
        assert "u2" in out
        assert "u1" not in out

    def test_full_mode_includes_all_turns(self) -> None:
        cfg = {
            "queryMode": "full",
            "recentUserTurns": 99,
            "recentAssistantTurns": 99,
            "recentUserChars": 200,
            "recentAssistantChars": 200,
        }
        out = build_query(
            {
                "latestUserMessage": "Now",
                "config": cfg,
                "recentTurns": [
                    {"role": "user", "text": "first"},
                    {"role": "assistant", "text": "second"},
                ],
            }
        )
        assert "Full conversation context:" in out
        assert "user: first" in out
        assert "assistant: second" in out
        assert out.endswith("Now")

    def test_full_mode_falls_back_to_latest_when_no_turns(self) -> None:
        cfg = {"queryMode": "full"}
        assert build_query({"latestUserMessage": "hi", "config": cfg}) == "hi"

    def test_recent_mode_truncates_per_turn_chars(self) -> None:
        cfg = {
            "queryMode": "recent",
            "recentUserTurns": 1,
            "recentAssistantTurns": 0,
            "recentUserChars": 5,
            "recentAssistantChars": 100,
        }
        out = build_query(
            {
                "latestUserMessage": "Now",
                "config": cfg,
                "recentTurns": [{"role": "user", "text": "abcdefghij"}],
            }
        )
        # Per-turn text is truncated to 5 chars; the "user:" prefix adds 6
        # bytes (not 5) because truncateUtf16Safe runs after stripping
        # whitespace but before the role-prefix is added.
        assert "abcde" in out
        assert "abcdefghij" not in out


# ── build_search_query ─────────────────────────────────────────────


class TestBuildSearchQuery:
    def test_strips_untrusted_fences(self) -> None:
        out = build_search_query(
            {
                "latestUserMessage": (
                    "<<<EXTERNAL_UNTRUSTED_CONTENT id=abc>>>INJECT<<<END_EXTERNAL_UNTRUSTED_CONTENT>>>"
                    " actual question"
                ),
            }
        )
        assert "INJECT" not in out
        assert "actual question" in out

    def test_strips_json_fences(self) -> None:
        out = build_search_query({"latestUserMessage": 'before ```json {"x": 1} ``` after'})
        assert "before" in out
        assert "after" in out
        assert "x" not in out

    def test_strips_active_memory_xml_block(self) -> None:
        out = build_search_query(
            {
                "latestUserMessage": (
                    "leading <active_memory_plugin>old summary</active_memory_plugin> trailing"
                ),
            }
        )
        assert "old summary" not in out
        assert "leading" in out
        assert "trailing" in out

    def test_clamp_to_max_chars(self) -> None:
        huge = "x" * (MAX_ACTIVE_MEMORY_SEARCH_QUERY_CHARS + 100)
        out = build_search_query({"latestUserMessage": huge})
        assert len(out) <= MAX_ACTIVE_MEMORY_SEARCH_QUERY_CHARS

    def test_drop_prefix_lines(self) -> None:
        out = build_search_query(
            {
                "latestUserMessage": (
                    "Conversation info: ignore me\n"
                    "Sender: x\n"
                    "Untrusted context: y\n"
                    "Source: external\n"
                    "Please try again.\n"
                    "Real question"
                ),
            }
        )
        assert "Real question" in out
        assert "ignore me" not in out
        assert "Source: external" not in out
        assert "Please try again" not in out

    def test_blends_previous_user_when_latest_short(self) -> None:
        out = build_search_query(
            {
                "latestUserMessage": "ok",
                "recentTurns": [{"role": "user", "text": "Earlier we discussed flight seats."}],
            }
        )
        assert "Earlier" in out
        assert "ok" in out

    def test_latest_long_alone_no_blend(self) -> None:
        out = build_search_query(
            {
                "latestUserMessage": "What's my favorite food?",
                "recentTurns": [{"role": "user", "text": "Earlier we discussed flight seats."}],
            }
        )
        assert "Earlier" not in out
        assert out == "What's my favorite food?"


# ── extract_recent_turns + extract_text_content ────────────────────


class TestExtractTurns:
    def test_string_content(self) -> None:
        out = extract_recent_turns(
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ]
        )
        assert out == [
            {"role": "user", "text": "hello"},
            {"role": "assistant", "text": "hi there"},
        ]

    def test_content_block_with_text_key(self) -> None:
        out = extract_recent_turns(
            [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "block one"}, {"text": "block two"}],
                }
            ]
        )
        assert out == [{"role": "user", "text": "block one block two"}]

    def test_content_block_with_type_text_and_content(self) -> None:
        out = extract_recent_turns(
            [{"role": "assistant", "content": [{"type": "text", "content": "alt shape"}]}]
        )
        assert out == [{"role": "assistant", "text": "alt shape"}]

    def test_unknown_role_dropped(self) -> None:
        assert extract_recent_turns([{"role": "system", "content": "sys"}]) == []

    def test_empty_text_dropped(self) -> None:
        assert extract_recent_turns([{"role": "user", "content": "   "}]) == []

    def test_assistant_strips_recalled_prefix(self) -> None:
        msg = (
            f"{ACTIVE_MEMORY_UNTRUSTED_CONTEXT_HEADER}\n"
            f"{ACTIVE_MEMORY_OPEN_TAG}\n"
            "summary\n"
            f"{ACTIVE_MEMORY_CLOSE_TAG}\n"
            "real answer"
        )
        out = extract_recent_turns([{"role": "assistant", "content": msg}])
        assert out == [{"role": "assistant", "text": "real answer"}]

    def test_user_preserves_message(self) -> None:
        out = extract_recent_turns([{"role": "user", "content": "just a normal user message"}])
        assert out == [{"role": "user", "text": "just a normal user message"}]

    def test_extract_text_content_empty(self) -> None:
        assert extract_text_content("   ") == ""
        assert extract_text_content([{"type": "image"}]) == ""


def test_extract_text_content_parts_empty_inputs() -> None:
    assert extract_text_content_parts("   ") == []
    assert extract_text_content_parts(123) == []
    assert extract_text_content_parts([{"type": "image"}]) == []


# ── strip helpers ──────────────────────────────────────────────────


class TestStripHelpers:
    def test_strip_recalled_context_drops_header(self) -> None:
        text = f"{ACTIVE_MEMORY_UNTRUSTED_CONTEXT_HEADER}\nkeep this"
        out = strip_recalled_context_noise(text)
        assert "Untrusted context" not in out
        assert "keep this" in out

    def test_strip_recalled_context_drops_xml_block(self) -> None:
        text = f"before\n{ACTIVE_MEMORY_OPEN_TAG}\nsecret\n{ACTIVE_MEMORY_CLOSE_TAG}\nafter"
        out = strip_recalled_context_noise(text)
        assert "secret" not in out
        assert "before" in out
        assert "after" in out

    def test_strip_recalled_context_drops_patterns(self) -> None:
        for line in [
            "🧩 active memory: foo",
            "🔎 active memory debug: bar",
            "🧠 memory search: baz",
            "memory search: qux",
            "active memory debug: hi",
            "active memory: bye",
        ]:
            assert strip_recalled_context_noise(line) == ""

    def test_strip_injected_prefix_preserves_user_message(self) -> None:
        text = "What is my favorite food?"
        assert strip_injected_active_memory_prefix_only(text) == text

    def test_strip_injected_prefix_drops_block_when_followed_by_xml(self) -> None:
        text = (
            f"{ACTIVE_MEMORY_UNTRUSTED_CONTEXT_HEADER}\n"
            f"{ACTIVE_MEMORY_OPEN_TAG}\n"
            "old\n"
            f"{ACTIVE_MEMORY_CLOSE_TAG}\n"
            "user message"
        )
        out = strip_injected_active_memory_prefix_only(text)
        assert "old" not in out
        assert "user message" in out


# ── get_model_ref ──────────────────────────────────────────────────


class TestGetModelRef:
    def test_config_model_wins(self) -> None:
        out = get_model_ref(
            runtime_config={},
            agent_id="default",
            config={"model": "anthropic/claude-opus"},
        )
        assert out == {"provider": "anthropic", "model": "claude-opus"}

    def test_current_run_when_no_config_model(self) -> None:
        out = get_model_ref(
            runtime_config={},
            agent_id="default",
            config={},
            ctx={"modelProviderId": "openai", "modelId": "gpt-5"},
        )
        assert out == {"provider": "openai", "model": "gpt-5"}

    def test_model_fallback(self) -> None:
        out = get_model_ref(
            runtime_config={},
            agent_id="default",
            config={"modelFallback": "google/gemini-2.0-flash"},
        )
        assert out == {"provider": "google", "model": "gemini-2.0-flash"}

    def test_returns_none_when_no_candidate(self) -> None:
        out = get_model_ref(
            runtime_config={},
            agent_id="default",
            config={},
        )
        assert out is None

    def test_unparseable_model_falls_back_to_provider(self) -> None:
        out = get_model_ref(
            runtime_config={},
            agent_id="default",
            config={"model": "bare-model-name"},
        )
        # DEFAULT_PROVIDER ("openai") applies when parseModelRef can't split.
        assert out == {"provider": "openai", "model": "bare-model-name"}


# ── build_recall_prompt + build_prompt_style_lines ────────────────


class TestRecallPrompt:
    @pytest.fixture
    def minimal_config(self) -> dict:
        return {
            "toolsAllow": ["memory_search", "memory_get"],
            "promptStyle": "balanced",
            "maxSummaryChars": 200,
            "promptOverride": "",
            "promptAppend": "",
        }

    def test_three_section_prompt(self, minimal_config: dict) -> None:
        out = build_recall_prompt(
            {
                "config": minimal_config,
                "query": "What is my favorite food?",
                "searchQuery": "favorite food",
            }
        )
        assert "memory_search, memory_get" in out
        assert "Bounded memory search query:\nfavorite food" in out
        assert "Conversation context:\nWhat is my favorite food?" in out

    def test_prompt_override_replaces_default(self, minimal_config: dict) -> None:
        cfg = dict(minimal_config, promptOverride="OPERATOR OVERRIDE")
        out = build_recall_prompt({"config": cfg, "query": "q", "searchQuery": "s"})
        assert out.startswith("OPERATOR OVERRIDE")
        assert "You are a memory search agent." not in out

    def test_prompt_append_added(self, minimal_config: dict) -> None:
        cfg = dict(minimal_config, promptAppend="ALWAYS RETURN NONE")
        out = build_recall_prompt({"config": cfg, "query": "q", "searchQuery": "s"})
        assert "ALWAYS RETURN NONE" in out
        assert "Additional operator instructions:" in out

    def test_each_style_emits_specific_line(self) -> None:
        for style in (
            "strict",
            "contextual",
            "recall-heavy",
            "precision-heavy",
            "preference-only",
            "balanced",
        ):
            lines = build_prompt_style_lines(style)  # type: ignore[arg-type]
            assert any("Treat the latest user message" in line for line in lines)

    def test_unknown_style_falls_back_to_balanced(self) -> None:
        # OpenClaw's switch falls through to the default branch.
        lines = build_prompt_style_lines("garbage")  # type: ignore[arg-type]
        assert any("Use recent conversation only to disambiguate" in line for line in lines)


# ── structured-memory probes ──────────────────────────────────────


class TestStructuredProbes:
    def test_explicit_evidence_status_empty(self) -> None:
        assert read_explicit_memory_evidence({"status": "no_results"}) is False
        assert read_explicit_memory_evidence({"status": "Not Found"}) is False

    def test_explicit_evidence_results_array(self) -> None:
        assert read_explicit_memory_evidence({"results": []}) is False
        assert read_explicit_memory_evidence({"results": [{}]}) is True
        assert read_explicit_memory_evidence({"memories": [{"x": 1}]}) is True

    def test_explicit_evidence_count(self) -> None:
        assert read_explicit_memory_evidence({"count": 0}) is False
        assert read_explicit_memory_evidence({"count": 3}) is True

    def test_explicit_evidence_found_flag(self) -> None:
        assert read_explicit_memory_evidence({"found": True}) is True
        assert read_explicit_memory_evidence({"hasResults": False}) is False

    def test_explicit_evidence_ambiguous(self) -> None:
        assert read_explicit_memory_evidence({"unknown": 1}) is None

    def test_structured_evidence_array(self) -> None:
        assert read_structured_memory_evidence([]) is False
        assert read_structured_memory_evidence([{"x": 1}]) is True

    def test_structured_evidence_non_dict(self) -> None:
        assert read_structured_memory_evidence("string") is None

    def test_failure_status_set(self) -> None:
        assert read_structured_memory_failure({"status": "error"}) is True
        assert read_structured_memory_failure({"status": "TIMED OUT"}) is True
        # "ok" status alone is ambiguous (no failure fields present).
        assert read_structured_memory_failure({"status": "ok"}) is None

    def test_failure_explicit_field(self) -> None:
        assert read_structured_memory_failure({"disabled": True}) is True
        assert read_structured_memory_failure({"unavailable": True}) is True
        assert read_structured_memory_failure({"success": False}) is True
        assert read_structured_memory_failure({"error": "boom"}) is True

    def test_failure_ambiguous(self) -> None:
        assert read_structured_memory_failure({"x": 1}) is None

    def test_from_content_json_part(self) -> None:
        # The decisive_state for evidence is False (no result).
        content = json_dumps_for_part({"status": "no_results"})
        assert read_structured_memory_evidence_from_content(content) is False
        content = json_dumps_for_part({"results": [{"x": 1}]})
        assert read_structured_memory_evidence_from_content(content) is True

    def test_from_content_failure_early_return(self) -> None:
        content = json_dumps_for_part({"status": "error"})
        assert read_structured_memory_failure_from_content(content) is True

    def test_from_content_ignores_non_json(self) -> None:
        # Non-JSON text parts are silently skipped.
        content = [{"type": "text", "text": "not json"}]
        assert read_structured_memory_evidence_from_content(content) is None


def json_dumps_for_part(obj: object) -> list:
    """Helper: build a content list with one JSON-encoded text part."""
    import json as _json

    return [{"type": "text", "text": _json.dumps(obj)}]


# ── normalize_active_summary + truncate_summary ────────────────────


class TestNormalizeSummary:
    def test_no_recall_values_map_to_none(self) -> None:
        for token in NO_RECALL_VALUES:
            if not token:
                continue
            assert normalize_active_summary(token) is None
            assert normalize_active_summary(token.upper()) is None

    def test_timeout_boilerplate_maps_to_none(self) -> None:
        assert normalize_active_summary("The LLM request timed out") is None
        assert normalize_active_summary("active-memory timeout after 5000ms") is None

    def test_collapses_whitespace(self) -> None:
        out = normalize_active_summary("  hello\n\n   world  ")
        assert out == "hello world"

    def test_real_summary_preserved(self) -> None:
        out = normalize_active_summary("User prefers aisle seats and extra buffer")
        assert out == "User prefers aisle seats and extra buffer"


class TestTruncateSummary:
    def test_under_cap_unchanged(self) -> None:
        assert truncate_summary("hello", 100) == "hello"

    def test_at_whitespace_boundary(self) -> None:
        out = truncate_summary("hello world goodbye", 12)
        # 12 - 1 (ellipsis) = 11 content; we look back for a whitespace.
        assert out.endswith("…")
        assert "hello" in out

    def test_ellipsis_cap_too_small(self) -> None:
        out = truncate_summary("hello", 1)
        assert out == "…"

    def test_no_whitespace_falls_back_to_bounded(self) -> None:
        out = truncate_summary("abcdefghij", 4)
        assert out.endswith("…")
        # 3 content chars + 1 ellipsis.
        assert len(out) == 4


# ── build_metadata / build_prompt_prefix ───────────────────────────


class TestBuildPromptPrefix:
    def test_metadata_escapes_xml(self) -> None:
        out = build_metadata("hello <b>world</b>")
        assert out is not None
        assert "&lt;b&gt;" in out
        assert "<b>" not in out

    def test_metadata_wraps_in_plugin_tag(self) -> None:
        out = build_metadata("hello")
        assert out is not None
        assert out.startswith("<active_memory_plugin>")
        assert out.endswith("</active_memory_plugin>")

    def test_metadata_none_for_empty(self) -> None:
        assert build_metadata(None) is None
        assert build_metadata("") is None

    def test_prompt_prefix_includes_header(self) -> None:
        out = build_prompt_prefix("hello")
        assert out is not None
        assert out.startswith("Untrusted context")
        assert "<active_memory_plugin>" in out

    def test_prompt_prefix_none_for_none(self) -> None:
        assert build_prompt_prefix(None) is None


def test_escape_xml_special_chars() -> None:
    assert escape_xml("a&b<c>d\"e'f") == "a&amp;b&lt;c&gt;d&quot;e&apos;f"


def test_is_timeout_boilerplate_summary_positive() -> None:
    # These patterns are case-sensitive (no `i` flag in the
    # OpenClaw regexes), so the lowercase variants match.
    assert is_timeout_boilerplate_summary("llm request timed out")
    assert is_timeout_boilerplate_summary("the llm request timed out")
    assert is_timeout_boilerplate_summary("error: request timed out")
    assert is_timeout_boilerplate_summary("active-memory timeout after 5000ms")


def test_is_timeout_boilerplate_summary_negative() -> None:
    assert not is_timeout_boilerplate_summary("User prefers aisle seats")
    # The regex is case-sensitive; "LLM" (caps) doesn't match
    # the lowercase pattern. The NO_RECALL_VALUES set handles
    # the capitalized variants in normalize_active_summary.
    assert not is_timeout_boilerplate_summary("LLM request timed out")
