"""jarvis.config.legacy_shared — shared legacy config rule contracts.

OpenClaw parity: mirrors
``openclaw-main/src/config/legacy.shared.ts``.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, TypedDict


class LegacyConfigRule(TypedDict, total=False):
    """Legacy config rule for detection and migration.

    Mirrors :type:`LegacyConfigRule`
    (``shared/config/legacy.shared.ts``).
    """
    path: List[str]
    message: str
    match: Callable[[Any, dict], bool]
    requireSourceLiteral: bool


def get_record(value) -> Optional[dict]:
    return value if isinstance(value, dict) else None


def ensure_record(root: dict, key: str) -> dict:
    """Return the record at ``root[key]``; create a new dict if missing."""
    if not isinstance(root, dict):
        raise TypeError("root must be a dict")
    existing = root.get(key)
    if isinstance(existing, dict):
        return existing
    next_: dict = {}
    root[key] = next_
    return next_


_BLOCKED_KEYS = frozenset({"__proto__", "prototype", "constructor"})


def _is_blocked_object_key(key: str) -> bool:
    return key in _BLOCKED_KEYS


def merge_missing(target: dict, source: dict) -> None:
    """Copy missing entries from ``source`` into ``target`` (no overwrites).

    Mirrors :func:`mergeMissing`
    (``shared/config/legacy.shared.ts``).
    """
    if not isinstance(target, dict) or not isinstance(source, dict):
        return
    for key, value in source.items():
        if value is None or _is_blocked_object_key(key):
            continue
        existing = target.get(key)
        if existing is None:
            target[key] = value
            continue
        if isinstance(existing, dict) and isinstance(value, dict):
            merge_missing(existing, value)


def is_safe_executable_value(value: str) -> bool:
    """Return whether ``value`` looks like a safe executable path.

    Focused minimal stub: delegates to a future infra/exec-safety port.
    """
    if not isinstance(value, str):
        return False
    return bool(value.strip())


def map_legacy_audio_transcription(value) -> Optional[dict]:
    """Map legacy audio-transcription config to the new schema.

    Mirrors :func:`mapLegacyAudioTranscription`
    (``shared/config/legacy.shared.ts``).
    """
    transcriber = get_record(value)
    command = transcriber.get("command") if transcriber else None
    if not isinstance(command, list) or not command:
        return None
    if not isinstance(command[0], str):
        return None
    if not all(isinstance(p, str) for p in command):
        return None
    raw_executable = command[0].strip()
    if not raw_executable or not is_safe_executable_value(raw_executable):
        return None
    args = [p.replace("{input}", "{{MediaPath}}") for p in command[1:]]
    timeout_seconds = (
        transcriber.get("timeoutSeconds")
        if transcriber and isinstance(transcriber.get("timeoutSeconds"), (int, float))
        else None
    )
    result: dict = {"command": raw_executable, "type": "cli"}
    if args:
        result["args"] = args
    if timeout_seconds is not None:
        result["timeoutSeconds"] = timeout_seconds
    return result


def define_legacy_config_migration(migration) -> dict:
    return migration


__all__ = [
    "LegacyConfigRule",
    "get_record",
    "ensure_record",
    "merge_missing",
    "is_safe_executable_value",
    "map_legacy_audio_transcription",
    "define_legacy_config_migration",
]
