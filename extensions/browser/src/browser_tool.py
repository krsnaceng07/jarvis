"""Browser agent tool contract.

Mirrors OpenClaw's ``extensions/browser/src/browser-tool.ts``:
- Implements the AgentTool protocol expected by jarvis_agent.agent_loop.
- Supports 24 OpenClaw actions (tabs, open, close, focus, navigate, snapshot,
  screenshot, act, text, console, errors, doctor, status, start, stop, profiles).
- Returns AgentToolResult with structured details and text content.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from jarvis_sdk import Err, Ok, Result

from .browser_profiles import resolve_browser_config, resolve_profile
from .browser_runtime import get_browser_runtime
from .browser_tool_schema import (
    AgentToolResult,
    BrowserToolInput,
    get_browser_tool_output_schema,
    get_browser_tool_schema,
    image_result,
    json_result,
)
from .config import ResolvedBrowserConfig


class BrowserTool:
    """The main Browser automation tool."""

    @property
    def name(self) -> str:
        return "browser"

    @property
    def label(self) -> str:
        return "Browser"

    @property
    def description(self) -> str:
        return (
            "Automate a browser. Open tabs, navigate URLs, inspect page structure "
            "with ARIA snapshots, capture screenshots, extract text, and perform interactions (click, type, etc.)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema dictionary for tool parameters (AgentTool parity)."""
        return get_browser_tool_schema()

    @property
    def schema(self) -> Any:
        """Alias for parameters for duck-typed callers."""
        return self.parameters

    @property
    def output_schema(self) -> dict[str, Any]:
        """JSON Schema dictionary for tool output."""
        return get_browser_tool_output_schema()

    @property
    def hide_from_channel_progress(self) -> bool | None:
        return None

    @property
    def execution_mode(self) -> Any:
        return None

    def prepare_arguments(self, args: Any) -> Any:
        """Compatibility shim for raw arguments before schema validation."""
        return args

    async def call(self, name: str, args: dict[str, Any]) -> Result[str]:
        """Adapter for desktop plugin dispatch.

        Dispatches tool calls directly into execute(), returning an Ok/Err
        Result for the desktop host application.
        """
        try:
            params = dict(args or {})
            res = await self.execute("desktop_call", params)
            if res.content and len(res.content) > 0:
                first = res.content[0]
                if hasattr(first, "text") and first.text:
                    return Ok(first.text)
            if res.details is not None:
                return Ok(json.dumps(res.details, ensure_ascii=False))
            return Ok("Browser action completed successfully.")
        except Exception as e:
            return Err(f"Browser action failed: {e}", code="BROWSER_ERROR")

    async def execute(
        self,
        tool_call_id_or_ctx: Any,
        params: Any = None,
        signal: Any = None,
        on_update: Any = None,
    ) -> AgentToolResult:
        """Execute a browser action.

        Signature supports both standard AgentTool protocol:
            execute(tool_call_id, params, signal=None, on_update=None)
        and legacy caller signature:
            execute(ctx, input_data)
        """
        # Normalize arguments
        raw_params: dict[str, Any] = {}
        ctx: Any = None

        if params is None:
            if isinstance(tool_call_id_or_ctx, dict):
                raw_params = dict(tool_call_id_or_ctx)
            elif isinstance(tool_call_id_or_ctx, BrowserToolInput):
                raw_params = tool_call_id_or_ctx.model_dump()
            else:
                raw_params = {}
        elif isinstance(params, dict):
            raw_params = dict(params)
            ctx = tool_call_id_or_ctx
        elif isinstance(params, BrowserToolInput):
            raw_params = params.model_dump()
            ctx = tool_call_id_or_ctx
        elif hasattr(params, "__dict__"):
            raw_params = dict(vars(params))
            ctx = tool_call_id_or_ctx

        # Flatten nested request object if provided (OpenClaw parity)
        nested_req = raw_params.get("request")
        if isinstance(nested_req, dict):
            for k, v in nested_req.items():
                if k not in raw_params or raw_params[k] is None:
                    raw_params[k] = v

        target_id = raw_params.get("targetId") or raw_params.get("target_id")
        target_url = (
            raw_params.get("targetUrl") or raw_params.get("target_url") or raw_params.get("url")
        )
        if target_url and isinstance(target_url, str):
            target_url = target_url.strip()
            if not (
                "://" in target_url
                or target_url.startswith(("about:", "data:", "chrome:", "edge:", "file:"))
            ):
                if " " in target_url or (
                    "." not in target_url
                    and target_url.lower()
                    not in ("youtube", "google", "github", "twitter", "x", "reddit", "spotify")
                ):
                    import urllib.parse

                    target_url = (
                        f"https://www.google.com/search?q={urllib.parse.quote_plus(target_url)}"
                    )
                elif target_url.lower().startswith("www.") or "." in target_url:
                    target_url = f"https://{target_url}"
                else:
                    target_url = f"https://www.{target_url.lower()}.com"
        label = raw_params.get("label", "")

        action = raw_params.get("action")
        if isinstance(action, str):
            action = action.strip().lower()
            if action in ("new_tab", "newtab", "open_tab"):
                action = "open"
                raw_params["action"] = "open"
            elif action in ("switch_tab", "switchtab", "focus_tab"):
                action = "focus"
                raw_params["action"] = "focus"
            elif action in ("close_tab", "closetab"):
                action = "close"
                raw_params["action"] = "close"
            elif action in ("goto", "visit", "browse", "go_to", "load"):
                action = "navigate"
                raw_params["action"] = "navigate"
        if not action:
            if target_url:
                action = "open"
                raw_params["action"] = "open"
            else:
                raise ValueError("action is required for browser tool")

        # Resolve configuration
        cfg: Optional[ResolvedBrowserConfig] = None
        if ctx and hasattr(ctx, "plugin_state") and hasattr(ctx.plugin_state, "get"):
            cfg = ctx.plugin_state.get("browser_config")

        if not cfg:
            cfg = resolve_browser_config({})

        # Resolve profile
        profile_name = raw_params.get("profile") or cfg.defaultProfile
        profile = resolve_profile(cfg, profile_name)
        if not profile:
            raise ValueError(f"Unknown browser profile: {profile_name}")

        runtime = await get_browser_runtime(cfg)

        # ── Lifecycle & Status Actions ──
        if action == "status":
            tabs = await runtime.list_tabs(profile) if runtime.is_running else []
            return json_result(
                {
                    "ok": True,
                    "running": runtime.is_running,
                    "profile": profile.name,
                    "driver": profile.driver,
                    "tabCount": len(tabs),
                    "tabs": tabs,
                }
            )

        elif action == "doctor":
            report = await runtime.doctor()
            return json_result(report)

        elif action == "start":
            await runtime.get_or_create_context(profile)
            return json_result({"ok": True, "status": "started", "profile": profile.name})

        elif action == "stop":
            await runtime.stop()
            return json_result({"ok": True, "status": "stopped"})

        elif action == "profiles":
            profile_list = [
                {"name": name, "driver": p.driver, "headless": p.headless}
                for name, p in cfg.profiles.items()
            ]
            return json_result({"ok": True, "profiles": profile_list})

        # ── Tab Management Actions ──
        elif action == "tabs":
            tab_list = await runtime.list_tabs(profile)
            return json_result(
                {
                    "ok": True,
                    "tabCount": len(tab_list),
                    "tabs": tab_list,
                }
            )

        elif action == "open":
            if (
                not label
                and target_url
                and ("youtube.com" in target_url or "youtu.be" in target_url)
            ):
                label = "youtube"
            res = await runtime.open_tab(profile, url=target_url, label=label)
            tid = res.get("targetId")
            try:
                from src.application_automation.browser_target_manager import BrowserTargetManager

                from src.agents.task.runtime_state import RuntimeStateManager

                BrowserTargetManager.get_instance().register_target(
                    target_id=tid, url=target_url or "", label=label
                )
                RuntimeStateManager.get_instance().update_browser_context(
                    target_id=tid, url=target_url or "", title=res.get("title", "")
                )
            except Exception:
                pass
            # OpenClaw parity (appendNavigatedPageState): attach fresh page snapshot
            # so model receives page context immediately without repeating open calls.
            try:
                import asyncio
                snap = await asyncio.wait_for(runtime.snapshot(profile, target_id=tid, max_chars=2000), timeout=1.5)
                if snap.get("ok"):
                    res["snapshot"] = snap.get("snapshot") or snap.get("text") or ""
                    if "elements" in snap:
                        res["elements"] = snap["elements"]
            except Exception:
                pass
            return json_result(res)

        elif action == "close":
            res = await runtime.close_tab(profile, target_id=target_id)
            return json_result(res)

        elif action == "focus":
            if not target_id:
                raise ValueError("targetId is required for focus action")
            res = await runtime.focus_tab(profile, target_id=target_id)
            return json_result(res)

        # ── Navigation & Inspection Actions ──
        elif action == "navigate":
            if not target_url:
                raise ValueError("targetUrl or url is required for navigate action")
            res = await runtime.navigate(profile, url=target_url, target_id=target_id)
            tid = res.get("targetId") or target_id
            try:
                from src.application_automation.browser_target_manager import BrowserTargetManager

                from src.agents.task.runtime_state import RuntimeStateManager

                BrowserTargetManager.get_instance().register_target(
                    target_id=tid, url=target_url or ""
                )
                RuntimeStateManager.get_instance().update_browser_context(
                    target_id=tid, url=target_url or "", title=res.get("title", "")
                )
            except Exception:
                pass
            try:
                import asyncio
                snap = await asyncio.wait_for(runtime.snapshot(profile, target_id=tid, max_chars=2000), timeout=1.5)
                if snap.get("ok"):
                    res["snapshot"] = snap.get("snapshot") or snap.get("text") or ""
                    if "elements" in snap:
                        res["elements"] = snap["elements"]
            except Exception:
                pass
            return json_result(res)

        elif action == "snapshot":
            fmt = raw_params.get("snapshotFormat") or "aria"
            max_c = raw_params.get("maxChars")
            res = await runtime.snapshot(
                profile, target_id=target_id, snapshot_format=fmt, max_chars=max_c
            )
            try:
                from src.application_automation.observation_manager import ObservationManager

                from src.agents.task.runtime_state import RuntimeStateManager

                obs = ObservationManager.get_instance().record_snapshot(
                    target_id=target_id or "default",
                    url=res.get("url", ""),
                    title=res.get("title", ""),
                    raw_aria_tree=res.get("snapshot") or res.get("text") or "",
                )
                res["observation_id"] = obs.observation_id
                RuntimeStateManager.get_instance().record_observation(obs.observation_id)
            except Exception:
                pass
            return json_result(res)

        elif action == "screenshot":
            full_page = bool(raw_params.get("fullPage", False))
            element = raw_params.get("element")
            file_path = raw_params.get("path")
            img_type = raw_params.get("type", "png")
            annotate = bool(
                raw_params.get("annotate")
                or raw_params.get("som")
                or raw_params.get("set_of_marks")
            )
            res = await runtime.screenshot(
                profile,
                target_id=target_id,
                full_page=full_page,
                element=element,
                path=file_path,
                image_type=img_type,
                annotate=annotate,
            )
            b64_data = res.pop("base64", "")
            return image_result(
                image_base64=b64_data,
                mime_type=res.get("format", "image/png"),
                details=res,
            )

        elif action == "download":
            res = await runtime.download(
                profile=profile,
                target_id=target_id,
                selector=raw_params.get("selector"),
                ref=raw_params.get("ref"),
                path=raw_params.get("path"),
                download_dir=raw_params.get("downloadDir"),
                timeout_ms=int(raw_params.get("timeoutMs") or cfg.actionTimeoutMs),
            )
            return json_result(res)

        elif action == "text":
            res = await runtime.extract_text(profile, target_id=target_id)
            return json_result(res)

        elif action == "console":
            res = await runtime.get_console(profile, target_id=target_id)
            return json_result(res)

        elif action == "errors":
            res = await runtime.get_errors(profile, target_id=target_id)
            return json_result(res)

        # ── Interaction Actions (act) ──
        elif action == "act" or action in {
            "click",
            "clickcoords",
            "type",
            "press",
            "press_key",
            "hover",
            "scrollintoview",
            "drag",
            "select",
            "fill",
            "resize",
            "wait",
            "evaluate",
        }:
            kind = raw_params.get("kind")
            if not kind:
                if action == "act":
                    raise ValueError("kind is required for act action")
                kind = "press" if action == "press_key" else action

            # 1. Turn boundary & task cancellation check (OpenClaw Parity)
            try:
                from src.agents.task.runtime_state import RuntimeStateManager

                state_mgr = RuntimeStateManager.get_instance()
                if state_mgr.state.cancellation_state:
                    return json_result(
                        {"ok": False, "status": "cancelled", "error": "Task has been cancelled."}
                    )
                turn_id = raw_params.get("turnId") or raw_params.get("turn_id")
                if (
                    turn_id
                    and state_mgr.state.active_user_turn_id
                    and turn_id != state_mgr.state.active_user_turn_id
                ):
                    return json_result(
                        {
                            "ok": False,
                            "status": "stale_turn",
                            "error": f"Tool call from stale turn '{turn_id}' rejected.",
                        }
                    )
            except Exception:
                pass

            # 2. Pre-action check for stateful mutations (e.g. Subscribe / Like)
            selector_str = (raw_params.get("selector") or "").lower()
            text_str = (raw_params.get("text") or "").lower()
            ref_str = (raw_params.get("ref") or "").lower()
            if kind == "click" and any(
                w in selector_str or w in text_str or w in ref_str
                for w in ("subscribe", "sub-button", "subscription")
            ):
                try:
                    page = await runtime.get_page(profile=profile, target_id=target_id)
                    if page:
                        from src.application_automation.applications.youtube.actions import (
                            YouTubeActions,
                        )

                        sub_state = await YouTubeActions.check_subscription_state(page)
                        if sub_state.get("is_subscribed"):
                            return json_result(
                                {
                                    "ok": True,
                                    "status": "already_completed",
                                    "action": "subscribe",
                                    "evidence": [
                                        f"Channel is already subscribed (button indicates '{sub_state.get('text')}'). Zero clicks executed."
                                    ],
                                    "effect": "confirmed",
                                }
                            )
                except Exception:
                    pass

            # 3. Target tab validation
            try:
                from src.application_automation.browser_target_manager import BrowserTargetManager

                tabs_info = await runtime.list_tabs(profile)
                target_mgr = BrowserTargetManager.get_instance()
                target_mgr.validate_target(target_id=target_id, runtime_tabs=tabs_info)
            except Exception as target_err:
                if "TargetStaleError" in type(target_err).__name__:
                    return json_result(
                        {"ok": False, "status": "target_stale", "error": str(target_err)}
                    )

            # 4. Driver execution
            res = await runtime.act(
                profile=profile,
                target_id=target_id,
                kind=kind,
                ref=raw_params.get("ref"),
                selector=raw_params.get("selector"),
                text=raw_params.get("text"),
                key=raw_params.get("key"),
                x=raw_params.get("x"),
                y=raw_params.get("y"),
                time_ms=raw_params.get("timeMs"),
                fn=raw_params.get("fn"),
                values=raw_params.get("values"),
                width=raw_params.get("width"),
                height=raw_params.get("height"),
                timeout_ms=raw_params.get("timeoutMs"),
            )

            # 5. Post-action verification for mutations
            if kind in ("click", "fill", "type", "press") and res.get("ok"):
                try:
                    page = await runtime.get_page(profile=profile, target_id=target_id)
                    if kind == "click" and any(
                        w in selector_str or w in text_str for w in ("subscribe", "sub-button")
                    ):
                        from src.application_automation.applications.youtube.actions import (
                            YouTubeActions,
                        )

                        post_state = await YouTubeActions.check_subscription_state(page)
                        if post_state.get("is_subscribed"):
                            res["status"] = "completed_verified"
                            res["effect"] = "confirmed"
                            res["evidence"] = [
                                f"Verified subscription button changed to: '{post_state.get('text')}'"
                            ]
                        else:
                            res["status"] = "completed_unverified"
                            res["effect"] = "suspected_noop"
                            res["evidence"] = [
                                "Clicked subscribe but button did not reflect 'Subscribed'."
                            ]
                    else:
                        # Dispatch success is not evidence that the user's intended
                        # page change occurred. Keep the task pending verification.
                        res["status"] = "completed_unverified"
                        res["effect"] = "unverifiable"
                except Exception:
                    res["status"] = "completed_unverified"
                    res["effect"] = "unverifiable"

            return json_result(res)

        # ── Specialized Video & Web Automation (YouTube / Google Search / Media) ──
        elif action in ("youtube_play", "play_youtube"):
            q = (
                raw_params.get("query")
                or raw_params.get("text")
                or raw_params.get("title")
                or target_url
                or ""
            )
            if not q and target_url and "youtube.com" in target_url:
                res = await runtime.open_tab(profile, url=target_url, label="youtube")
                return json_result(res)
            res = await runtime.youtube_play(
                query=str(q),
                profile=profile,
                target_id=target_id,
            )
            return json_result(res)

        elif action in ("skip_ad", "youtube_skip_ad", "skip"):
            res = await runtime.youtube_skip_ad(profile=profile, target_id=target_id)
            return json_result(res)

        elif action in (
            "pause",
            "youtube_pause",
            "pause_video",
            "play_pause",
            "toggle_play",
            "resume",
            "play_video",
            "resume_video",
            "pause_music",
            "stop_music",
        ):
            res = await runtime.act(profile=profile, target_id=target_id, kind="pause")
            return json_result(res)

        elif action in ("google_search", "search_google"):
            q = raw_params.get("query") or raw_params.get("text") or ""
            res = await runtime.google_search(query=str(q), profile=profile, target_id=target_id)
            return json_result(res)

        elif action in ("search",):
            q = raw_params.get("query") or raw_params.get("text") or ""
            page = await runtime.get_page(profile=profile, target_id=target_id)
            curr_url = getattr(page, "url", "").lower() if page else ""
            if "youtube.com" in curr_url or "youtube" in str(q).lower():
                res = await runtime.youtube_play(query=str(q), profile=profile, target_id=target_id)
            else:
                res = await runtime.google_search(
                    query=str(q), profile=profile, target_id=target_id
                )
            return json_result(res)

        elif action in ("app", "youtube", "web"):
            cmd = str(
                raw_params.get("command")
                or raw_params.get("cmd")
                or raw_params.get("kind")
                or "play"
            ).lower()
            q = str(raw_params.get("query") or raw_params.get("text") or "").strip()

            if action == "youtube" or raw_params.get("app") == "youtube":
                if cmd in ("play", "youtube_play", "search_and_play", "play_first_result") or q:
                    res = await runtime.youtube_play(query=q, profile=profile, target_id=target_id)
                    return json_result(res)
                elif cmd in ("skip_ad", "skip", "skip_advertisement"):
                    res = await runtime.youtube_skip_ad(profile=profile, target_id=target_id)
                    return json_result(res)
                else:
                    res = await runtime.open_tab(
                        profile, url="https://www.youtube.com", label="youtube"
                    )
                    return json_result(res)

            # Generic web action fallback
            page = await runtime.get_page(profile=profile, target_id=target_id)
            return json_result(
                {
                    "ok": True,
                    "action": action,
                    "command": cmd,
                    "url": getattr(page, "url", ""),
                }
            )

        else:
            raise ValueError(f"Action '{action}' is not supported")
