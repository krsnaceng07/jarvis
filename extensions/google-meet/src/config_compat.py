"""Google Meet configuration compatibility and doctor migration rules."""

from __future__ import annotations

import copy
from typing import Any, Callable


class LegacyConfigRule:
    def __init__(self, path: list[str | int], message: str, match: Callable[[Any], bool]) -> None:
        self.path = path
        self.message = message
        self.match = match


def _has_legacy_google_realtime_provider(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    provider = str(value.get("provider") or "").strip().lower()
    if provider != "google":
        return False
    return "voiceProvider" not in value or "transcriptionProvider" not in value


legacy_config_rules: list[LegacyConfigRule] = [
    LegacyConfigRule(
        path=["plugins", "entries", "google-meet", "config", "realtime"],
        message=(
            'plugins.entries.google-meet.config.realtime.provider="google" is legacy for Gemini Live bidi mode; '
            'use realtime.voiceProvider="google" and realtime.transcriptionProvider="openai". Run "jarvis doctor --fix".'
        ),
        match=_has_legacy_google_realtime_provider,
    ),
]


def migrate_google_meet_legacy_realtime_provider(config: dict[str, Any]) -> dict[str, Any] | None:
    plugins = config.get("plugins")
    if not isinstance(plugins, dict):
        return None
    entries = plugins.get("entries")
    if not isinstance(entries, dict):
        return None
    raw_entry = entries.get("google-meet")
    if not isinstance(raw_entry, dict):
        return None
    raw_plugin_config = raw_entry.get("config")
    if not isinstance(raw_plugin_config, dict):
        return None
    raw_realtime = raw_plugin_config.get("realtime")
    if not isinstance(raw_realtime, dict) or not _has_legacy_google_realtime_provider(raw_realtime):
        return None

    next_config = copy.deepcopy(config)
    next_plugins = next_config.setdefault("plugins", {})
    next_entries = next_plugins.setdefault("entries", {})
    next_entry = next_entries.setdefault("google-meet", {})
    next_plugin_config = next_entry.setdefault("config", {})
    next_realtime = next_plugin_config.setdefault("realtime", {})

    next_realtime["provider"] = "openai"
    next_realtime["voiceProvider"] = "google"
    next_realtime["transcriptionProvider"] = "openai"
    return next_config


def migrate_legacy_google_meet_config(config: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Migrate flat or legacy configuration keys to modern structure."""
    out = copy.deepcopy(config)
    changed = False

    # Flat keys to nested chrome
    if "chromeProfile" in out:
        out.setdefault("chrome", {})["profile"] = out.pop("chromeProfile")
        changed = True
    if "audioIn" in out:
        out.setdefault("chrome", {})["audioIn"] = out.pop("audioIn")
        changed = True
    if "audioOut" in out:
        out.setdefault("chrome", {})["audioOut"] = out.pop("audioOut")
        changed = True

    # Flat keys to nested oauth
    if "clientId" in out:
        out.setdefault("oauth", {})["clientId"] = out.pop("clientId")
        changed = True
    if "clientSecret" in out:
        out.setdefault("oauth", {})["clientSecret"] = out.pop("clientSecret")
        changed = True
    if "accessToken" in out:
        out.setdefault("oauth", {})["accessToken"] = out.pop("accessToken")
        changed = True
    if "refreshToken" in out:
        out.setdefault("oauth", {})["refreshToken"] = out.pop("refreshToken")
        changed = True

    # Realtime provider legacy migration
    rt = out.get("realtime")
    if isinstance(rt, dict) and _has_legacy_google_realtime_provider(rt):
        rt["provider"] = "openai"
        rt["voiceProvider"] = "google"
        rt["transcriptionProvider"] = "openai"
        changed = True

    return out, changed
