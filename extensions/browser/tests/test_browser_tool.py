"""Tests for Browser tool and runtime matching OpenClaw architecture."""

import json
import pytest
from extensions.browser.src.browser_runtime import (
    find_system_chromium,
    get_browser_runtime,
    resolve_space_safe_temp_dir,
)
from extensions.browser.src.browser_tool import BrowserTool
from extensions.browser.src.browser_tool_schema import (
    AgentToolResult,
)


def test_browser_tool_schema_and_metadata():
    """Verify tool metadata and schema match OpenClaw AgentTool contract."""
    tool = BrowserTool()
    assert tool.name == "browser"
    assert "Automate a browser" in tool.description

    params = tool.parameters
    assert params["type"] == "object"
    assert "action" in params["properties"]
    assert "required" in params
    assert "action" in params["required"]

    actions = params["properties"]["action"]["enum"]
    expected_actions = [
        "doctor",
        "status",
        "start",
        "stop",
        "profiles",
        "tabs",
        "open",
        "close",
        "focus",
        "navigate",
        "snapshot",
        "screenshot",
        "text",
        "console",
        "errors",
        "act",
    ]
    for act in expected_actions:
        assert act in actions

    assert "targetUrl" in params["properties"]
    assert "url" in params["properties"]
    assert "targetId" in params["properties"]
    assert "snapshotFormat" in params["properties"]
    assert "maxChars" in params["properties"]
    assert "fullPage" in params["properties"]

    out_schema = tool.output_schema
    assert out_schema["type"] == "object"
    assert "ok" in out_schema["properties"]


def test_space_safe_temp_dir():
    """Verify safe temp directory points to a location with sufficient free disk space."""
    temp_dir = resolve_space_safe_temp_dir()
    assert temp_dir.exists()
    assert temp_dir.is_dir()


def test_chromium_detection():
    """Verify system Chromium / Chrome / Edge is detected on the host."""
    exec_path = find_system_chromium()
    assert exec_path is not None
    assert "chrome" in exec_path.lower() or "edge" in exec_path.lower()


@pytest.mark.asyncio
async def test_browser_tool_doctor_action():
    """Verify 'doctor' action performs complete diagnostic check."""
    tool = BrowserTool()
    res = await tool.execute("call_doctor", {"action": "doctor"})

    assert isinstance(res, AgentToolResult)
    data = json.loads(res.content[0].text)
    assert data["ok"] is True
    check_names = [c["name"] for c in data["checks"]]
    assert "playwright_installed" in check_names
    assert "chromium_executable" in check_names
    assert "storage_disk_space" in check_names


@pytest.mark.asyncio
async def test_browser_tool_status_and_profiles():
    """Verify 'status' and 'profiles' actions return proper metadata."""
    tool = BrowserTool()
    res_status = await tool.execute("call_status", {"action": "status"})
    assert isinstance(res_status, AgentToolResult)
    data_status = json.loads(res_status.content[0].text)
    assert data_status["ok"] is True
    assert data_status["profile"] == "openclaw"

    res_profiles = await tool.execute("call_profiles", {"action": "profiles"})
    assert isinstance(res_profiles, AgentToolResult)
    data_profiles = json.loads(res_profiles.content[0].text)
    assert data_profiles["ok"] is True
    profile_names = [p["name"] for p in data_profiles["profiles"]]
    assert "openclaw" in profile_names


@pytest.mark.asyncio
async def test_browser_tool_validation_errors():
    """Verify missing or invalid arguments produce expected exceptions."""
    tool = BrowserTool()

    with pytest.raises(ValueError, match="action is required"):
        await tool.execute("call_err", {})

    with pytest.raises(ValueError, match="not supported"):
        await tool.execute("call_err", {"action": "invalid_action_xyz"})

    with pytest.raises(ValueError, match="targetUrl or url is required"):
        await tool.execute("call_err", {"action": "navigate"})

    with pytest.raises(ValueError, match="kind is required"):
        await tool.execute("call_err", {"action": "act"})


@pytest.mark.asyncio
async def test_browser_tool_live_lifecycle_and_automation():
    """Verify end-to-end browser automation: open, snapshot, act, text, close."""
    tool = BrowserTool()
    runtime = await get_browser_runtime()

    html_payload = "data:text/html,<html><body><h1>JARVIS Browser Parity</h1><p>Running under OpenClaw design.</p><button id='btn' onclick='window.clicked=true'>Click Me</button></body></html>"

    try:
        # 1. Open tab
        open_res = await tool.execute("call_open", {"action": "open", "url": html_payload})
        assert isinstance(open_res, AgentToolResult)
        open_data = json.loads(open_res.content[0].text)
        assert open_data["ok"] is True
        target_id = open_data["targetId"]
        assert target_id is not None

        # 2. List tabs
        tabs_res = await tool.execute("call_tabs", {"action": "tabs"})
        tabs_data = json.loads(tabs_res.content[0].text)
        assert tabs_data["ok"] is True
        assert tabs_data["tabCount"] >= 1

        # 3. Snapshot (ARIA tree)
        snap_res = await tool.execute("call_snap", {"action": "snapshot", "targetId": target_id})
        snap_data = json.loads(snap_res.content[0].text)
        assert snap_data["ok"] is True
        assert (
            "JARVIS Browser Parity" in snap_data["snapshot"] or "Click Me" in snap_data["snapshot"]
        )

        # 4. Extract innerText
        text_res = await tool.execute("call_text", {"action": "text", "targetId": target_id})
        text_data = json.loads(text_res.content[0].text)
        assert text_data["ok"] is True
        assert "JARVIS Browser Parity" in text_data["text"]
        assert "OpenClaw design" in text_data["text"]

        # 5. Act - click button
        act_click = await tool.execute(
            "call_click",
            {"action": "act", "kind": "click", "selector": "#btn", "targetId": target_id},
        )
        click_data = json.loads(act_click.content[0].text)
        assert click_data["ok"] is True

        # 6. Act - evaluate javascript state
        act_eval = await tool.execute(
            "call_eval",
            {
                "action": "act",
                "kind": "evaluate",
                "fn": "() => window.clicked",
                "targetId": target_id,
            },
        )
        eval_data = json.loads(act_eval.content[0].text)
        assert eval_data["ok"] is True
        assert eval_data["result"] is True

        # 7. Screenshot capture
        shot_res = await tool.execute("call_shot", {"action": "screenshot", "targetId": target_id})
        assert isinstance(shot_res, AgentToolResult)
        assert shot_res.details["ok"] is True

        # 8. Close tab
        close_res = await tool.execute("call_close", {"action": "close", "targetId": target_id})
        close_data = json.loads(close_res.content[0].text)
        assert close_data["ok"] is True
        assert close_data["status"] == "closed"

    finally:
        await runtime.stop()
