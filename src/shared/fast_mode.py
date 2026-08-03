"""jarvis.shared.fast_mode — fast-mode config + status helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/fast-mode.ts``.

Public surface:

- :data:`FastModeSource`
- :data:`FastModeAutoProgressState`
- :data:`DEFAULT_FAST_MODE_AUTO_ON_SECONDS`
- :func:`resolve_fast_mode_model_params`
- :func:`resolve_fast_mode_model_auto_on_seconds`
- :func:`resolve_fast_mode_for_elapsed`
- :func:`format_fast_mode_auto_progress_text`
- :func:`format_fast_mode_value`
- :func:`format_fast_mode_auto_label`
- :func:`format_fast_mode_status_value`
- :func:`format_fast_mode_command_options`
- :func:`format_fast_mode_source_suffix`
- :func:`format_fast_mode_current_status`
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Union


#: Default auto-on duration in seconds when no override is configured.
DEFAULT_FAST_MODE_AUTO_ON_SECONDS = 60

#: FastMode is one of: True, False, "auto".
FastMode = Union[bool, str]


FastModeSource = str  # "session" | "agent" | "config" | "default"


class FastModeAutoProgressState:
    """Per-session auto-mode progress state."""

    def __init__(self, off_announced: bool = False, reset_announced: bool = False) -> None:
        self.off_announced = off_announced
        self.reset_announced = reset_announced

    def to_dict(self) -> Dict[str, bool]:
        return {
            "offAnnounced": self.off_announced,
            "resetAnnounced": self.reset_announced,
        }


def _normalize_lower(value: Any) -> str:
    if isinstance(value, str):
        return value.strip().lower()
    return ""


def _model_config_key(provider: Optional[str], model: Optional[str]) -> str:
    provider_id = (provider or "").strip()
    model_id = (model or "").strip()
    if not provider_id:
        return model_id
    if not model_id:
        return provider_id
    if _normalize_lower(model_id).startswith(_normalize_lower(provider_id) + "/"):
        return model_id
    return f"{provider_id}/{model_id}"


def _model_config_keys(provider: Optional[str], model: Optional[str]) -> list:
    key = _model_config_key(provider, model)
    provider_id = _normalize_lower((provider or "").strip())
    if provider_id != "openai-codex":
        return [key]
    openai_key = _model_config_key("openai", model)
    return [key] if openai_key == key else [key, openai_key]


def resolve_fast_mode_model_params(params: dict) -> Optional[Dict[str, Any]]:
    """Return the fast-mode `params` block for a given provider/model from cfg.

    Mirrors :func:`resolveFastModeModelParams` (``shared/fast-mode.ts``).
    """
    cfg = params.get("cfg")
    if not isinstance(cfg, dict):
        return None
    models = (((cfg.get("agents") or {}).get("defaults") or {}).get("models") or {})
    if not isinstance(models, dict):
        return None
    for key in _model_config_keys(params.get("provider"), params.get("model")):
        model_config = models.get(key)
        if isinstance(model_config, dict) and model_config.get("params"):
            return model_config["params"]
    return None


def _normalize_fast_auto_on_seconds(value: Any) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def resolve_fast_mode_model_auto_on_seconds(params: dict) -> int:
    """Resolve the auto-on seconds for a given provider/model from cfg.

    Mirrors :func:`resolveFastModeModelAutoOnSeconds` (``shared/fast-mode.ts``).
    """
    model_params = resolve_fast_mode_model_params(params) or {}
    return (
        _normalize_fast_auto_on_seconds(model_params.get("fastAutoOnSeconds"))
        or _normalize_fast_auto_on_seconds(model_params.get("fast_auto_on_seconds"))
        or _normalize_fast_auto_on_seconds(model_params.get("fastSeconds"))
        or _normalize_fast_auto_on_seconds(model_params.get("fast_seconds"))
        or DEFAULT_FAST_MODE_AUTO_ON_SECONDS
    )


def resolve_fast_mode_for_elapsed(params: dict) -> Dict[str, Any]:
    """Resolve the current effective fast-mode for a given elapsed time.

    Mirrors :func:`resolveFastModeForElapsed` (``shared/fast-mode.ts``).
    """
    now_ms = params.get("nowMs")
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    elapsed_ms = max(0, int(now_ms) - int(params.get("startedAtMs") or 0))
    threshold_s = _normalize_fast_auto_on_seconds(params.get("fastAutoOnSeconds")) or DEFAULT_FAST_MODE_AUTO_ON_SECONDS
    threshold_ms = threshold_s * 1000
    mode = params.get("mode")
    enabled = (mode == "auto" and elapsed_ms <= threshold_ms) or mode is True
    return {
        "mode": mode,
        "enabled": bool(enabled),
        "elapsedSeconds": int(elapsed_ms // 1000),
        "fastAutoOnSeconds": threshold_s,
    }


def format_fast_mode_auto_progress_text(params: dict) -> str:
    """Format the human-facing fast-mode progress text.

    Mirrors :func:`formatFastModeAutoProgressText` (``shared/fast-mode.ts``).
    """
    if params.get("enabled"):
        return "💨Fast: auto-on"
    threshold = (
        _normalize_fast_auto_on_seconds(params.get("fastAutoOnSeconds"))
        or DEFAULT_FAST_MODE_AUTO_ON_SECONDS
    )
    return f"💨Fast: auto-off({params.get('elapsedSeconds', 0)}s>={threshold}s)"


def format_fast_mode_value(mode: Any) -> str:
    """Format a fast-mode value as one of ``"auto" | "on" | "off"``.

    Mirrors :func:`formatFastModeValue` (``shared/fast-mode.ts``).
    """
    if mode == "auto":
        return "auto"
    if mode is True:
        return "on"
    return "off"


def format_fast_mode_auto_label(params: Optional[dict] = None) -> str:
    threshold = (
        _normalize_fast_auto_on_seconds((params or {}).get("fastAutoOnSeconds"))
        or DEFAULT_FAST_MODE_AUTO_ON_SECONDS
    )
    return f"auto ({threshold} sec)"


def format_fast_mode_status_value(params: dict) -> str:
    if params.get("mode") == "auto":
        return format_fast_mode_auto_label({"fastAutoOnSeconds": params.get("fastAutoOnSeconds")})
    return format_fast_mode_value(params.get("mode"))


def format_fast_mode_command_options(params: Optional[dict] = None) -> str:
    return f"on, off, {format_fast_mode_auto_label(params)}, default, status"


def format_fast_mode_source_suffix(source: Optional[str]) -> str:
    if source == "session":
        return " (session)"
    if source == "agent":
        return " (default: agent)"
    if source == "config":
        return " (default: model)"
    if source == "default":
        return " (default)"
    return ""


def format_fast_mode_current_status(params: dict) -> str:
    label = params.get("label") or "Current fast mode"
    return (
        f"{label}: {format_fast_mode_status_value(params)}"
        f"{format_fast_mode_source_suffix(params.get('source'))}."
    )


__all__ = [
    "FastMode",
    "FastModeSource",
    "FastModeAutoProgressState",
    "DEFAULT_FAST_MODE_AUTO_ON_SECONDS",
    "resolve_fast_mode_model_params",
    "resolve_fast_mode_model_auto_on_seconds",
    "resolve_fast_mode_for_elapsed",
    "format_fast_mode_auto_progress_text",
    "format_fast_mode_value",
    "format_fast_mode_auto_label",
    "format_fast_mode_status_value",
    "format_fast_mode_command_options",
    "format_fast_mode_source_suffix",
    "format_fast_mode_current_status",
]
