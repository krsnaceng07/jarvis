"""Runtime helpers for tool_open_app.

Phase 1C: pure-OS launching primitives. The actual ``subprocess`` and
``pyautogui`` calls live here; ``plugin.py`` only orchestrates
(alias-lookup → launch → report).
"""

# ruff: noqa: S110, S603, S607, PLC0415
# - S110: `try/except/pass` is intentional — each block is a "soft
#   fallback" that lets the next try-block attempt a different path.
# - S603: `subprocess.run` with a list-form command is the documented
#   safe pattern; the app_name comes from the LLM and is passed as
#   a positional arg, never shell-constructed.
# - S607: `xdg-open`, `gtk-launch`, etc. are intentional PATH lookups
#   for cross-platform app launching.
# - PLC0415: `import pyautogui` lives inside the fallback path because
#   pyautogui is an optional dependency (the plugin works without it).

from __future__ import annotations

import platform
import shutil
import subprocess
import time

# ── App name aliases (per OS) ────────────────────────────────────────
# Mirrors OpenClaw's per-extension `runtime-config.ts` pattern: a
# small table the host reads to resolve user-friendly app names
# (e.g. "vscode") into OS-specific binary names.
_APP_ALIASES: dict[str, dict[str, str]] = {
    "whatsapp": {"Windows": "WhatsApp", "Darwin": "WhatsApp", "Linux": "whatsapp"},
    "chrome": {"Windows": "chrome", "Darwin": "Google Chrome", "Linux": "google-chrome"},
    "google chrome": {"Windows": "chrome", "Darwin": "Google Chrome", "Linux": "google-chrome"},
    "firefox": {"Windows": "firefox", "Darwin": "Firefox", "Linux": "firefox"},
    "spotify": {"Windows": "Spotify", "Darwin": "Spotify", "Linux": "spotify"},
    "vscode": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
    "visual studio code": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
    "discord": {"Windows": "Discord", "Darwin": "Discord", "Linux": "discord"},
    "telegram": {"Windows": "Telegram", "Darwin": "Telegram", "Linux": "telegram"},
    "instagram": {"Windows": "Instagram", "Darwin": "Instagram", "Linux": "instagram"},
    "tiktok": {"Windows": "TikTok", "Darwin": "TikTok", "Linux": "tiktok"},
    "notepad": {"Windows": "notepad.exe", "Darwin": "TextEdit", "Linux": "gedit"},
    "calculator": {
        "Windows": "calc.exe",
        "Darwin": "Calculator",
        "Linux": "gnome-calculator",
    },
    "terminal": {
        "Windows": "cmd.exe",
        "Darwin": "Terminal",
        "Linux": "gnome-terminal",
    },
    "cmd": {"Windows": "cmd.exe", "Darwin": "Terminal", "Linux": "bash"},
    "explorer": {"Windows": "explorer.exe", "Darwin": "Finder", "Linux": "nautilus"},
    "file explorer": {
        "Windows": "explorer.exe",
        "Darwin": "Finder",
        "Linux": "nautilus",
    },
    "paint": {"Windows": "mspaint.exe", "Darwin": "Preview", "Linux": "gimp"},
    "word": {"Windows": "winword", "Darwin": "Microsoft Word", "Linux": "libreoffice --writer"},
    "excel": {"Windows": "excel", "Darwin": "Microsoft Excel", "Linux": "libreoffice --calc"},
    "powerpoint": {
        "Windows": "powerpnt",
        "Darwin": "Microsoft PowerPoint",
        "Linux": "libreoffice --impress",
    },
    "vlc": {"Windows": "vlc", "Darwin": "VLC", "Linux": "vlc"},
    "zoom": {"Windows": "Zoom", "Darwin": "zoom.us", "Linux": "zoom"},
    "slack": {"Windows": "Slack", "Darwin": "Slack", "Linux": "slack"},
    "steam": {"Windows": "steam", "Darwin": "Steam", "Linux": "steam"},
    "task manager": {
        "Windows": "taskmgr.exe",
        "Darwin": "Activity Monitor",
        "Linux": "gnome-system-monitor",
    },
}


def resolve_alias(app_name: str, system: str | None = None) -> str:
    """Return the OS-specific binary name for ``app_name`` (no launch)."""
    system = system or platform.system()
    return _APP_ALIASES.get(app_name.lower(), {}).get(system, app_name)


# ── Per-OS launchers ────────────────────────────────────────────────


def _launch_windows(app_name: str) -> bool:
    """Launch ``app_name`` on Windows. Tries ``os.startfile`` first,
    then pyautogui (Start-menu fallback)."""
    try:
        os_startfile = __import__("os").startfile  # type: ignore[attr-defined]
        os_startfile(app_name)
        time.sleep(1.0)
        return True
    except Exception:
        pass
    try:
        import pyautogui  # type: ignore[import-not-found]

        pyautogui.PAUSE = 0.1
        pyautogui.press("win")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(3.0)
        return True
    except Exception as e:
        print(f"[open_app] Windows launch failed: {e}")
        return False


def _launch_macos(app_name: str) -> bool:
    """Launch ``app_name`` on macOS via ``open -a`` then Spotlight."""
    try:
        result = subprocess.run(
            ["open", "-a", app_name], capture_output=True, timeout=8, check=False
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"], capture_output=True, timeout=8, check=False
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass
    try:
        import pyautogui  # type: ignore[import-not-found]

        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] macOS Spotlight failed: {e}")
        return False


def _launch_linux(app_name: str) -> bool:
    """Launch ``app_name`` on Linux. Tries ``which`` → ``xdg-open`` → ``gtk-launch``."""
    binary = (
        shutil.which(app_name)
        or shutil.which(app_name.lower())
        or shutil.which(app_name.lower().replace(" ", "-"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass
    try:
        subprocess.run(["xdg-open", app_name], capture_output=True, timeout=5, check=False)
        return True
    except Exception:
        pass
    try:
        desktop_name = app_name.lower().replace(" ", "-")
        subprocess.run(["gtk-launch", desktop_name], capture_output=True, timeout=5, check=False)
        return True
    except Exception:
        pass
    return False


_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin": _launch_macos,
    "Linux": _launch_linux,
}


def launch(app_name: str, system: str | None = None) -> bool:
    """Launch ``app_name`` on the current OS. Returns True on success.

    Phase 1C contract:
    - The launcher returns ``True`` if it *attempted* the launch
      (not necessarily confirmed the process is running).
    - The caller (``OpenAppPlugin``) wraps this in a ``Result``.
    - We never raise — every error is suppressed and reported as
      ``False``. See AGENTS.md §\"Reliability Invariants\".
    """
    system = system or platform.system()
    launcher = _LAUNCHERS.get(system)
    if launcher is None:
        return False
    try:
        return bool(launcher(app_name))
    except Exception as e:
        print(f"[open_app] launch error for {app_name!r}: {e}")
        return False


__all__ = ["launch", "resolve_alias"]
