"""Tests for src/commands/commands_registry.py.

Mirrors tests of docs/tools/commands.md and src/auto-reply/commands-registry in OpenClaw.
"""

from __future__ import annotations


from src.commands.commands_registry import (
    CommandsConfig,
    extract_directives_and_shortcuts,
)


def test_extract_directives_only():
    res = extract_directives_and_shortcuts("/think:high /fast")
    assert res.is_directive_only is True
    assert res.cleaned_text == ""
    assert res.directives_found["think"] == "high"
    assert res.directives_found["fast"] == "true"


def test_extract_directives_inline_with_text():
    res = extract_directives_and_shortcuts("/think:high Please write a quick poem")
    assert res.is_directive_only is False
    assert res.cleaned_text == "Please write a quick poem"
    assert res.directives_found["think"] == "high"


def test_extract_shortcuts():
    res = extract_directives_and_shortcuts("/whoami tell me who I am")
    assert res.is_directive_only is False
    assert res.cleaned_text == "tell me who I am"
    assert "whoami" in res.directives_found


def test_commands_config_defaults():
    cfg = CommandsConfig()
    assert cfg.text is True
    assert cfg.native == "auto"
    assert cfg.bash is False
