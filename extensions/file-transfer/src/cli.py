"""File Transfer CLI and doctor migrations."""

from __future__ import annotations

from typing import Any


def handle_file_transfer_cli(args: list[str], config: dict[str, Any]) -> str:
    """Handle jarvis file-transfer CLI command."""
    if not args or args[0] in ("status", "list"):
        nodes = config.get("nodes", {}) if isinstance(config, dict) else {}
        grants = config.get("literalGrants", []) if isinstance(config, dict) else []
        lines = [
            "File Transfer Status:",
            f"- Configured nodes: {len(nodes)}",
            f"- Standing literal grants: {len(grants)}",
        ]
        return "\n".join(lines)
    return "Usage: jarvis file-transfer [status|list]"


def repair_file_transfer_config(config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Doctor repair contract for file-transfer configuration."""
    repaired = dict(config)
    repairs: list[str] = []

    if "policyVersion" not in repaired or repaired["policyVersion"] != 2:
        repaired["policyVersion"] = 2
        repairs.append("Set file-transfer policyVersion to 2")

    if "literalGrants" not in repaired:
        repaired["literalGrants"] = []

    return repaired, repairs
