"""extensions/cua-computer/src/router.py

Tier Router for JARVIS computer use:
- Tier 0: Direct DOM / Browser manipulation via BrowserTool (Playwright/Selenium)
- Tier 1: Direct OS accessibility invocation via Windows UIAutomation (no cursor movement)
- Tier 2: Real input synthesis with exclusive InputLeaseArbiter, smooth Bézier cursor,
          and PyQt6 Cursor Overlay
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import Any, Callable, Optional
import uuid

from jarvis_sdk.input_backend import ComputerFailureCode, ComputerTier

from .arbiter import (
    InputLeaseArbiter,
    LeaseBusyException,
    PanicStopException,
    UserTakeoverException,
)
from .db import ComputerAuditStore
from .policy import InputPolicyGate
from .verifier import ActionLoopDetector, VisualActionVerifier
from .win.backend import WindowsInputBackend
from .win.geometry import ScreenGeometry

logger = logging.getLogger(__name__)


class TierRouter:
    """Intelligently routes desktop actions to the most reliable, lowest-intrusion tier."""

    def __init__(
        self,
        backend: Optional[WindowsInputBackend] = None,
        arbiter: Optional[InputLeaseArbiter] = None,
        audit_store: Optional[ComputerAuditStore] = None,
        policy_gate: Optional[InputPolicyGate] = None,
        loop_detector: Optional[ActionLoopDetector] = None,
        verifier: Optional[VisualActionVerifier] = None,
    ) -> None:
        self.geometry = ScreenGeometry()
        self.backend = backend or WindowsInputBackend(geometry=self.geometry)

        # Create and start the low-level input watcher so the arbiter
        # can detect human takeover and panic hotkeys in real time.
        self._watcher: Any = None
        if sys.platform == "win32":
            from .win.watcher import LowLevelInputWatcher as _Watcher

            self._watcher = _Watcher()
            started = self._watcher.start()
            if not started:
                logger.warning("LowLevelInputWatcher failed to install hooks; human takeover detection disabled")
                self._watcher = None

        self.arbiter = arbiter or InputLeaseArbiter(backend=self.backend, watcher=self._watcher)
        self.audit_store = audit_store or ComputerAuditStore()
        self.policy_gate = policy_gate or InputPolicyGate()
        self.loop_detector = loop_detector or ActionLoopDetector()
        self.verifier = verifier or VisualActionVerifier()

    def shutdown(self) -> None:
        """Stop the low-level input watcher thread and release resources."""
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None

    def set_overlay_callback(self, callback: Callable[[str, dict], None]) -> None:
        """Connect PyQt6 cursor overlay window to receive backend and lease events."""
        self.backend.on_cursor_event = callback
        self.arbiter.on_lease_event = callback

    async def execute_action(
        self, session_id: str, action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Route and execute a computer action through Tier 0, Tier 1, or Tier 2."""
        action_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        norm_action = action.strip().lower()

        # Coordinate extraction
        coord = params.get("coordinate")
        if not coord and "x" in params and "y" in params:
            try:
                coord = [int(params["x"]), int(params["y"])]
            except (ValueError, TypeError):
                pass

        target_id = params.get("target_id")
        element_name = params.get("element_name")
        text = params.get("text")
        key = params.get("key")
        modifiers = params.get("modifiers")

        target_desc = (
            f"target_id={target_id}"
            if target_id is not None
            else f"element='{element_name}'"
            if element_name
            else f"coord={coord}"
            if coord
            else norm_action
        )

        # ── 1. Policy Gate Evaluation ──────────────────────────────
        perm_res = self.policy_gate.check_permissions("input:synthesize")
        if not perm_res.allowed:
            self.audit_store.record_action(
                action_id=action_id,
                lease_id=None,
                tier=ComputerTier.TIER_2_OVERLAY_INPUT.value,
                action_name=norm_action,
                target_desc=target_desc,
                target_x=coord[0] if coord else None,
                target_y=coord[1] if coord else None,
                chars_typed_count=len(text) if text else 0,
                started_at=start_time,
                duration_ms=0.0,
                success=False,
                error_code=perm_res.failure_code.value if perm_res.failure_code else "PERMISSION_DENIED",
            )
            return {"ok": False, "error": perm_res.reason, "code": perm_res.failure_code.value if perm_res.failure_code else "PERMISSION_DENIED"}

        if text and norm_action == "type":
            type_res = self.policy_gate.check_typing_content(text)
            if not type_res.allowed:
                self.audit_store.record_action(
                    action_id=action_id,
                    lease_id=None,
                    tier=ComputerTier.TIER_2_OVERLAY_INPUT.value,
                    action_name=norm_action,
                    target_desc=target_desc,
                    target_x=coord[0] if coord else None,
                    target_y=coord[1] if coord else None,
                    chars_typed_count=0,
                    started_at=start_time,
                    duration_ms=0.0,
                    success=False,
                    error_code=ComputerFailureCode.TYPING_GUARD_BLOCKED.value,
                )
                return {"ok": False, "error": type_res.reason, "code": ComputerFailureCode.TYPING_GUARD_BLOCKED.value}

        # ── 2. Loop Detection Check ────────────────────────────────
        is_loop = self.loop_detector.record_and_check(
            action_name=norm_action,
            target_id=target_id,
            target_coord=(coord[0], coord[1]) if coord and len(coord) >= 2 else None,
            text=text,
        )
        if is_loop:
            self.audit_store.record_action(
                action_id=action_id,
                lease_id=None,
                tier=ComputerTier.TIER_2_OVERLAY_INPUT.value,
                action_name=norm_action,
                target_desc=target_desc,
                target_x=coord[0] if coord else None,
                target_y=coord[1] if coord else None,
                chars_typed_count=len(text) if text else 0,
                started_at=start_time,
                duration_ms=0.0,
                success=False,
                error_code=ComputerFailureCode.ACTION_LOOP.value,
            )
            return {
                "ok": False,
                "error": f"Action loop detected: action '{norm_action}' repeated consecutively without state progress.",
                "code": ComputerFailureCode.ACTION_LOOP.value,
            }

        # ── 3. Tier 0 Check: Web Browser Tasks ─────────────────────
        if self._is_browser_target(params):
            tier0_res = await self._execute_tier0_browser(norm_action, params)
            if tier0_res.get("ok"):
                duration_ms = (time.time() - start_time) * 1000.0
                self.audit_store.record_action(
                    action_id=action_id,
                    lease_id=None,
                    tier=ComputerTier.TIER_0_BROWSER.value,
                    action_name=norm_action,
                    target_desc=target_desc,
                    target_x=None,
                    target_y=None,
                    chars_typed_count=len(text) if text else 0,
                    started_at=start_time,
                    duration_ms=duration_ms,
                    success=True,
                )
                return tier0_res

        # ── 4. Target Element Grounding ────────────────────────────
        resolved_x, resolved_y = None, None
        if coord and len(coord) >= 2:
            resolved_x, resolved_y = int(coord[0]), int(coord[1])
        elif target_id is not None or element_name is not None:
            resolved_pt = self._resolve_ui_target(target_id, element_name)
            if resolved_pt:
                resolved_x, resolved_y = resolved_pt
            else:
                return {
                    "ok": False,
                    "error": f"Target element not found: target_id={target_id}, element_name={element_name}",
                    "code": ComputerFailureCode.TARGET_NOT_FOUND.value,
                }

        # ── 5. Tier 2: Real Input Synthesis with Lease & Overlay ───
        try:
            async with self.arbiter.acquire_lease(session_id, norm_action) as lease_id:
                self.audit_store.record_lease_start(lease_id, session_id, "ACTIVE")

                # Move cursor if target point is known
                if resolved_x is not None and resolved_y is not None:
                    await self.backend.move(resolved_x, resolved_y, smooth=True)

                # Execute action
                if norm_action in ("click", "left_click"):
                    await self.backend.click("left", count=1)
                elif norm_action in ("double_click", "double_click_coordinate"):
                    await self.backend.click("left", count=2)
                elif norm_action in ("triple_click", "triple_click_coordinate"):
                    await self.backend.click("left", count=3)
                elif norm_action in ("right_click", "context_click"):
                    await self.backend.click("right", count=1)
                elif norm_action in ("middle_click", "middle_click_coordinate"):
                    await self.backend.click("middle", count=1)
                elif norm_action == "move":
                    pass  # Already moved above
                elif norm_action == "type" and text:
                    if resolved_x is not None and resolved_y is not None:
                        await self.backend.click("left", count=1)
                        await asyncio.sleep(0.04)
                    await self.backend.type_text(str(text))
                elif norm_action in ("key", "press_key") and key:
                    mods = modifiers if isinstance(modifiers, list) else None
                    await self.backend.key(str(key), mods)
                elif norm_action == "scroll":
                    dx = int(params.get("deltaX", params.get("dx", 0)))
                    dy = int(params.get("deltaY", params.get("dy", params.get("delta", 0))))
                    await self.backend.scroll(dx, dy)
                elif norm_action == "drag":
                    start_pt = params.get("start") or [resolved_x or 0, resolved_y or 0]
                    end_pt = params.get("end") or params.get("to") or [resolved_x or 0, resolved_y or 0]
                    await self.backend.drag(start_pt[0], start_pt[1], end_pt[0], end_pt[1])
                elif norm_action == "wait":
                    wait_s = float(params.get("seconds", params.get("duration", 0.5)))
                    await asyncio.sleep(min(max(wait_s, 0.05), 10.0))

                duration_ms = (time.time() - start_time) * 1000.0
                self.audit_store.record_action(
                    action_id=action_id,
                    lease_id=lease_id,
                    tier=ComputerTier.TIER_2_OVERLAY_INPUT.value,
                    action_name=norm_action,
                    target_desc=target_desc,
                    target_x=resolved_x,
                    target_y=resolved_y,
                    chars_typed_count=len(text) if text else 0,
                    started_at=start_time,
                    duration_ms=duration_ms,
                    success=True,
                )

                return {
                    "ok": True,
                    "action": norm_action,
                    "tier": ComputerTier.TIER_2_OVERLAY_INPUT.value,
                    "lease_id": lease_id,
                    "target_x": resolved_x,
                    "target_y": resolved_y,
                    "duration_ms": duration_ms,
                }

        except UserTakeoverException:
            logger.warning("Action %s aborted: user takeover", norm_action)
            duration_ms = (time.time() - start_time) * 1000.0
            self.audit_store.record_action(
                action_id=action_id,
                lease_id=self.arbiter.current_lease_id,
                tier=ComputerTier.TIER_2_OVERLAY_INPUT.value,
                action_name=norm_action,
                target_desc=target_desc,
                target_x=resolved_x,
                target_y=resolved_y,
                chars_typed_count=0,
                started_at=start_time,
                duration_ms=duration_ms,
                success=False,
                error_code=ComputerFailureCode.USER_TOOK_OVER.value,
            )
            return {
                "ok": False,
                "error": "Execution interrupted: User moved physical mouse or pressed keyboard.",
                "code": ComputerFailureCode.USER_TOOK_OVER.value,
            }

        except PanicStopException:
            logger.warning("Action %s aborted: panic stop", norm_action)
            duration_ms = (time.time() - start_time) * 1000.0
            self.audit_store.record_action(
                action_id=action_id,
                lease_id=self.arbiter.current_lease_id,
                tier=ComputerTier.TIER_2_OVERLAY_INPUT.value,
                action_name=norm_action,
                target_desc=target_desc,
                target_x=resolved_x,
                target_y=resolved_y,
                chars_typed_count=0,
                started_at=start_time,
                duration_ms=duration_ms,
                success=False,
                error_code=ComputerFailureCode.PANIC_STOP.value,
            )
            return {
                "ok": False,
                "error": "Emergency panic stop triggered by user.",
                "code": ComputerFailureCode.PANIC_STOP.value,
            }

        except LeaseBusyException as lbe:
            return {
                "ok": False,
                "error": str(lbe),
                "code": ComputerFailureCode.LEASE_BUSY.value,
            }

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000.0
            logger.error("Tier 2 input synthesis failed: %s", e)
            self.audit_store.record_action(
                action_id=action_id,
                lease_id=self.arbiter.current_lease_id,
                tier=ComputerTier.TIER_2_OVERLAY_INPUT.value,
                action_name=norm_action,
                target_desc=target_desc,
                target_x=resolved_x,
                target_y=resolved_y,
                chars_typed_count=0,
                started_at=start_time,
                duration_ms=duration_ms,
                success=False,
                error_code=str(e),
            )
            return {"ok": False, "error": str(e)}

    def _is_browser_target(self, params: dict[str, Any]) -> bool:
        """Check if target app or active window belongs to a web browser."""
        app_name = str(params.get("app_name") or params.get("target") or "").lower()
        if any(b in app_name for b in ("chrome", "edge", "firefox", "brave", "browser")):
            return True

        if sys.platform == "win32":
            try:
                import pygetwindow as gw
                win = gw.getActiveWindow()
                if win and any(b in str(win.title).lower() for b in ("chrome", "edge", "firefox", "brave", "youtube")):
                    return True
            except Exception:
                pass

        return False

    async def _execute_tier0_browser(
        self, action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Delegate a browser action to the host-owned browser tool.

        Resolved through ``src.tools.browser_host`` so this extension never
        imports a sibling extension; ``None`` means the browser capability is
        not installed and the caller falls through to the native tiers.
        """
        try:
            from src.tools.browser_host import get_browser_tool

            tool = get_browser_tool()
            if tool is None:
                return {"ok": False, "error": "browser capability not installed"}
            b_args = dict(params)
            b_args["action"] = "act"
            if action in ("click", "left_click"):
                b_args["kind"] = "click"
            elif action == "type":
                b_args["kind"] = "type"
            res = await tool.execute(b_args)
            return {"ok": True, "tier": ComputerTier.TIER_0_BROWSER.value, "result": res}
        except Exception as e:
            logger.debug("Tier 0 browser delegation fallback: %s", e)
            return {"ok": False, "error": str(e)}

    def _resolve_ui_target(
        self, target_id: int | None, element_name: str | None
    ) -> tuple[int, int] | None:
        """Resolve UI target coordinates via UIElementCache."""
        try:
            from src.agents.sessions.tools.ui_grounding import (
                get_ui_cache,
                scan_interactive_elements,
            )
            cache = get_ui_cache()
            pt = cache.resolve_target(target_id, element_name)
            if pt is None:
                scan_interactive_elements()
                pt = cache.resolve_target(target_id, element_name)
            return pt
        except Exception:
            return None


__all__ = ["TierRouter"]
