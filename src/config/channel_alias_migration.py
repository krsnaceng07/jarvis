"""jarvis.config.channel_alias_migration — channel doctor alias-migration spec.

OpenClaw parity: mirrors
``openclaw-main/src/config/channel-alias-migration.ts``.

Focused minimal port: exposes the public :func:`define_channel_alias_migration`
factory. Heavy lifting (legacy-alias detection, channel-config normalizer)
is delegated to caller-provided callables until those subsystems land.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


#: Streaming-alias migration modes.
StreamingAliasMode = str  # "off" | "partial" | "block" | "progress"


def _default_as_object_record(value: Any) -> Optional[dict]:
    """Default ``as_object_record`` callback.

    Mirrors OpenClaw's ``asObjectRecord`` helper: a value is a "record" iff it
    is a non-array dict-like mapping. Anything else (None, lists, scalars) is
    not a record.
    """
    if value is None or isinstance(value, (list, tuple, str, bytes, int, float, bool)):
        return None
    if not isinstance(value, dict):
        return None
    return value


def _build_alias_rule_message(params: dict) -> str:
    """Compose the doctor-style migration message for a channel spec."""
    streaming = params.get("streaming") or {}
    prefix = params.get("prefix") or ""
    is_root = params.get("root", True)
    delivery_only = streaming.get("deliveryOnly", False)
    flat_keys = []
    if not delivery_only:
        flat_keys.extend(["streamMode", "streaming (scalar)"])
    flat_keys.extend(["chunkMode", "blockStreaming"])
    if streaming.get("includePreviewChunk"):
        flat_keys.append("draftChunk")
    flat_keys.append("blockStreamingCoalesce")
    if streaming.get("resolveNativeTransport"):
        flat_keys.append("nativeStreaming")
    nested_keys = []
    if not delivery_only:
        nested_keys.append("mode")
    nested_keys.append("chunkMode")
    if streaming.get("includePreviewChunk"):
        nested_keys.append("preview.chunk")
    nested_keys.extend(["block.enabled", "block.coalesce"])
    if streaming.get("resolveNativeTransport"):
        nested_keys.append("nativeTransport")
    if not flat_keys:
        return ""
    # Root messages spell out the ambiguous scalar `streaming` key with its full
    # path; account messages prefix only the first key.
    prefixed_count = 2 if (is_root and not delivery_only) else 1
    keys = [
        f"{prefix}.{k}" if i < prefixed_count else k
        for i, k in enumerate(flat_keys)
    ]
    if len(keys) == 1:
        key_list = keys[0]
    else:
        key_list = ", ".join(keys[:-1]) + ", and " + keys[-1]
    return (
        f"{key_list} are legacy; use {prefix}.streaming.{{{','.join(nested_keys)}}}. "
        f'Run "openclaw doctor --fix".'
    )


def define_channel_alias_migration(
    spec: dict,
    *,
    as_object_record_fn: Optional[Callable] = None,
    has_legacy_streaming_aliases_fn: Optional[Callable] = None,
    has_legacy_account_streaming_aliases_fn: Optional[Callable] = None,
    normalize_legacy_channel_aliases_fn: Optional[Callable] = None,
    resolve_legacy_alias_streaming_mode_fn: Optional[Callable] = None,
) -> dict:
    """Build the channel doctor alias-migration surface from a small spec.

    Mirrors :func:`defineChannelAliasMigration`
    (``shared/config/channel-alias-migration.ts`).
    """
    streaming = spec.get("streaming") or {}
    path_prefix = f"channels.{spec.get('channelId')}"
    as_object_record = as_object_record_fn if callable(as_object_record_fn) else _default_as_object_record

    def has_legacy_aliases(value: Any) -> bool:
        if streaming.get("deliveryOnly"):
            entry = as_object_record(value) if as_object_record else None
            return bool(
                entry is not None
                and (
                    entry.get("chunkMode") is not None
                    or entry.get("blockStreaming") is not None
                    or entry.get("blockStreamingCoalesce") is not None
                )
            )
        if callable(has_legacy_streaming_aliases_fn):
            return bool(has_legacy_streaming_aliases_fn(value, {
                "includePreviewChunk": streaming.get("includePreviewChunk"),
                "includeNativeTransport": streaming.get("resolveNativeTransport") is not None,
            }))
        return False

    def resolve_streaming_options(entry: dict) -> dict:
        resolved_mode = streaming.get("defaultMode")
        if callable(resolve_legacy_alias_streaming_mode_fn):
            resolved_mode = resolve_legacy_alias_streaming_mode_fn(entry, streaming.get("defaultMode"))
        return {
            "resolvedMode": resolved_mode,
            "aliasOnlyMode": streaming.get("absentObjectDefault"),
            "includePreviewChunk": streaming.get("includePreviewChunk"),
        }

    def normalize_channel_config(params: dict) -> dict:
        changes = params.get("changes")
        if changes is None:
            changes = []
        cfg = params.get("cfg")
        if not isinstance(cfg, dict):
            return {"config": cfg, "changes": changes}
        channels = cfg.get("channels")
        if not isinstance(channels, dict):
            return {"config": cfg, "changes": changes}
        entry = channels.get(spec.get("channelId"))
        if not isinstance(entry, dict):
            return {"config": cfg, "changes": changes}
        if streaming.get("deliveryOnly"):
            has_account_legacy = bool(
                callable(has_legacy_account_streaming_aliases_fn)
                and has_legacy_account_streaming_aliases_fn(entry.get("accounts"), has_legacy_aliases)
            )
            if not has_legacy_aliases(entry) and not has_account_legacy:
                return {"config": cfg, "changes": changes}
        if not callable(normalize_legacy_channel_aliases_fn):
            return {"config": cfg, "changes": changes}
        result = normalize_legacy_channel_aliases_fn({
            "entry": entry,
            "pathPrefix": path_prefix,
            "changes": changes,
            "normalizeDm": (spec.get("dm") or {}).get("root"),
            "rootDmPromoteAllowFrom": (spec.get("dm") or {}).get("rootPromoteAllowFrom"),
            "normalizeAccountDm": (spec.get("dm") or {}).get("accounts"),
            "seedAccountStreamingFromRoot": spec.get("accountStreamingReplacesRoot"),
            "resolveStreamingOptions": resolve_streaming_options,
            "normalizeAccountExtra": spec.get("normalizeAccountExtra"),
        })
        if not result or not result.get("changed"):
            return {"config": cfg, "changes": changes}
        return {
            "config": {
                **cfg,
                "channels": {
                    **channels,
                    spec.get("channelId"): result.get("entry"),
                },
            },
            "changes": changes,
        }

    return {
        "legacyConfigRules": [
            {
                "path": ["channels", spec.get("channelId")],
                "message": _build_alias_rule_message({
                    "streaming": streaming, "prefix": path_prefix, "root": True,
                }),
                "match": has_legacy_aliases,
            },
            {
                "path": ["channels", spec.get("channelId"), "accounts"],
                "message": _build_alias_rule_message({
                    "streaming": streaming,
                    "prefix": f"{path_prefix}.accounts.<id>",
                    "root": False,
                }),
                "match": (
                    lambda v: callable(has_legacy_account_streaming_aliases_fn)
                    and has_legacy_account_streaming_aliases_fn(v, has_legacy_aliases)
                ),
            },
        ],
        "hasLegacyAliases": has_legacy_aliases,
        "normalizeChannelConfig": normalize_channel_config,
    }


__all__ = [
    "StreamingAliasMode",
    "define_channel_alias_migration",
]
