"""jarvis.desktop_automation.state.session_manager — Application session manager.

OpenClaw parity: Tracks host application sessions, active windows, PIDs,
minimized states, and active chat contexts across conversational turns.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ApplicationSession:
    app_id: str
    app_name: str
    process_id: Optional[int] = None
    window_id: Optional[int] = None
    window_title: str = ""
    is_minimized: bool = False
    is_foreground: bool = False
    active_chat: Optional[str] = None
    active_contact: Optional[str] = None
    last_action: Optional[str] = None
    last_verified_action: Optional[str] = None
    session_started_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_fresh(self, max_age_sec: float = 300.0) -> bool:
        """Check if session was seen within max_age_sec."""
        return (time.time() - self.last_seen_at) <= max_age_sec


class ApplicationSessionManager:
    """Manages active application sessions across desktop workflows."""

    _instance: Optional[ApplicationSessionManager] = None

    def __init__(self) -> None:
        self._sessions: Dict[str, ApplicationSession] = {}

    @classmethod
    def get_instance(cls) -> ApplicationSessionManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_session(self, app_id: str) -> Optional[ApplicationSession]:
        """Retrieve existing session for app_id if fresh."""
        session = self._sessions.get(app_id.lower())
        if session and session.is_fresh():
            return session
        return None

    def update_session(
        self,
        app_id: str,
        app_name: str,
        process_id: Optional[int] = None,
        window_id: Optional[int] = None,
        window_title: str = "",
        is_minimized: bool = False,
        is_foreground: bool = False,
        active_chat: Optional[str] = None,
        active_contact: Optional[str] = None,
        last_action: Optional[str] = None,
        last_verified_action: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApplicationSession:
        """Create or update application session."""
        key = app_id.lower()
        now = time.time()
        existing = self._sessions.get(key)

        if existing:
            existing.process_id = process_id or existing.process_id
            existing.window_id = window_id or existing.window_id
            existing.window_title = window_title or existing.window_title
            existing.is_minimized = is_minimized
            existing.is_foreground = is_foreground
            if active_chat:
                existing.active_chat = active_chat
            if active_contact:
                existing.active_contact = active_contact
            if last_action:
                existing.last_action = last_action
            if last_verified_action:
                existing.last_verified_action = last_verified_action
            if metadata:
                existing.metadata.update(metadata)
            existing.last_seen_at = now
            return existing

        session = ApplicationSession(
            app_id=key,
            app_name=app_name,
            process_id=process_id,
            window_id=window_id,
            window_title=window_title,
            is_minimized=is_minimized,
            is_foreground=is_foreground,
            active_chat=active_chat,
            active_contact=active_contact,
            last_action=last_action,
            last_verified_action=last_verified_action,
            session_started_at=now,
            last_seen_at=now,
            metadata=metadata or {},
        )
        self._sessions[key] = session
        return session

    def clear_session(self, app_id: str) -> None:
        """Remove session when application is closed."""
        self._sessions.pop(app_id.lower(), None)
