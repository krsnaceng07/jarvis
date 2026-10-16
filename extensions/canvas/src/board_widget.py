"""Canvas board widget representation generator."""

from __future__ import annotations

from typing import Any


def generate_board_widget(
    board_id: str,
    title: str,
    columns: list[dict[str, Any]],
    cards: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate canvas document payload for a task board widget."""
    return {
        "kind": "board_widget",
        "boardId": board_id,
        "title": title,
        "columns": columns,
        "cards": cards,
        "cardCount": len(cards),
    }
