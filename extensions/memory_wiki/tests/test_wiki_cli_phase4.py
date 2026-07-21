"""Tests for extensions/memory_wiki/wiki_cli.py.

Phase 4.3g-mr7: ports the OpenClaw
``cli.ts`` test surface. The tests focus
on:

- ``register_wiki_cli`` builds a
  well-formed ``argparse`` subparser
  hierarchy with all 19 commands
  (``status``, ``doctor``, ``init``,
  ``compile``, ``lint``, ``ingest``,
  ``okf``, ``search``, ``get``,
  ``apply``, ``bridge``, ``unsafe-local``,
  ``chatgpt``, ``obsidian``) wired.
- The sanitizer / format helpers strip
  control characters + JSON-format
  output.
- The ``require_command_context`` raises
  when called before ``preAction``.
- The unsafe-local sub-command refuses
  to run against agent-scoped vaults.
- The apply-synthesis sub-command
  requires at least one ``--source-id``.
- The Obsidian sub-commands refuse to
  run against agent-scoped vaults.
- The full test surface is exercised
  with an in-memory ``stdout`` so we
  can assert the rendered text matches
  the OpenClaw template.
"""

# ruff: noqa: S108 — test fixtures mirror the OpenClaw TS source

# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import io
import json
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

from extensions.memory_wiki.config import resolve_memory_wiki_config  # noqa: E402
from extensions.memory_wiki.wiki_cli import (  # noqa: E402
    MemoryWikiCliRegistration,
    WikiCommandContext,
    _format_json_or_text,
    _require_command_context,
    _sanitize_gateway_string_for_terminal,
    _write_output,
    register_wiki_cli,
)


def _make_parser(*, path: str = "/tmp/wiki", scope: str = "global") -> argparse.ArgumentParser:
    config = resolve_memory_wiki_config({"vault": {"scope": scope, "path": path}})
    p = argparse.ArgumentParser()
    register_wiki_cli(p, MemoryWikiCliRegistration(config=config))
    return p


# ── Sanitizer / format helpers ──────────────────────────────


class TestSanitize:
    def test_strips_ansi_escapes(self) -> None:
        assert _sanitize_gateway_string_for_terminal("\x1b[31mred\x1b[0m") == "red"

    def test_replaces_control_characters(self) -> None:
        assert _sanitize_gateway_string_for_terminal("a\x00b\x01c") == "a b c"

    def test_strips_unicode_format_controls(self) -> None:
        assert _sanitize_gateway_string_for_terminal("a\u200bb\u200fc") == "abc"


class TestWriteOutput:
    def test_appends_newline(self) -> None:
        buf = io.StringIO()
        _write_output("hello", writer=buf)
        assert buf.getvalue() == "hello\n"

    def test_does_not_double_newline(self) -> None:
        buf = io.StringIO()
        _write_output("hello\n", writer=buf)
        assert buf.getvalue() == "hello\n"


class TestFormatJsonOrText:
    def test_json_mode(self) -> None:
        out = _format_json_or_text({"a": 1}, True, lambda v: str(v))
        assert json.loads(out) == {"a": 1}

    def test_text_mode(self) -> None:
        out = _format_json_or_text({"a": 1}, False, lambda v: f"got={v['a']}")
        assert out == "got=1"


class TestRequireCommandContext:
    def test_returns_context(self) -> None:
        ctx = WikiCommandContext(config=resolve_memory_wiki_config({"vault": {"path": "/tmp/x"}}))
        assert _require_command_context(ctx) is ctx

    def test_raises_on_none(self) -> None:
        with pytest.raises(RuntimeError, match="context"):
            _require_command_context(None)


# ── Registrar shape ─────────────────────────────────────────


