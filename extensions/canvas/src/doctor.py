"""Canvas CLI commands and doctor migrations."""

from __future__ import annotations

from typing import Any


def handle_canvas_cli(args: list[str], config: dict[str, Any]) -> str:
    """Handle jarvis canvas CLI command."""
    if not args or args[0] in ("status", "info"):
        host_cfg = config.get("host", {}) if isinstance(config, dict) else {}
        enabled = host_cfg.get("enabled", True)
        return f"Canvas Status:\n- Host enabled: {enabled}"
    return "Usage: jarvis canvas [status]"


def repair_canvas_config(config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Doctor config repair for canvas."""
    repaired = dict(config)
    repairs: list[str] = []

    # Migrate legacy canvasHost top-level or deprecated shape
    if "canvasHost" in repaired:
        legacy = repaired.pop("canvasHost")
        if isinstance(legacy, dict) and "enabled" in legacy:
            if "host" not in repaired:
                repaired["host"] = {}
            repaired["host"]["enabled"] = legacy["enabled"]
            repairs.append("Migrated canvasHost.enabled to host.enabled")

    return repaired, repairs
