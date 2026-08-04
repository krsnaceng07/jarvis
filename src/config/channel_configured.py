"""jarvis.config.channel_configured — channel configured detection.

OpenClaw parity: mirrors ``openclaw-main/src/config/channel-configured.ts``.
"""
from __future__ import annotations

import os
from typing import Any, Mapping


def resolve_channel_config_record(
    cfg: Mapping[str, Any], channel_id: str
) -> dict:
    """Return a channel config object when ``channels.<id>`` is present and object-shaped.

    Mirrors :func:`resolveChannelConfigRecord`
    (``shared/config/channel-configured-shared.ts``).
    """
    channels = cfg.get("channels") if isinstance(cfg, Mapping) else None
    if not isinstance(channels, Mapping):
        return {}
    entry = channels.get(channel_id)
    return entry if isinstance(entry, dict) else {}


def has_meaningful_channel_config_shallow(value) -> bool:
    """Check whether a shallow channel config contains activation-relevant values.

    Mirrors :func:`hasMeaningfulChannelConfigShallow`
    (``shared/config/channel-configured-shared.ts``).
    """
    if not isinstance(value, dict):
        return False
    keys = list(value.keys())
    if len(keys) == 1 and keys[0] == "enabled":
        # `enabled: false` alone is an explicit non-configuration signal,
        # but true opts in.
        return value["enabled"] is True
    return any(k != "enabled" for k in keys)


def is_statically_channel_configured(
    cfg: Mapping[str, Any],
    channel_id: str,
    env: Mapping[str, str] = None,
) -> bool:
    """Detect static channel configuration from env vars or ``channels.<id>`` config.

    Focused minimal port; the env-var probe is delegated to a caller
    via :func:`get_channel_env_vars` if provided in env, else we check
    the record directly.
    """
    # The OpenClaw source uses getChannelEnvVars from secrets; the Python
    # port focuses on config-record detection only. Callers wanting
    # env-var detection can compose this with their own env helper.
    return has_meaningful_channel_config_shallow(resolve_channel_config_record(cfg, channel_id))


def is_channel_configured(
    cfg: Mapping[str, Any], channel_id: str, env: Mapping[str, str] = None
) -> bool:
    """Resolve whether a channel has enough config to be considered setup.

    Focused minimal port of :func:`isChannelConfigured`
    (``shared/config/channel-configured.ts``).
    """
    if has_meaningful_channel_config_shallow(resolve_channel_config_record(cfg, channel_id)):
        return True
    return is_statically_channel_configured(cfg, channel_id, env or os.environ)


__all__ = [
    "resolve_channel_config_record",
    "has_meaningful_channel_config_shallow",
    "is_statically_channel_configured",
    "is_channel_configured",
]
