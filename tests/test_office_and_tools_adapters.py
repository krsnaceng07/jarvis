"""Tests for VS Code, Antigravity, Office, Calculator, Settings, and Explorer adapters."""

import pytest
from unittest.mock import patch

from src.desktop_automation.applications.vscode import VSCodeDesktopAdapter
from src.desktop_automation.applications.antigravity import AntigravityDesktopAdapter
from src.desktop_automation.applications.calculator import CalculatorDesktopAdapter
from src.desktop_automation.applications.office import OfficeDesktopAdapter
from src.desktop_automation.applications.explorer import ExplorerDesktopAdapter
from src.desktop_automation.state.active_desktop_context import ActiveDesktopContext


@pytest.mark.asyncio
async def test_vscode_adapter_actions():
    adapter = VSCodeDesktopAdapter()
    ctx = ActiveDesktopContext()

    with patch.object(adapter, "hotkey", return_value=True),          patch.object(adapter, "type_text", return_value=True),          patch.object(adapter, "press_key", return_value=True):

        # Open file
        res_open = await adapter.execute_action("open_file", {"path": "src/main.py"}, ctx)
        assert res_open.ok is True
        assert res_open.evidence["path"] == "src/main.py"

        # Toggle terminal
        res_term = await adapter.execute_action("toggle_terminal", {}, ctx)
        assert res_term.ok is True

        # Save file
        res_save = await adapter.execute_action("save_file", {}, ctx)
        assert res_save.ok is True


@pytest.mark.asyncio
async def test_antigravity_adapter_actions():
    adapter = AntigravityDesktopAdapter()
    ctx = ActiveDesktopContext()

    with patch.object(adapter, "hotkey", return_value=True),          patch.object(adapter, "press_key", return_value=True),          patch.object(adapter, "get_clipboard_text", return_value=""),          patch.object(adapter, "set_clipboard_text", return_value=True):

        res = await adapter.execute_action("submit_prompt", {"text": "check tests"}, ctx)
        assert res.ok is True
        assert res.evidence["length"] == len("check tests")


@pytest.mark.asyncio
async def test_calculator_adapter_calculation():
    adapter = CalculatorDesktopAdapter()
    ctx = ActiveDesktopContext()

    with patch.object(adapter, "press_key", return_value=True),          patch.object(adapter, "type_text", return_value=True),          patch.object(adapter, "hotkey", return_value=True),          patch.object(adapter, "get_clipboard_text", return_value="42"):

        res = await adapter.execute_action("calculate", {"expression": "21*2"}, ctx)
        assert res.ok is True
        assert res.output_text == "42"
        assert res.evidence["result"] == "42"


@pytest.mark.asyncio
async def test_office_adapter_word_and_powerpoint():
    word = OfficeDesktopAdapter("word")
    ctx = ActiveDesktopContext()

    with patch.object(word, "hotkey", return_value=True),          patch.object(word, "get_clipboard_text", return_value=""),          patch.object(word, "set_clipboard_text", return_value=True):

        res_new = await word.execute_action("new_document", {}, ctx)
        assert res_new.ok is True

        res_text = await word.execute_action("insert_text", {"text": "Quarterly Report"}, ctx)
        assert res_text.ok is True

    ppt = OfficeDesktopAdapter("powerpoint")
    with patch.object(ppt, "press_key", return_value=True):
        res_show = await ppt.execute_action("start_slideshow", {}, ctx)
        assert res_show.ok is True


@pytest.mark.asyncio
async def test_explorer_adapter():
    explorer = ExplorerDesktopAdapter()
    ctx = ActiveDesktopContext()

    with patch.object(explorer, "hotkey", return_value=True),          patch.object(explorer, "type_text", return_value=True),          patch.object(explorer, "press_key", return_value=True):

        res_nav = await explorer.execute_action("navigate", {"path": "C:\\Users"}, ctx)
        assert res_nav.ok is True
        assert res_nav.evidence["path"] == "C:\\Users"
