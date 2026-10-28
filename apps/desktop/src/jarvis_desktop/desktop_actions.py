"""Native desktop action execution for the desktop host.

Mechanically extracted from ``tool_pipeline`` (Phase 2 split) so that module
stays under the 2000-line limit. Bodies are unchanged; ``tool_pipeline``
re-exports ``execute_desktop_action`` for the host and its tests.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

_desktop_tier_router: Any = None


def get_desktop_tier_router() -> Any:
    """Return singleton instance of TierRouter with attached CursorOverlayWindow."""
    global _desktop_tier_router
    if _desktop_tier_router is None:
        try:
            from extensions.cua_computer.src.router import TierRouter

            from .cursor_overlay import attach_overlay_to_router

            _desktop_tier_router = TierRouter()
            attach_overlay_to_router(_desktop_tier_router)
        except Exception:
            _desktop_tier_router = None
    return _desktop_tier_router


_LAST_WHATSAPP_SEND: dict[str, Any] = {
    "time": 0.0,
    "recipient": "",
    "message": "",
    "idempotency_key": "",
}


async def execute_auto_control(args: dict[str, Any]) -> str:
    """Route a high-level computer-control task through the best available channel."""
    # Check if target is a browser action
    raw_action = str(args.get("action", "")).strip().lower()
    if (
        raw_action in ("browser", "navigate", "open_tab", "click_web", "type_web")
        or "url" in args
        or "targetUrl" in args
    ):
        try:
            from extensions.browser.src.browser_tool import BrowserTool

            browser = BrowserTool()
            result = await browser.execute("desktop_auto_control", args)
            payload = result.details if result.details is not None else {}
            if result.content:
                first = result.content[0]
                payload = payload or {"text": getattr(first, "text", "")}
            return json.dumps(
                {
                    "ok": True,
                    "channel": "browser_dom",
                    "result": payload,
                },
                ensure_ascii=False,
            )
        except Exception as err:
            return json.dumps(
                {"ok": False, "channel": "browser_dom", "error": str(err)}, ensure_ascii=False
            )

    return await execute_desktop_action(args)


async def execute_desktop_action(args: dict[str, Any]) -> str:
    """Execute native desktop automation action with resilient OS window and input support."""
    action = str(args.get("action", "")).strip().lower()
    app_name = str(
        args.get("app_name")
        or args.get("application")
        or args.get("target")
        or args.get("title")
        or args.get("name")
        or ""
    ).strip()

    if action in ("auto_control", "human_control", "computer_control"):
        return await execute_auto_control(args)

    # Native Real-Time Host Clock & Nepal Standard Time Queries
    if action in (
        "get_time",
        "time",
        "current_time",
        "get_current_time",
        "clock",
        "date",
        "get_date",
        "current_date",
    ):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        try:
            npt_zone = ZoneInfo("Asia/Kathmandu")
            now_npt = datetime.now(npt_zone)
        except Exception:
            now_npt = datetime.now()

        now_local = datetime.now()
        npt_time_12h = now_npt.strftime("%I:%M:%S %p")
        npt_time_24h = now_npt.strftime("%H:%M:%S")
        npt_date = now_npt.strftime("%A, %B %d, %Y")

        data = {
            "status": "success",
            "nepal_time": npt_time_12h,
            "nepal_time_24h": npt_time_24h,
            "nepal_date": npt_date,
            "timezone": "Asia/Kathmandu (NPT, UTC+5:45)",
            "host_local_time": now_local.strftime("%I:%M:%S %p"),
            "iso_timestamp": now_npt.isoformat(),
            "formatted": f"Current Nepal Time: {npt_time_12h} ({npt_date}, Nepal Standard Time)",
        }
        return json.dumps(data, ensure_ascii=False)

    # Native Audio Volume & Mute Controls
    if action in ("set_volume", "volume", "adjust_volume", "get_volume", "mute", "unmute"):
        from src.system.audio_controller import AudioController

        ac = AudioController.get_instance()
        if action == "get_volume":
            res = ac.get_volume()
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        if action == "mute":
            res = ac.set_mute(True)
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        if action == "unmute":
            res = ac.set_mute(False)
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        if action == "adjust_volume":
            raw_delta = args.get("delta") if args.get("delta") is not None else args.get("value")
            try:
                delta_pct = int(raw_delta) if raw_delta is not None else 10
            except (ValueError, TypeError):
                delta_pct = 10
            res = ac.adjust_volume(delta_pct)
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        raw_val = (
            args.get("value")
            if args.get("value") is not None
            else args.get("volume")
            if args.get("volume") is not None
            else args.get("level")
            if args.get("level") is not None
            else args.get("percent")
        )
        if raw_val is None:
            res = ac.get_volume()
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        try:
            target_pct = int(raw_val)
        except (ValueError, TypeError):
            target_pct = 50
        res = ac.set_volume(target_pct)
        return res.get("formatted") or json.dumps(res, ensure_ascii=False)

    # Native Display Brightness Controls
    if action in ("set_brightness", "brightness", "adjust_brightness", "get_brightness"):
        from src.system.brightness_controller import BrightnessController

        bc = BrightnessController.get_instance()
        if action == "get_brightness":
            res = await bc.get_brightness_async()
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        if action == "adjust_brightness":
            raw_delta = args.get("delta") if args.get("delta") is not None else args.get("value")
            try:
                delta_pct = int(raw_delta) if raw_delta is not None else 10
            except (ValueError, TypeError):
                delta_pct = 10
            res = await bc.adjust_brightness_async(delta_pct)
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        raw_val = (
            args.get("value")
            if args.get("value") is not None
            else args.get("brightness")
            if args.get("brightness") is not None
            else args.get("level")
            if args.get("level") is not None
            else args.get("percent")
        )
        if raw_val is None:
            res = await bc.get_brightness_async()
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        try:
            target_pct = int(raw_val)
        except (ValueError, TypeError):
            target_pct = 50
        res = await bc.set_brightness_async(target_pct)
        return res.get("formatted") or json.dumps(res, ensure_ascii=False)

    # Antigravity parity: Redirect web / browser automation away from blind OS pyautogui clicks to Selenium DOM
    is_web_intent = (
        action
        in (
            "google_search",
            "youtube_play",
            "navigate",
            "extract_text",
            "snapshot_dom",
            "browser",
            "browse",
        )
        or any(k in args for k in ("url", "targetUrl", "link", "query", "search_query"))
        or any(
            w in app_name.lower()
            for w in (
                "chrome",
                "google-chrome",
                "browser",
                "youtube",
                "edge",
                "firefox",
                "chatgpt",
                "openai",
                "facebook",
                "instagram",
                "twitter",
                "reddit",
                "linkedin",
                "github",
                "gmail",
            )
        )
        or any(w in action for w in ("youtube", "google", "web_"))
    )
    if is_web_intent:
        try:
            from extensions.browser.src.browser_tool import BrowserTool

            browser = BrowserTool()
            b_args = dict(args)
            if "action" not in b_args or b_args["action"] in (
                "open_app",
                "launch_app",
                "launch",
                "open",
                "start",
                "focus_app",
            ):
                t_raw = app_name or str(b_args.get("target") or b_args.get("url") or "")
                t_low = t_raw.lower().strip()
                web_app_urls = {
                    "youtube": "https://www.youtube.com",
                    "yt": "https://www.youtube.com",
                    "google": "https://www.google.com",
                    "chatgpt": "https://chatgpt.com",
                    "openai": "https://chatgpt.com",
                    "facebook": "https://www.facebook.com",
                    "fb": "https://www.facebook.com",
                    "twitter": "https://x.com",
                    "x": "https://x.com",
                    "instagram": "https://www.instagram.com",
                    "reddit": "https://www.reddit.com",
                    "linkedin": "https://www.linkedin.com",
                    "github": "https://github.com",
                    "gmail": "https://mail.google.com",
                }
                b_args["action"] = "open"
                b_args["url"] = web_app_urls.get(t_low) or (
                    f"https://{t_raw}" if not t_raw.startswith(("http://", "https://")) else t_raw
                )
                if t_low in web_app_urls:
                    b_args["label"] = t_low
            b_res = await browser.execute("desktop_auto_control", b_args)
            p_text = (
                b_res.content[0].text
                if getattr(b_res, "content", None) and hasattr(b_res.content[0], "text")
                else str(b_res)
            )
            return p_text
        except Exception as exc:
            return json.dumps(
                {"status": "error", "error": f"Browser action failed: {exc}"}, ensure_ascii=False
            )

    # 0. Intelligent parameter normalization & auto-repair (OpenClaw parity)
    if "recipient" in args:
        msg = args.get("message") or args.get("text")
        if msg:
            args["message"] = msg
            if action in (
                "generic",
                "send",
                "send_message",
                "message",
                "",
            ) or not action.startswith("whatsapp_"):
                action = "whatsapp_send"
                args["action"] = "whatsapp_send"
        elif action in ("generic", "search", "open", "chat", "") or not action.startswith(
            "whatsapp_"
        ):
            action = "whatsapp_search"
            args["action"] = "whatsapp_search"

    # 1. WhatsApp shortcuts
    if action.startswith("whatsapp_"):
        sub_action = action.replace("whatsapp_", "")
        recipient = str(args.get("recipient") or args.get("target") or "").strip()
        msg = str(args.get("message") or args.get("text") or "").strip()

        if sub_action != "send":
            return (
                f"WhatsApp action '{sub_action}' is not supported here. "
                "Use action='whatsapp_send' with a phone number or JID recipient."
            )
        if not recipient or not msg:
            return "WhatsApp send requires both 'recipient' and 'message'."

        digits = "".join(c for c in recipient if c.isdigit())
        if "@" not in recipient and len(digits) < 8:
            return (
                f"WhatsApp cannot resolve '{recipient}' to a chat. Use a phone number "
                "with country code (e.g. +97798XXXXXXXX) or a full WhatsApp JID."
            )

        idempotency_key = str(
            args.get("idempotency_key") or args.get("_tool_call_id") or args.get("_turn_id") or ""
        ).strip()
        now = time.time()
        if (
            idempotency_key
            and _LAST_WHATSAPP_SEND.get("idempotency_key") == idempotency_key
            and _LAST_WHATSAPP_SEND.get("recipient") == recipient
            and _LAST_WHATSAPP_SEND.get("message") == msg
            and (now - float(_LAST_WHATSAPP_SEND.get("time", 0.0))) < 6.0
        ):
            return f"WhatsApp message to '{recipient}' was already sent this turn; not sending it again."

        try:
            from src.channels.channel_manager import ChannelManager

            plugin = ChannelManager.get_instance().get_plugin("whatsapp")
            if plugin is None:
                from extensions.whatsapp.plugin import WhatsAppPlugin

                plugin = WhatsAppPlugin()
            target = recipient if "@" in recipient else f"whatsapp:{digits}"
            res = await plugin.send(target, {"text": msg})
        except Exception as exc:  # noqa: BLE001 - reported to the model as tool output
            return f"WhatsApp error: could not reach the WhatsApp channel bridge: {exc}"

        if getattr(res, "is_err", False):
            return f"WhatsApp error: {getattr(res, 'error', 'send failed')}"

        evidence = res.value if isinstance(getattr(res, "value", None), dict) else {}
        message_id = str(evidence.get("message_id") or "")
        _LAST_WHATSAPP_SEND.update(
            {
                "time": now,
                "recipient": recipient,
                "message": msg,
                "idempotency_key": idempotency_key,
            }
        )
        suffix = f" (message id {message_id})" if message_id else ""
        return f"SUCCESS: WhatsApp message delivered to '{recipient}'{suffix}."

    # 2. Focus application / Bring window to front
    if action in ("focus_app", "focus", "bring_to_front"):
        target = app_name or str(args.get("target") or "")
        if not target:
            return "Application name or window title is required for focus_app."
        try:
            import pygetwindow as gw

            all_wins = gw.getAllWindows()
            t_low = target.lower().strip()

            # YouTube-aware matching: if looking for youtube/yt, check titles with youtube, then common browsers
            if t_low in ("youtube", "yt"):
                matched = [w for w in all_wins if "youtube" in w.title.lower() and w.title.strip()]
                if not matched:
                    matched = [
                        w
                        for w in all_wins
                        if any(b in w.title.lower() for b in ("chrome", "edge", "brave", "firefox"))
                        and w.title.strip()
                    ]
            else:
                matched = [w for w in all_wins if t_low in w.title.lower() and w.title.strip()]

            if matched:
                win = matched[0]
                try:
                    if getattr(win, "isMinimized", False):
                        win.restore()
                    try:
                        win.maximize()
                    except Exception:
                        pass
                    win.activate()
                    return f"Focused application '{target}' (window: '{win.title}')."
                except Exception:
                    # Windows API fallback with thread attachment
                    try:
                        import win32api
                        import win32con
                        import win32gui
                        import win32process

                        curr_tid = win32api.GetCurrentThreadId()
                        fore_hwnd = win32gui.GetForegroundWindow()
                        fore_tid, _ = win32process.GetWindowThreadProcessId(fore_hwnd)
                        if curr_tid != fore_tid:
                            win32process.AttachThreadInput(curr_tid, fore_tid, True)
                        win32gui.ShowWindow(win._hWnd, win32con.SW_RESTORE)
                        win32gui.ShowWindow(win._hWnd, win32con.SW_MAXIMIZE)
                        win32gui.SetForegroundWindow(win._hWnd)
                        if curr_tid != fore_tid:
                            win32process.AttachThreadInput(curr_tid, fore_tid, False)
                        return f"Focused application '{target}' (window: '{win.title}')."
                    except Exception:
                        return f"Found window '{win.title}', brought to view."

            # If no open window found, launch the application
            if sys.platform == "win32":
                from src.agents.sessions.tools.path_utils import launch_windows_app

                launch_windows_app(target)
            else:
                import subprocess

                subprocess.Popen(["cmd", "/c", "start", target], shell=True)
            # Adaptive readiness check: poll up to 0.5s max (in 50ms intervals) for window emergence
            t_low = target.lower().strip()
            for _ in range(10):
                await asyncio.sleep(0.05)
                all_wins_after = gw.getAllWindows()
                matched_after = [
                    w for w in all_wins_after if t_low in w.title.lower() and w.title.strip()
                ]
                if matched_after:
                    try:
                        matched_after[0].activate()
                    except Exception:
                        pass
                    return f"Launched and focused application '{target}' (window: '{matched_after[0].title}')."
            return f"Application '{target}' launched."
        except Exception as exc:
            return f"Could not focus application '{target}': {exc}"

    # 2b. Window state control (minimize / maximize / restore).
    # ``computer(action='minimize', app_name='chrome')`` previously fell through to the
    # pyautogui tail and reported success without touching any window.
    if action in (
        "minimize",
        "minimize_window",
        "maximize",
        "maximize_window",
        "restore",
        "restore_window",
    ):
        if sys.platform != "win32":
            return f"Window action '{action}' is only supported on Windows."
        verb = action.split("_")[0]
        target = app_name or str(args.get("target") or "")
        try:
            import pygetwindow as gw

            if target:
                t_low = target.lower().strip()
                matched = [
                    w
                    for w in gw.getAllWindows()
                    if t_low in (w.title or "").lower() and w.title.strip()
                ]
                if not matched:
                    return f"No open window matches '{target}'; nothing to {verb}."
                win = matched[0]
                if verb == "minimize":
                    win.minimize()
                elif verb == "maximize":
                    if getattr(win, "isMinimized", False):
                        win.restore()
                    win.maximize()
                else:
                    win.restore()
                return f"{verb.capitalize()}d window '{win.title}'."

            if verb == "maximize":
                active = gw.getActiveWindow()
                if active is None:
                    return "No active window to maximize."
                if getattr(active, "isMinimized", False):
                    active.restore()
                active.maximize()
                return f"Maximized window '{active.title}'."

            script = (
                "(New-Object -ComObject Shell.Application).MinimizeAll()"
                if verb == "minimize"
                else "(New-Object -ComObject Shell.Application).UndoMinimizeALL()"
            )
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if completed.returncode != 0:
                return f"Failed to {verb} all windows: {completed.stderr.strip()}"
            return f"Successfully {verb}d all open windows on host PC."
        except Exception as exc:
            return f"Window action '{action}' failed: {exc}"

    # 3. Launch application / Open target
    if action in ("launch_app", "launch", "open_app", "open", "start", "open_file"):
        target = app_name or str(args.get("target") or args.get("file_path") or args.get("path") or "")
        if not target:
            return "Target application or path is required for launch_app or open_file."
        try:
            if sys.platform == "win32":
                from src.agents.sessions.tools.path_utils import launch_windows_app

                ok, l_msg = launch_windows_app(target)
                if not ok and os.path.exists(target):
                    try:
                        os.startfile(target)
                        ok = True
                    except Exception as sf_exc:
                        return f"Failed to open '{target}': {sf_exc}"
            else:
                import subprocess

                subprocess.Popen(["cmd", "/c", "start", target], shell=True)
            # Adaptive readiness check: poll up to 0.4s max (in 50ms intervals)
            try:
                import pygetwindow as gw

                t_low = target.lower().strip()
                for _ in range(8):
                    await asyncio.sleep(0.05)
                    wins = [w for w in gw.getAllWindows() if w.title and t_low in w.title.lower()]
                    if wins:
                        return f"Opened '{target}' successfully. Window '{wins[0].title}' active."
            except Exception:
                await asyncio.sleep(0.05)
            return f"Opened '{target}' successfully. Window initialized."
        except Exception as exc:
            return f"Failed to open '{target}': {exc}"

    # 4. List running applications / windows
    if action in ("list_apps", "list_windows", "running_apps", "apps"):
        try:
            import pygetwindow as gw

            all_wins = gw.getAllWindows()
            titles = [w.title.strip() for w in all_wins if w.title.strip()]
            unique_titles = list(dict.fromkeys(titles))
            if not unique_titles:
                return "No active desktop application windows found."
            lines = ["Running Desktop Applications on PC:"]
            for t in unique_titles[:25]:
                lines.append(f"- {t}")
            return "\n".join(lines)
        except Exception as exc:
            return f"Failed to list applications: {exc}"

    # 5. UI Grounding: inspect_ui action
    if action in ("inspect_ui", "inspect", "ui_tree", "ground_ui"):
        from src.agents.sessions.tools.ui_grounding import (
            get_ui_cache,
            scan_interactive_elements,
        )

        elements = scan_interactive_elements()
        cache = get_ui_cache()
        return json.dumps(
            {
                "action": "inspect_ui",
                "status": "ok",
                "window": cache.window_title,
                "element_count": len(elements),
                "elements": [elem.to_dict() for elem in elements],
            },
            ensure_ascii=False,
        )

    # 6. Screenshot (with optional Set-of-Mark visual annotation)
    if action == "screenshot":
        try:
            import io
            from pathlib import Path

            from PIL import ImageGrab

            from src.agents.sessions.tools.ui_grounding import (
                annotate_screenshot_with_marks,
                scan_interactive_elements,
            )

            img = ImageGrab.grab()
            annotate = bool(args.get("annotate") or args.get("som") or args.get("set_of_marks"))
            include_b64 = bool(args.get("include_base64") or args.get("b64"))

            # Determine best user directory for saving screenshots
            user_profile = os.environ.get("USERPROFILE") or str(Path.home())
            target_dirs = [
                Path(user_profile) / "OneDrive" / "Pictures" / "Screenshots",
                Path(user_profile) / "Pictures" / "Screenshots",
                Path(user_profile) / ".jarvis" / "screenshots",
            ]
            save_dir = next((d for d in target_dirs if d.exists()), target_dirs[-1])
            save_dir.mkdir(parents=True, exist_ok=True)

            ts_str = time.strftime("%Y%m%d_%H%M%S")
            save_path = save_dir / f"screenshot_{ts_str}.png"

            elements = []
            if annotate:
                elements = scan_interactive_elements()
                annotated_img = annotate_screenshot_with_marks(img, elements)
                annotated_img.save(save_path)
            else:
                img.save(save_path)

            payload: dict[str, Any] = {
                "action": "screenshot",
                "status": "success",
                "annotated": annotate,
                "width": img.width,
                "height": img.height,
                "element_count": len(elements),
                "file_path": str(save_path),
                "summary": f"Screenshot successfully captured and saved to {save_path} ({img.width}x{img.height}).",
            }
            if include_b64:
                import base64

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=80)
                payload["image_base64"] = base64.b64encode(buf.getvalue()).decode("utf-8")

            return json.dumps(payload, ensure_ascii=False)
        except Exception as exc:
            return f"Failed to take screenshot: {exc}"

    # 7. Settle and adaptive wait (no pyautogui import needed, zero latency)
    if action in ("wait", "wait_loading", "settle", "sleep"):
        sec = float(
            args.get("wait_seconds")
            or args.get("seconds")
            or args.get("duration")
            or args.get("time")
            or 1.0
        )
        target = (
            str(args.get("target") or args.get("app_name") or args.get("app") or "").strip().lower()
        )
        # Adaptive wait: if target window is already open and ready, return immediately
        if target:
            try:
                import pygetwindow as gw

                wins = [w for w in gw.getAllWindows() if w.title and target in w.title.lower()]
                if wins:
                    return f"Window '{wins[0].title}' is already loaded and ready. Proceeding immediately without wait."
            except Exception:
                pass

        elapsed = 0.0
        step = 0.05
        while elapsed < min(max(sec, 0.05), 30.0):
            await asyncio.sleep(step)
            elapsed += step
            if target:
                try:
                    import pygetwindow as gw

                    wins = [w for w in gw.getAllWindows() if w.title and target in w.title.lower()]
                    if wins:
                        return f"Window '{wins[0].title}' loaded and settled (waited {elapsed:.2f}s). Proceeding."
                except Exception:
                    pass
        return f"Waited {elapsed:.2f}s for UI / window to settle and load."

    # 8. Mouse and keyboard actions via pyautogui / canonical computer tool
    try:
        import pyautogui

        pyautogui.FAILSAFE = True

        coord = args.get("coordinate") or (
            [args.get("x"), args.get("y")]
            if args.get("x") is not None and args.get("y") is not None
            else None
        )
        text = args.get("text")
        key = args.get("key")

        # Target element resolution by target_id or element_name
        target_id = args.get("target_id")
        element_name = str(args.get("element_name") or "").strip() or None
        target_resolved_desc = ""

        if target_id is not None or element_name is not None:
            from src.agents.sessions.tools.ui_grounding import (
                get_ui_cache,
                scan_interactive_elements,
            )

            cache = get_ui_cache()
            pt = cache.resolve_target(target_id, element_name)
            if pt is None:
                scan_interactive_elements()
                pt = cache.resolve_target(target_id, element_name)

            if pt is not None:
                coord = [pt[0], pt[1]]
                matched = (
                    cache.get_by_id(target_id)
                    if target_id is not None
                    else cache.find_by_name(element_name or "")
                )
                if matched:
                    target_resolved_desc = (
                        f" (resolved target: [{matched.id}] '{matched.name}' at {coord})"
                    )
            elif not coord:
                return (
                    f"Target element not found: target_id={target_id}, element_name={element_name}. "
                    "Use action='inspect_ui' or action='screenshot' with annotate=True to discover valid element IDs."
                )

        # 8a. TierRouter (Tier 0 Browser -> Tier 1 UIA -> Tier 2 Overlay Real Input)
        router = get_desktop_tier_router()
        if router is not None:
            tier_actions = {
                "click": "click",
                "left_click": "click",
                "right_click": "right_click",
                "context_click": "right_click",
                "double_click": "double_click",
                "triple_click": "triple_click",
                "middle_click": "middle_click",
                "move_cursor": "move",
                "mouse_move": "move",
                "move": "move",
                "type": "type",
                "press_key": "key",
                "key": "key",
                "hotkey": "key",
                "scroll": "scroll",
                "scroll_at": "scroll",
                "drag": "drag",
            }
            if action in tier_actions:
                mapped_act = tier_actions[action]
                r_args = dict(args)
                if coord:
                    r_args["coordinate"] = coord
                if action == "hotkey":
                    keys = args.get("keys") or ([key] if key else [])
                    if keys:
                        r_args["key"] = keys[-1]
                        r_args["modifiers"] = keys[:-1]
                r_res = await router.execute_action("desktop_pipeline", mapped_act, r_args)
                if not r_res.get("ok"):
                    return f"Desktop action '{action}' failed: {r_res.get('error')} [{r_res.get('code')}]"
                tier_num = r_res.get("tier", 2)
                tier_label = (
                    "Tier 0 (Browser DOM)"
                    if tier_num == 0
                    else "Tier 1 (UIAutomation)"
                    if tier_num == 1
                    else "Tier 2 (Real Hardware Input + Jarvis Cursor)"
                )
                return f"Desktop action '{action}' executed via {tier_label}{target_resolved_desc}."

        if action in ("click", "left_click"):
            if not coord and target_id is None and element_name is None:
                # If foreground window is Chrome / Browser, route to SeleniumDOMEngine to prevent blind random desktop click
                try:
                    import pygetwindow as gw

                    active_win = gw.getActiveWindow()
                    if active_win and any(
                        b in active_win.title.lower()
                        for b in ("chrome", "youtube", "google", "edge", "browser")
                    ):
                        from extensions.browser.src.browser_tool import BrowserTool

                        browser = BrowserTool()
                        click_args = dict(args)
                        click_args["action"] = "act"
                        click_args["kind"] = "click"
                        if (
                            "text" not in click_args
                            and "selector" not in click_args
                            and "ref" not in click_args
                        ):
                            click_args["ref"] = "1"
                        res = await browser.execute("desktop_auto_control", click_args)
                        p_text = (
                            res.content[0].text
                            if getattr(res, "content", None) and hasattr(res.content[0], "text")
                            else str(res)
                        )
                        return p_text
                except Exception:
                    pass

            if coord and len(coord) >= 2:
                pyautogui.click(coord[0], coord[1])
            else:
                pyautogui.click()
            return f"Clicked at {coord if coord else 'current position'}{target_resolved_desc}."

        elif action in ("right_click", "context_click"):
            if coord and len(coord) >= 2:
                pyautogui.rightClick(coord[0], coord[1])
            else:
                pyautogui.rightClick()
            return (
                f"Right-clicked at {coord if coord else 'current position'}{target_resolved_desc}."
            )

        elif action == "double_click":
            if coord and len(coord) >= 2:
                pyautogui.doubleClick(coord[0], coord[1])
            else:
                pyautogui.doubleClick()
            return (
                f"Double-clicked at {coord if coord else 'current position'}{target_resolved_desc}."
            )

        elif action in ("move_cursor", "mouse_move"):
            if coord and len(coord) >= 2:
                pyautogui.moveTo(coord[0], coord[1])
                return f"Moved cursor to {coord}{target_resolved_desc}."
            return "No coordinate provided for move_cursor."

        elif action == "type" and text:
            if coord and len(coord) >= 2:
                pyautogui.click(coord[0], coord[1])
                await asyncio.sleep(0.05)
            pyautogui.write(text, interval=0.01)
            return f"Typed '{text}' successfully into target{target_resolved_desc}."

        elif action in ("press_key", "key") and key:
            pyautogui.press(key)
            return f"Pressed key '{key}' successfully."

        elif action == "hotkey":
            keys = args.get("keys") or ([key] if key else [])
            if keys:
                pyautogui.hotkey(*keys)
                return f"Pressed hotkey {keys} successfully."
            return "No keys provided for hotkey."

        elif action in ("scroll", "scroll_at"):
            delta = int(args.get("delta") or -100)
            pyautogui.scroll(delta)
            return f"Scrolled {delta}."

    except Exception as act_err:
        return f"Desktop action '{action}' failed: {act_err}"

    return f"Desktop action '{action}' completed."
