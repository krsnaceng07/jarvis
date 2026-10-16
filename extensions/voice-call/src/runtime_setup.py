"""Runtime setup entry point for Voice Call."""

from __future__ import annotations

from typing import Any

from .config import VoiceCallConfig, resolve_voice_call_config
from .setup import VoiceCallSetupStatus, get_voice_call_setup_status


def validate_voice_call_runtime_setup(
    raw_config: dict[str, Any] | None = None,
    full_config: Any = None,
) -> VoiceCallSetupStatus:
    """Validate runtime readiness from raw config dictionary."""
    res = resolve_voice_call_config(raw_config)
    config = res.unwrap() if res.is_ok else VoiceCallConfig()
    return get_voice_call_setup_status(config, full_config=full_config)
