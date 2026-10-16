"""jarvis.plugins.logbook — Logbook automatic work journal plugin configuration & RPC method definitions.

OpenClaw parity: mirrors
``openclaw-main/extensions/logbook/src/config.ts`` and
``openclaw-main/extensions/logbook/index.ts``.

Features:
- `LOGBOOK_RPC_METHODS`: List of registered Gateway RPC methods.
- `LogbookConfig`: Clamped configuration dataclass.
- `resolve_logbook_config()`: Resolves and clamps Logbook options.
- `parse_model_ref()`: Splits `"provider/model"` string into `(provider, model)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LOGBOOK_RPC_METHODS: list[str] = [
    "logbook.status",
    "logbook.days",
    "logbook.timeline",
    "logbook.frames",
    "logbook.frame",
    "logbook.standup",
    "logbook.ask",
    "logbook.capture.set",
    "logbook.analyze.now",
]


@dataclass
class LogbookConfig:
    captureEnabled: bool = True
    captureIntervalSeconds: int = 30
    analysisIntervalMinutes: int = 15
    nodeId: str | None = None
    screenIndex: int = 0
    maxWidth: int = 1440
    visionModel: str | None = None
    retentionDays: int = 14


def _clamp_number(value: Any, fallback: int, min_val: int, max_val: int) -> int:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        num = round(value)
        return max(min_val, min(max_val, num))
    return fallback


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        if len(trimmed) > 0:
            return trimmed
    return None


def resolve_logbook_config(raw: dict[str, Any] | None) -> LogbookConfig:
    """Resolve and clamp Logbook plugin options from configuration dictionary."""
    val = raw if isinstance(raw, dict) else {}

    capture_enabled = val.get("captureEnabled")
    is_capture_enabled = True if capture_enabled is None else bool(capture_enabled)

    return LogbookConfig(
        captureEnabled=is_capture_enabled,
        captureIntervalSeconds=_clamp_number(val.get("captureIntervalSeconds"), 30, 5, 600),
        analysisIntervalMinutes=_clamp_number(val.get("analysisIntervalMinutes"), 15, 3, 120),
        nodeId=_optional_string(val.get("nodeId")),
        screenIndex=_clamp_number(val.get("screenIndex"), 0, 0, 16),
        maxWidth=_clamp_number(val.get("maxWidth"), 1440, 480, 3840),
        visionModel=_optional_string(val.get("visionModel")),
        retentionDays=_clamp_number(val.get("retentionDays"), 14, 1, 365),
    )


def parse_model_ref(ref: str) -> tuple[str, str] | None:
    """Split a 'provider/model' reference string into (provider, model)."""
    if not ref or "/" not in ref:
        return None
    slash = ref.find("/")
    if slash <= 0 or slash == len(ref) - 1:
        return None
    return ref[:slash], ref[slash + 1 :]


__all__ = [
    "LOGBOOK_RPC_METHODS",
    "LogbookConfig",
    "parse_model_ref",
    "resolve_logbook_config",
]
