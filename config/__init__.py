from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

_CONFIG_PATH = Path(__file__).parent / "api_keys.json"


def get_config() -> dict[str, Any]:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        data: Any = json.load(f)
        if isinstance(data, dict):
            typed_data: dict[str, Any] = cast("dict[str, Any]", data)
            return typed_data
        return {}


def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'"""
    val = get_config().get("os_system", "windows")
    if isinstance(val, str):
        return val.lower()
    return "windows"


def is_windows() -> bool:
    return get_os() == "windows"


def is_mac() -> bool:
    return get_os() == "mac"


def is_linux() -> bool:
    return get_os() == "linux"
