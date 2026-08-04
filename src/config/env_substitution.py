"""jarvis.config.env_substitution — ``${VAR}`` substitution for config values.

OpenClaw parity: mirrors
``openclaw-main/src/config/env-substitution.ts``.
"""
from __future__ import annotations

import os
import re
from typing import Any, Callable, Optional, TypedDict


#: Pattern for valid uppercase env var names.
_ENV_VAR_NAME_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class MissingEnvVarError(Exception):
    """Error thrown when a config value references a missing env var."""

    def __init__(self, var_name: str, config_path: str) -> None:
        self.var_name = var_name
        self.config_path = config_path
        super().__init__(
            f'Missing env var "{var_name}" referenced at config path: {config_path}'
        )
        self.name = "MissingEnvVarError"


class EnvSubstitutionWarning(TypedDict):
    varName: str
    configPath: str


def _is_plain_object(value) -> bool:
    return isinstance(value, dict) and not isinstance(value, (list, tuple, str, bytes))


def _parse_env_token_at(value: str, index: int):
    """Return ``(kind, name, end)`` for an env token starting at ``index``, else ``None``."""
    if value[index] != "$":
        return None
    nxt = value[index + 1] if index + 1 < len(value) else ""
    after_nxt = value[index + 2] if index + 2 < len(value) else ""
    # Escaped: $${VAR} -> ${VAR}
    if nxt == "$" and after_nxt == "{":
        start = index + 3
        end = value.find("}", start)
        if end != -1:
            name = value[start:end]
            if _ENV_VAR_NAME_PATTERN.match(name):
                return ("escaped", name, end)
    # Substitution: ${VAR} -> value
    if nxt == "{":
        start = index + 2
        end = value.find("}", start)
        if end != -1:
            name = value[start:end]
            if _ENV_VAR_NAME_PATTERN.match(name):
                return ("substitution", name, end)
    return None


def contains_env_var_reference(value: str) -> bool:
    """Return whether ``value`` has any unescaped ``${VAR}`` references.

    Mirrors :func:`containsEnvVarReference`
    (``shared/config/env-substitution.ts``).
    """
    if not isinstance(value, str) or "$" not in value:
        return False
    i = 0
    while i < len(value):
        if value[i] != "$":
            i += 1
            continue
        token = _parse_env_token_at(value, i)
        if token is None:
            i += 1
            continue
        kind, _, end = token
        if kind == "escaped":
            i = end + 1
            continue
        if kind == "substitution":
            return True
        i += 1
    return False


def _substitute_string(
    value: str,
    env: dict,
    config_path: str,
    on_missing: Optional[Callable[[EnvSubstitutionWarning], None]] = None,
) -> str:
    if "$" not in value:
        return value
    chunks: list = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch != "$":
            chunks.append(ch)
            i += 1
            continue
        token = _parse_env_token_at(value, i)
        if token is None:
            chunks.append(ch)
            i += 1
            continue
        kind, name, end = token
        if kind == "escaped":
            chunks.append(f"${{{name}}}")
            i = end + 1
            continue
        env_value = env.get(name)
        if env_value is None or env_value == "":
            if on_missing is not None:
                on_missing({"varName": name, "configPath": config_path})
                chunks.append(f"${{{name}}}")
                i = end + 1
                continue
            raise MissingEnvVarError(name, config_path)
        chunks.append(env_value)
        i = end + 1
    return "".join(chunks)


def _substitute_any(
    value: Any,
    env: dict,
    path: str,
    on_missing: Optional[Callable[[EnvSubstitutionWarning], None]] = None,
) -> Any:
    if isinstance(value, str):
        return _substitute_string(value, env, path, on_missing)
    if isinstance(value, list):
        return [
            _substitute_any(item, env, f"{path}[{i}]", on_missing)
            for i, item in enumerate(value)
        ]
    if _is_plain_object(value):
        out: dict = {}
        for k, v in value.items():
            child = f"{path}.{k}" if path else k
            out[k] = _substitute_any(v, env, child, on_missing)
        return out
    return value


def resolve_config_env_vars(
    obj: Any,
    env: Optional[dict] = None,
    on_missing: Optional[Callable[[EnvSubstitutionWarning], None]] = None,
) -> Any:
    """Resolve ``${VAR_NAME}`` references in ``obj``.

    Mirrors :func:`resolveConfigEnvVars`
    (``shared/config/env-substitution.ts``).
    """
    return _substitute_any(obj, env if env is not None else dict(os.environ), "", on_missing)


__all__ = [
    "MissingEnvVarError",
    "EnvSubstitutionWarning",
    "contains_env_var_reference",
    "resolve_config_env_vars",
]
