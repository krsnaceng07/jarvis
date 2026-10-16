"""Workboard CLI subcommands and doctor migrations."""

from __future__ import annotations

from typing import Any

from .store import WorkboardStore


def handle_workboard_cli(args: list[str], store: WorkboardStore) -> str:
    """Handle jarvis workboard CLI command."""
    if not args or args[0] in ("status", "stats"):
        stats = store.get_stats()
        lines = [
            "Workboard Status:",
            f"- Total cards: {stats['total']}",
            f"- Active: {stats['active']}",
            f"- Done: {stats['done']}",
        ]
        return "\n".join(lines)

    action = args[0].lower()
    if action == "list":
        cards = store.list_cards()
        if not cards:
            return "No cards found on workboard."
        lines = [f"Cards ({len(cards)}):"]
        for c in cards:
            lines.append(f"  [{c.status}] {c.title} ({c.id})")
        return "\n".join(lines)

    if action == "boards":
        boards = store.list_boards()
        lines = [f"Boards ({len(boards)}):"]
        for b in boards:
            lines.append(f"  - {b.name} ({b.id})")
        return "\n".join(lines)

    return "Usage: jarvis workboard [status|list|boards]"


def repair_workboard_config(config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Doctor repair for workboard."""
    return config, []
