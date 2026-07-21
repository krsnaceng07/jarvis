"""Tests for extensions/memory_wiki/obsidian.py.

Phase 4.3g-mr1: ports the OpenClaw
``obsidian.ts`` test surface. The tests
focus on:

- ``probe_obsidian_cli`` returns
  ``available=True`` when the resolver
  finds the binary.
- ``probe_obsidian_cli`` returns
  ``available=False`` when the resolver
  returns ``None``.
- ``run_obsidian_search`` builds the
  OpenClaw argv (``vault=<name> search
  query=<query>``) with the right timeout
  + ``logOutput=False`` options.
- ``run_obsidian_daily`` raises a clean
  error when the binary is not available.
- The ``exec`` dependency is called once
  per invocation with the right command
  + argv.
"""

# ruff: noqa: S108 — tests use hard-coded
# ``/tmp/wiki`` paths because they're
# config-shape fixtures, not real
# filesystem paths.

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
# pyright: reportReturnType=false

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[3]

if TYPE_CHECKING:
    from types import SimpleNamespace
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)


import pytest  # noqa: E402

from extensions.memory_wiki import obsidian as obs  # noqa: E402
from extensions.memory_wiki.config import resolve_memory_wiki_config  # noqa: E402


def _config(*, vault_name: str | None = None) -> SimpleNamespace:
    raw: dict = {"vault": {"scope": "global", "path": "/tmp/wiki"}}
    if vault_name is not None:
        raw["obsidian"] = {"enabled": True, "useOfficialCli": True, "vaultName": vault_name}
    return resolve_memory_wiki_config(raw)


def _capturing_deps(
    *,
    command: str | None = "/usr/local/bin/obsidian",
    stdout: str = "ok\n",
    stderr: str = "",
) -> tuple[list, list, obs.ObsidianCliDeps]:
    """Return ``(calls, exec_calls, deps)`` so tests can assert on them."""
    calls: list[dict] = []
    exec_calls: list[dict] = []

    async def _resolve(cmd: str):
        calls.append({"kind": "resolve", "command": cmd})
        return command

    async def _exec(command: str, argv: list[str], options: dict):
        exec_calls.append({"command": command, "argv": argv, "options": options})
        return {"stdout": stdout, "stderr": stderr}

    return calls, exec_calls, obs.ObsidianCliDeps(exec=_exec, resolve_command=_resolve)


class TestProbeObsidianCli:
    async def test_available_when_resolver_returns_path(self) -> None:
        calls, _, deps = _capturing_deps(command="/usr/local/bin/obsidian")
        probe = await obs.probe_obsidian_cli(deps)
        assert probe.available is True
        assert probe.command == "/usr/local/bin/obsidian"
        assert calls == [{"kind": "resolve", "command": "obsidian"}]

    async def test_unavailable_when_resolver_returns_none(self) -> None:
        calls, _, deps = _capturing_deps(command=None)
        probe = await obs.probe_obsidian_cli(deps)
        assert probe.available is False
        assert probe.command is None


class TestRunObsidianSearch:
    async def test_builds_official_argv_with_vault_name(self) -> None:
        config = _config(vault_name="OpenClaw Wiki")
        _, exec_calls, deps = _capturing_deps(
            command="/usr/local/bin/obsidian",
            stdout="search output\n",
        )
        result = await obs.run_obsidian_search(config=config, query="agent memory", deps=deps)
        assert exec_calls == [
            {
                "command": "/usr/local/bin/obsidian",
                "argv": [
                    "vault=OpenClaw Wiki",
                    "search",
                    "query=agent memory",
                ],
                "options": {
                    "logOutput": False,
                    "timeoutMs": obs.OBSIDIAN_CLI_TIMEOUT_MS,
                },
            }
        ]
        assert result.stdout == "search output\n"
        assert result.stderr == ""

    async def test_omits_vault_arg_when_vault_name_unset(self) -> None:
        config = _config()
        _, exec_calls, deps = _capturing_deps(command="/usr/local/bin/obsidian")
        await obs.run_obsidian_search(config=config, query="hello", deps=deps)
        argv = exec_calls[0]["argv"]
        assert argv == ["search", "query=hello"]


class TestRunObsidianDaily:
    async def test_fails_cleanly_when_binary_missing(self) -> None:
        config = _config()
        _, _, deps = _capturing_deps(command=None)
        with pytest.raises(RuntimeError, match="Obsidian CLI is not available on PATH"):
            await obs.run_obsidian_daily(config=config, deps=deps)

    async def test_runs_with_no_args(self) -> None:
        config = _config()
        _, exec_calls, deps = _capturing_deps(command="/usr/local/bin/obsidian")
        await obs.run_obsidian_daily(config=config, deps=deps)
        argv = exec_calls[0]["argv"]
        # Only the "daily" subcommand (no
        # vault prefix when not configured).
        assert argv == ["daily"]


class TestReset:
    def test_reset_returns_none(self) -> None:
        assert obs.reset_memory_wiki_obsidian_state_for_tests() is None


class TestExports:
    def test_all_exports(self) -> None:
        for name in (
            "OBSIDIAN_CLI_TIMEOUT_MS",
            "ObsidianCliDeps",
            "ObsidianCliProbe",
            "ObsidianCliResult",
            "probe_obsidian_cli",
            "reset_memory_wiki_obsidian_state_for_tests",
            "run_obsidian_cli",
            "run_obsidian_command",
            "run_obsidian_daily",
            "run_obsidian_open",
            "run_obsidian_search",
        ):
            assert hasattr(obs, name), f"missing export: {name}"
