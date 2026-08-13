"""jarvis.config.io_factory — config-IO factory facade.

OpenClaw parity: mirrors ``openclaw-main/src/config/io.factory.ts``.

Focused minimal port: thin facade. The full factory wires together
filesystem, JSON5, env-substitution, schema validation, and runtime
snapshot refresh — all delegated to caller-provided callables until
those subsystems land.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, cast

from src.config.io import create_config_io as _create_config_io


def create_config_io(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover
    """Build a configured ``ConfigIO`` instance for the active runtime.

    Mirrors :func:`createConfigIO`
    (``shared/config/io.factory.ts``).

    In the minimal port, this delegates to the concrete local ``ConfigIO``
    implementation so callers can exercise the stable read/write facade
    without requiring a full runtime installation.
    """
    if args or kwargs:
        _create_config_io_callable = cast(Callable[..., Any], _create_config_io)
        return _create_config_io_callable(*args, **kwargs)
    raise NotImplementedError("createConfigIO facade — install via runtime hooks")


def make_deps(
    *,
    fs: Any = None,
    json5: Any = None,
    env: dict[str, Any] | None = None,
    lower_precedence_env: dict[str, Any] | None = None,
    homedir_fn: Optional[Callable[[], str]] = None,
    config_path: Optional[str] = None,
    logger: Any = None,
    measure: Optional[Callable[..., Any]] = None,
    observe: bool = True,
) -> dict[str, Any]:
    """Build a config-IO deps dict with sensible defaults for the missing fields."""
    return {
        "fs": fs,
        "json5": json5,
        "env": env or {},
        "lowerPrecedenceEnv": lower_precedence_env or {},
        "homedir": homedir_fn,
        "configPath": config_path,
        "logger": logger,
        "measure": measure,
        "observe": observe,
    }


__all__ = [
    "create_config_io",
    "make_deps",
]
