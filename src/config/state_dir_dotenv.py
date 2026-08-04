"""jarvis.config.state_dir_dotenv — state-directory dotenv loader.

OpenClaw parity: mirrors ``openclaw-main/src/config/state-dir-dotenv.ts``.

Focused minimal port: shell-reference detection + dotenv parser
helper. Real file I/O is delegated to caller-provided callables
until the infra/regular-file module lands.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional


#: Max bytes read from the state-directory .env file.
MAX_STATE_DIR_DOTENV_BYTES = 1024 * 1024


#: ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV canonical name.
ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV = "OPENCLAW_ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS"


#: Matches a bare shell variable reference (e.g. ``$VAR``).
_SHELL_REF_BARE_RE = re.compile(r"^\$[A-Z_][A-Z0-9_]*$")
#: Matches a brace-form shell reference (e.g. ``${VAR}``).
_SHELL_REF_BRACE_RE = re.compile(r"^\$\{[A-Z_][A-Z0-9_]*[^}]*\}$")
#: Matches a command substitution (e.g. ``$(cmd)``).
_SHELL_REF_CMD_RE = re.compile(r"^\$\([^)]*\)$")


def _unwrap_matching_literal_quotes(value: str) -> str:
    if not isinstance(value, str) or len(value) < 2:
        return value or ""
    first, last = value[0], value[-1]
    if (first == '"' or first == "'") and first == last:
        return value[1:-1]
    return value


def is_unresolved_shell_reference(value: str) -> bool:
    """Return whether ``value`` is a bare shell reference ($VAR / ${VAR} / $(cmd))."""
    if not isinstance(value, str):
        return False
    candidate = _unwrap_matching_literal_quotes(value.strip())
    return bool(
        _SHELL_REF_BARE_RE.match(candidate)
        or _SHELL_REF_BRACE_RE.match(candidate)
        or _SHELL_REF_CMD_RE.match(candidate)
    )


def _normalize_env_var_key(raw_key: str) -> str:
    """Best-effort env-var key normalization."""
    if not isinstance(raw_key, str):
        return ""
    return raw_key.strip().upper()


def _is_dangerous_host_env_var_name(key: str) -> bool:
    """Heuristic for env vars that must never be loaded from a dotenv."""
    if not isinstance(key, str):
        return False
    upper = key.upper()
    return upper in {
        "PATH", "PATHEXT", "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
    }


def _is_dangerous_host_env_override_var_name(key: str) -> bool:
    """Heuristic for env vars that must never be overridden by a dotenv."""
    if not isinstance(key, str):
        return False
    return key.upper().startswith("OPENCLAW_FORCE_")


def _is_blocked_service_env_var(key: str) -> bool:
    if not isinstance(key, str):
        return False
    if key.upper() == ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV:
        return True
    return _is_dangerous_host_env_var_name(key) or _is_dangerous_host_env_override_var_name(key)


def parse_state_dir_dot_env_content(
    content: Any,
    *,
    parse_dot_env_fn: Optional[Callable] = None,
) -> dict:
    """Parse a dotenv content blob and return the kept + skipped-key views.

    Mirrors :func:`parseStateDirDotEnvContent`
    (``shared/config/state-dir-dotenv.ts`).
    """
    if not callable(parse_dot_env_fn):
        return {"entries": {}, "skippedShellReferenceKeys": []}
    try:
        parsed = parse_dot_env_fn(content) or {}
    except Exception:
        return {"entries": {}, "skippedShellReferenceKeys": []}
    entries: dict = {}
    skipped: list = []
    if not isinstance(parsed, dict):
        return {"entries": entries, "skippedShellReferenceKeys": skipped}
    for raw_key, value in parsed.items():
        if not isinstance(value, str) or not value.strip():
            continue
        key = _normalize_env_var_key(raw_key)
        if not key or _is_blocked_service_env_var(key):
            continue
        if is_unresolved_shell_reference(value):
            skipped.append(key)
            continue
        entries[key] = value
    return {"entries": entries, "skippedShellReferenceKeys": skipped}


def read_state_dir_dot_env_from_state_dir(
    state_dir: str,
    *,
    read_file_fn: Optional[Callable] = None,
    parse_dot_env_fn: Optional[Callable] = None,
) -> dict:
    """Read and parse the state-dir ``.env``; return entries + skipped keys.

    Mirrors :func:`readStateDirDotEnvFromStateDir`
    (``shared/config/state-dir-dotenv.ts`).
    """
    if not isinstance(state_dir, str) or not state_dir or not callable(read_file_fn):
        return {"entries": {}, "skippedShellReferenceKeys": []}
    return parse_state_dir_dot_env_content(
        read_file_fn(state_dir),
        parse_dot_env_fn=parse_dot_env_fn,
    )


def collect_durable_service_env_var_sources(params: dict) -> dict:
    """Aggregate state-dir dotenv + config service env vars.

    Mirrors :func:`collectDurableServiceEnvVarSources`
    (``shared/config/state-dir-dotenv.ts`).
    """
    state_dir_env = read_state_dir_dot_env_from_state_dir(
        params.get("stateDir") or "",
        read_file_fn=params.get("read_file_fn"),
        parse_dot_env_fn=params.get("parse_dot_env_fn"),
    )["entries"]
    config_env = params.get("configServiceEnvVars") or {}
    if not isinstance(config_env, dict):
        config_env = {}
    return {
        "stateDirDotEnvEnvironment": state_dir_env,
        "configEnvironment": config_env,
        "durableEnvironment": {**state_dir_env, **config_env},
    }


def collect_durable_service_env_vars(params: dict) -> dict:
    """Flat durable env map (state-dir dotenv < config env)."""
    return collect_durable_service_env_var_sources(params).get("durableEnvironment") or {}


__all__ = [
    "MAX_STATE_DIR_DOTENV_BYTES",
    "ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV",
    "is_unresolved_shell_reference",
    "parse_state_dir_dot_env_content",
    "read_state_dir_dot_env_from_state_dir",
    "collect_durable_service_env_var_sources",
    "collect_durable_service_env_vars",
]
