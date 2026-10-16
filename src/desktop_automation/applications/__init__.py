"""jarvis.desktop_automation.applications — Application adapter barrel."""

from .base import BaseDesktopApplicationAdapter
from .whatsapp import WhatsAppDesktopAdapter
from .vscode import VSCodeDesktopAdapter
from .antigravity import AntigravityDesktopAdapter
from .claude_code import ClaudeCodeDesktopAdapter
from .office import OfficeDesktopAdapter
from .calculator import CalculatorDesktopAdapter
from .settings import SettingsDesktopAdapter
from .explorer import ExplorerDesktopAdapter
from .generic import GenericDesktopAdapter

__all__ = [
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

