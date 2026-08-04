"""jarvis.config.commands — native command setting resolution.

OpenClaw parity: mirrors ``openclaw-main/src/config/commands.ts``.

Focused minimal port: the channel plugin discovery is delegated to a
caller-provided ``get_loaded_channel_plugin`` callable. The
``NativeCommandsSetting`` shape accepts ``True``/``False``/``"auto"``.
"""
from __future__ import annotations

from typing import Any, Callable, Literal, Optional, Union


NativeCommandsSetting = Union[bool, Literal["auto"]]


def resolve_native_skills_enabled(params: dict) -> bool:
    """Resolve native skill exposure for a provider.

    Mirrors :func:`resolveNativeSkillsEnabled`
    (``shared/config/commands.ts``).
    """
    return _resolve_native_command_setting({**params, "kind": "nativeSkills"})


def resolve_native_commands_enabled(params: dict) -> bool:
    """Resolve native command exposure for a provider.

    Mirrors :func:`resolveNativeCommandsEnabled`
    (``shared/config/commands.ts``).
    """
    return _resolve_native_command_setting({**params, "kind": "native"})


def _resolve_auto_default(
    provider_id: Optional[str],
    kind: str,
    *,
    auto_default: Optional[bool] = None,
    get_loaded_channel_plugin: Optional[Callable[[str], Any]] = None,
    resolve_read_only_defaults: Optional[Callable[[str, dict], Any]] = None,
) -> bool:
    if not provider_id:
        return False
    if isinstance(auto_default, bool):
        return auto_default
    command_defaults = None
    if get_loaded_channel_plugin is not None:
        plugin = get_loaded_channel_plugin(provider_id)
        command_defaults = getattr(plugin, "commands", None)
    if command_defaults is None and resolve_read_only_defaults is not None:
        command_defaults = resolve_read_only_defaults(provider_id, {})
    if kind == "native":
        return getattr(command_defaults, "native_commands_auto_enabled", False) is True
    return getattr(command_defaults, "native_skills_auto_enabled", False) is True


def _resolve_native_command_setting(params: dict) -> bool:
    provider_id = params.get("providerId")
    provider_setting = params.get("providerSetting")
    global_setting = params.get("globalSetting")
    kind = params.get("kind", "native")
    setting = global_setting if provider_setting is None else provider_setting
    if setting is True:
        return True
    if setting is False:
        return False
    return _resolve_auto_default(
        provider_id,
        kind,
        auto_default=params.get("autoDefault"),
        get_loaded_channel_plugin=params.get("getLoadedChannelPlugin"),
        resolve_read_only_defaults=params.get("resolveReadOnlyChannelCommandDefaults"),
    )


def is_native_commands_explicitly_disabled(params: dict) -> bool:
    """Return true only when native commands are explicitly disabled.

    Mirrors :func:`isNativeCommandsExplicitlyDisabled`
    (``shared/config/commands.ts``).
    """
    provider_setting = params.get("providerSetting")
    global_setting = params.get("globalSetting")
    if provider_setting is False:
        return True
    if provider_setting is None:
        return global_setting is False
    return False


__all__ = [
    "NativeCommandsSetting",
    "resolve_native_skills_enabled",
    "resolve_native_commands_enabled",
    "is_native_commands_explicitly_disabled",
]
