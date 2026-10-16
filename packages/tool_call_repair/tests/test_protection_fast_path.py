"""Parity tests for the Markdown-protection fast path.

Mirrors ``packages/tool-call-repair/src/protection-fast-path.test.ts``:
conservative answers from fence state, decline (``None``) for every
unmodeled shape.
"""

from __future__ import annotations

from collections.abc import Callable

from jarvis_tool_call_repair import (
    advance_protection_scan_state,
    create_protection_scan_state,
    resolve_protection_fast_path,
)


def _verdict(prefix: str, incoming: str) -> Callable[[int], bool] | None:
    state = create_protection_scan_state()
    advance_protection_scan_state(state, prefix)
    return resolve_protection_fast_path(state, incoming)


def _ask(prefix: str, incoming: str, offset: int = 0) -> bool:
    verdict = _verdict(prefix, incoming)
    assert verdict is not None
    return verdict(offset)


def test_fenced_content_protected() -> None:
    verdict = _verdict("intro\n\n```toml\n", "[read]\n")
    assert verdict is not None
    assert verdict(0) is True


def test_prose_unprotected() -> None:
    verdict = _verdict("intro\n\nplain\n", "[read]\n")
    assert verdict is not None
    assert verdict(0) is False


def test_fence_closes_only_on_matching_run() -> None:
    assert _ask("```\ninside\n~~~\n", "[read]\n") is True
    assert _ask("````\ninside\n```\n", "[read]\n") is True
    assert _ask("```\ninside\n```\n", "[read]\n") is False


def test_backtick_in_backtick_info_string_declines() -> None:
    assert _verdict("```` ```\n", "[read]\n") is None
    assert _verdict("```js`\n", "[read]\n") is None


def test_tilde_fence_with_backtick_info_string_tracks() -> None:
    assert _ask("~~~ js`\n", "[read]\n") is True


def test_only_spaces_tabs_close_fences() -> None:
    assert _ask("```\nliteral\n``` \n", "[read]\n") is True
    assert _ask("```\nliteral\n```\t\n", "[read]\n") is False
    assert _ask("```\nliteral\n```  \n", "[read]\n") is False


def test_unicode_space_line_not_blank() -> None:
    assert _verdict("a `code` b\n \n", "[read]\n") is None


def test_unmodeled_shapes_decline() -> None:
    assert _verdict("a `code` b\n", "[read]\n") is None
    assert _verdict("> quoted\n", "[read]\n") is None
    assert _verdict("- item\n", "[read]\n") is None
    assert _verdict("para\n\n", "    [read]\n") is None


def test_tab_indented_code_declines() -> None:
    assert _verdict("para\n\n", "\t[read]\n") is None
    assert _verdict("", "\t[read]\n") is None
    assert _verdict("para\n\n", "  \t[read]\n") is None
    assert _verdict("para\n\n", "    \t[read]\n") is None
    assert _verdict("para\n\n", "\t  [read]\n") is None


def test_unfinished_line_outside_fence_declines() -> None:
    assert _verdict("plain\n", "[read]") is None


def test_bare_carriage_return_declines() -> None:
    assert _verdict("```\nliteral\n```\r", "[read]\n") is None
    assert _verdict("```\r[read]\r", "[read]\n") is None
    assert _verdict("```\nliteral\n", "```\r[read]\n") is None
    assert _ask("```toml\r\n", "[read]\r\n") is True


def test_blank_clears_ambiguity_never_parity_doubt() -> None:
    assert _ask("a `code` b\n\nplain\n", "[read]\n") is False
    assert _verdict("- item\n```\n\nplain\n", "[read]\n") is None


def test_successive_offsets() -> None:
    incoming = "\n".join(["plain", "```toml", "[a]", "[b]", "```", "plain2"]) + "\n"
    verdict = _verdict("", incoming)
    assert verdict is not None
    plain_len = len("plain\n")
    fence_open_len = plain_len + len("```toml\n")
    a_start = fence_open_len
    b_start = a_start + len("[a]\n")
    close_start = b_start + len("[b]\n")
    plain2_start = close_start + len("```\n")
    assert verdict(0) is False
    assert verdict(plain_len) is True
    assert verdict(a_start) is True
    assert verdict(b_start) is True
    assert verdict(close_start) is True
    assert verdict(plain2_start) is False
