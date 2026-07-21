"""obsidian — Memory Wiki Obsidian CLI integration.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/obsidian.ts``.

A thin wrapper around the official
Obsidian CLI. The host uses these helpers
from the ``wiki.obsidian.*`` gateway
methods (Phase 4.3f-mr4) and from the
``wiki obsidian ...`` CLI commands
(Phase 4.3g).

All helpers accept an optional
``ObsidianCliDeps`` argument so tests
can inject a fake ``exec`` /
``resolveCommand`` instead of invoking
the real Obsidian CLI binary. The default
implementations probe ``PATH`` for the
``obsidian`` executable (with the
Windows ``PATHEXT`` / ``.cmd`` /
``.bat`` lookup) and run the command
through :func:`jarvis_sdk.security_runtime.run_exec`
with a 10-second timeout.
"""

from __future__ import annotations

# ruff: noqa: TCH003 — ``Awaitable`` /
# ``Callable`` are needed at runtime so
# the public ``ObsidianCliDeps`` dataclass
# default-argument types resolve without
# forward-ref string annotations.
import os
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


# Mirrors the OpenClaw
# ``OBSIDIAN_CLI_TIMEOUT_MS = 10_000`` constant.
OBSIDIAN_CLI_TIMEOUT_MS = 10_000


@dataclass(frozen=True, slots=True)
class ObsidianCliProbe:
    """The result of :func:`probe_obsidian_cli`.

    Mirrors the OpenClaw
    ``ObsidianCliProbe`` type. ``available``
    is True when ``command`` resolved to a
    real binary on ``PATH``.
    """

    available: bool
    command: str | None = None


@dataclass(frozen=True, slots=True)
class ObsidianCliResult:
    """The result of a successful ``obsidian`` CLI invocation.

    Mirrors the OpenClaw
    ``ObsidianCliResult`` type.
    """

    command: str
    argv: list[str]
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class ObsidianCliDeps:
    """The injectable dependencies for the
    Obsidian CLI helpers.

    Mirrors the OpenClaw
    ``ObsidianCliDeps`` type. Both
    callables are async; ``exec`` runs
    the binary and returns ``{stdout,
    stderr}``, while ``resolve_command``
    maps a command name (e.g.
    ``"obsidian"``) to an absolute path.
    """

    exec: Callable[
        [str, list[str], dict[str, Any]],
        Awaitable[dict[str, str]],
    ] = field(default=None)  # type: ignore[assignment]
    resolve_command: Callable[[str], Awaitable[str | None]] = field(
        default=None  # type: ignore[assignment]
    )


# ── Default dependency implementations ──────────────────────


