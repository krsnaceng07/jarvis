"""Canvas configuration and migration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CanvasHostConfig:
    """Canvas host configuration."""

    enabled: bool = True


@dataclass(frozen=True, slots=True)
class CanvasConfig:
    """Canvas plugin configuration."""

    host: CanvasHostConfig = CanvasHostConfig()


def resolve_canvas_config(raw_config: Any) -> CanvasConfig:
    """Resolve CanvasConfig from dictionary."""
    if not isinstance(raw_config, dict):
        return CanvasConfig()

    host_dict = raw_config.get("host")
    if isinstance(host_dict, dict):
        enabled = host_dict.get("enabled", True)
        return CanvasConfig(host=CanvasHostConfig(enabled=bool(enabled)))

    return CanvasConfig()
