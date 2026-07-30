"""jarvis.agents.sessions.resolve_config_value — config value resolution.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/resolve-config-value.ts``.

Resolve configuration values that may be shell
commands, environment variables, or literals. Used by
``auth-storage`` (Phase 6.6) and ``model-registry``
(Phase 6.7).

Parity
======
- ``resolve_config_value(config) -> str | None``
  (``resolve-config-value.ts:21-27``).
- ``resolve_config_value_uncached(config) -> str | None``
  (``resolve-config-value.ts:104-110``).
- ``resolve_config_value_or_throw(config, description) -> str``
  (``resolve-config-value.ts:112-123``) — raises on
  failure with the same error wording.
- ``resolve_headers_or_throw(headers, description) -> dict | None``
  (``resolve-config-value.ts:125-137``).
- ``clear_config_value_cache() -> None``
  (``resolve-config-value.ts:140-142``) — exposed for
  tests.

Resolution rules (matches the OpenClaw source):
- If ``config`` starts with ``"!"``, the rest is
  executed as a shell command; stdout (trimmed) is
  the value. The result is *cached* for the process
  lifetime.
- Otherwise, ``process.env[config]`` is consulted
  first. If the env var is unset, ``config`` is
  returned as a literal. The literal / env path is
  *not* cached.
- A non-zero exit code or timeout returns ``None``
  (the function never raises for command execution;
  the ``*_or_throw`` form converts ``None`` to an
  exception).

Phase 6.0 — scaffolding + helpers + small types.

Adaptations
-----------
- The OpenClaw source uses ``node:child_process``'s
  ``execSync`` / ``spawnSync`` + the project's
  ``buildShellCommandInvocation`` / ``getBashShellConfig``
  shell helpers. The Python port uses
  ``subprocess.run`` + ``shutil.which`` for the
  configured-shell path. The Phase 6.0 port supports
  both the ``posix`` (POSIX shell) and ``win32``
  (cmd.exe) platforms; the full configured-shell
  helper (``getBashShellConfig`` + the
  ``buildShellCommandInvocation`` OpenClaw port)
  lands in Phase 6.1.
- A 10s timeout (matches OpenClaw).
- The command-result cache is a module-level
  ``dict[str, str | None]`` guarded by a
  ``threading.Lock`` for cross-thread safety.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import Mapping


#: 10s timeout for shell command execution. Mirrors
#: the OpenClaw ``timeout: 10000`` constant
#: (``resolve-config-value.ts:40``).
_COMMAND_TIMEOUT_SECONDS = 10.0


#: Per-process cache for shell command results. Mirrors
#: the OpenClaw module-level ``commandResultCache``
#: (``resolve-config-value.ts:14``). Keyed by the raw
#: ``"!command"`` config string.
_command_result_cache: dict[str, str | None] = {}
_cache_lock = threading.Lock()


def _execute_command_uncached(command_config: str) -> str | None:
    """Run a shell command and return its trimmed
    stdout. Mirrors the body of
    ``executeCommandUncached``
    (``resolve-config-value.ts:79-89``).

    On any failure (ENOENT, non-zero exit, timeout,
    OS error), returns ``None`` instead of raising.
    The OpenClaw source swallows the same failures
    with bare ``catch {}`` blocks; the Python port
    logs the failure via the host logger if one is
    configured, but does not raise.
    """
    # Strip the leading ``!`` marker; the rest is the
    # raw shell command. The OpenClaw source does
    # ``commandConfig.slice(1)`` for the same effect.
    command = command_config[1:]

    if sys.platform == "win32":
        # Windows: prefer cmd.exe so behavior matches
        # the typical Windows desktop host. The
        # full configured-shell port lands in Phase
        # 6.1; for now we use the system ``cmd``.
        try:
            completed = subprocess.run(
                ["cmd.exe", "/c", command],
                capture_output=True,
                text=True,
                timeout=_COMMAND_TIMEOUT_SECONDS,
                check=False,
                # Suppress the cmd.exe window on
                # Windows desktop hosts.
                creationflags=(
                    subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
                    if hasattr(subprocess, "CREATE_NO_WINDOW")
                    else 0
                ),
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return None

        if completed.returncode != 0:
            return None
        value = (completed.stdout or "").strip()
        return value or None

    # POSIX: use ``/bin/sh -c`` to honor shell syntax
    # (pipes, redirects, globs). The OpenClaw source
    # uses ``execSync(command, ...)`` which routes
    # through the user's default shell on POSIX
    # (typically ``/bin/sh``).
    try:
        completed = subprocess.run(
            ["/bin/sh", "-c", command],
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None
    value = (completed.stdout or "").strip()
    return value or None


def _execute_command(command_config: str) -> str | None:
    """Cached wrapper around
    :func:`_execute_command_uncached`. Mirrors
    ``executeCommand``
    (``resolve-config-value.ts:91-99``)."""
    with _cache_lock:
        cached = _command_result_cache.get(command_config)
    if cached is not None or command_config in _command_result_cache:
        # Hit (including the ``None`` cache entry that
        # records a previous failure). The OpenClaw
        # source uses ``Map.has`` + ``Map.get`` for
        # the same "explicit ``None`` cache hit"
        # semantics.
        return cached

    result = _execute_command_uncached(command_config)
    with _cache_lock:
        _command_result_cache[command_config] = result
    return result


def resolve_config_value(config: str) -> str | None:
    """Resolve a config value (API key, header value,
    etc.) to an actual value.

    Mirrors ``resolveConfigValue``
    (``resolve-config-value.ts:21-27``).

    Resolution order:
    1. If ``config`` starts with ``"!"``, execute the
       rest as a shell command and return trimmed
       stdout (cached).
    2. Otherwise, look up ``process.env[config]``. If
       the env var is set (truthy), return it.
    3. Otherwise, return ``config`` as a literal.

    The literal / env path is *not* cached; only the
    command path is. Matches OpenClaw.
    """
    if config.startswith("!"):
        return _execute_command(config)
    env_value = os.environ.get(config)
    return env_value if env_value else config


def resolve_config_value_uncached(config: str) -> str | None:
    """Same as :func:`resolve_config_value` but always
    re-runs the shell command (bypasses the cache).

    Mirrors ``resolveConfigValueUncached``
    (``resolve-config-value.ts:104-110``).
    """
    if config.startswith("!"):
        return _execute_command_uncached(config)
    env_value = os.environ.get(config)
    return env_value if env_value else config


def resolve_config_value_or_throw(config: str, description: str) -> str:
    """Resolve a config value or raise a descriptive
    error. Mirrors ``resolveConfigValueOrThrow``
    (``resolve-config-value.ts:112-123``).

    The error message format matches the OpenClaw
    source so the host's error surface is identical.
    """
    resolved = resolve_config_value_uncached(config)
    if resolved is not None:
        return resolved

    if config.startswith("!"):
        raise RuntimeError(
            f"Failed to resolve {description} from shell command: "
            f"{config[1:]}"
        )
    raise RuntimeError(f"Failed to resolve {description}")


def resolve_headers_or_throw(
    headers: Mapping[str, str] | None,
    description: str,
) -> dict[str, str] | None:
    """Resolve all header values using the same
    resolution logic as API keys.

    Mirrors ``resolveHeadersOrThrow``
    (``resolve-config-value.ts:125-137``). The
    resulting dict is returned as a regular
    ``dict[str, str]`` (OpenClaw uses
    ``Record<string, string>``).

    Parameters
    ----------
    headers : Mapping[str, str] | None
        Headers to resolve. ``None`` passes through.
    description : str
        Human-readable description used in error
        messages (e.g. ``"provider \"anthropic\""``).
    """
    if not headers:
        return None
    resolved: dict[str, str] = {}
    for key, value in headers.items():
        resolved[key] = resolve_config_value_or_throw(
            value, f'{description} header "{key}"'
        )
    if not resolved:
        return None
    return resolved


def clear_config_value_cache() -> None:
    """Clear the shell-command result cache.

    Mirrors ``clearConfigValueCache``
    (``resolve-config-value.ts:140-142``). Exposed
    for tests so a test can reset state between
    cases.
    """
    with _cache_lock:
        _command_result_cache.clear()


__all__ = [
    "clear_config_value_cache",
    "resolve_config_value",
    "resolve_config_value_or_throw",
    "resolve_config_value_uncached",
    "resolve_headers_or_throw",
]
