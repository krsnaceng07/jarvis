"""jarvis.config.gateway_env_selection — gateway config selection env-var guard.

OpenClaw parity: mirrors
``openclaw-main/src/config/gateway-env-selection.ts``.
"""
from __future__ import annotations



#: Env keys the running gateway considers process-stable selectors.
GATEWAY_CONFIG_SELECTION_ENV_KEYS = frozenset({
    "ANDROID_DATA",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "OPENCLAW_AGENT_DIR",
    "OPENCLAW_CONFIG_PATH",
    "OPENCLAW_HOME",
    "OPENCLAW_INCLUDE_ROOTS",
    "OPENCLAW_NIX_MODE",
    "OPENCLAW_OAUTH_DIR",
    "OPENCLAW_PACKAGE_DIR",
    "OPENCLAW_PROFILE",
    "OPENCLAW_STATE_DIR",
    "OPENCLAW_TEST_FAST",
    "OPENCLAW_WORKSPACE_DIR",
    "PI_CODING_AGENT_DIR",
    "PREFIX",
    "USERPROFILE",
})


def _collect_runtime_env_vars(config: dict) -> dict:
    """Collect the env-var values from a config.

    Focused minimal stub: returns an empty mapping until
    ``collectConfigRuntimeEnvVars`` lands.
    """
    return {}


def _normalize(env_map) -> dict:
    out: dict = {}
    for k, v in (env_map or {}).items():
        if not isinstance(k, str):
            continue
        out[k.upper()] = v
    return out


def assert_gateway_config_env_selection_unchanged(
    previous_config: dict, next_config: dict
) -> None:
    """Reject config.env changes that would retarget a running Gateway process.

    Mirrors :func:`assertGatewayConfigEnvSelectionUnchanged`
    (``shared/config/gateway-env-selection.ts``).
    """
    previous = _normalize(_collect_runtime_env_vars(previous_config or {}))
    next_ = _normalize(_collect_runtime_env_vars(next_config or {}))
    for key in GATEWAY_CONFIG_SELECTION_ENV_KEYS:
        if previous.get(key) != next_.get(key):
            raise ValueError(
                f"Config env cannot change process-stable Gateway selector "
                f"{key} during reload. Restart with the target environment instead."
            )


__all__ = [
    "GATEWAY_CONFIG_SELECTION_ENV_KEYS",
    "assert_gateway_config_env_selection_unchanged",
]
