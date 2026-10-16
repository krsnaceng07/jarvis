"""Logbook plugin config resolution.

Mirrors OpenClaw's ``extensions/logbook/src/config.ts``.

Clamps operator input into safe runtime bounds and parses
``"provider/model"`` refs for the optional vision model
override.

Public surface (mirrors the TS source):
- ``LogbookConfig`` TypedDict
- ``resolve_logbook_config(raw)`` — clamp + default
- ``parse_model_ref(ref)`` — split ``"provider/model"`` ref
"""

from __future__ import annotations

from typing import Any, TypedDict


# ── Defaults + clamps ─────────────────────────────────────


_LOGBOOK_DEFAULTS: dict[str, Any] = {
    "captureEnabled": True,
    "captureIntervalSeconds": 30,
    "analysisIntervalMinutes": 15,
    "screenIndex": 0,
    "maxWidth": 1440,
    "retentionDays": 14,
}


def _clamp_number(value: Any, fallback: int, min_v: int, max_v: int) -> int:
    """Round-and-clamp ``value`` to ``[min_v, max_v]``.

    Mirrors the private ``clampNumber`` helper.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return fallback
    if value != value:  # NaN check
        return fallback
    try:
        num = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    if num < min_v:
        return min_v
    if num > max_v:
        return max_v
    return num


def _optional_string(value: Any) -> str | None:
    """Trim a string value, returning ``None`` for empty/non-string.

    Mirrors the private ``optionalString`` helper.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


# ── Public surface ──────────────────────────────────────────


class LogbookConfig(TypedDict, total=False):
    captureEnabled: bool
    captureIntervalSeconds: int
    analysisIntervalMinutes: int
    nodeId: str
    screenIndex: int
    maxWidth: int
    visionModel: str
    retentionDays: int


def resolve_logbook_config(raw: Any) -> LogbookConfig:
    """Resolve the Logbook plugin config from raw host config.

    Mirrors ``resolveLogbookConfig``. Clamps each numeric
    field to its documented safe range; missing fields
    fall back to the OpenClaw defaults.
    """
    value: dict[str, Any] = raw if isinstance(raw, dict) else {}
    return {
        "captureEnabled": value.get("captureEnabled") is not False,
        "captureIntervalSeconds": _clamp_number(
            value.get("captureIntervalSeconds"),
            _LOGBOOK_DEFAULTS["captureIntervalSeconds"],
            5,
            600,
        ),
        "analysisIntervalMinutes": _clamp_number(
            value.get("analysisIntervalMinutes"),
            _LOGBOOK_DEFAULTS["analysisIntervalMinutes"],
            3,
            120,
        ),
        "screenIndex": _clamp_number(
            value.get("screenIndex"),
            _LOGBOOK_DEFAULTS["screenIndex"],
            0,
            16,
        ),
        "maxWidth": _clamp_number(
            value.get("maxWidth"),
            _LOGBOOK_DEFAULTS["maxWidth"],
            480,
            3840,
        ),
        "retentionDays": _clamp_number(
            value.get("retentionDays"),
            _LOGBOOK_DEFAULTS["retentionDays"],
            1,
            365,
        ),
        **({"nodeId": node_id} if (node_id := _optional_string(value.get("nodeId"))) else {}),
        **(
            {"visionModel": vision}
            if (vision := _optional_string(value.get("visionModel")))
            else {}
        ),
    }


def parse_model_ref(ref: str) -> dict[str, str] | None:
    """Split a ``"provider/model"`` ref into ``{provider, model}``.

    Mirrors ``parseModelRef``. Model ids may themselves
    contain slashes, so the split is on the FIRST slash.
    Returns ``None`` when the ref is missing the slash or
    the slash is at the boundary.
    """
    if not isinstance(ref, str):
        return None
    slash = ref.find("/")
    if slash <= 0 or slash == len(ref) - 1:
        return None
    return {"provider": ref[:slash], "model": ref[slash + 1 :]}


__all__ = [
    "LogbookConfig",
    "parse_model_ref",
    "resolve_logbook_config",
]
