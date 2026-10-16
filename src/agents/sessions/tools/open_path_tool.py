"""jarvis.agents.sessions.tools.open_path_tool — Built-in open_path tool.

Provides explicit system opening capability for Windows File Explorer, logical drives,
user directories (Downloads, Desktop, Documents), local files, and host applications.
Ensures JARVIS never attempts to use the browser tool for local folders or File Explorer.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Optional
import webbrowser

from ..extensions.types import AgentToolResult, ToolDefinition
from .path_utils import is_drive_available, resolve_to_cwd, resolve_unicode_path

WEB_SERVICE_ALIASES: dict[str, str] = {
    "google": "https://www.google.com",
    "google search": "https://www.google.com",
    "google one": "https://one.google.com",
    "googleone": "https://one.google.com",
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "deepseek": "https://www.deepseek.com",
    "deepseek ai": "https://www.deepseek.com",
    "deepseekai": "https://www.deepseek.com",
}
_WEB_ALIASES = WEB_SERVICE_ALIASES


def create_open_path_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for the open_path tool."""

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")

        raw_target = str(params.get("target", "")).strip()
        if not raw_target:
            raise ValueError("target is required")

        # Normalize target: strip quotes, leading command verbs, and trailing host qualifiers
        target = raw_target.strip("'\"`")
        target = re.sub(r"^(?:open|launch|start|run)\s+", "", target, flags=re.IGNORECASE).strip()
        target = re.sub(
            r"\s+on\s+(?:the\s+)?(?:pc|computer|windows|host)$", "", target, flags=re.IGNORECASE
        ).strip()
        target = re.sub(r"\s+in\s+windows$", "", target, flags=re.IGNORECASE).strip()
        if not target:
            target = raw_target

        norm_lower = target.lower().strip()
        user_home = Path.home()

        # 1. Direct File Explorer launch
        if norm_lower in ("explorer", "file explorer", "explorer.exe", "file_explorer"):
            if sys.platform == "win32":
                subprocess.Popen(["explorer.exe"])
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "File Explorer opened successfully on host PC.",
                        }
                    ],
                    "details": {"target": "explorer", "opened": True},
                }
            else:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"File Explorer is a Windows feature; current platform is {sys.platform}.",
                        }
                    ],
                    "details": {"target": target, "opened": False},
                }

        # 2. Known user directory aliases
        known_dirs = {
            "downloads": user_home / "Downloads",
            "desktop": user_home / "Desktop",
            "documents": user_home / "Documents",
            "pictures": user_home / "Pictures",
            "music": user_home / "Music",
            "videos": user_home / "Videos",
            "home": user_home,
        }

        resolved_path: Optional[str] = None
        if norm_lower in known_dirs:
            resolved_path = str(known_dirs[norm_lower])
        if norm_lower in WEB_SERVICE_ALIASES:
            url_to_open = WEB_SERVICE_ALIASES[norm_lower]
            webbrowser.open(url_to_open)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Successfully opened {norm_lower.title()} ({url_to_open}) in default browser.",
                    }
                ],
                "details": {
                    "target": target,
                    "url": url_to_open,
                    "opened": True,
                    "type": "web_service",
                },
            }
        elif target.startswith("http://") or target.startswith("https://"):
            webbrowser.open(target)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"URL opened in default browser: {target}",
                    }
                ],
                "details": {"target": target, "opened": True, "type": "url"},
            }
        else:
            # Check drive availability on Windows if target looks like a drive
            if not is_drive_available(target):
                raise FileNotFoundError(
                    f"Drive not available on this host: {target}. "
                    f"Please verify available drives with 'ls(path=\"drives\")'."
                )
            # Resolve relative against cwd or expand ~ with Unicode & home normalization
            candidate = resolve_unicode_path(target, cwd or os.getcwd())
            if os.path.exists(candidate):
                resolved_path = candidate

        # 3. Handle resolved filesystem path (directory or file)
        if resolved_path:
            if sys.platform == "win32":
                if os.path.isdir(resolved_path):
                    subprocess.Popen(["explorer.exe", resolved_path])
                else:
                    try:
                        os.startfile(resolved_path)  # type: ignore[attr-defined]
                    except Exception:
                        subprocess.Popen(["explorer.exe", "/select,", resolved_path])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", resolved_path])
            else:
                subprocess.Popen(["xdg-open", resolved_path])

            target_type = "folder" if os.path.isdir(resolved_path) else "file"
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Successfully opened {target_type} at '{resolved_path}' on host PC.",
                    }
                ],
                "details": {
                    "target": target,
                    "resolved_path": resolved_path,
                    "type": target_type,
                    "opened": True,
                },
            }

        # 4. Handle known system application names (e.g. terminal, notepad, calc)
        if sys.platform == "win32":
            wt_path = shutil.which("wt") or shutil.which("wt.exe") or "wt.exe"
            ps_path = shutil.which("powershell") or "powershell.exe"
            known_apps = {
                "terminal": wt_path,
                "windows terminal": wt_path,
                "windowsterminal": wt_path,
                "wt": wt_path,
                "cmd": "cmd.exe",
                "powershell": ps_path,
                "pwsh": shutil.which("pwsh") or ps_path,
                "notepad": "notepad.exe",
                "calc": "calc.exe",
                "calculator": "calc.exe",
                "mspaint": "mspaint.exe",
                "paint": "mspaint.exe",
                "taskmgr": "taskmgr.exe",
                "task manager": "taskmgr.exe",
                "control": "control.exe",
                "control panel": "control.exe",
                "edge": "msedge.exe",
                "msedge": "msedge.exe",
                "chrome": "chrome.exe",
                "whatsapp": "whatsapp:",
                "spotify": "spotify:",
                "discord": "discord:",
            }
            if shutil.which("code.cmd"):
                known_apps["code"] = "code.cmd"
                known_apps["vscode"] = "code.cmd"
            elif shutil.which("code"):
                known_apps["code"] = "code"
                known_apps["vscode"] = "code"

            app_cmd = known_apps.get(norm_lower)
            if not app_cmd:
                app_cmd = (
                    shutil.which(target)
                    or shutil.which(f"{target}.exe")
                    or shutil.which(f"{target}.cmd")
                )

            if not app_cmd and not os.path.exists(target):
                # Search Windows Start Apps (UWP / Store app like WhatsApp, Slack, Spotify, etc.)
                try:
                    ps_cmd = (
                        f"Get-StartApps -Name '*{target}*' | "
                        "Select-Object -First 1 -ExpandProperty AppID"
                    )
                    res = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", ps_cmd],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    app_id = res.stdout.strip()
                    if app_id:
                        app_cmd = ["explorer.exe", f"shell:AppsFolder\\{app_id}"]
                except Exception:
                    pass

            if not app_cmd and not os.path.exists(target):
                # Smart editor intent: if user or model specifies 'notepad.py', 'test.py', or starts with 'notepad'
                # launch Notepad to create/edit the file rather than raising FileNotFoundError
                if norm_lower in ("notepad.py", "notepad.exe"):
                    app_cmd = "notepad.exe"
                elif norm_lower.startswith("notepad") or norm_lower.endswith(
                    (".txt", ".md", ".json")
                ):
                    file_target = resolve_to_cwd(target, cwd or os.getcwd())
                    # If target starts with 'notepad ', strip 'notepad ' prefix
                    clean_file = re.sub(r"^notepad\s+", "", target, flags=re.IGNORECASE).strip()
                    if clean_file:
                        file_target = resolve_to_cwd(clean_file, cwd or os.getcwd())
                    app_cmd = ["notepad.exe", file_target]
                else:
                    raise FileNotFoundError(
                        f"Target '{raw_target}' not found on host filesystem or registered applications."
                    )

            target_cmd = app_cmd or target
            opened_label = "notepad" if norm_lower in ("notepad.py", "notepad.exe") else raw_target
            try:
                proc = None
                if isinstance(target_cmd, list):
                    proc = subprocess.Popen(target_cmd)
                elif str(target_cmd).endswith(":"):
                    try:
                        os.startfile(str(target_cmd))  # type: ignore[attr-defined]
                    except Exception:
                        proc = subprocess.Popen(["cmd.exe", "/c", "start", "", str(target_cmd)])
                elif os.path.isabs(str(target_cmd)) or shutil.which(str(target_cmd)):
                    proc = subprocess.Popen([str(target_cmd)])
                else:
                    proc = subprocess.Popen(str(target_cmd), shell=True)

                # Brief probe to verify process did not exit with immediate failure code
                if proc is not None:
                    time.sleep(0.15)
                    ret = proc.poll()
                    if ret is not None and ret != 0:
                        raise RuntimeError(
                            f"Command '{target_cmd}' exited immediately with error code {ret}."
                        )

                # Bring window to foreground and focus (Windows UI assurance)
                found_win = None
                clean_app = norm_lower.removesuffix(".exe").removesuffix(":")
                try:
                    from src.desktop_automation.discovery.window_detector import WindowDetector
                    from src.desktop_automation.discovery.window_manager import WindowManager
                    from src.desktop_automation.state.global_state_tracker import GlobalStateTracker

                    for _ in range(8):  # Poll up to 1.6s
                        time.sleep(0.2)
                        wins = WindowDetector.find_windows_by_process(clean_app) or WindowDetector.find_windows_by_title(clean_app)
                        if wins:
                            visible = [w for w in wins if w.is_visible and not w.is_minimized]
                            found_win = visible[0] if visible else wins[0]
                            break

                    ctx = GlobalStateTracker.get_context()
                    ctx.active_application = opened_label.title()
                    if found_win:
                        try:
                            WindowManager.focus_window(found_win.hwnd)
                        except Exception:
                            pass
                        ctx.active_window_title = found_win.title
                        ctx.active_hwnd = found_win.hwnd
                        ctx.active_pid = found_win.pid
                        ctx.workflow_stage = "app_opened"
                        return {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Successfully launched and brought to front: '{opened_label}' (Window: '{found_win.title}').",
                                }
                            ],
                            "details": {
                                "target": opened_label,
                                "app_cmd": str(target_cmd),
                                "launched": True,
                                "window_title": found_win.title,
                                "hwnd": found_win.hwnd,
                            },
                        }
                    else:
                        ctx.workflow_stage = "app_launched_pending_ui"
                except Exception:
                    pass

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Successfully launched application command for '{opened_label}', but no foreground window was verified yet. "
                                "Observe the live screen or process list before claiming it opened."
                            ),
                        }
                    ],
                    "details": {
                        "target": opened_label,
                        "app_cmd": str(target_cmd),
                        "launched": True,
                        "opened": False,
                        "verification": "pending_window",
                    },
                }
            except Exception as launch_err:
                raise RuntimeError(
                    f"Could not open or launch '{raw_target}': {launch_err}"
                ) from launch_err

        elif sys.platform == "darwin":
            try:
                subprocess.Popen(["open", "-a", target])
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Successfully launched application '{raw_target}'.",
                        }
                    ],
                    "details": {"target": raw_target, "launched": True},
                }
            except Exception as err:
                raise RuntimeError(f"Could not launch application '{raw_target}': {err}") from err
        else:
            cmd = shutil.which(target)
            if cmd:
                subprocess.Popen([cmd])
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Successfully launched application '{raw_target}'.",
                        }
                    ],
                    "details": {"target": raw_target, "launched": True},
                }

        raise FileNotFoundError(
            f"Target '{raw_target}' not found on host filesystem or applications."
        )

    return {
        "name": "open_path",
        "description": (
            "Open a local folder, file, drive, or application on the host PC in Windows File Explorer or the default application. "
            "Examples: target='explorer', target='terminal', target='notepad', target='calc', target='E:\\', target='Downloads', target='C:\\Users\\...\\Desktop'. "
            "Use this tool whenever the user asks to open File Explorer, open a terminal, open a folder, explore a drive, or launch a desktop application. "
            "Do NOT use the browser tool for local folders or File Explorer."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "target": {
                    "type": "STRING",
                    "description": (
                        "The folder path, drive (e.g. 'E:\\', 'C:\\'), user directory ('Downloads', 'Desktop', 'Documents'), "
                        "application name ('explorer', 'notepad', 'calc'), or file path to open."
                    ),
                },
            },
            "required": ["target"],
        },
        "execute": _execute,
    }


def create_open_path_tool(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Convenience alias matching create_write_tool / create_ls_tool naming."""
    return create_open_path_tool_definition(cwd=cwd, options=options)


__all__ = [
    "create_open_path_tool",
    "create_open_path_tool_definition",
]
