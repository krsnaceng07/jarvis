"""Tests for desktop application process and window discovery, focus, and reuse."""

import pytest
from unittest.mock import patch

from src.desktop_automation.discovery.process_detector import ProcessDetector
from src.desktop_automation.discovery.window_detector import WindowInfo
from src.desktop_automation.discovery.window_manager import WindowManager
from src.desktop_automation.discovery.application_registry import ApplicationRegistry


def test_application_registry_lookup():
    wa = ApplicationRegistry.get("whatsapp")
    assert wa is not None
    assert wa.app_id == "whatsapp"
    assert "WhatsApp.Root.exe" in wa.process_names

    calc = ApplicationRegistry.get("calculator")
    assert calc is not None
    assert "CalculatorApp.exe" in calc.process_names or "calc.exe" in calc.process_names

    # Reverse lookup by process name
    found = ApplicationRegistry.find_by_process_or_title("WhatsApp.Root.exe", "WhatsApp")
    assert found is not None
    assert found.app_id == "whatsapp"

    # Reverse lookup by window title
    found_title = ApplicationRegistry.find_by_process_or_title("unknown.exe", "Visual Studio Code - project")
    assert found_title is not None
    assert found_title.app_id == "vscode"


def test_process_detector():
    detector = ProcessDetector()
    procs = detector.list_processes()
    assert isinstance(procs, list)

    # Mock process lookup
    with patch.object(ProcessDetector, "list_processes", return_value=[{"pid": 1234, "name": "WhatsApp.exe"}]), \
         patch.object(ProcessDetector, "get_process_by_pid", return_value={"pid": 1234, "name": "WhatsApp.exe"}):
        assert detector.is_process_running("WhatsApp.exe") is True
        assert detector.is_process_running("nonexistent.exe") is False
        proc = detector.get_process_by_pid(1234)
        assert proc is not None
        assert proc["name"] == "WhatsApp.exe"


def test_window_info_serialization():
    win = WindowInfo(
        hwnd=65536,
        pid=1234,
        title="WhatsApp",
        rect={"left": 0, "top": 0, "right": 800, "bottom": 600, "width": 800, "height": 600},
        is_visible=True,
        is_minimized=False,
    )
    d = win.to_dict()
    assert d["hwnd"] == 65536
    assert d["title"] == "WhatsApp"
    assert d["is_visible"] is True
    assert d["rect"]["width"] == 800


def test_window_manager_responsiveness():
    # Responsiveness check does not raise exception
    assert WindowManager.is_responsive(0) is True


@pytest.mark.asyncio
async def test_window_manager_focus_window():
    with patch("src.desktop_automation.discovery.window_manager.user32") as mock_user32:
        mock_user32.IsIconic.return_value = 1
        mock_user32.ShowWindow.return_value = 1
        mock_user32.SetForegroundWindow.return_value = 1
        mock_user32.BringWindowToTop.return_value = 1

        res = await WindowManager.focus_window_async(12345)
        assert res is True
        mock_user32.ShowWindow.assert_called()
        mock_user32.SetForegroundWindow.assert_called_with(12345)


def test_window_detector_find_methods():
    from src.desktop_automation.discovery.window_detector import WindowDetector

    mock_wins = [
        WindowInfo(hwnd=101, pid=5001, title="WhatsApp", rect={}, is_visible=True, is_minimized=False),
        WindowInfo(hwnd=102, pid=5002, title="Visual Studio Code", rect={}, is_visible=True, is_minimized=False),
        WindowInfo(hwnd=103, pid=5003, title="Calculator", rect={}, is_visible=False, is_minimized=True),
    ]

    with patch.object(WindowDetector, "list_windows", return_value=mock_wins):
        # By title
        wa_wins = WindowDetector.find_windows_by_title("whats")
        assert len(wa_wins) == 1
        assert wa_wins[0].hwnd == 101

        # By PID
        pid_wins = WindowDetector.find_windows_by_pid(5002)
        assert len(pid_wins) == 1
        assert pid_wins[0].title == "Visual Studio Code"

        # By process (with PID match)
        with patch.object(ProcessDetector, "find_processes_by_name", return_value=[{"pid": 5001, "name": "WhatsApp.exe"}]):
            proc_wins = WindowDetector.find_windows_by_process("WhatsApp.exe")
            assert len(proc_wins) == 1
            assert proc_wins[0].hwnd == 101

        # By process (with title fallback when process PID not in top windows)
        with patch.object(ProcessDetector, "find_processes_by_name", return_value=[]):
            proc_wins_fb = WindowDetector.find_windows_by_process("WhatsApp.Root.exe")
            assert len(proc_wins_fb) == 1
            assert proc_wins_fb[0].title == "WhatsApp"


@pytest.mark.asyncio
async def test_whatsapp_adapter_action_aliases():
    from src.desktop_automation.applications.whatsapp import WhatsAppDesktopAdapter
    from src.desktop_automation.state.active_desktop_context import ActiveDesktopContext
    adapter = WhatsAppDesktopAdapter()
    ctx = ActiveDesktopContext()
    
    # whatsapp_send and send actions map cleanly without throwing unrecognized error
    with patch.object(adapter, "action_send_message", return_value="mock_result") as mock_send:
        res1 = await adapter.execute_action("whatsapp_send", {"recipient": "Alice", "message": "Hi"}, ctx)
        assert res1 == "mock_result"
        mock_send.assert_called()

        mock_send.reset_mock()
        res2 = await adapter.execute_action("send", {"recipient": "Alice", "message": "Hi"}, ctx)
        assert res2 == "mock_result"
        mock_send.assert_called()

