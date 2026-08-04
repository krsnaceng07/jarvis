"""jarvis.config.zod_schema_gateway — gateway config Zod schema fragments.

OpenClaw parity: mirrors ``openclaw-main/src/config/zod-schema.gateway.ts``.

Focused minimal port: thin facade. The full zod schema lands with the
schema validator port; until then the public surface exposes only the
non-zod helpers (channelHealthCheckMinutes cross-check).
"""
from __future__ import annotations

from typing import Any, Optional


#: Gateway config schema (zod facade).
GatewayConfigSchema: Any = None  # z.strictObject({...}).superRefine(...).optional()


def validate_gateway_health_check_thresholds(value: Any, issues: Optional[list] = None) -> Optional[list]:
    """Validate that ``channelStaleEventThresholdMinutes >= channelHealthCheckMinutes``.

    Mirrors the ``.superRefine`` block in the upstream zod schema.

    Returns a list of issue dicts on failure.
    """
    if not isinstance(value, dict):
        return issues
    out: list = issues if issues is not None else []
    effective_health = value.get("channelHealthCheckMinutes")
    if effective_health is None:
        effective_health = 5
    stale = value.get("channelStaleEventThresholdMinutes")
    if (
        stale is not None
        and effective_health != 0
        and isinstance(stale, (int, float))
        and isinstance(effective_health, (int, float))
        and stale < effective_health
    ):
        out.append({
            "path": ["channelStaleEventThresholdMinutes"],
            "message": (
                "channelStaleEventThresholdMinutes should be >= "
                "channelHealthCheckMinutes to avoid delayed stale detection"
            ),
        })
    return out or None


__all__ = [
    "GatewayConfigSchema",
    "validate_gateway_health_check_thresholds",
]
