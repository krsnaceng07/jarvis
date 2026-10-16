"""jarvis.desktop_automation - Unified Desktop Automation, Computer-Use and Task Continuity Subsystem."""

from .core.action_contract import (
    ActionEffect,
    ActionVerificationResult,
    DesktopAction,
    DesktopActionResult,
)
from .core.control_strategy import ControlChannel, ControlPlan, ControlRisk, build_control_plan
from .core.desktop_runtime import DesktopRuntime
from .core.task_continuity import TaskContinuity
from .discovery.application_registry import ApplicationMetadata, ApplicationRegistry
from .discovery.process_detector import ProcessDetector
from .discovery.window_detector import WindowDetector, WindowInfo
from .discovery.window_manager import WindowManager
from .interaction.keyboard_controller import KeyboardController
from .interaction.mouse_controller import MouseController
from .interaction.screenshot_controller import ScreenshotController
from .security.confirmation_manager import ConfirmationManager
from .security.recipient_guard import RecipientGuard
from .state.active_desktop_context import ActiveDesktopContext
from .state.global_state_tracker import GlobalStateTracker
from .applications import (
    BaseDesktopApplicationAdapter,
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

__all__ = [
    "ActionEffect",
    "ActionVerificationResult",
    "DesktopAction",
    "DesktopActionResult",
    "ControlChannel",
    "ControlPlan",
    "ControlRisk",
    "build_control_plan",
    "DesktopRuntime",
    "TaskContinuity",
    "ApplicationMetadata",
    "ApplicationRegistry",
    "ProcessDetector",
    "WindowDetector",
    "WindowInfo",
    "WindowManager",
    "KeyboardController",
    "MouseController",
    "ScreenshotController",
    "ConfirmationManager",
    "RecipientGuard",
    "ActiveDesktopContext",
    "GlobalStateTracker",
    "BaseDesktopApplicationAdapter",
    "WhatsAppDesktopAdapter",
    "VSCodeDesktopAdapter",
    "AntigravityDesktopAdapter",
    "ClaudeCodeDesktopAdapter",
    "OfficeDesktopAdapter",
    "CalculatorDesktopAdapter",
    "SettingsDesktopAdapter",
    "ExplorerDesktopAdapter",
    "GenericDesktopAdapter",
]
