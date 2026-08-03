"""jarvis.logging.parse_log_line — parse JSON log lines into structured records.

OpenClaw parity: mirrors ``openclaw-main/src/logging/parse-log-line.ts``.

Public surface:

- :func:`parse_log_line`
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


def _extract_message(value: Dict[str, Any]) -> str:
    parts: list = []
    for key in value:
        if not key.isdigit():
            continue
        item = value[key]
        if isinstance(item, str):
            parts.append(item)
        elif item is not None:
            try:
                parts.append(json.dumps(item))
            except (TypeError, ValueError):
                parts.append(str(item))
    return " ".join(parts)


def _parse_meta_name(raw: Any) -> Dict[str, Optional[str]]:
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        "subsystem": parsed.get("subsystem") if isinstance(parsed.get("subsystem"), str) else None,
        "module": parsed.get("module") if isinstance(parsed.get("module"), str) else None,
    }


def parse_log_line(raw: str) -> Optional[Dict[str, Any]]:
    """Parse a raw log line into a structured record, or None for non-JSON lines.

    Mirrors :func:`parseLogLine` (``logging/parse-log-line.ts``).
    """
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    meta = parsed.get("_meta")
    meta_dict = meta if isinstance(meta, dict) else {}
    name_meta = _parse_meta_name(meta_dict.get("name"))
    level_raw = meta_dict.get("logLevelName")
    return {
        "time": parsed.get("time") if isinstance(parsed.get("time"), str) else None,
        "level": level_raw.lower() if isinstance(level_raw, str) and level_raw else None,
        "subsystem": name_meta.get("subsystem"),
        "module": name_meta.get("module"),
        "message": _extract_message(parsed),
        "raw": raw,
    }


__all__ = ["parse_log_line"]
