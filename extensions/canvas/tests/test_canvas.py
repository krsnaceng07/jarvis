"""Tests for canvas tool, A2UI JSONL, board widget, config, and doctor."""

from __future__ import annotations

import pytest

from extensions.canvas.src.a2ui_jsonl import format_a2ui_jsonl, parse_a2ui_jsonl
from extensions.canvas.src.board_widget import generate_board_widget
from extensions.canvas.src.config import resolve_canvas_config
from extensions.canvas.src.doctor import handle_canvas_cli, repair_canvas_config
from extensions.canvas.src.plugin import canvas_plugin
from extensions.canvas.src.tool import execute_canvas_tool


def test_canvas_descriptor() -> None:
    assert canvas_plugin.id == "canvas"
    assert canvas_plugin.kind == "tools"


def test_a2ui_jsonl_parser_and_formatter() -> None:
    events = [
        {"type": "init", "title": "Dashboard"},
        {"type": "update", "value": 42},
    ]
    formatted = format_a2ui_jsonl(events)
    assert '{"type": "init", "title": "Dashboard"}' in formatted
    assert '{"type": "update", "value": 42}' in formatted

    parsed = parse_a2ui_jsonl(formatted)
    assert len(parsed) == 2
    assert parsed[0]["title"] == "Dashboard"
    assert parsed[1]["value"] == 42


def test_board_widget_generation() -> None:
    cols = [{"id": "todo", "title": "To Do"}, {"id": "done", "title": "Done"}]
    cards = [{"id": "card-1", "title": "Task 1", "columnId": "todo"}]
    widget = generate_board_widget("board-123", "Sprint Board", cols, cards)
    assert widget["kind"] == "board_widget"
    assert widget["boardId"] == "board-123"
    assert widget["cardCount"] == 1


def test_canvas_config_and_doctor() -> None:
    cfg = resolve_canvas_config({"host": {"enabled": False}})
    assert cfg.host.enabled is False

    repaired, repairs = repair_canvas_config({"canvasHost": {"enabled": True}})
    assert repaired["host"]["enabled"] is True
    assert "canvasHost" not in repaired
    assert len(repairs) == 1

    cli_out = handle_canvas_cli(["status"], repaired)
    assert "Host enabled: True" in cli_out


@pytest.mark.asyncio
async def test_execute_canvas_tool_url() -> None:
    res = await execute_canvas_tool(
        {"action": "present", "url": "https://example.com", "target": "main"}
    )
    assert "Presented URL on canvas target 'main'" in res["content"][0]["text"]
    assert res["details"]["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_execute_canvas_tool_a2ui_content() -> None:
    a2ui_str = '{"type": "root", "title": "Stats"}\n{"type": "row"}'
    res = await execute_canvas_tool({"action": "present", "content": a2ui_str, "target": "stats"})
    assert (
        "Presented interactive A2UI widget on canvas 'stats' (2 events)"
        in res["content"][0]["text"]
    )


@pytest.mark.asyncio
async def test_execute_canvas_tool_hide() -> None:
    res = await execute_canvas_tool({"action": "hide", "target": "main"})
    assert "Hidden canvas target 'main'" in res["content"][0]["text"]
