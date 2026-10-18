"""tests.test_desktop_host_interaction — Tests for Desktop Host App Interaction & Parity.

Covers:
- process tool: host process termination (taskkill/pkill), sessionId/session_id compatibility, list fallback.
- tool_argument_repair: healing process arguments and PowerShell scripts.
- desktop ui: single-source-of-truth logging in _send.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.agents.sessions.tools.process_tool import create_process_tool_definition
from src.agents.self_healing.strategies.tool_argument_repair import (
    ToolArgumentRepairStrategy,
)


@pytest.mark.asyncio
async def test_process_tool_kill_host_app_by_name():
    tool = create_process_tool_definition()
    execute = tool["execute"]

    # Test killing notepad using session_id via PowerShell wildcard first
    with patch("subprocess.run") as mock_run, patch("sys.platform", "win32"):
        mock_run.return_value = MagicMock(returncode=0, stdout="KILLED\n", stderr="")
        res = await execute("call-4", {"action": "kill", "session_id": "notepad"})
        assert res["details"]["killed"] is True
        assert "Successfully closed host application/process" in res["content"][0]["text"]
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "*notepad*" in cmd[3]


@pytest.mark.asyncio
async def test_process_tool_kill_not_found_idempotent_success():
    tool = create_process_tool_definition()
    execute = tool["execute"]

    # Test killing explorer when not running returns idempotent success (already closed)
    with patch("subprocess.run") as mock_run, patch("sys.platform", "win32"):
        mock_run.return_value = MagicMock(
            returncode=128,
            stdout="",
            stderr='ERROR: The process "explorer.exe" not found.',
        )
        res = await execute("call-4b", {"action": "kill", "session_id": "explorer"})
        assert res["details"]["killed"] is True
        assert res["details"]["already_closed"] is True
        assert "is not running (already closed)" in res["content"][0]["text"]


@pytest.mark.asyncio
async def test_process_tool_kill_terminal():
    tool = create_process_tool_definition()
    execute = tool["execute"]

    with patch("subprocess.run") as mock_run, patch("sys.platform", "win32"):
        mock_run.return_value = MagicMock(returncode=0, stdout="SUCCESS", stderr="")
        res = await execute("call-5", {"action": "kill", "sessionId": "terminal"})
        assert res["details"]["killed"] is True
        assert "Successfully closed terminal on PC" in res["content"][0]["text"]


@pytest.mark.asyncio
async def test_process_tool_list_guidance_when_empty():
    tool = create_process_tool_definition()
    execute = tool["execute"]

    res = await execute("call-6", {"action": "list"})
    text = res["content"][0]["text"]
    assert "No active background exec sessions found" in text
    assert "process(action='kill', session_id='<app_name>')" in text


def test_tool_argument_repair_process():
    strategy = ToolArgumentRepairStrategy()
    repaired, changes = strategy.repair_arguments(
        "process",
        {"action": "kill", "name": "notepad"},
    )
    assert repaired["session_id"] == "notepad"
    assert repaired["sessionId"] == "notepad"
    assert any("Mapped alias 'name' -> 'session_id'" in c for c in changes)


def test_ui_send_does_not_append_log_directly():
    from jarvis_desktop.ui import MainWindow

    with patch.object(MainWindow, "__init__", return_value=None):
        win = MainWindow("mock_face_path")
        win._input = MagicMock()
        win._input.text.return_value = "hello jarvis"
        win._log = MagicMock()
        win.on_text_command = MagicMock()

        MainWindow._send(win)

        # Ensure _input was cleared
        win._input.clear.assert_called_once()
        # Ensure _log.append_log was NOT called (app.py handles logging)
        win._log.append_log.assert_not_called()


@pytest.mark.asyncio
async def test_shutdown_jarvis_blocked_without_explicit_command():
    from jarvis_desktop.app import JarvisLive

    app = JarvisLive.__new__(JarvisLive)
    app.ui = MagicMock()
    app.ui.muted = False
    app._tool_loop_guard = MagicMock()
    app._tool_loop_guard.check_before.return_value = None

    fc = MagicMock()
    fc.name = "shutdown_jarvis"
    fc.args = {}
    fc.id = "call-1"

    # Test 1: Autonomous call with no args (model ending task goal)
    resp = await app._execute_tool(fc)
    assert isinstance(resp.response, dict)
    assert resp.response.get("error") is True
    assert "SHUTDOWN BLOCKED" in resp.response.get("result", "")

    # Test 2: Autonomous call with task completion context
    fc2 = MagicMock()
    fc2.name = "shutdown_jarvis"
    fc2.args = {"user_command": "Organized Downloads folder successfully", "confirmed": False}
    fc2.id = "call-2"
    resp2 = await app._execute_tool(fc2)
    assert isinstance(resp2.response, dict)
    assert resp2.response.get("error") is True
    assert "SHUTDOWN BLOCKED" in resp2.response.get("result", "")

    # Test 3: Explicit Nepali Devanagari command ("बंद गर्देउ।") with confirmed=True
    app.speak = MagicMock()
    with patch("threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        fc3 = MagicMock()
        fc3.name = "shutdown_jarvis"
        fc3.args = {"user_command": "बंद गर्देउ।", "confirmed": True}
        fc3.id = "call-3"
        resp3 = await app._execute_tool(fc3)
        assert isinstance(resp3.response, dict)
        assert resp3.response.get("error") is not True
        assert "Shutdown initiated" in resp3.response.get("result", "")

    # Test 4: Explicit romanized Nepali command ("banda gardeu") with confirmed=True
    with patch("threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        fc4 = MagicMock()
        fc4.name = "shutdown_jarvis"
        fc4.args = {"user_command": "banda gardeu", "confirmed": True}
        fc4.id = "call-4"
        resp4 = await app._execute_tool(fc4)
        assert isinstance(resp4.response, dict)
        assert resp4.response.get("error") is not True
        assert "Shutdown initiated" in resp4.response.get("result", "")


@pytest.mark.asyncio
async def test_read_tool_directory_raises_is_a_directory_error(tmp_path):
    from src.agents.sessions.tools.read import create_read_tool_definition

    test_dir = tmp_path / "test_folder"
    test_dir.mkdir()

    tool = create_read_tool_definition()
    execute = tool["execute"]

    with pytest.raises(IsADirectoryError) as excinfo:
        await execute("call-read-dir", {"path": str(test_dir)})
    assert "is a directory" in str(excinfo.value)
    assert "Use 'ls' to list its contents" in str(excinfo.value)


@pytest.mark.asyncio
async def test_tool_fallback_routes_directory_read_to_ls(tmp_path):
    from src.agents.self_healing.failure_event import ErrorCategory, FailureEvent
    from src.agents.self_healing.strategies.tool_fallback import ToolFallbackStrategy

    test_dir = tmp_path / "somedir"
    test_dir.mkdir()

    strategy = ToolFallbackStrategy()
    event = FailureEvent(
        category=ErrorCategory.TOOL_EXECUTION_ERROR,
        error_message=f"Read requires a file path, but '{test_dir}' is a directory.",
        context={"tool_name": "read", "args": {"path": str(test_dir)}},
    )

    assert await strategy.can_handle(event) is True
    res = await strategy.execute(event)
    assert res.success is True
    assert res.details["fallback_tool"] == "ls"
    assert res.details["fallback_args"] == {"path": str(test_dir)}


def test_tool_argument_repair_powershell_remove_item():
    strategy = ToolArgumentRepairStrategy()

    # 1. Piped temp cleanup without -ErrorAction
    raw_cmd1 = "Get-ChildItem -Path $env:TEMP -Recurse | Remove-Item -Force -Recurse"
    repaired1, changes1 = strategy.repair_arguments("exec", {"command": raw_cmd1})
    assert "-ErrorAction SilentlyContinue" in repaired1["command"]
    assert any("Added -ErrorAction SilentlyContinue to Remove-Item" in c for c in changes1)

    # 2. Directory cleanup missing -Recurse
    raw_cmd2 = (
        "Get-ChildItem -Path E:\\ -Recurse -Directory | "
        "Where-Object { (Get-ChildItem -Path $_.FullName -Force).Count -eq 0 } | "
        "Remove-Item -Force"
    )
    repaired2, changes2 = strategy.repair_arguments("exec", {"command": raw_cmd2})
    assert "-Recurse" in repaired2["command"]
    assert "-Force" in repaired2["command"]
    assert "-ErrorAction SilentlyContinue" in repaired2["command"]
    assert any("Added -Recurse to Remove-Item" in c for c in changes2)


def test_tool_argument_repair_powershell_wscript_and_loop():
    strategy = ToolArgumentRepairStrategy()
    broken_cmd = (
        " = New-Object -ComObject WScript.Shell; "
        "for(=0;  -lt 50; ++) { .SendKeys([char]174) }; "
        "for(=0;  -lt 40; ++) { .SendKeys([char]175) }"
    )
    repaired, changes = strategy.repair_arguments("exec", {"command": broken_cmd})
    cmd = repaired["command"]
    assert "$ws = New-Object" in cmd
    assert "for($i=0; $i -lt 50; $i++)" in cmd
    assert "$ws.SendKeys([char]174)" in cmd
    assert "for($i=0; $i -lt 40; $i++)" in cmd
    assert "$ws.SendKeys([char]175)" in cmd
    assert len(changes) >= 3


@pytest.mark.asyncio
async def test_browser_runtime_strict_mode_fallback():
    from extensions.browser.src.browser_profiles import resolve_browser_config
    from extensions.browser.src.browser_runtime import BrowserRuntime

    runtime = BrowserRuntime(resolve_browser_config({}))

    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.url = "https://www.youtube.com"
    mock_page.title = AsyncMock(return_value="YouTube")
    mock_page.evaluate = AsyncMock(return_value=False)

    mock_loc = MagicMock()
    # First call raises strict mode violation
    mock_loc.click.side_effect = Exception(
        "Locator.click: Error: strict mode violation: locator resolved to 36 elements"
    )
    # mock_loc.first.click succeeds
    mock_first = MagicMock()
    mock_first.first = mock_first
    mock_first.click = AsyncMock()
    mock_loc.first = mock_first

    mock_page.locator.return_value = mock_loc

    with patch.object(runtime, "get_page", return_value=mock_page):
        res = await runtime.act(selector="#video-title", kind="click")
        assert res["ok"] is True
        mock_first.click.assert_called_once()


@pytest.mark.asyncio
async def test_process_tool_kill_whatsapp_uwp():
    """Verify WhatsApp termination finds and kills UWP process (WhatsApp.Root)."""
    tool = create_process_tool_definition()
    execute = tool["execute"]

    with patch("subprocess.run") as mock_run, patch("sys.platform", "win32"):
        # Mock PowerShell finding and killing WhatsApp.Root
        mock_run.return_value = MagicMock(returncode=0, stdout="KILLED\n", stderr="")
        res = await execute("call-wa", {"action": "kill", "session_id": "whatsapp"})
        assert res["details"]["killed"] is True
        assert "Successfully closed host application/process" in res["content"][0]["text"]
        # Verify powershell command was run with wildcard matching
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "powershell" in cmd[0]
        assert "*whatsapp*" in cmd[3]


@pytest.mark.asyncio
async def test_process_tool_minimize_and_restore():
    """Verify window minimization and restore via native Shell.Application COM."""
    tool = create_process_tool_definition()
    execute = tool["execute"]

    with patch("subprocess.run") as mock_run, patch("sys.platform", "win32"):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        res_min = await execute("call-min", {"action": "minimize"})
        assert res_min["details"]["minimized"] is True
        assert "minimized all open windows" in res_min["content"][0]["text"]

        res_res = await execute("call-res", {"action": "restore"})
        assert res_res["details"]["restored"] is True
        assert "restored open windows" in res_res["content"][0]["text"]


@pytest.mark.asyncio
async def test_process_tool_list_apps():
    """Verify listing active desktop applications."""
    tool = create_process_tool_definition()
    execute = tool["execute"]

    with patch("subprocess.run") as mock_run, patch("sys.platform", "win32"):
        # Mock tasklist /apps and Get-Process output
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout='"Image Name","PID","Mem Usage","Package Name"\n"WhatsApp.exe","16164","50,000 K","5319275A.WhatsAppDesktop_1.0"\n',
            ),
            MagicMock(returncode=0, stdout="Notepad\nWindowsTerminal\n"),
        ]
        res = await execute("call-apps", {"action": "list_apps"})
        assert "WhatsApp" in res["content"][0]["text"]
        assert "Notepad" in res["content"][0]["text"]


@pytest.mark.asyncio
async def test_nepali_unicode_filename_lifecycle(tmp_path):
    """Verify writing, reading, and removing Nepali/Devanagari Unicode files (परिचय.txt)."""
    import os
    from src.agents.sessions.tools.read import read_text_file
    from src.agents.sessions.tools.write import write_file

    nepali_filename = tmp_path / "परिचय.txt"
    content = "नमस्ते, म जार्भिस हुँ।"

    # 1. Write Unicode file
    await write_file(str(nepali_filename), content)
    assert nepali_filename.exists()

    # 2. Read Unicode file
    read_res = read_text_file(str(nepali_filename))
    assert content in read_res["content"]

    # 3. Clean up Unicode file
    os.remove(str(nepali_filename))
    assert not nepali_filename.exists()


def test_tool_argument_repair_no_double_slashes():
    """Verify tool argument repair eliminates double-slashes and preserves clean drive syntax."""
    strategy = ToolArgumentRepairStrategy()
    repaired, changes = strategy.repair_arguments(
        "read", {"path": r"C:\Program Files\WindowsApps"}
    )
    # Must NOT produce C://
    assert repaired["path"] == "C:/Program Files/WindowsApps"
    assert "C://" not in repaired["path"]


def test_tool_argument_repair_minimize_wscript():
    """Verify tool argument repair fixes WScript minimize commands to native COM."""
    strategy = ToolArgumentRepairStrategy()
    broken_cmd = "New-Object -ComObject WScript.Shell; $ws.SendKeys('^{ESC}'); win+m"
    repaired, changes = strategy.repair_arguments("exec", {"command": broken_cmd})
    assert "(New-Object -ComObject Shell.Application).MinimizeAll()" in repaired["command"]


@pytest.mark.asyncio
async def test_browser_tab_reuse_same_domain():
    """Verify open_tab reuses existing open tab matching domain instead of creating duplicate."""
    from extensions.browser.src.browser_profiles import resolve_browser_config
    from extensions.browser.src.browser_runtime import BrowserRuntime, TabRecord

    runtime = BrowserRuntime(resolve_browser_config({}))

    mock_existing_page = MagicMock()
    mock_existing_page.is_closed.return_value = False
    mock_existing_page.url = "https://www.youtube.com/watch?v=123"
    mock_existing_page.title = AsyncMock(return_value="YouTube Existing")
    mock_existing_page.bring_to_front = AsyncMock()
    mock_existing_page.goto = AsyncMock()

    # Pre-register tab
    rec = TabRecord(target_id="tab_yt", page=mock_existing_page, url=mock_existing_page.url)
    runtime._tabs["tab_yt"] = rec

    # Call open_tab for another YouTube URL
    res = await runtime.open_tab(url="https://www.youtube.com/results?search_query=test")
    assert res["ok"] is True
    assert res.get("reused") is True
    assert res["targetId"] == "tab_yt"
    mock_existing_page.bring_to_front.assert_called_once()
    mock_existing_page.goto.assert_called_once()


def test_browser_profile_alias_resolution():
    """Verify smart browser profile alias resolution for 'chrome', 'user', and unknown fallbacks."""
    from extensions.browser.src.browser_profiles import resolve_browser_config, resolve_profile

    config = resolve_browser_config({})

    # 1. Alias "chrome" resolves to "jarvis"
    chrome_prof = resolve_profile(config, "chrome")
    assert chrome_prof is not None
    assert chrome_prof.name == "jarvis"

    # 2. Alias "user" resolves to "user"
    user_prof = resolve_profile(config, "user")
    assert user_prof is not None
    assert user_prof.name == "user"

    # 3. Default fallback for unknown custom profile
    fallback_prof = resolve_profile(config, "custom_nonexistent_profile")
    assert fallback_prof is not None
    assert fallback_prof.name == "jarvis"


def test_clear_chrome_singleton_artifacts(tmp_path):
    """Verify stale Chrome lock artifacts are purged before browser initialization."""
    from extensions.browser.src.browser_runtime import clear_chrome_singleton_artifacts

    lock_file = tmp_path / "SingletonLock"
    socket_file = tmp_path / "SingletonSocket"
    cookie_file = tmp_path / "SingletonCookie"
    lockfile = tmp_path / "lockfile"

    lock_file.write_text("lock")
    socket_file.write_text("sock")
    cookie_file.write_text("cook")
    lockfile.write_text("lockfile")

    assert lock_file.exists()
    assert socket_file.exists()
    assert cookie_file.exists()
    assert lockfile.exists()

    clear_chrome_singleton_artifacts(tmp_path)

    assert not lock_file.exists()
    assert not socket_file.exists()
    assert not cookie_file.exists()
    assert not lockfile.exists()


@pytest.mark.asyncio
async def test_process_tool_open_action():
    """Verify that calling process(action='open', session_id='notepad') launches application."""
    from src.agents.sessions.tools.process_tool import create_process_tool_definition

    process_tool = create_process_tool_definition()
    with patch("os.startfile", create=True) as mock_startfile:
        res = await process_tool["execute"](
            "call_proc_open",
            {"action": "open", "session_id": "notepad"}
        )
        assert res["details"]["launched"] is True
        assert "Successfully launched" in res["content"][0]["text"]
        mock_startfile.assert_called_once_with("notepad")


@pytest.mark.asyncio
async def test_jarvis_live_execute_tool_dispatches_process_and_coding_tools():
    """Verify JarvisLive._execute_tool successfully dispatches process and coding tools without legacy rejection."""
    from apps.desktop.src.jarvis_desktop.app import JarvisLive

    mock_ui = MagicMock()
    mock_ui.write_log = MagicMock()
    mock_ui.muted = False
    mock_ui.set_state = MagicMock()

    live = JarvisLive(mock_ui)

    # 1. process(action='open', session_id='notepad')
    fc_proc = MagicMock()
    fc_proc.name = "process"
    fc_proc.id = "call_p1"
    fc_proc.args = {"action": "open", "session_id": "notepad"}

    with patch("os.startfile", create=True):
        resp = await live._execute_tool(fc_proc)
        assert resp.name == "process"
        assert resp.response is not None
        assert "Tool 'process' is no longer available" not in str(resp.response["result"])
        assert "Successfully launched" in str(resp.response["result"])

    # 2. write(path='test.txt', content='hello')
    fc_write = MagicMock()
    fc_write.name = "write"
    fc_write.id = "call_w1"
    fc_write.args = {"path": "test.txt", "content": "hello"}

    with patch("src.agents.sessions.tools.write.write_file", new_callable=AsyncMock):
        resp_write = await live._execute_tool(fc_write)
        assert resp_write.name == "write"
        assert resp_write.response is not None
        assert resp_write.response.get("error") is not True


def test_codex_plugin_contracts_declared():
    """Verify that codex plugin manifest declares tools so loader does not skip them."""
    import json
    from pathlib import Path

    manifest_p = Path("extensions/codex/jarvis.plugin.json")
    assert manifest_p.exists()
    data = json.loads(manifest_p.read_text(encoding="utf-8"))
    contracts = data.get("contracts", {})
    tools = contracts.get("tools", [])
    assert "codex_threads" in tools
    assert "codex_plugins" in tools
