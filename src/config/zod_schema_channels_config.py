"""jarvis.config.zod_schema_channels_config — channel config Zod schema fragments.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.channels-config.ts``.
"""
from __future__ import annotations

from typing import Any, List


#: Per-channel bot loop protection schema.
ChannelBotLoopProtectionSchema: Any = None  # z.object({...}).strict()

#: Top-level channels config schema.
ChannelsSchema: Any = None  # z.object({...}).passthrough().superRefine(...).optional()


def add_legacy_channel_acp_binding_issues(
    value: Any,
    issues: List[dict],
    path: List = None,
) -> None:
    """Walk ``value`` and append a legacy-channel-acp-binding issue when found.

    Mirrors :func:`addLegacyChannelAcpBindingIssues`
    (``shared/config/zod-schema.channels-config.ts`).
    """
    path = path or []
    if not value or not isinstance(value, (dict, list)):
        return
    if isinstance(value, list):
        for i, entry in enumerate(value):
            add_legacy_channel_acp_binding_issues(entry, issues, [*path, i])
        return
    bindings = value.get("bindings") if isinstance(value, dict) else None
    if isinstance(bindings, dict) and "acp" in bindings and isinstance(bindings.get("acp"), dict):
        issues.append({
            "path": [*path, "bindings", "acp"],
            "message": (
                "Legacy channel-local ACP bindings were removed; "
                "use top-level bindings[] entries."
            ),
        })
    if isinstance(value, dict):
        for key, entry in value.items():
            add_legacy_channel_acp_binding_issues(entry, issues, [*path, key])


__all__ = [
    "ChannelBotLoopProtectionSchema",
    "ChannelsSchema",
    "add_legacy_channel_acp_binding_issues",
]
