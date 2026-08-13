"""jarvis.routing.channel_route_targets — agent↔channel coverage summary.

OpenClaw parity: mirrors ``src/routing/channel-route-targets.ts``.

Agent-to-channel coverage summary for diagnostics and background
checks. It samples configured channels/accounts and explicit
bindings.
"""

from __future__ import annotations

from typing import Any

from jarvis_normalization_core.string_coerce import normalize_lowercase_string_or_empty

from .channel_ids import normalize_chat_channel_id
from .config_bindings import list_route_bindings
from .resolve_route import resolve_agent_route
from .session_key import DEFAULT_ACCOUNT_ID, normalize_account_id, normalize_agent_id

CHANNELS_CONFIG_META_KEYS = frozenset({"defaults", "modelByChannel"})


def _is_record(value: object) -> bool:
    return isinstance(value, dict)


def _normalize_configured_channel_key(raw: object) -> str:
    normalized = normalize_chat_channel_id(raw)
    if normalized is not None:
        return normalized
    return normalize_lowercase_string_or_empty(raw)


def _normalize_route_binding_channel_key(raw: object) -> str:
    return normalize_lowercase_string_or_empty(raw)


def _list_configured_channel_ids(cfg: dict[str, Any]) -> list[str]:
    channels = cfg.get("channels")
    if not _is_record(channels):
        return []
    out: list[str] = []
    for channel_id, value in channels.items():
        if channel_id in CHANNELS_CONFIG_META_KEYS:
            continue
        if _is_record(value) and value.get("enabled") is False:
            continue
        normalized = _normalize_configured_channel_key(channel_id)
        if normalized:
            out.append(normalized)
    return sorted(out)


def _list_configured_channel_account_ids(cfg: dict[str, Any], channel_id: str) -> list[str]:
    channels = cfg.get("channels")
    if not _is_record(channels):
        return []
    channel = None
    for raw_id, value in channels.items():
        if _normalize_configured_channel_key(raw_id) == channel_id:
            channel = value
            break
    if not _is_record(channel) or not _is_record(channel.get("accounts")):
        return []
    out: list[str] = []
    for account_id, value in channel["accounts"].items():
        if _is_record(value) and value.get("enabled") is False:
            continue
        normalized = normalize_account_id(account_id)
        if normalized:
            out.append(normalized)
    return sorted(out)


def _add_target(by_agent: dict[str, dict[str, None]], agent_id: str, channel: str) -> None:
    normalized_agent_id = normalize_agent_id(agent_id)
    trimmed_channel = (channel or "").strip()
    if not normalized_agent_id or not trimmed_channel:
        return
    channels = by_agent.get(normalized_agent_id)
    if channels is None:
        channels = {}
        by_agent[normalized_agent_id] = channels
    channels[trimmed_channel] = None


def collect_channel_route_targets(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Mirrors ``collectChannelRouteTargets``.

    Returns ``[{"agentId": ..., "channels": [...sorted]}]`` sorted by
    agentId, skipping agents with empty channel lists.
    """
    by_agent: dict[str, dict[str, None]] = {}

    for binding in list_route_bindings(cfg):
        match = binding.get("match") if isinstance(binding, dict) else None
        _add_target(
            by_agent,
            binding.get("agentId") if isinstance(binding, dict) else "",
            _normalize_route_binding_channel_key(match.get("channel") if isinstance(match, dict) else None),
        )

    for channel in _list_configured_channel_ids(cfg):
        account_ids = _list_configured_channel_account_ids(cfg, channel)
        # Channels with no explicit accounts still have an implicit default
        # account route, so sample it to discover the effective agent target.
        sampled_account_ids = account_ids if len(account_ids) > 0 else [DEFAULT_ACCOUNT_ID]
        for account_id in sampled_account_ids:
            route = resolve_agent_route({"cfg": cfg, "channel": channel, "accountId": account_id})
            _add_target(by_agent, route["agentId"], channel)

    targets = [
        {"agentId": agent_id, "channels": sorted(channels.keys())}
        for agent_id, channels in by_agent.items()
        if len(channels) > 0
    ]
    return sorted(targets, key=lambda target: target["agentId"])


__all__ = ["CHANNELS_CONFIG_META_KEYS", "collect_channel_route_targets"]
