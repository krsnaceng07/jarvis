"""Phase 5.8 gate: ``prompt_template_arguments.py``.

Ports every vector from ``prompt-template-arguments.test.ts`` (11 lines) and
``prompt-templates.test.ts`` (30 lines), plus the JavaScript/Python
divergences neither file can exercise.

Three of the tests here exist because a Python port fails where the
TypeScript cannot: ``\\s`` covering different characters, ``re.sub`` treating
``\\1`` in replacement *text* as a group reference, and — caught during this
port — a whitespace set built from ints instead of characters, which makes
every membership test false and silently collapses all arguments into one
token.
"""

from __future__ import annotations

import pytest

from jarvis_agent.prompt_template_arguments import (
    PromptTemplate,
    _JS_WHITESPACE,
    format_prompt_template_invocation,
    parse_command_args,
    substitute_args,
)

# ── ported verbatim from prompt-template-arguments.test.ts ───────────


def test_preserves_quoted_empty_arguments_so_positionals_stay_aligned() -> None:
    """The vector, and the reason the ``has_token`` flag exists.

    If the empty argument collapsed, ``$3`` would resolve to ``third``'s
    successor — every later placeholder silently shifted by one.
    """
    assert parse_command_args('first "" third') == ["first", "", "third"]
    assert parse_command_args("first '' third") == ["first", "", "third"]
    assert substitute_args("$1|$2|$3", parse_command_args('first "" third')) == "first||third"


# ── ported verbatim from prompt-templates.test.ts ────────────────────


def test_parses_quoted_and_multiline_arguments() -> None:
    assert parse_command_args("alpha \"beta gamma\"\ndelta 'echo one two'") == [
        "alpha",
        "beta gamma",
        "delta",
        "echo one two",
    ]


def test_rejects_unsafe_positional_placeholders() -> None:
    """Past ``MAX_SAFE_INTEGER`` the placeholder blanks instead of throwing."""
    assert substitute_args("$9007199254740992", ["first", "second"]) == ""


def test_rejects_unsafe_slice_starts_and_lengths() -> None:
    args = ["alpha", "beta", "gamma"]
    assert substitute_args("${@:9007199254740992}", args) == ""
    assert substitute_args("${@:1:9007199254740992}", args) == ""


def test_preserves_zero_slice_compatibility() -> None:
    """``${@:0:N}`` maps to the first argument, shell-style."""
    assert substitute_args("${@:0:0}", ["alpha", "beta"]) == ""
    assert substitute_args("${@:0:1}", ["alpha", "beta"]) == "alpha"


# ── the whitespace set ───────────────────────────────────────────────


def test_the_whitespace_set_holds_characters_not_codepoints() -> None:
    """Regression: the set was briefly built from ints.

    Every ``char in _JS_WHITESPACE`` test then returned False, so nothing
    ever split and all arguments merged into one token. Nothing raised —
    the only symptom was wrong output, which is exactly the failure mode
    this suite has to catch.
    """
    assert all(isinstance(c, str) for c in _JS_WHITESPACE)
    assert " " in _JS_WHITESPACE
    assert len(_JS_WHITESPACE) == 25


@pytest.mark.parametrize(
    "char",
    ["\t", "\n", "\v", "\f", "\r", " ", " ", " ", " ", " ",
     " ", " ", " ", " ", "　", "﻿"],
)
def test_javascript_whitespace_splits_arguments(char: str) -> None:
    assert parse_command_args(f"a{char}b") == ["a", "b"]


@pytest.mark.parametrize("char", ["\x1c", "\x1d", "\x1e", "\x1f", "\x85"])
def test_python_only_whitespace_does_not_split(char: str) -> None:
    """Python's ``\\s`` matches these; JavaScript's does not.

    Using Python's ``\\s`` would split arguments OpenClaw keeps whole, so
    the same template would render differently in the two runtimes.
    """
    assert parse_command_args(f"a{char}b") == [f"a{char}b"]


def test_the_bom_splits_arguments() -> None:
    """U+FEFF is whitespace in JavaScript but not in Python.

    A BOM pasted mid-line is exactly the invisible character a user would
    never think to look for.
    """
    assert parse_command_args("a﻿b") == ["a", "b"]


# ── quoting ──────────────────────────────────────────────────────────


def test_quotes_group_but_are_not_preserved() -> None:
    assert parse_command_args('"a b c"') == ["a b c"]


def test_the_other_quote_is_literal_inside_a_quote() -> None:
    assert parse_command_args("\"it's\"") == ["it's"]
    assert parse_command_args("'say \"hi\"'") == ['say "hi"']


def test_an_unterminated_quote_still_yields_its_token() -> None:
    """Falls off the end of the loop with ``has_token`` set.

    A malformed invocation loses the quote, not the argument — better than
    dropping user input entirely.
    """
    assert parse_command_args('first "unterminated') == ["first", "unterminated"]


def test_adjacent_quoted_segments_join_into_one_token() -> None:
    """No whitespace between them means no split, as in a real shell."""
    assert parse_command_args('"a""b"') == ["ab"]
    assert parse_command_args('a"b c"d') == ["ab cd"]


def test_there_is_no_backslash_escape() -> None:
    """Deliberately simpler than a shell: a backslash is literal."""
    assert parse_command_args("a\\ b") == ["a\\", "b"]


def test_leading_and_trailing_and_repeated_whitespace_is_collapsed() -> None:
    assert parse_command_args("   alpha    beta   ") == ["alpha", "beta"]


def test_an_empty_or_blank_string_parses_to_no_arguments() -> None:
    assert parse_command_args("") == []
    assert parse_command_args("     ") == []


