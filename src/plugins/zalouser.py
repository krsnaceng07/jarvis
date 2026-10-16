"""jarvis.plugins.zalouser — Zalo Personal (unofficial user account) channel plugin configuration.

OpenClaw parity: mirrors
``openclaw-main/extensions/zalouser/src/config-schema.ts`` and
``openclaw-main/extensions/zalouser/index.ts``.

Features:
- `ZALOUSER_PLUGIN_ID`: `"zalouser"`
- `ZALOUSER_CHANNEL_ID`: `"zalouser"`
- `ZALOUSER_TOOL_NAME`: `"zalouser"`
- `ZALOUSER_TOOL_ACTIONS`: `send`, `image`, `link`, `friends`, `groups`, `me`, `status`.
- `ZalouserAccountConfig`: Dataclass containing per-account channel settings.
- `resolve_zalouser_config()`: Resolves and defaults Zalo personal channel configuration under `channels.zalouser`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ZALOUSER_PLUGIN_ID: str = "zalouser"
ZALOUSER_CHANNEL_ID: str = "zalouser"
ZALOUSER_TOOL_NAME: str = "zalouser"

ZalouserDmPolicy = Literal["pairing", "allowlist", "open", "disabled"]
ZalouserGroupPolicy = Literal["allowlist", "open", "disabled"]

ZALOUSER_TOOL_ACTIONS: list[str] = [
    "send",
    "image",
    "link",
    "friends",
    "groups",
    "me",
    "status",
]


@dataclass
class ZalouserAccountConfig:
    enabled: bool = True
    dmPolicy: ZalouserDmPolicy = "pairing"
    allowFrom: list[str] = field(default_factory=list)
    groupPolicy: ZalouserGroupPolicy = "allowlist"
    groups: dict[str, Any] = field(default_factory=dict)
    messagePrefix: str | None = None
    responsePrefix: str | None = None


def resolve_zalouser_config(channels_cfg: dict[str, Any] | None) -> ZalouserAccountConfig:
    """Resolve Zalo Personal channel options from global `channels` configuration dictionary."""
    val = channels_cfg if isinstance(channels_cfg, dict) else {}
    zalo_raw = val.get("zalouser") if isinstance(val.get("zalouser"), dict) else {}

    raw_dm = str(zalo_raw.get("dmPolicy") or "pairing").lower()
    dm_policy: ZalouserDmPolicy = (
        raw_dm if raw_dm in ("pairing", "allowlist", "open", "disabled") else "pairing"  # type: ignore[assignment]
    )

    raw_group_pol = str(zalo_raw.get("groupPolicy") or "allowlist").lower()
    group_policy: ZalouserGroupPolicy = (
        raw_group_pol if raw_group_pol in ("allowlist", "open", "disabled") else "allowlist"  # type: ignore[assignment]
    )

    allow_from = zalo_raw.get("allowFrom")
    clean_allow = (
        [str(x).strip() for x in allow_from if isinstance(x, str) and str(x).strip()]
        if isinstance(allow_from, list)
        else []
    )

    groups_raw = zalo_raw.get("groups")
    clean_groups = groups_raw if isinstance(groups_raw, dict) else {}

    return ZalouserAccountConfig(
        enabled=bool(zalo_raw.get("enabled", True)),
        dmPolicy=dm_policy,
        allowFrom=clean_allow,
        groupPolicy=group_policy,
        groups=clean_groups,
        messagePrefix=zalo_raw.get("messagePrefix"),
        responsePrefix=zalo_raw.get("responsePrefix"),
    )


__all__ = [
    "ZALOUSER_CHANNEL_ID",
    "ZALOUSER_PLUGIN_ID",
    "ZALOUSER_TOOL_ACTIONS",
    "ZALOUSER_TOOL_NAME",
    "ZalouserAccountConfig",
    "ZalouserDmPolicy",
    "ZalouserGroupPolicy",
    "resolve_zalouser_config",
]
