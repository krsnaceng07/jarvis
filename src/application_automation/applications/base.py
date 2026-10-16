"""jarvis.application_automation.applications.base — Base contract for application adapters.

Defines the abstract interface all specialized web application adapters must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from jarvis_sdk import Result
from ..action_verifier import ActionVerificationResult


class BaseApplicationAdapter(ABC):
    """Abstract contract for application-specific automation adapters."""

    @property
    @abstractmethod
    def app_name(self) -> str:
        """Application identifier (e.g. 'youtube', 'spotify')."""
        ...

    @abstractmethod
    def can_handle(self, url: str, app_name: Optional[str] = None) -> bool:
        """Check whether this adapter handles the target URL or application name."""
        ...

    @abstractmethod
    def get_current_state(self) -> str:
        """Current state of the application finite state machine."""
        ...

    @abstractmethod
    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        page: Any,
    ) -> Result[Dict[str, Any]]:
        """Execute a specialized application action on the active page."""
        ...

    @abstractmethod
    async def verify_action(
        self,
        action: str,
        params: Dict[str, Any],
        page: Any,
    ) -> ActionVerificationResult:
        """Verify that the action had the intended observable effect on the application."""
        ...

    @abstractmethod
    async def handle_interstitials(self, page: Any) -> bool:
        """Detect and automatically dismiss blocking popups, consent dialogs, or ads."""
        ...
