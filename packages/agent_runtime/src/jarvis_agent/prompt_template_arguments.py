"""Prompt template arguments: shell-style parsing and placeholder substitution.

Port of ``packages/agent-core/src/harness/prompt-template-arguments.ts``
(97 lines).

Two Python/JavaScript differences are handled explicitly rather than left to
the regex engine, because both fail silently:

``re.sub`` treats backslash escapes in a *string* replacement as group
references, so every substitution here passes a function instead. A user
argument containing ``\\1`` would otherwise be reinterpreted as a capture
group — user text must never be able to steer the substitution.

``\\s`` is not the same set in the two languages: JavaScript includes
``\\ufeff`` (BOM) and excludes ``\\x1c``–``\\x1f`` and ``\\x85``, while Python
does the reverse. The JavaScript set is spelled out in
:data:`_JS_WHITESPACE` so a pasted argument tokenizes identically in both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "PromptTemplate",
    "format_prompt_template_invocation",
    "parse_command_args",
    "substitute_args",
]

#: ``Number.MAX_SAFE_INTEGER``. Parity: ``Number.isSafeInteger``.
_MAX_SAFE_INTEGER = 2**53 - 1

#: Exactly the characters JavaScript's ``\s`` matches, written as explicit
#: codepoints rather than literals: an editor or encoding pass that
#: normalized invisible characters in this file would otherwise change
#: tokenization silently. Python's ``\s`` is a different set (it excludes
#: U+FEFF and includes U+001C-U+001F and U+0085), so it cannot be used.
_JS_WHITESPACE = frozenset(
    chr(codepoint)
    for codepoint in {
        0x09, 0x0A, 0x0B, 0x0C, 0x0D,  # tab, LF, VT, FF, CR
        0x20,  # space
        0xA0,  # no-break space
        0x1680,  # ogham space mark
        *range(0x2000, 0x200B),  # en/em quad through hair space
        0x2028, 0x2029,  # line/paragraph separator
        0x202F,  # narrow no-break space
        0x205F,  # medium mathematical space
        0x3000,  # ideographic space
        0xFEFF,  # zero-width no-break space (BOM)
    }
)

#: Guard against an edit above silently changing the set. Both halves matter:
#: the count catches a dropped codepoint, and the membership check catches a
#: set of *ints* instead of characters — which would make every `in` test
#: false and collapse all arguments into a single token, silently.
assert len(_JS_WHITESPACE) == 25
assert " " in _JS_WHITESPACE

_POSITIONAL = re.compile(r"\$(\d+)")
_SLICE = re.compile(r"\$\{@:(\d+)(?::(\d+))?\}")
_ARGUMENTS = re.compile(r"\$ARGUMENTS")
_AT = re.compile(r"\$@")


@dataclass(frozen=True)
class PromptTemplate:
    """A named prompt template. Parity: ``PromptTemplate``."""

    name: str
    content: str
    description: str | None = None


def parse_command_args(args_string: str) -> list[str]:
    """Split an argument string using shell-style single and double quotes.

    Parity: ``parseCommandArgs``.

    The ``has_token`` flag is what makes ``'first "" third'`` yield three
    arguments including an empty one. Quotes set the flag before any
    character is consumed, so an empty quoted string is still a token.
    Without it, the empty argument would collapse and every later
    positional placeholder would shift by one — ``$3`` would silently
    resolve to the wrong value rather than fail.

    Note that quotes only group; they are not preserved, and there is no
    backslash escape. This is deliberately simpler than a real shell.
    """
    args: list[str] = []
    current = ""
    in_quote: str | None = None
    has_token = False

    for char in args_string:
        if in_quote is not None:
            if char == in_quote:
                in_quote = None
            else:
                has_token = True
                current += char
        elif char in ('"', "'"):
            # Set before consuming anything, so `""` is an empty token
            # rather than nothing at all.
            has_token = True
            in_quote = char
        elif char in _JS_WHITESPACE:
            if has_token:
                args.append(current)
                current = ""
                has_token = False
        else:
            has_token = True
            current += char

    if has_token:
        args.append(current)
    return args


def _parse_safe_non_negative_integer(raw: str) -> int | None:
    """A non-negative integer within JavaScript's safe range, or ``None``.

    Parity: ``parseSafeNonNegativeInteger``. The ceiling is not arbitrary:
    beyond 2**53-1 JavaScript numbers stop being exact, so OpenClaw refuses
    them rather than acting on an imprecise index. The Python port would be
    exact at any size, but accepting more would diverge in behaviour on the
    same template.
    """
    try:
        parsed = int(raw)
    except ValueError:
        return None
    return parsed if 0 <= parsed <= _MAX_SAFE_INTEGER else None


def substitute_args(content: str, args: list[str]) -> str:
    """Replace ``$1``, ``$@``, ``$ARGUMENTS``, ``${@:N}`` and ``${@:N:L}``.

    Parity: ``substituteArgs``.

    Malformed placeholders resolve to empty text and never raise, so a bad
    template cannot abort prompt loading or invocation — a broken template
    degrades one prompt instead of breaking the session.

    Substitution order is fixed and load-bearing: positionals, then slices,
    then ``$ARGUMENTS``, then ``$@``. Each pass runs over the *accumulated*
    result, so text inserted by an earlier pass is still visible to later
    ones. An argument containing ``$2`` is therefore safe (positionals
    already ran), but one containing ``$@`` or ``${@:1}`` will be expanded
    by the pass that follows.

    That is OpenClaw's behaviour and is preserved deliberately. It means
    argument text can influence the remaining substitutions, so callers
    must not treat prompt templates as a trust boundary for untrusted
    argument values.
    """

    def positional(match: re.Match[str]) -> str:
        parsed = _parse_safe_non_negative_integer(match.group(1))
        # `$0` is not the first argument — there is no command name to be
        # argument zero, so it resolves to empty like any out-of-range index.
        if parsed is None or parsed <= 0:
            return ""
        index = parsed - 1
        return args[index] if index < len(args) else ""

    def slice_(match: re.Match[str]) -> str:
        start_raw, length_raw = match.group(1), match.group(2)
        parsed_start = _parse_safe_non_negative_integer(start_raw)
        if parsed_start is None:
            return ""

        # Shell-style `${@:0:...}` compatibility: in a shell, start 0
        # includes `$0`, the command name. Prompt templates have no command
        # name, so 0 and 1 both map to the first provided argument.
        start = parsed_start - 1
        if start < 0:
            start = 0

        if length_raw is not None:
            length = _parse_safe_non_negative_integer(length_raw)
            if length is None:
                return ""
            # A length of 0 yields the empty string, not "the rest" — the
            # regex cannot capture an empty length, so `${@:0:0}` is an
            # explicit request for nothing.
            return " ".join(args[start : start + length])
        return " ".join(args[start:])

    result = _POSITIONAL.sub(positional, content)
    result = _SLICE.sub(slice_, result)

    all_args = " ".join(args)
    result = _ARGUMENTS.sub(lambda _: all_args, result)
    result = _AT.sub(lambda _: all_args, result)
    return result



def format_prompt_template_invocation(
    template: PromptTemplate, args: list[str] | None = None
) -> str:
    """Render a template with command-style argument substitution.

    Parity: ``formatPromptTemplateInvocation``. ``args`` defaults to empty,
    which blanks every placeholder rather than leaving the raw ``$1`` text
    in the prompt.
    """
    return substitute_args(template.content, args if args is not None else [])
