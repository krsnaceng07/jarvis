"""jarvis.config.env_vars — public facade for config env var collection.

OpenClaw parity: mirrors ``openclaw-main/src/config/env-vars.ts``.
"""
from __future__ import annotations

# The OpenClaw source re-exports the four functions from
# config-env-vars.ts. The Python port delegates to a focused minimal
# re-export shape; the underlying impl lands as the env-vars port.
from .env_substitution import (
    MissingEnvVarError,
    contains_env_var_reference,
    resolve_config_env_vars,
)

__all__ = [
    "MissingEnvVarError",
    "contains_env_var_reference",
    "resolve_config_env_vars",
]


def clone_env_with_platform_semantics(env: dict) -> dict:
    """Return a copy of ``env`` with platform-specific case semantics.

    Focused minimal stub: the full OpenClaw implementation applies Windows
    case-insensitive process.env semantics; on POSIX this is a no-op.
    """
    return dict(env)


def collect_config_runtime_env_vars(env: dict, config: dict) -> list:
    """Return the env vars requested by the runtime config surface.

    Focused minimal stub: returns an empty list until the runtime env
    surface lands.
    """
    return []


def create_config_runtime_env(env: dict, config: dict) -> dict:
    """Build a runtime env mapping with config-driven vars applied.

    Focused minimal stub: returns the env unchanged.
    """
    return dict(env)


def is_config_runtime_env_var_allowed(name: str) -> bool:
    """Return whether ``name`` is in the runtime env allowlist.

    Focused minimal stub: allow everything until the allowlist lands.
    """
    return bool(name)
