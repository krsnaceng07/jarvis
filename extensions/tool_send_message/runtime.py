"""Runtime helpers for tool_send_message.

Phase 1C: per-platform message senders. The plugin (``plugin.py``) is
a thin wrapper that dispatches on platform name; this module owns the
pyautogui-based automation.

Mirrors OpenClaw's per-extension ``runtime.ts`` pattern.
"""
from __future__ import annotations

import time
import webbrowser

import pyautogui  # type: ignore[import-not-found]


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.08


# ── App-launching primitive ────────────────────────────────────────


def _open_app(app_name: str) -> bool:
    """Open ``app_name`` via the OS Start/Spotlight menu (pyautogui)."""
    try:
        pyautogui.press("win")
        time.sleep(0.4)
        pyautogui.write(app_name, interval=0.04)
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(2.0)
        return True
    except Exception as e:
        print(f"[SendMessage] could not open {app_name}: {e}")
        return False


# ── Per-platform senders ──────────────────────────────────────────


def send_whatsapp(receiver: str, message: str) -> str:
    """Send via the WhatsApp Windows desktop app."""
    try:
        if not _open_app("WhatsApp"):
            return "Could not open WhatsApp."
        time.sleep(1.5)
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.4)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.write(receiver, interval=0.04)
        time.sleep(1.0)
        pyautogui.press("enter")
        time.sleep(0.8)
        pyautogui.write(message, interval=0.03)
        time.sleep(0.2)
        pyautogui.press("enter")
        return f"Message sent to {receiver} via WhatsApp."
    except Exception as e:
        return f"WhatsApp error: {e}"


def send_instagram(receiver: str, message: str) -> str:
    """Send via Instagram web DM (instagram.com/direct/new/)."""
    try:
        webbrowser.open("https://www.instagram.com/direct/new/")
        time.sleep(3.5)
        pyautogui.write(receiver, interval=0.05)
        time.sleep(1.5)
        pyautogui.press("down")
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.5)
        for _ in range(3):
            pyautogui.press("tab")
            time.sleep(0.1)
        pyautogui.press("enter")
        time.sleep(1.5)
        pyautogui.write(message, interval=0.04)
        time.sleep(0.2)
        pyautogui.press("enter")
        return f"Message sent to {receiver} via Instagram."
    except Exception as e:
        return f"Instagram error: {e}"


def send_telegram(receiver: str, message: str) -> str:
    """Send via the Telegram Windows desktop app."""
    try:
        if not _open_app("Telegram"):
            return "Could not open Telegram."
        time.sleep(1.5)
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.4)
        pyautogui.write(receiver, interval=0.04)
        time.sleep(1.0)
        pyautogui.press("enter")
        time.sleep(0.8)
        pyautogui.write(message, interval=0.03)
        time.sleep(0.2)
        pyautogui.press("enter")
        return f"Message sent to {receiver} via Telegram."
    except Exception as e:
        return f"Telegram error: {e}"


def send_generic(platform: str, receiver: str, message: str) -> str:
    """Fallback: open the named app, search contact, type, send.

    Works for Messenger, Discord, Signal, etc. — any app that supports
    Ctrl+F search + Enter to open a contact.
    """
    try:
        if not _open_app(platform):
            return f"Could not open {platform}."
        time.sleep(1.5)
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.4)
        pyautogui.write(receiver, interval=0.04)
        time.sleep(1.0)
        pyautogui.press("enter")
        time.sleep(0.8)
        pyautogui.write(message, interval=0.03)
        time.sleep(0.2)
        pyautogui.press("enter")
        return f"Message sent to {receiver} via {platform}."
    except Exception as e:
        return f"{platform} error: {e}"


__all__ = [
    "send_generic",
    "send_instagram",
    "send_telegram",
    "send_whatsapp",
]
