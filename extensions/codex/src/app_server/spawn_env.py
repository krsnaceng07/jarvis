"""OpenClaw-aligned environment isolation for local Codex app-server starts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from extensions.codex.src.app_server.config import CodexAppServerRuntimeOptions

CODEX_HOME_ENV_VAR = "CODEX_HOME"
HOME_ENV_VAR = "HOME"
CODEX_AUTH_ENV_VARS = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY", "CODEX_ACCESS_TOKEN"})
UNSAFE_ENVIRONMENT_KEYS = frozenset({"__proto__", "constructor", "prototype"})


def resolve_codex_app_server_home_dir(
    options: CodexAppServerRuntimeOptions,
    agent_dir: str,
    base_env: Mapping[str, str] | None = None,
) -> str:
    """Resolve the scoped CODEX_HOME without changing the operator's HOME."""
    env = base_env or os.environ
    if options.home_scope == "user":
        configured = env.get(CODEX_HOME_ENV_VAR, "").strip()
        if configured:
            return configured
        return str(Path.home() / ".codex")
    return str(Path(agent_dir).resolve() / "codex-home")


def resolve_codex_app_server_spawn_env(
    options: CodexAppServerRuntimeOptions,
    *,
    agent_dir: str,
    base_env: Mapping[str, str] | None = None,
    prepared_auth: bool = False,
) -> dict[str, str]:
    """Build the child environment with Codex-home and auth isolation applied."""
    source = base_env or os.environ
    env = {
        key: value
        for key, value in source.items()
        if key not in UNSAFE_ENVIRONMENT_KEYS and isinstance(value, str)
    }
    env[CODEX_HOME_ENV_VAR] = resolve_codex_app_server_home_dir(
        options,
        agent_dir,
        source,
    )
    keys_to_clear = {key.strip() for key in options.clear_env if key.strip()}
    if prepared_auth:
        keys_to_clear.update(CODEX_AUTH_ENV_VARS)
    for key in list(env):
        if key in keys_to_clear:
            del env[key]
    for key in list(env):
        upper_key = key.upper()
        if upper_key in {"NODE_PATH", "LD_AUDIT", "LD_LIBRARY_PATH", "LD_PRELOAD"}:
            del env[key]
        elif upper_key.startswith("DYLD_"):
            del env[key]
    env[CODEX_HOME_ENV_VAR] = resolve_codex_app_server_home_dir(
        options,
        agent_dir,
        source,
    )
    return env


__all__ = [
    "CODEX_AUTH_ENV_VARS",
    "CODEX_HOME_ENV_VAR",
    "resolve_codex_app_server_home_dir",
    "resolve_codex_app_server_spawn_env",
]
