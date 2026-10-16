"""jarvis.desktop_automation.core.desktop_runtime — Central desktop coordinator.

Manages application discovery, active context, action routing, and execution serialization.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional


from .action_contract import DesktopActionResult
from ..discovery.process_detector import ProcessDetector
from ..discovery.window_detector import WindowDetector
from ..discovery.window_manager import WindowManager
from ..discovery.application_registry import ApplicationRegistry
from ..state.global_state_tracker import GlobalStateTracker
from ..security.confirmation_manager import ConfirmationManager
from ..security.input_lease import ai_input_lease
from ..applications import (
    WhatsAppDesktopAdapter,
    VSCodeDesktopAdapter,
    AntigravityDesktopAdapter,
    ClaudeCodeDesktopAdapter,
    OfficeDesktopAdapter,
    CalculatorDesktopAdapter,
    SettingsDesktopAdapter,
    ExplorerDesktopAdapter,
    GenericDesktopAdapter,
)


class DesktopRuntime:
    """Central singleton coordinator for desktop application automation."""

    _instance: Optional[DesktopRuntime] = None

    def __init__(self) -> None:
        self.context = GlobalStateTracker.get_context()
        self.window_manager = WindowManager()
        self.process_detector = ProcessDetector()
        self.window_detector = WindowDetector()
        self._adapters: Dict[str, Any] = {}
        self._execution_lock = asyncio.Lock()
        self._register_builtin_adapters()

    def _register_builtin_adapters(self) -> None:
        adapters = [
            WhatsAppDesktopAdapter(),
            VSCodeDesktopAdapter(),
            AntigravityDesktopAdapter(),
            ClaudeCodeDesktopAdapter(),
            OfficeDesktopAdapter("word"),
            OfficeDesktopAdapter("powerpoint"),
            OfficeDesktopAdapter("excel"),
            CalculatorDesktopAdapter(),
            SettingsDesktopAdapter(),
            ExplorerDesktopAdapter(),
            GenericDesktopAdapter(),
        ]
        for a in adapters:
            self.register_adapter(a)

    @classmethod
    def get_instance(cls) -> DesktopRuntime:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_adapter(self, adapter: Any) -> None:
        if hasattr(adapter, "app_id"):
            self._adapters[adapter.app_id.lower()] = adapter
        if hasattr(adapter, "app_name"):
            self._adapters[adapter.app_name.lower()] = adapter

    def get_adapter(self, app_name: str) -> Optional[Any]:
        return self._adapters.get(app_name.lower())

    def detect_active_application(self) -> Optional[str]:
        """Detect the application corresponding to the current foreground window."""
        hwnd = self.window_manager.get_foreground_window()
        if not hwnd:
            return None
        windows = self.window_detector.list_windows()
        for win in windows:
            if win.hwnd == hwnd:
                self.context.active_hwnd = win.hwnd
                self.context.active_pid = win.pid
                self.context.active_window_title = win.title
                proc = self.process_detector.get_process_by_pid(win.pid)
                pname = proc["name"] if proc else ""
                meta = ApplicationRegistry.find_by_process_or_title(pname, win.title)
                if meta:
                    self.context.active_application = meta.app_id
                    return meta.app_id
                return "generic"
        return None

    async def execute_action(
        self,
        app_name: str,
        action: str,
        params: Dict[str, Any],
    ) -> DesktopActionResult:
        """Execute action through target application adapter with serialization and safety checks."""
        async with self._execution_lock:
            adapter = self.get_adapter(app_name) or self.get_adapter("generic")
            if not adapter:
                return DesktopActionResult(
                    ok=False,
                    action=action,
                    application=app_name,
                    error=f"No adapter registered for application '{app_name}'",
                )

            # Safety check: Confirmation Gating
            if ConfirmationManager.requires_confirmation(action, params) and not params.get(
                "confirmed", False
            ):
                prompt = ConfirmationManager.build_confirmation_prompt(action, params)
                return DesktopActionResult(
                    ok=True,
                    action=action,
                    application=app_name,
                    requires_confirmation=True,
                    confirmation_prompt=prompt,
                    evidence={"status": "pending_confirmation", "prompt": prompt},
                )

            # Ensure application window is focused in the foreground before acting
            focused = await adapter.ensure_running_and_focused()
            if not focused:
                return DesktopActionResult(
                    ok=False,
                    action=action,
                    application=app_name,
                    error=(
                        f"Application '{adapter.app_name}' could not be brought to the foreground "
                        f"(it may be minimized or blocked by another window). "
                        f"Action aborted to prevent typing into the wrong window."
                    ),
                )

            # Execute action via adapter under an optional short input lease.
            with ai_input_lease(action):
                res = await adapter.execute_action(action, params, self.context)
            if not res.ok:
                return res

            # Update context state
            self.context.active_application = app_name
            if res.verified:
                self.context.last_verified_action = f"{app_name}_{action}_completed"

            return res
