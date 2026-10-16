"""Talk Voice extension package."""

from __future__ import annotations

from .plugin import TalkVoicePlugin, entry, talk_voice_plugin
from .voice_command import (
    SpeechVoiceOption,
    find_voice,
    format_voice_list,
    format_voice_meta,
    handle_voice_command,
    is_likely_voice_id,
    mask,
    requires_admin_to_set_voice,
    resolve_command_label,
    resolve_provider_label,
)

__all__ = [
    "SpeechVoiceOption",
    "TalkVoicePlugin",
    "entry",
    "find_voice",
    "format_voice_list",
    "format_voice_meta",
    "handle_voice_command",
    "is_likely_voice_id",
    "mask",
    "requires_admin_to_set_voice",
    "resolve_command_label",
    "resolve_provider_label",
    "talk_voice_plugin",
]
