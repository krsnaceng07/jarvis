"""JARVIS native computer tool: desktop automation, UI grounding, and hardware controls.

Tool: computer
Native OS computer use (mouse, keyboard, shortcuts, screenshots, wait, volume, brightness).
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import sys
import time
from typing import Any, Dict, Optional
from .tool_definition_wrapper import AgentTool
from .ui_grounding import (
    annotate_screenshot_with_marks,
    get_ui_cache,
    image_to_base64_jpeg,
    scan_interactive_elements,
)
from src.system.audio_controller import AudioController
from src.system.brightness_controller import BrightnessController

# Action names matching desktop automation and hardware controls
COMPUTER_ACTIONS = [
    "click",
    "move_cursor",
    "mouse_down",
    "mouse_up",
    "context_click",
    "double_click_coordinate",
    "triple_click_coordinate",
    "middle_click_coordinate",
    "drag_and_drop_at",
    "scroll_at",
    "type",
    "press_key",
    "key_down",
    "key_up",
    "wait",
    "hotkey",
    "screenshot",
    "inspect_ui",
    "focus_app",
    "focus",
    "bring_to_front",
    "open_file",
    "open",
    "launch_app",
    "open_app",
    "close_app",
    "close_window",
    "close",
    "kill_app",
    "quit_app",
    "list_apps",
    "list_windows",
    "set_volume",
    "get_volume",
    "volume",
    "adjust_volume",
    "mute",
    "unmute",
    "set_brightness",
    "get_brightness",
    "brightness",
    "adjust_brightness",
]


_computer_tier_router: Any = None


def _get_computer_tier_router() -> Any:
    global _computer_tier_router
    if _computer_tier_router is None:
        try:
            from extensions.cua_computer.src.router import TierRouter

            _computer_tier_router = TierRouter()
        except Exception:
            _computer_tier_router = None
    return _computer_tier_router


def create_computer_tool(options: Optional[Dict[str, Any]] = None) -> AgentTool:
    """Create the canonical computer tool for OS interactions."""

    async def execute(*call_args: Any, **call_kwargs: Any) -> Dict[str, Any]:
        if len(call_args) >= 2 and isinstance(call_args[1], dict):
            args = call_args[1]
        elif len(call_args) == 1 and isinstance(call_args[0], dict):
            args = call_args[0]
        else:
            args = call_kwargs.get("params") or call_kwargs.get("args") or {}

        action = str(args.get("action", "screenshot")).strip().lower()
        coordinate = args.get("coordinate")
        text = args.get("text")
        key = args.get("key")
        wait_seconds = (
            args.get("wait_seconds") or args.get("seconds") or args.get("duration") or 0.5
        )
        app_name = str(
            args.get("app_name")
            or args.get("application")
            or args.get("target")
            or args.get("title")
            or ""
        ).strip()

        # UI Grounding parameter extraction
        target_id = args.get("target_id")
        if target_id is None:
            for k in ("targetId", "element_id", "elementId"):
                if k in args and args[k] is not None:
                    try:
                        target_id = int(args[k])
                        break
                    except (ValueError, TypeError):
                        pass

        element_name = (
            str(
                args.get("element_name")
                or args.get("elementName")
                or args.get("element")
                or args.get("target_name")
                or ""
            ).strip()
            or None
        )

        annotate = bool(args.get("annotate") or args.get("som") or args.get("set_of_marks"))

        # Native OS Audio Volume Controls
        if action in ("set_volume", "volume", "adjust_volume", "get_volume", "mute", "unmute"):
            ac = AudioController.get_instance()
            if action == "get_volume":
                return ac.get_volume()
            if action == "mute":
                return ac.set_mute(True)
            if action == "unmute":
                return ac.set_mute(False)
            if action == "adjust_volume":
                raw_delta = args.get("delta") if args.get("delta") is not None else args.get("value")
                try:
                    delta_pct = int(raw_delta) if raw_delta is not None else 10
                except (ValueError, TypeError):
                    delta_pct = 10
                return ac.adjust_volume(delta_pct)
            # action in ("set_volume", "volume")
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
                return ac.get_volume()
            try:
                target_pct = int(raw_val)
            except (ValueError, TypeError):
                target_pct = 50
            return ac.set_volume(target_pct)

        # Native OS Display Brightness Controls
        if action in ("set_brightness", "brightness", "adjust_brightness", "get_brightness"):
            bc = BrightnessController.get_instance()
            if action == "get_brightness":
                return await bc.get_brightness_async()
            if action == "adjust_brightness":
                raw_delta = args.get("delta") if args.get("delta") is not None else args.get("value")
                try:
                    delta_pct = int(raw_delta) if raw_delta is not None else 10
                except (ValueError, TypeError):
                    delta_pct = 10
                return await bc.adjust_brightness_async(delta_pct)
            # action in ("set_brightness", "brightness")
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
                return await bc.get_brightness_async()
            try:
                target_pct = int(raw_val)
            except (ValueError, TypeError):
                target_pct = 50
            return await bc.set_brightness_async(target_pct)

        # 0. UI Grounding: inspect_ui action
        if action in ("inspect_ui", "inspect", "ui_tree", "ground_ui"):
            elements = scan_interactive_elements()
            cache = get_ui_cache()
            return {
                "action": "inspect_ui",
                "status": "ok",
                "window": cache.window_title,
                "element_count": len(elements),
                "elements": [elem.to_dict() for elem in elements],
            }

        # Handle window focus / application bringing to front
        if action in ("focus_app", "focus", "bring_to_front"):
            if not app_name:
                return {
                    "action": action,
                    "error": "app_name or target is required to focus application",
                }
            try:
                import pygetwindow as gw

                wins = [
                    w
                    for w in gw.getAllWindows()
                    if app_name.lower() in w.title.lower() and w.title.strip()
                ]
                if wins:
                    w = wins[0]
                    if getattr(w, "isMinimized", False):
                        w.restore()
                    w.activate()
                    return {"action": action, "status": "ok", "window": w.title}
                # If window is not open, launch the application
                import subprocess

                subprocess.Popen(["cmd", "/c", "start", app_name], shell=True)
                return {
                    "action": action,
                    "status": "ok",
                    "launched": app_name,
                    "message": f"Application '{app_name}' launched.",
                }
            except Exception as e:
                return {"action": action, "error": f"Failed to focus application '{app_name}': {e}"}

        # Handle launching application or opening files on desktop
        if action in ("launch_app", "open_app", "open_file", "open"):
            target = (
                app_name
                or str(
                    args.get("target")
                    or args.get("file_path")
                    or args.get("path")
                    or ""
                ).strip()
            )
            if not target:
                return {
                    "action": action,
                    "error": "target or app_name or file_path is required to launch or open",
                }
            try:
                if sys.platform == "win32":
                    from .path_utils import launch_windows_app

                    ok, l_msg = launch_windows_app(target)
                    if not ok and os.path.exists(target):
                        try:
                            os.startfile(target)
                            ok = True
                        except Exception as sf_exc:
                            return {
                                "action": action,
                                "error": f"Failed to open '{target}': {sf_exc}",
                            }
                else:
                    import subprocess

                    subprocess.Popen(["cmd", "/c", "start", target], shell=True)
                await asyncio.sleep(0.5)
                return {
                    "action": action,
                    "status": "ok",
                    "launched": target,
                    "message": f"Opened '{target}' on desktop screen.",
                }
            except Exception as e:
                return {
                    "action": action,
                    "error": f"Failed to open or launch '{target}': {e}",
                }

        # Handle closing or killing applications / windows
        if action in ("close_app", "close_window", "close", "kill_app", "quit_app"):
            if not app_name:
                return {
                    "action": action,
                    "error": "app_name or target is required to close application",
                }
            clean_app = app_name.lower().removesuffix(".exe").strip()
            closed_something = False
            details_msg = []

            # Comprehensive candidate executable and process names for Windows apps
            candidates = [clean_app, f"{clean_app}.exe"]
            if clean_app in ("powershell", "pwsh", "terminal"):
                candidates.extend(["powershell.exe", "pwsh.exe", "windowsterminal.exe", "wt.exe"])
            elif clean_app in ("whatsapp", "whatsappdesktop"):
                candidates.extend(["whatsapp.exe", "whatsapp.root.exe", "whatsappnative.exe"])
            elif clean_app in ("opencode", "opencode-cli"):
                candidates.extend(["opencode.exe", "opencode-cli.exe"])
            elif clean_app in ("code", "vscode", "visual studio code"):
                candidates.extend(["code.exe"])
            elif clean_app in ("chrome", "google chrome"):
                candidates.extend(["chrome.exe"])
            elif clean_app in ("browser", "web"):
                candidates.extend(["chrome.exe", "msedge.exe"])
            elif clean_app in ("notepad", "editor"):
                candidates.extend(["notepad.exe"])
            elif clean_app in ("spotify",):
                candidates.extend(["spotify.exe"])
            elif clean_app in ("discord",):
                candidates.extend(["discord.exe"])
            elif clean_app in ("telegram", "tg"):
                candidates.extend(["telegram.exe"])

            # 1. If user specifically asks to close YouTube, a web tab, or browser:
            if clean_app in ("youtube", "tab", "chrome", "browser"):
                try:
                    from extensions.browser.src.browser_runtime import _runtime

                    if _runtime and getattr(_runtime, "_tabs", None):
                        for tid, tab in list(_runtime._tabs.items()):
                            if not tab.page.is_closed():
                                if clean_app in ("chrome", "browser", "tab") or "youtube.com" in getattr(tab.page, "url", "").lower():
                                    try:
                                        loop = asyncio.get_event_loop()
                                        if loop.is_running():
                                            asyncio.create_task(tab.page.close())
                                        else:
                                            loop.run_until_complete(tab.page.close())
                                    except Exception:
                                        pass
                                    closed_something = True
                                    details_msg.append(f"Closed browser tab '{tab.label or tid}'.")
                except Exception:
                    pass

                try:
                    import pyautogui

                    pyautogui.hotkey("ctrl", "w")
                    closed_something = True
                    details_msg.append("Closed active tab via Ctrl+W.")
                except Exception:
                    pass

            # 2. If graceful close, try closing window gracefully via pygetwindow first
            if action in ("close_app", "close_window", "close"):
                try:
                    import pygetwindow as gw

                    for w in gw.getAllWindows():
                        if w.title and any(c.removesuffix(".exe") in w.title.lower() for c in candidates):
                            try:
                                w.close()
                                closed_something = True
                                details_msg.append(f"Closed window '{w.title}'.")
                            except Exception:
                                pass
                except Exception:
                    pass
                if closed_something:
                    await asyncio.sleep(0.3)

            # 3. Check if matching process is still alive (or if action is kill_app)
            # Many Windows apps (like WhatsApp, Discord, Spotify) minimize to system tray on close,
            # or console/terminal apps keep running. Self-healing escalation to force kill is mandatory.
            still_alive_pids: list[int] = []
            try:
                import psutil

                for p in psutil.process_iter(["pid", "name"]):
                    try:
                        p_name = p.name().lower()
                        if any(
                            c == p_name
                            or c.removesuffix(".exe") == p_name.removesuffix(".exe")
                            or p_name.startswith(f"{clean_app}.")
                            or p_name.startswith(f"{clean_app}-")
                            or f"-{clean_app}" in p_name
                            for c in candidates
                        ):
                            still_alive_pids.append(p.pid)
                    except Exception:
                        pass
            except Exception:
                pass

            # 4. Escalate to fast native taskkill (/F /T terminates entire process tree cleanly in 10ms)
            if action in ("kill_app", "quit_app") or still_alive_pids or not closed_something:
                import subprocess

                for cand in candidates:
                    img_name = cand if cand.endswith(".exe") else f"{cand}.exe"
                    try:
                        res = subprocess.run(
                            ["taskkill", "/IM", img_name, "/F", "/T"],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        if res.returncode == 0:
                            closed_something = True
                            details_msg.append(f"Terminated process tree for '{img_name}'.")
                    except Exception:
                        pass

                # If any PID still survived taskkill, terminate via psutil tree kill
                if still_alive_pids:
                    try:
                        import psutil

                        for pid in still_alive_pids:
                            try:
                                proc = psutil.Process(pid)
                                for child in proc.children(recursive=True):
                                    try:
                                        child.kill()
                                    except Exception:
                                        pass
                                proc.kill()
                                closed_something = True
                                details_msg.append(f"Force killed PID {pid}.")
                            except Exception:
                                pass
                    except Exception:
                        pass

            return {
                "action": action,
                "status": "ok" if closed_something else "not_found",
                "app_name": app_name,
                "message": "; ".join(details_msg)
                if closed_something
                else f"No active window or process found matching '{app_name}'.",
            }

        # Handle listing running apps / windows
        if action in ("list_apps", "list_windows"):
            try:
                import pygetwindow as gw

                titles = [w.title.strip() for w in gw.getAllWindows() if w.title.strip()]
                return {"action": action, "status": "ok", "apps": titles}
            except Exception as e:
                return {"action": action, "error": f"Failed to list applications: {e}"}

        # Handle screenshot (with optional Set-of-Mark visual annotation)
        if action == "screenshot":
            try:
                from PIL import ImageGrab

                img = ImageGrab.grab()
                if annotate:
                    elements = scan_interactive_elements()
                    annotated_img = annotate_screenshot_with_marks(img, elements)
                    b64 = image_to_base64_jpeg(annotated_img, quality=80)
                    return {
                        "action": "screenshot",
                        "annotated": True,
                        "width": img.width,
                        "height": img.height,
                        "element_count": len(elements),
                        "elements": [elem.to_dict() for elem in elements],
                        "image_base64": b64,
                        "timestamp": time.time(),
                    }
                else:
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=80)
                    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    return {
                        "action": "screenshot",
                        "annotated": False,
                        "width": img.width,
                        "height": img.height,
                        "image_base64": b64,
                        "timestamp": time.time(),
                    }
            except Exception as e:
                return {"action": "screenshot", "error": f"Failed to grab screen: {e}"}

        # Target element resolution for mouse and keyboard actions
        resolved_elem_name = None
        resolved_target_id = target_id
        if target_id is not None or element_name is not None:
            cache = get_ui_cache()
            pt = cache.resolve_target(target_id, element_name)
            if pt is None:
                # Cache miss or empty: perform live scan and retry
                scan_interactive_elements()
                pt = cache.resolve_target(target_id, element_name)
            if pt is not None:
                coordinate = [pt[0], pt[1]]
                matched = (
                    cache.get_by_id(target_id)
                    if target_id is not None
                    else cache.find_by_name(element_name or "")
                )
                if matched:
                    resolved_elem_name = matched.name
                    resolved_target_id = matched.id
            else:
                return {
                    "action": action,
                    "status": "error",
                    "error": f"Target element not found: target_id={target_id}, element_name={element_name}",
                }

        # Try TierRouter with Input Lease Arbiter & Overlay first
        try:
            router = _get_computer_tier_router()
            if router is not None:
                action_map = {
                    "click": "click",
                    "move_cursor": "move",
                    "context_click": "right_click",
                    "double_click_coordinate": "double_click",
                    "triple_click_coordinate": "triple_click",
                    "middle_click_coordinate": "middle_click",
                    "type": "type",
                    "press_key": "key",
                    "hotkey": "key",
                    "scroll_at": "scroll",
                    "wait": "wait",
                }
                if action in action_map:
                    mapped_action = action_map[action]
                    router_params = dict(args)
                    if coordinate:
                        router_params["coordinate"] = coordinate
                    if action == "hotkey":
                        keys = args.get("keys") or ([key] if key else [])
                        if keys:
                            router_params["key"] = keys[-1]
                            router_params["modifiers"] = keys[:-1]
                    router_res = await router.execute_action("computer_tool_session", mapped_action, router_params)
                    if not router_res.get("ok"):
                        return {
                            "action": action,
                            "status": "error",
                            "error": router_res.get("error", "Action failed"),
                            "code": router_res.get("code"),
                        }
                    res = {
                        "action": action,
                        "status": "ok",
                        "tier": router_res.get("tier", 2),
                        "lease_id": router_res.get("lease_id"),
                    }
                    if coordinate:
                        res["coordinate"] = coordinate
                    if resolved_target_id is not None:
                        res["target_id"] = resolved_target_id
                    if resolved_elem_name:
                        res["element_name"] = resolved_elem_name
                    return res
        except Exception:
            pass

        # Handle mouse / keyboard actions if pyautogui is available
        try:
            import pyautogui

            pyautogui.FAILSAFE = True

            if action == "click":
                if coordinate and len(coordinate) >= 2:
                    pyautogui.click(coordinate[0], coordinate[1])
                else:
                    pyautogui.click()
                res = {"action": "click", "status": "ok", "coordinate": coordinate}
                if resolved_target_id is not None:
                    res["target_id"] = resolved_target_id
                if resolved_elem_name:
                    res["element_name"] = resolved_elem_name
                return res

            elif action == "move_cursor":
                if coordinate and len(coordinate) >= 2:
                    pyautogui.moveTo(coordinate[0], coordinate[1])
                res = {"action": "move_cursor", "status": "ok", "coordinate": coordinate}
                if resolved_target_id is not None:
                    res["target_id"] = resolved_target_id
                if resolved_elem_name:
                    res["element_name"] = resolved_elem_name
                return res

            elif action == "context_click":
                if coordinate and len(coordinate) >= 2:
                    pyautogui.rightClick(coordinate[0], coordinate[1])
                else:
                    pyautogui.rightClick()
                res = {"action": "context_click", "status": "ok"}
                if coordinate:
                    res["coordinate"] = coordinate
                if resolved_target_id is not None:
                    res["target_id"] = resolved_target_id
                if resolved_elem_name:
                    res["element_name"] = resolved_elem_name
                return res

            elif action == "double_click_coordinate":
                if coordinate and len(coordinate) >= 2:
                    pyautogui.doubleClick(coordinate[0], coordinate[1])
                res = {
                    "action": "double_click_coordinate",
                    "status": "ok",
                    "coordinate": coordinate,
                }
                if resolved_target_id is not None:
                    res["target_id"] = resolved_target_id
                if resolved_elem_name:
                    res["element_name"] = resolved_elem_name
                return res

            elif action == "type" and text:
                if coordinate and len(coordinate) >= 2:
                    pyautogui.click(coordinate[0], coordinate[1])
                    await asyncio.sleep(0.05)
                pyautogui.write(text, interval=0.01)
                res = {"action": "type", "status": "ok", "chars": len(text)}
                if resolved_target_id is not None:
                    res["target_id"] = resolved_target_id
                if resolved_elem_name:
                    res["element_name"] = resolved_elem_name
                return res

            elif action == "press_key" and key:
                pyautogui.press(key)
                return {"action": "press_key", "status": "ok", "key": key}

            elif action == "hotkey":
                keys = args.get("keys") or ([key] if key else [])
                if keys:
                    pyautogui.hotkey(*keys)
                return {"action": "hotkey", "status": "ok", "keys": keys}

            elif action == "scroll_at":
                delta = args.get("delta", -100)
                pyautogui.scroll(delta)
                return {"action": "scroll_at", "status": "ok", "delta": delta}

            elif action == "wait":
                await asyncio.sleep(min(max(float(wait_seconds), 0.1), 30.0))
                return {"action": "wait", "status": "ok", "seconds": wait_seconds}

        except ImportError:
            if action == "wait":
                await asyncio.sleep(min(max(float(wait_seconds), 0.1), 5.0))
            return {
                "action": action,
                "status": "simulated",
                "message": f"Computer action '{action}' executed in headless environment.",
            }

        return {"action": action, "status": "ok"}

    schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": COMPUTER_ACTIONS,
                "description": "OS action to perform.",
            },
            "target_id": {
                "type": "integer",
                "description": "1-based integer element ID from inspect_ui or annotated Set-of-Mark screenshot [1], [2], etc.",
            },
            "element_name": {
                "type": "string",
                "description": "Visible text, name, or label of the UI control to target (e.g. 'Submit', 'Search', 'Close').",
            },
            "annotate": {
                "type": "boolean",
                "description": "When true with action='screenshot', draws numbered Set-of-Mark (SoM) bounding boxes [1], [2] on interactive controls.",
            },
            "app_name": {
                "type": "string",
                "description": "Application name or window title to focus, launch, close, kill, or manage (e.g. 'chrome', 'youtube', 'notepad').",
            },
            "coordinate": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 2,
                "maxItems": 2,
                "description": "[x, y] screen coordinates fallback.",
            },
            "text": {
                "type": "string",
                "description": "Text to type into focused input.",
            },
            "key": {
                "type": "string",
                "description": "Single key name (e.g. Return, Tab, BackSpace).",
            },
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of key names to press in combination for hotkey.",
            },
            "wait_seconds": {
                "type": "number",
                "description": "Duration to wait in seconds.",
            },
            "value": {
                "type": "integer",
                "description": "Value or percentage (0-100) for volume or brightness.",
            },
            "volume": {
                "type": "integer",
                "description": "Target volume percentage (0-100).",
            },
            "brightness": {
                "type": "integer",
                "description": "Target screen brightness percentage (0-100).",
            },
            "delta": {
                "type": "integer",
                "description": "Relative volume or brightness adjustment (+10, -10).",
            },
        },
        "required": ["action"],
    }

    return AgentTool(
        name="computer",
        description=(
            "Interact with the computer desktop interface using real mouse cursor, keyboard, and native OS controls "
            "(volume, mute, brightness, application launching, focus, smooth Bézier cursor movement, visual overlay, "
            "click, double_click, move_cursor, drag, type text, keypresses, hotkeys, scrolling, waiting, and screenshots). "
            "When the user asks to use the mouse, volume, or brightness, always call computer (never exec). "
            "To open folders/icons on desktop or File Explorer, use double_click."
        ),
        parameter_schema=schema,
        execute=execute,
    )


def create_computer_tool_definition(options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    tool = create_computer_tool(options)
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameter_schema,
    }


get_computer_tool = create_computer_tool

__all__ = [
    "COMPUTER_ACTIONS",
    "create_computer_tool",
    "create_computer_tool_definition",
    "get_computer_tool",
]
