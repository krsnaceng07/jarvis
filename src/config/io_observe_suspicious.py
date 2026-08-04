"""jarvis.config.io_observe_suspicious — config-snapshot suspicious-reasons resolver.

OpenClaw parity: mirrors
``openclaw-main/src/config/io.observe-suspicious.ts``.
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class ConfigObserveSuspiciousBaseline(TypedDict, total=False):
    bytes: int
    hasMeta: bool
    gatewayMode: str


def _is_update_channel_only_root(value) -> bool:
    if not isinstance(value, dict):
        return False
    keys = list(value.keys())
    if len(keys) != 1 or keys[0] != "update":
        return False
    update = value["update"]
    if not isinstance(update, dict):
        return False
    update_keys = list(update.keys())
    return len(update_keys) == 1 and isinstance(update.get("channel"), str)


def resolve_config_observe_suspicious_reasons(params: dict) -> list:
    """Build a list of suspicious-reason tags for a config snapshot.

    Mirrors :func:`resolveConfigObserveSuspiciousReasons`
    (``shared/config/io.observe-suspicious.ts`).
    """
    reasons: list = []
    baseline: Optional[dict] = params.get("lastKnownGood")
    if not baseline:
        return reasons
    try:
        bytes_now = int(params.get("bytes") or 0)
        has_meta = bool(params.get("hasMeta"))
        gateway_mode = params.get("gatewayMode")
        parsed = params.get("parsed")
        baseline_bytes = int(baseline.get("bytes") or 0)
    except (TypeError, ValueError):
        return reasons
    if baseline_bytes >= 512 and bytes_now < int(baseline_bytes * 0.5):
        reasons.append(f"size-drop-vs-last-good:{baseline_bytes}->{bytes_now}")
    if baseline.get("hasMeta") and not has_meta:
        reasons.append("missing-meta-vs-last-good")
    if baseline.get("gatewayMode") and not gateway_mode:
        reasons.append("gateway-mode-missing-vs-last-good")
    if baseline.get("gatewayMode") and _is_update_channel_only_root(parsed):
        reasons.append("update-channel-only-root")
    return reasons


__all__ = [
    "ConfigObserveSuspiciousBaseline",
    "resolve_config_observe_suspicious_reasons",
]
