"""jarvis.desktop_automation.providers.base_provider — Base messaging provider contract.

OpenClaw parity: Defines the provider abstraction layer separating messaging
intent and channel routing from concrete execution engines (Desktop, Web, API).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CompletionStatus(str, Enum):
    COMPLETED_VERIFIED = "completed_verified"
    COMPLETED_UNVERIFIED = "completed_unverified"
    FAILED = "failed"
    BLOCKED = "blocked"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class ApplicationState:
    """Snapshot of host application runtime state."""
    app_id: str
    is_running: bool
    is_minimized: bool
    is_foreground: bool
    hwnd: Optional[int] = None
    pid: Optional[int] = None
    window_title: str = ""
    active_chat: str = ""


@dataclass(frozen=True, slots=True)
class ContactCandidate:
    """Disambiguated contact match from provider search."""
    name: str
    phone: Optional[str] = None
    identifier: Optional[str] = None
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class MessageDraft:
    """Preserved user dictated message with exact text preservation."""
    original_text: str
    normalized_text: str
    recipient: str
    modification_reason: Optional[str] = None


@dataclass
class ProviderActionResult:
    """Structured result of a provider operation with truthful verification."""
    ok: bool
    action: str
    application: str
    status: CompletionStatus = CompletionStatus.COMPLETED_VERIFIED
    verified: bool = False
    evidence: Dict[str, Any] = field(default_factory=dict)
    output_text: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "application": self.application,
            "status": self.status.value,
            "verified": self.verified,
            "evidence": self.evidence,
            "output_text": self.output_text,
            "error": self.error,
        }


class BaseMessagingProvider(ABC):
    """Abstract base class for all JARVIS messaging providers."""

    app_id: str
    app_name: str

    @abstractmethod
    async def get_state(self) -> ApplicationState:
        """Inspect and return current application and session state."""
        ...

    @abstractmethod
    async def ensure_active(self) -> bool:
        """Ensure application is running, unminimized, and in active foreground."""
        ...

    @abstractmethod
    async def search_contacts(self, query: str) -> List[ContactCandidate]:
        """Search contacts and return candidate list for disambiguation."""
        ...

    @abstractmethod
    async def open_chat(self, recipient: str) -> ProviderActionResult:
        """Open conversation with recipient and assert chat header."""
        ...

    @abstractmethod
    async def send_message(self, recipient: str, message: str) -> ProviderActionResult:
        """Send message with strict foreground verification and exact text preservation."""
        ...

    @abstractmethod
    async def verify_delivery(self, recipient: str, message: str) -> bool:
        """Verify message delivery in the active conversation."""
        ...
