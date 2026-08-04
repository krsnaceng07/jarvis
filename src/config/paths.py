"""jarvis.config.paths — OpenClaw filesystem path resolution.

OpenClaw parity: mirrors ``openclaw-main/src/config/paths.ts``.

Focused minimal port: state-dir + config-path resolvers. Real
filesystem lookups (xdg, ~/.openclaw) are delegated to caller-
provided callables so the port stays importable without side effects.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional


#: Default OpenClaw state directory.
DEFAULT_STATE_DIR = "~/.openclaw"
#: Default OpenClaw config file path.
DEFAULT_CONFIG_PATH = "~/.openclaw/openclaw.json"


def _normalize_env(env: Any) -> dict:
    if env is None:
        return dict(os.environ)
    if isinstance(env, dict):
        return env
    return dict(env or {})


def resolve_state_dir(
    env: Any = None,
    *,
    homedir_fn: Optional[Callable[[], str]] = None,
) -> str:
    """Resolve the OpenClaw state directory from the given env.

    Mirrors :func:`resolveStateDir`
    (``shared/config/paths.ts`).
    """
    e = _normalize_env(env)
    explicit = e.get("OPENCLAW_STATE_DIR")
    if isinstance(explicit, str) and explicit.strip():
        return os.path.expanduser(explicit)
    if callable(homedir_fn):
        home = homedir_fn()
    else:
        home = os.path.expanduser("~")
    if not home:
        home = "."
    return os.path.join(home, ".openclaw")


def resolve_config_path(
    env: Any = None,
    *,
    homedir_fn: Optional[Callable[[], str]] = None,
) -> str:
    """Resolve the OpenClaw config file path from the given env.

    Mirrors :func:`resolveConfigPath`
    (``shared/config/paths.ts`).
    """
    e = _normalize_env(env)
    explicit = e.get("OPENCLAW_CONFIG_PATH")
    if isinstance(explicit, str) and explicit.strip():
        return os.path.expanduser(explicit)
    return os.path.join(resolve_state_dir(env, homedir_fn=homedir_fn), "openclaw.json")


def resolve_workspace_dir(
    env: Any = None,
    *,
    homedir_fn: Optional[Callable[[], str]] = None,
) -> str:
    """Resolve the default OpenClaw workspace directory from the given env."""
    e = _normalize_env(env)
    explicit = e.get("OPENCLAW_WORKSPACE_DIR")
    if isinstance(explicit, str) and explicit.strip():
        return os.path.expanduser(explicit)
    if callable(homedir_fn):
        home = homedir_fn()
    else:
        home = os.path.expanduser("~")
    if not home:
        home = "."
    return os.path.join(home, ".openclaw", "workspace")


__all__ = [
    "DEFAULT_STATE_DIR",
    "DEFAULT_CONFIG_PATH",
    "resolve_state_dir",
    "resolve_config_path",
    "resolve_workspace_dir",
]