async def _default_exec(
    command: str,
    args: list[str],
    options: dict[str, Any],
) -> dict[str, str]:
    """Default ``exec`` implementation.

    Mirrors the OpenClaw ``runExec``:
    invokes the command via
    :mod:`subprocess` with a timeout. Runs
    the blocking ``subprocess.run`` in a
    thread so the Obsidian CLI call doesn't
    pin the event loop.
    """
    import asyncio
    import subprocess

    timeout_ms = int(options.get("timeoutMs", OBSIDIAN_CLI_TIMEOUT_MS))
    timeout_s = max(1, timeout_ms // 1000)

    def _run() -> dict[str, str]:
        completed = subprocess.run(  # noqa: S603 — args validated by caller
            [command, *args],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return {
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
        }

    return await asyncio.to_thread(_run)


async def _default_resolve_command(command: str) -> str | None:
    """Default ``resolve_command`` implementation.

    Mirrors the OpenClaw
    ``resolveCommandOnPath``: if
    ``command`` contains a path separator,
    just check it's an executable file;
    otherwise walk ``PATH`` (and on
    Windows, ``PATHEXT``) looking for the
    binary.
    """
    if os.sep in command or (os.altsep and os.altsep in command):
        return command if os.path.isfile(command) else None
    path_value = os.environ.get("PATH") or os.environ.get("PATH") or ""
    path_entries = [p for p in path_value.split(os.pathsep) if p]
    if os.name == "nt":
        pathext = os.environ.get("PATHEXT") or ".EXE;.CMD;.BAT"
        windows_exts = [ext for ext in pathext.split(";") if ext]
    else:
        windows_exts = [""]
    for entry in path_entries:
        for ext in windows_exts:
            candidate = os.path.join(entry, f"{command}{ext}" if ext else command)
            if os.path.isfile(candidate):
                return candidate
    # Fallback to shutil.which which handles
    # PATHEXT on Windows.
    return shutil.which(command)


def _get_exec(
    deps: ObsidianCliDeps | None,
) -> Callable[[str, list[str], dict[str, Any]], Awaitable[dict[str, str]]]:
    return deps.exec if deps is not None and deps.exec is not None else _default_exec


def _get_resolve_command(
    deps: ObsidianCliDeps | None,
) -> Callable[[str], Awaitable[str | None]]:
    return (
        deps.resolve_command
        if deps is not None and deps.resolve_command is not None
        else _default_resolve_command
    )


# ── Public API ──────────────────────────────────────────────


async def probe_obsidian_cli(
    deps: ObsidianCliDeps | None = None,
) -> ObsidianCliProbe:
    """Probe ``PATH`` for the ``obsidian`` binary.

    Mirrors the OpenClaw
    :func:`probeObsidianCli`. Returns an
    :class:`ObsidianCliProbe` with
    ``available`` set to True when the
    binary is found.
    """
    resolve = _get_resolve_command(deps)
    command = await resolve("obsidian")
    return ObsidianCliProbe(
        available=command is not None,
        command=command,
    )


def _build_vault_prefix(config: ResolvedMemoryWikiConfig) -> list[str]:
    """Build the ``vault=<name>`` argv prefix when a vault name is set.

    Mirrors the OpenClaw
    ``buildVaultPrefix`` helper.
    """
    vault_name = getattr(getattr(config, "obsidian", None), "vaultName", None)
    if isinstance(vault_name, str) and vault_name.strip():
        return [f"vault={vault_name.strip()}"]
    return []


async def run_obsidian_cli(
    *,
    config: ResolvedMemoryWikiConfig,
    subcommand: str,
    args: list[str] | None = None,
    deps: ObsidianCliDeps | None = None,
) -> ObsidianCliResult:
    """Run ``obsidian <subcommand> ...``.

    Mirrors the OpenClaw
    :func:`runObsidianCli`. Raises when
    the binary is not available.
    """
    resolve = _get_resolve_command(deps)
    probe = await probe_obsidian_cli(
        ObsidianCliDeps(resolve_command=resolve)
        if resolve is not _default_resolve_command
        else None
    )
    if not probe.available or not probe.command:
        raise RuntimeError("Obsidian CLI is not available on PATH.")
    argv = [
        *_build_vault_prefix(config),
        subcommand,
        *(args or []),
    ]
    exec_fn = _get_exec(deps)
    result = await exec_fn(
        probe.command,
        argv,
        {"logOutput": False, "timeoutMs": OBSIDIAN_CLI_TIMEOUT_MS},
    )
    return ObsidianCliResult(
        command=probe.command,
        argv=argv,
        stdout=result.get("stdout", ""),
        stderr=result.get("stderr", ""),
    )


async def run_obsidian_search(
    *,
    config: ResolvedMemoryWikiConfig,
    query: str,
    deps: ObsidianCliDeps | None = None,
) -> ObsidianCliResult:
    """Run ``obsidian search query=<query>``.

    Mirrors the OpenClaw
    :func:`runObsidianSearch`.
    """
    return await run_obsidian_cli(
        config=config,
        subcommand="search",
        args=[f"query={query}"],
        deps=deps,
    )


async def run_obsidian_open(
    *,
    config: ResolvedMemoryWikiConfig,
    vault_path: str,
    deps: ObsidianCliDeps | None = None,
) -> ObsidianCliResult:
    """Run ``obsidian open path=<vault_path>``.

    Mirrors the OpenClaw
    :func:`runObsidianOpen`.
    """
    return await run_obsidian_cli(
        config=config,
        subcommand="open",
        args=[f"path={vault_path}"],
        deps=deps,
    )


async def run_obsidian_command(
    *,
    config: ResolvedMemoryWikiConfig,
    id: str,
    deps: ObsidianCliDeps | None = None,
) -> ObsidianCliResult:
    """Run ``obsidian command id=<id>``.

    Mirrors the OpenClaw
    :func:`runObsidianCommand`.
    """
    return await run_obsidian_cli(
        config=config,
        subcommand="command",
        args=[f"id={id}"],
        deps=deps,
    )


async def run_obsidian_daily(
    *,
    config: ResolvedMemoryWikiConfig,
    deps: ObsidianCliDeps | None = None,
) -> ObsidianCliResult:
    """Run ``obsidian daily``.

    Mirrors the OpenClaw
    :func:`runObsidianDaily`.
    """
    return await run_obsidian_cli(
        config=config,
        subcommand="daily",
        deps=deps,
    )


def reset_memory_wiki_obsidian_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


__all__ = [
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
]
