"""Channel model override resolver — mirrors OpenClaw ``src/channels/model-overrides.ts``."""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger("jarvis.channels.model_overrides")


def resolve_channel_model(channel_id: str, config: dict[str, Any] | None) -> str | None:
    """Resolve per-channel model override from config.

    Checks:
      1. config["channels"][channel_id]["model"]
      2. config["channels"][channel_id]["model_override"]
    """
    if not config or not isinstance(config, dict):
        return None

    channels_cfg = config.get("channels")
    if not isinstance(channels_cfg, dict):
        return None

    ch_cfg = channels_cfg.get(channel_id)
    if not isinstance(ch_cfg, dict):
        return None

    model = ch_cfg.get("model") or ch_cfg.get("model_override")
    if model and isinstance(model, str):
        _log.debug("Resolved channel %s model override: %s", channel_id, model)
        return model.strip()

    return None


__all__ = ["resolve_channel_model"]
