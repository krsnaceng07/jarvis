"""jarvis.config.gateway_dispatch_config — gateway dispatch config projection.

OpenClaw parity: mirrors
``openclaw-main/src/config/gateway-dispatch-config.ts``.

Focused minimal port: the public surface reads a config file, applies
the dispatch top-level projection, resolves env-substitution, and
returns the projected config. Includes/env parsing and the SQLite
shell-env fallback wiring land as the corresponding ports land.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional


#: Top-level keys kept in the gateway dispatch projection.
GATEWAY_DISPATCH_TOP_LEVEL_KEYS = (
    "agents",
    "env",
    "gateway",
    "plugins",
    "secrets",
    "session",
)

#: Env keys that the shell-env fallback is expected to surface.
GATEWAY_DISPATCH_SHELL_ENV_EXPECTED_KEYS = (
    "OPENCLAW_GATEWAY_TOKEN",
    "OPENCLAW_GATEWAY_PASSWORD",
)


def _is_plain_record(value) -> bool:
    return bool(value) and isinstance(value, dict) and not isinstance(value, (list, tuple, str, bytes))


def _clone(value) -> Any:
    if isinstance(value, list):
        return [_clone(v) for v in value]
    if not _is_plain_record(value):
        return value
    return {k: _clone(v) for k, v in value.items()}


def project_gateway_dispatch_config(value: Any) -> dict:
    """Project ``value`` down to the dispatch top-level key set.

    Mirrors :func:`projectGatewayDispatchConfig`
    (``shared/config/gateway-dispatch-config.ts``).
    """
    if not _is_plain_record(value):
        return {}
    projected: dict = {}
    for key in GATEWAY_DISPATCH_TOP_LEVEL_KEYS:
        if key in value:
            projected[key] = _clone(value[key])
    return projected


def apply_gateway_dispatch_session_defaults(config: dict) -> dict:
    """Pin ``session.mainKey`` to ``"main"`` for the dispatch surface."""
    if not isinstance(config, dict):
        return config
    session = config.get("session")
    if not isinstance(session, dict) or session.get("mainKey") is None:
        return config
    new_session = dict(session)
    new_session["mainKey"] = "main"
    new_config = dict(config)
    new_config["session"] = new_session
    return new_config


def _apply_env_substitution(config: Any, env: dict) -> Any:
    from .env_substitution import resolve_config_env_vars
    return resolve_config_env_vars(config, env, on_missing=lambda w: None)


def _read_raw_gateway_dispatch_config(
    *,
    config_path: Optional[str] = None,
    env: Optional[dict] = None,
    read_file: Optional[Any] = None,
    parse_json: Optional[Any] = None,
    resolve_includes: Optional[Any] = None,
    resolve_config_path: Optional[Any] = None,
) -> dict:
    env = env if env is not None else dict(os.environ)
    config_path = config_path or (resolve_config_path(env) if callable(resolve_config_path) else None)
    if not config_path or not os.path.isfile(config_path):
        return {"config": {}, "configPath": config_path}
    raw = (read_file or (lambda p: open(p, "r", encoding="utf-8").read()))(config_path)
    parsed = (parse_json or json.loads)(raw)
    if callable(resolve_includes):
        parsed = resolve_includes(parsed, config_path, env)
    resolved = _apply_env_substitution(parsed, env)
    return {
        "config": apply_gateway_dispatch_session_defaults(
            project_gateway_dispatch_config(resolved)
        ),
        "configPath": config_path,
    }


def read_gateway_dispatch_config(
    *,
    config_path: Optional[str] = None,
    env: Optional[dict] = None,
    read_file: Optional[Any] = None,
    parse_json: Optional[Any] = None,
    resolve_includes: Optional[Any] = None,
    resolve_config_path: Optional[Any] = None,
) -> dict:
    """Read the projected gateway dispatch config.

    Mirrors :func:`readGatewayDispatchConfig`
    (``shared/config/gateway-dispatch-config.ts``).
    """
    return _read_raw_gateway_dispatch_config(
        config_path=config_path,
        env=env,
        read_file=read_file,
        parse_json=parse_json,
        resolve_includes=resolve_includes,
        resolve_config_path=resolve_config_path,
    )["config"]


__all__ = [
    "GATEWAY_DISPATCH_TOP_LEVEL_KEYS",
    "GATEWAY_DISPATCH_SHELL_ENV_EXPECTED_KEYS",
    "project_gateway_dispatch_config",
    "apply_gateway_dispatch_session_defaults",
    "read_gateway_dispatch_config",
]
