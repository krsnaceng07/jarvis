"""jarvis.config.channel_config_metadata — channel/plugin config UI metadata.

OpenClaw parity: mirrors
``openclaw-main/src/config/channel-config-metadata.ts``.

The OpenClaw source consumes the plugin manifest registry directly; this
focused minimal port accepts any iterable of plugin records with the
fields the collector uses, so callers can supply their own registry
shape during incremental migration.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


#: Plugin origin precedence for the same plugin id.
PLUGIN_ORIGIN_RANK: Dict[str, int] = {
    "config": 0,
    "workspace": 1,
    "global": 2,
    "bundled": 3,
}


class ChannelUiMetadata(TypedDict, total=False):
    id: str
    label: str
    description: str
    configSchema: Any
    configUiHints: Any


class PluginUiMetadata(TypedDict, total=False):
    id: str
    name: str
    description: str
    configUiHints: Any
    configSchema: Any


def _record_origin_rank(record) -> int:
    return PLUGIN_ORIGIN_RANK.get(getattr(record, "origin", None), 2**31)


def _record_channel_configs(record) -> Dict[str, Any]:
    return getattr(record, "channelConfigs", None) or {}


def _record_channels(record) -> List[str]:
    return list(getattr(record, "channels", None) or [])


def _record_channel_catalog_meta(record) -> Any:
    return getattr(record, "channelCatalogMeta", None)


def _record_package_channel(record) -> Any:
    return getattr(record, "packageChannel", None)


def collect_plugin_schema_metadata(registry: Any) -> List[PluginUiMetadata]:
    """Collect plugin config UI metadata with deterministic origin precedence.

    Mirrors :func:`collectPluginSchemaMetadata`
    (``shared/config/channel-config-metadata.ts``).
    """
    deduped: Dict[str, dict] = {}
    for record in getattr(registry, "plugins", []) or []:
        rid = getattr(record, "id", None)
        if not rid:
            continue
        next_rank = _record_origin_rank(record)
        current = deduped.get(rid)
        if current and current["originRank"] <= next_rank:
            continue
        deduped[rid] = {
            "id": rid,
            "name": getattr(record, "name", None),
            "description": getattr(record, "description", None),
            "configUiHints": getattr(record, "configUiHints", None),
            "configSchema": getattr(record, "configSchema", None),
            "originRank": next_rank,
        }
    out: List[PluginUiMetadata] = []
    for entry in sorted(deduped.values(), key=lambda e: e["id"]):
        entry.pop("originRank", None)
        out.append(entry)  # type: ignore[arg-type]
    return out


def collect_channel_schema_metadata(registry: Any) -> List[ChannelUiMetadata]:
    """Collect public per-channel config UI metadata.

    Mirrors :func:`collectChannelSchemaMetadata`
    (``shared/config/channel-config-metadata.ts``).
    """
    by_channel: Dict[str, dict] = {}
    for record in getattr(registry, "plugins", []) or []:
        origin_rank = _record_origin_rank(record)
        catalog = _record_channel_catalog_meta(record)
        root_label = getattr(catalog, "label", None) if catalog else None
        root_description = getattr(catalog, "blurb", None) if catalog else None
        for channel_id in _record_channels(record):
            current = by_channel.get(channel_id)
            if not current or origin_rank <= current["originRank"]:
                by_channel[channel_id] = {
                    "id": channel_id,
                    "label": root_label if root_label is not None else (current or {}).get("label"),
                    "description": root_description if root_description is not None else (current or {}).get("description"),
                    "configSchema": (current or {}).get("configSchema"),
                    "configUiHints": (current or {}).get("configUiHints"),
                    "schemaPluginId": (current or {}).get("schemaPluginId"),
                    "schemaPluginOrigin": (current or {}).get("schemaPluginOrigin"),
                    "originRank": origin_rank,
                }
        for channel_id, channel_config in _record_channel_configs(record).items():
            current = by_channel.get(channel_id)
            if (
                current
                and current["originRank"] < origin_rank
                and (current.get("configSchema") is not None
                     or current.get("configUiHints") is not None)
            ):
                continue
            schema = channel_config.get("schema")
            by_channel[channel_id] = {
                "id": channel_id,
                "label": channel_config.get("label") or root_label or (current or {}).get("label"),
                "description": channel_config.get("description") or root_description
                or (current or {}).get("description"),
                "configSchema": schema,
                "configUiHints": channel_config.get("uiHints"),
                "schemaPluginId": record.id if schema is not None else None,
                "schemaPluginOrigin": record.origin if schema is not None else None,
                "originRank": origin_rank,
            }
    out: List[ChannelUiMetadata] = []
    for entry in sorted(by_channel.values(), key=lambda e: e["id"]):
        entry.pop("originRank", None)
        entry.pop("schemaPluginId", None)
        entry.pop("schemaPluginOrigin", None)
        out.append(entry)  # type: ignore[arg-type]
    return out


def collect_channel_dm_policy_metadata(registry: Any) -> List[dict]:
    """Collect channel DM policy metadata without importing doctor/runtime modules.

    Mirrors :func:`collectChannelDmPolicyMetadata`
    (``shared/config/channel-config-metadata.ts``).
    """
    by_channel: Dict[str, dict] = {}
    for record in getattr(registry, "plugins", []) or []:
        origin_rank = _record_origin_rank(record)
        package = _record_package_channel(record)
        package_channel_id = getattr(package, "id", None) if package else None
        if isinstance(package_channel_id, str):
            package_channel_id = package_channel_id.strip() or None
        dm_allow_from_mode = (
            getattr(getattr(package, "doctorCapabilities", None), "dmAllowFromMode", None)
            if package else None
        )

        def _put(channel_id, mode):
            cid = channel_id.strip() if isinstance(channel_id, str) else None
            if not cid:
                return
            current = by_channel.get(cid)
            if current and current["originRank"] < origin_rank:
                return
            entry = {"id": cid, "originRank": origin_rank}
            if mode:
                entry["dmAllowFromMode"] = mode
            by_channel[cid] = entry

        for channel_id in _record_channels(record):
            _put(channel_id, dm_allow_from_mode if channel_id == package_channel_id else None)
        _put(package_channel_id, dm_allow_from_mode)
        for channel_id in _record_channel_configs(record).keys():
            _put(channel_id, dm_allow_from_mode if channel_id == package_channel_id else None)

    out = []
    for entry in sorted(by_channel.values(), key=lambda e: e["id"]):
        entry.pop("originRank", None)
        out.append(entry)
    return out


__all__ = [
    "PLUGIN_ORIGIN_RANK",
    "ChannelUiMetadata",
    "PluginUiMetadata",
    "collect_plugin_schema_metadata",
    "collect_channel_schema_metadata",
    "collect_channel_dm_policy_metadata",
]