# ── positional placeholders ──────────────────────────────────────────


def test_positional_placeholders_are_one_based() -> None:
    assert substitute_args("$1 $2", ["a", "b"]) == "a b"


def test_dollar_zero_resolves_to_empty() -> None:
    """There is no command name to be argument zero."""
    assert substitute_args("[$0]", ["a", "b"]) == "[]"


def test_an_out_of_range_positional_resolves_to_empty() -> None:
    """Not an IndexError. A template outliving its arguments must not crash."""
    assert substitute_args("[$5]", ["a"]) == "[]"


def test_multi_digit_positionals_are_read_whole() -> None:
    """``$12`` is argument twelve, not argument one followed by ``2``."""
    args = [f"a{i}" for i in range(1, 13)]
    assert substitute_args("$12", args) == "a12"


def test_a_placeholder_with_no_digits_is_left_alone() -> None:
    assert substitute_args("$ and $x", ["a"]) == "$ and $x"


# ── slices ───────────────────────────────────────────────────────────


def test_an_open_ended_slice_takes_the_rest() -> None:
    assert substitute_args("${@:2}", ["a", "b", "c"]) == "b c"


def test_slice_start_one_and_zero_agree() -> None:
    """Both mean "from the first argument"."""
    args = ["a", "b", "c"]
    assert substitute_args("${@:0}", args) == substitute_args("${@:1}", args) == "a b c"


def test_a_slice_past_the_end_is_empty() -> None:
    assert substitute_args("${@:9}", ["a"]) == ""


def test_a_slice_length_past_the_end_is_clamped() -> None:
    """Python slicing clamps rather than raising, matching JS ``slice``."""
    assert substitute_args("${@:1:99}", ["a", "b"]) == "a b"


def test_slice_elements_are_joined_with_single_spaces() -> None:
    assert substitute_args("${@:1:2}", ["a", "b", "c"]) == "a b"


def test_a_malformed_slice_is_left_literal() -> None:
    """The regex requires digits, so these never match and pass through."""
    assert substitute_args("${@:}", ["a"]) == "${@:}"
    assert substitute_args("${@:x}", ["a"]) == "${@:x}"


# ── $@ and $ARGUMENTS ────────────────────────────────────────────────


def test_all_args_placeholders_expand_to_the_joined_arguments() -> None:
    assert substitute_args("$@", ["a", "b"]) == "a b"
    assert substitute_args("$ARGUMENTS", ["a", "b"]) == "a b"


def test_all_args_placeholders_expand_to_empty_with_no_arguments() -> None:
    assert substitute_args("[$@]", []) == "[]"
    assert substitute_args("[$ARGUMENTS]", []) == "[]"


def test_every_occurrence_is_replaced() -> None:
    """Global replacement, not first-only."""
    assert substitute_args("$@ / $@", ["x"]) == "x / x"
    assert substitute_args("$1 $1 $1", ["x"]) == "x x x"


def test_arguments_is_substituted_before_the_at_form() -> None:
    """Order matters: ``$ARGUMENTS`` must not be seen as ``$A`` + text.

    Since ``$A`` is not a placeholder this is safe either way, but the
    ordering is asserted so a reordering does not go unnoticed.
    """
    assert substitute_args("$ARGUMENTS", ["a"]) == "a"


# ── substituted text is never rescanned ──────────────────────────────


def test_an_argument_containing_an_earlier_placeholder_stays_literal() -> None:
    """Positionals run first, so a ``$2`` in argument text is not re-read.

    This is the one direction that *is* safe. The companion test below
    covers the direction that is not.
    """
    assert substitute_args("$1", ["$2", "secret"]) == "$2"


def test_an_argument_containing_a_backreference_stays_literal() -> None:
    """Python-specific.

    ``re.sub`` with a *string* replacement expands ``\\1`` as a group
    reference. Passing a function avoids it — without that, an argument
    containing ``\\1`` would be rewritten into captured text.
    """
    assert substitute_args("$1", [r"\1"]) == r"\1"
    assert substitute_args("$@", [r"\g<0>"]) == r"\g<0>"


def test_an_argument_containing_a_later_placeholder_is_expanded() -> None:
    """Documents real behaviour, which is *not* full isolation.

    Each substitution pass runs over the accumulated result, so an argument
    inserted by the positional pass is still visible to the slice and
    ``$@`` passes that follow. This is OpenClaw's behaviour and is kept for
    parity — but it means prompt templates are not a trust boundary for
    untrusted argument text.
    """
    assert substitute_args("$1", ["${@:1}", "b"]) == "${@:1} b"
    assert substitute_args("$1", ["$@", "b"]) == "$@ b"
    assert substitute_args("$1", ["$ARGUMENTS", "b"]) == "$ARGUMENTS b"


# ── format_prompt_template_invocation ────────────────────────────────


def test_format_substitutes_into_the_template_content() -> None:
    template = PromptTemplate(name="t", content="Hello $1, from $2")
    assert format_prompt_template_invocation(template, ["world", "here"]) == (
        "Hello world, from here"
    )



def test_format_defaults_to_no_arguments() -> None:
    """Placeholders blank out rather than leaving raw ``$1`` in the prompt."""
    template = PromptTemplate(name="t", content="Hello $1 $@")
    assert format_prompt_template_invocation(template) == "Hello  "


def test_format_leaves_content_without_placeholders_untouched() -> None:
    template = PromptTemplate(name="t", content="no placeholders here")
    assert format_prompt_template_invocation(template, ["ignored"]) == "no placeholders here"


def test_the_description_is_optional() -> None:
    assert PromptTemplate(name="t", content="c").description is None
