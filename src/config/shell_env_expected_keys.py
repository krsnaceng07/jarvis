"""jarvis.config.shell_env_expected_keys — login-shell env key list builder.

OpenClaw parity: mirrors
``openclaw-main/src/config/shell-env-expected-keys.ts``.

Focused minimal port: the core shell-env keys are constant; the provider/
channel env-var lookups are delegated to caller-provided callables.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional, Set


#: Core shell env keys always expected for OpenClaw config loading.
CORE_SHELL_ENV_EXPECTED_KEYS: list = [
    "OPENCLAW_GATEWAY_TOKEN",
    "OPENCLAW_GATEWAY_PASSWORD",
]


def _unique_strings(values: Iterable[str]) -> list:
    seen: Set[str] = set()
    out: list = []
    for v in values:
        if not isinstance(v, str):
            continue
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def resolve_shell_env_expected_keys(
    env: Optional[dict] = None,
    *,
    list_known_provider_auth_env_var_names: Optional[Callable] = None,
    list_known_channel_env_var_names: Optional[Callable] = None,
) -> list:
    """List env vars worth importing from login-shell fallback for this config load.

    Mirrors :func:`resolveShellEnvExpectedKeys`
    (``shared/config/shell-env-expected-keys.ts`).
    """
    provider_keys: list = []
    channel_keys: list = []
    if callable(list_known_provider_auth_env_var_names):
        provider_keys = list(list_known_provider_auth_env_var_names({"env": env}) or [])
    if callable(list_known_channel_env_var_names):
        channel_keys = list(list_known_channel_env_var_names({"env": env}) or [])
    return _unique_strings([
        *provider_keys,
        *channel_keys,
        *CORE_SHELL_ENV_EXPECTED_KEYS,
    ])


__all__ = [
    "CORE_SHELL_ENV_EXPECTED_KEYS",
    "resolve_shell_env_expected_keys",
]