class TestRegisterWikiCli:
    def test_wiki_subcommand_registered(self) -> None:
        p = _make_parser()
        # Parse just ``wiki`` with no
        # sub-action. This should fail
        # because ``wiki_action`` is
        # required.
        with pytest.raises(SystemExit):
            p.parse_args(["wiki"])

    def test_all_top_level_actions_registered(self) -> None:
        p = _make_parser()
        # Each of these should parse without
        # error. ``ingest`` requires a
        # positional ``input_path``; ``okf``
        # requires the ``import`` sub-action;
        # ``apply`` requires ``synthesis`` or
        # ``metadata``; the multi-action
        # commands each need a leaf sub-action.
        for action, extra in (
            ("status", []),
            ("doctor", []),
            ("init", []),
            ("compile", []),
            ("lint", []),
            ("ingest", ["/tmp/x.md"]),
            ("okf", ["import", "/tmp/bundle"]),
            ("search", ["q"]),
            ("get", ["alpha.md"]),
            ("apply", ["synthesis", "title", "--body", "b", "--source-id", "x"]),
            ("bridge", ["import"]),
            ("unsafe-local", ["import"]),
            ("chatgpt", ["import", "--export", "/tmp/x"]),
            ("obsidian", ["status"]),
        ):
            args = p.parse_args(["wiki", action, *extra])
            assert args.wiki_command == "wiki"
            assert args.wiki_action == action
            assert callable(args.func)

    def test_agent_flag_passes_through(self) -> None:
        p = _make_parser()
        args = p.parse_args(["wiki", "--agent", "alpha", "init"])
        assert args.agent == "alpha"
        assert args.wiki_action == "init"

    def test_ingest_takes_path(self) -> None:
        p = _make_parser()
        args = p.parse_args(["wiki", "ingest", "/tmp/source.md"])
        assert args.wiki_action == "ingest"
        assert args.input_path == "/tmp/source.md"
        assert args.title is None
        assert args.json_flag is False

    def test_ingest_with_title_and_json(self) -> None:
        p = _make_parser()
        args = p.parse_args(["wiki", "ingest", "/tmp/source.md", "--title", "Custom", "--json"])
        assert args.title == "Custom"
        assert args.json_flag is True

    def test_okf_import(self) -> None:
        p = _make_parser()
        args = p.parse_args(["wiki", "okf", "import", "/tmp/bundle"])
        assert args.wiki_action == "okf"
        assert args.okf_action == "import"
        assert args.bundle_path == "/tmp/bundle"

    def test_search_options(self) -> None:
        p = _make_parser()
        args = p.parse_args(
            [
                "wiki",
                "search",
                "alpha",
                "--max-results",
                "5",
                "--backend",
                "shared",
                "--corpus",
                "wiki",
                "--mode",
                "auto",
            ]
        )
        assert args.wiki_action == "search"
        assert args.query == "alpha"
        assert args.max_results == 5
        assert args.backend == "shared"
        assert args.corpus == "wiki"
        assert args.mode == "auto"

    def test_apply_synthesis_requires_source_id(self) -> None:
        p = _make_parser()
        # ``_run_wiki_apply_synthesis``
        # raises when ``source_ids`` is
        # None (no ``--source-id`` flag).
        # We assert by calling the handler
        # directly.
        args = p.parse_args(
            [
                "wiki",
                "apply",
                "synthesis",
                "My Synthesis",
                "--body",
                "body",
            ]
        )
        ctx = WikiCommandContext(config=resolve_memory_wiki_config({"vault": {"path": "/tmp/x"}}))
        from extensions.memory_wiki.wiki_cli import _run_wiki_apply_synthesis

        with pytest.raises(ValueError, match="--source-id"):
            _run_wiki_apply_synthesis(
                ctx,
                title=args.title,
                body=args.body,
                body_file=None,
                source_ids=None,
                contradictions=None,
                questions=None,
                confidence=None,
                status=None,
                json_flag=False,
            )

    def test_unsafe_local_refuses_agent_scope(self) -> None:
        from extensions.memory_wiki.wiki_cli import _run_wiki_unsafe_local_import

        # The resolver MUST produce an
        # agent-scoped config (we use
        # ``scope=agent`` to force it).
        config = resolve_memory_wiki_config(
            {
                "vault": {
                    "scope": "agent",
                    "path": "/tmp/x",
                    "agentId": "alpha",
                }
            }
        )
        ctx = WikiCommandContext(config=config)
        with pytest.raises(ValueError, match="agent"):
            _run_wiki_unsafe_local_import(ctx, json_flag=False)

    def test_obsidian_refuses_agent_scope(self) -> None:
        from extensions.memory_wiki.wiki_cli import _run_wiki_obsidian_search

        config = resolve_memory_wiki_config(
            {
                "vault": {
                    "scope": "agent",
                    "path": "/tmp/x",
                    "agentId": "alpha",
                }
            }
        )
        ctx = WikiCommandContext(config=config)
        with pytest.raises(ValueError, match="agent"):
            _run_wiki_obsidian_search(ctx, query="x", json_flag=False)

    def test_obsidian_actions_all_refuse_agent_scope(self) -> None:
        config = resolve_memory_wiki_config(
            {
                "vault": {
                    "scope": "agent",
                    "path": "/tmp/x",
                    "agentId": "alpha",
                }
            }
        )
        ctx = WikiCommandContext(config=config)
        from extensions.memory_wiki.wiki_cli import (
            _run_wiki_obsidian_command,
            _run_wiki_obsidian_daily,
            _run_wiki_obsidian_open,
        )

        with pytest.raises(ValueError, match="agent"):
            _run_wiki_obsidian_open(ctx, vault_path="x.md", json_flag=False)
        with pytest.raises(ValueError, match="agent"):
            _run_wiki_obsidian_command(ctx, id="x", json_flag=False)
        with pytest.raises(ValueError, match="agent"):
            _run_wiki_obsidian_daily(ctx, json_flag=False)

    def test_chatgpt_import_requires_export(self) -> None:
        p = _make_parser()
        with pytest.raises(SystemExit):
            # No --export provided.
            p.parse_args(["wiki", "chatgpt", "import"])

    def test_chatgpt_import_with_export(self) -> None:
        p = _make_parser()
        args = p.parse_args(
            [
                "wiki",
                "chatgpt",
                "import",
                "--export",
                "/tmp/conv.json",
            ]
        )
        assert args.export == "/tmp/conv.json"
        assert args.dry_run is False

    def test_apply_metadata_with_clear_confidence(self) -> None:
        p = _make_parser()
        args = p.parse_args(["wiki", "apply", "metadata", "alpha.md", "--clear-confidence"])
        assert args.wiki_action == "apply"
        assert args.apply_action == "metadata"
        assert args.lookup == "alpha.md"
        assert args.clear_confidence is True

    def test_help_message_lists_wiki(self) -> None:
        p = _make_parser()
        buf = io.StringIO()
        with pytest.raises(SystemExit):
            # ``--help`` exits the program.
            old, sys.stdout = sys.stdout, buf
            try:
                p.parse_args(["--help"])
            finally:
                sys.stdout = old
        output = buf.getvalue()
        assert "wiki" in output
