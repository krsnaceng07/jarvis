"""Tests for src/plugins/open_prose.py.

Mirrors tests of docs/plugins/open-prose.md and extensions/open-prose in OpenClaw.
"""

from __future__ import annotations


from src.plugins.open_prose import (
    OpenProseConfig,
    parse_prose_command,
    resolve_prose_target_url,
)


def test_resolve_prose_target_url():
    assert resolve_prose_target_url("alice/my-program") == "https://p.prose.md/alice/my-program"
    assert resolve_prose_target_url("https://example.com/test.prose") == "https://example.com/test.prose"
    assert resolve_prose_target_url("local_file.prose") == "local_file.prose"


def test_parse_prose_command():
    c1 = parse_prose_command("run alice/my-program --state=sqlite")
    assert c1.action == "run"
    assert c1.target == "alice/my-program"
    assert c1.flags.get("state") == "sqlite"

    c2 = parse_prose_command("compile workflow.prose")
    assert c2.action == "compile"
    assert c2.target == "workflow.prose"

    c3 = parse_prose_command("")
    assert c3.action == "help"


def test_open_prose_config():
    cfg = OpenProseConfig()
    assert cfg.enabled is True
    assert cfg.state_backend == "filesystem"
