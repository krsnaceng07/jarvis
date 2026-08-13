"""Exclusive plugin slot defaults and helpers.

OpenClaw parity: ``src/plugins/slots.ts``.
"""
from __future__ import annotations

from typing import Iterable, cast

__all__ = [
    "DEFAULT_SLOT_BY_KEY",
    "apply_exclusive_slot_selection",
    "default_slot_id_for_key",
    "has_kind",
    "kinds_equal",
    "reset_plugin_slots_to_defaults",
]

DEFAULT_SLOT_BY_KEY: dict[str, str] = {
    "memory": "memory-core",
    "contextEngine": "legacy",
}


def _ensure_object_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def _ensure_object_list(value: object) -> list[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    return []


def default_slot_id_for_key(slot_key: str) -> str:
    """Return the built-in default engine id for an exclusive slot key."""
    default_id = DEFAULT_SLOT_BY_KEY.get(slot_key)
    if default_id is None:
        raise KeyError(f"Unknown exclusive plugin slot key: {slot_key!r}")
    return default_id


def has_kind(kinds: object, kind: str) -> bool:
    """Return whether the supplied kind collection contains a target kind."""
    if kinds is None:
        return False
    if isinstance(kinds, str):
        return kinds == kind
    if isinstance(kinds, (list, tuple, set)):
        return kind in kinds
    return False


def kinds_equal(left: object, right: object) -> bool:
    """Return whether two kind values describe the same set of kinds."""
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False

    def _normalize(value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        if isinstance(value, (list, tuple, set)):
            return tuple(sorted(str(item) for item in cast(Iterable[object], value)))
        return (str(value),)

    return _normalize(left) == _normalize(right)


def reset_plugin_slots_to_defaults(
    slots: dict[str, str] | None,
    plugin_id: str,
) -> dict[str, str] | None:
    """Reset the slots currently owned by the plugin back to their defaults."""
    if slots is None:
        return None

    owned_slot_keys = [
        slot_key
        for slot_key, owner_id in slots.items()
        if owner_id == plugin_id
    ]
    if not owned_slot_keys:
        return slots

    next_slots = dict(slots)
    for slot_key in owned_slot_keys:
        next_slots[slot_key] = default_slot_id_for_key(slot_key)
    return next_slots


def apply_exclusive_slot_selection(payload: dict[str, object]) -> dict[str, object]:
    """Apply exclusive-slot selection to a plugin config payload."""
    config = payload.get("config")
    selected_id = payload.get("selectedId")
    selected_kind = payload.get("selectedKind")
    registry = _ensure_object_dict(payload.get("registry"))

    if not isinstance(config, dict):
        return {"changed": False, "warnings": [], "config": config}
    if not selected_id or selected_kind is None:
        return {"changed": False, "warnings": [], "config": config}

    config_dict = cast(dict[str, object], config)
    plugins = _ensure_object_list(registry.get("plugins"))
    plugin_entries: list[dict[str, object]] = []
    for entry in plugins:
        if isinstance(entry, dict):
            plugin_entries.append(cast(dict[str, object], entry))
    selected_plugin = next(
        (entry for entry in plugin_entries if entry.get("id") == selected_id),
        None,
    )
    if selected_plugin is None:
        return {"changed": False, "warnings": [], "config": config}

    plugins_config = _ensure_object_dict(config_dict.get("plugins"))
    plugin_slots = _ensure_object_dict(plugins_config.get("slots"))

    slot_keys: list[str] = []
    if plugin_slots:
        slot_keys = [
            slot_key
            for slot_key in plugin_slots.keys()
            if has_kind(
                selected_plugin.get("kind"),
                "context-engine" if slot_key == "contextEngine" else slot_key,
            )
        ]
    else:
        if isinstance(selected_kind, str):
            slot_keys = [
                "contextEngine"
                if selected_kind == "context-engine"
                else selected_kind
            ]
        elif isinstance(selected_kind, (list, tuple, set)):
            selected_kind_list = cast(Iterable[object], selected_kind)
            slot_keys = [
                "contextEngine" if kind == "context-engine" else str(kind)
                for kind in selected_kind_list
            ]

    if not slot_keys:
        return {"changed": False, "warnings": [], "config": config}

    changed = False
    warnings: list[str] = []
    next_config = cast(dict[str, object], config)

    def _is_dual_kind_plugin(plugin: dict[str, object] | None) -> bool:
        if not isinstance(plugin, dict):
            return False
        kind = plugin.get("kind")
        if isinstance(kind, list):
            kind_list = cast(list[object], kind)
            return len(kind_list) > 1
        if isinstance(kind, tuple):
            kind_tuple = cast(tuple[object, ...], kind)
            return len(kind_tuple) > 1
        if isinstance(kind, set):
            kind_set = cast(set[object], kind)
            return len(kind_set) > 1
        return False

    for slot_key in slot_keys:
        current_owner = plugin_slots.get(slot_key)
        if current_owner is None:
            current_owner = default_slot_id_for_key(slot_key)
        if current_owner == selected_id:
            continue

        changed = True
        warnings.append(
            f'Exclusive slot "{slot_key}" switched from "{current_owner}" to "{selected_id}".'
        )

        next_config = dict(config_dict)
        if "plugins" not in next_config or not isinstance(next_config["plugins"], dict):
            next_config["plugins"] = {}
        if "slots" not in next_config["plugins"] or not isinstance(next_config["plugins"]["slots"], dict):
            next_config["plugins"]["slots"] = {}
        next_config["plugins"]["slots"][slot_key] = selected_id

        next_plugins_config = _ensure_object_dict(next_config.get("plugins"))
        next_entries = _ensure_object_dict(next_plugins_config.get("entries"))
        if not next_entries:
            continue
        current_entry = next_entries.get(str(current_owner))
        owner_plugin = next(
            (
                entry
                for entry in plugin_entries
                if entry.get("id") == str(current_owner)
            ),
            None,
        )
        current_entry_dict = cast(dict[str, object], current_entry) if isinstance(current_entry, dict) else None
        should_disable_competitor = (
            not _is_dual_kind_plugin(owner_plugin)
            and (
                current_entry_dict is None
                or current_entry_dict.get("enabled") is True
            )
        )
        if should_disable_competitor:
            if isinstance(current_entry, dict):
                next_entries[str(current_owner)] = {
                    **current_entry,
                    "enabled": False,
                }
            warnings.append(
                f'Disabled other "{slot_key}" slot plugins: {current_owner}.'
            )

    if not changed:
        return {"changed": False, "warnings": [], "config": config}

    return {"changed": True, "warnings": warnings, "config": next_config}
