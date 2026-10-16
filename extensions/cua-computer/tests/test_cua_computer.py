"""Unit tests for cua-computer extension."""

import asyncio
import pytest

from extensions.cua_computer.src.actions import (
    modifier_alias,
    normalize_key,
    normalize_modifiers,
)
from extensions.cua_computer.src.commands import create_cua_computer_provider


def test_modifier_alias():
    assert modifier_alias("ctrl", "linux") == "ctrl"
    assert modifier_alias("control", "linux") == "ctrl"
    assert modifier_alias("cmd", "darwin") == "cmd"
    assert modifier_alias("meta", "darwin") == "cmd"
    assert modifier_alias("meta", "linux") == "meta"
    assert modifier_alias("win", "win32") == "meta"


def test_normalize_modifiers():
    assert normalize_modifiers("ctrl+shift", "linux") == ["ctrl", "shift"]
    assert normalize_modifiers(None) == []
    with pytest.raises(ValueError, match="unknown modifier"):
        normalize_modifiers("invalidmod", "linux")


def test_normalize_key():
    assert normalize_key("Return", "linux") == "enter"
    assert normalize_key("ESC", "linux") == "escape"
    assert normalize_key("F5", "linux") == "f5"
    assert normalize_key("c", "linux") == "c"
    with pytest.raises(ValueError, match="key chord contains an empty key"):
        normalize_key("", "linux")
    with pytest.raises(ValueError, match="loses layout shift state"):
        normalize_key("!", "linux")


def test_provider_actions():
    provider = create_cua_computer_provider(platform="linux")

    # 1. Cursor position & move
    pos = asyncio.run(provider.execute_action("cursor_position", {}))
    assert pos == {"x": 0, "y": 0}

    move_res = asyncio.run(provider.execute_action("move", {"x": 200, "y": 150}))
    assert move_res == {"ok": True, "x": 200, "y": 150}

    # 2. Click
    click_res = asyncio.run(provider.execute_action("click", {}))
    assert click_res["ok"] is True
    assert click_res["x"] == 200
    assert click_res["button"] == "left"

    # 3. Type
    type_res = asyncio.run(provider.execute_action("type", {"text": "hello"}))
    assert type_res["ok"] is True
    assert type_res["text"] == "hello"

    # 4. Key
    key_res = asyncio.run(provider.execute_action("key", {"key": "enter", "modifiers": "ctrl"}))
    assert key_res["ok"] is True
    assert key_res["key"] == "enter"
    assert key_res["modifiers"] == ["ctrl"]

    # 5. Screenshot
    snap_res = asyncio.run(provider.execute_action("screenshot", {}))
    assert snap_res["ok"] is True
    assert snap_res["format"] == "png"
