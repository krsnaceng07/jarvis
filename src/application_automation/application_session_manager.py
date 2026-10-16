"""jarvis.application_automation.application_session_manager — Central application orchestrator.

Coordinates active applications, session affinity, adapter dispatch, and task continuity.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from jarvis_sdk import Err, Ok, Result

from .active_tab_tracker import ActiveTabTracker
from .applications.base import BaseApplicationAdapter
from .contextual_resolver import ContextualResolver


class ApplicationSessionManager:
    """Singleton orchestrator managing registered application adapters and active sessions."""

    _instance: Optional[ApplicationSessionManager] = None

    def __init__(
        self,
        tab_tracker: Optional[ActiveTabTracker] = None,
        contextual_resolver: Optional[ContextualResolver] = None,
    ) -> None:
        self.tab_tracker = tab_tracker or ActiveTabTracker.get_instance()
        self.contextual_resolver = contextual_resolver or ContextualResolver(self.tab_tracker)
        self._adapters: Dict[str, BaseApplicationAdapter] = {}
        self._active_app: Optional[str] = None
        # Auto-register built-in adapters
        from .applications.youtube.adapter import YouTubeAdapter
        from .applications.web import GenericWebAdapter
        self.register_adapter(YouTubeAdapter())
        self.register_adapter(GenericWebAdapter())

    @classmethod
    def get_instance(cls) -> ApplicationSessionManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_adapter(self, adapter: BaseApplicationAdapter) -> None:
        """Register an application adapter."""
        self._adapters[adapter.app_name.lower()] = adapter

    def get_adapter(self, app_name: str) -> Optional[BaseApplicationAdapter]:
        """Retrieve adapter by name."""
        return self._adapters.get(app_name.lower())

    def find_adapter_for_url(self, url: str) -> Optional[BaseApplicationAdapter]:
        """Find an adapter that can handle the given URL.
        
        Specific adapters (e.g. YouTube, Spotify) take precedence;
        GenericWebAdapter is used as the universal fallback for web URLs.
        """
        for adapter in self._adapters.values():
            if adapter.app_name != "web" and adapter.can_handle(url):
                return adapter
        web_adapter = self.get_adapter("web")
        if web_adapter and web_adapter.can_handle(url):
            return web_adapter
        return None

    @property
    def active_application(self) -> Optional[str]:
        return self._active_app

    def set_active_application(self, app_name: Optional[str]) -> None:
        self._active_app = app_name.lower() if app_name else None

    async def execute_action(
        self,
        app_name: str,
        action: str,
        params: Dict[str, Any],
        page: Any,
    ) -> Result[Dict[str, Any]]:
        """Dispatch action to the target application adapter with pre-recovery and verification."""
        adapter = self.get_adapter(app_name)
        if not adapter:
            return Err(f"No adapter registered for application '{app_name}'", code="ADAPTER_NOT_FOUND")

        # 1. Pre-execution interstitial handling (cookie consent, popups, ads)
        try:
            await adapter.handle_interstitials(page)
        except Exception:
            pass

        # 2. Execute action via adapter
        res = await adapter.execute_action(action, params, page)
        if not res.is_ok:
            return res

        # 3. Post-execution verification
        verification = await adapter.verify_action(action, params, page)
        payload = dict(res.unwrap())
        payload["verification"] = {
            "effect": verification.effect.value,
            "verified": verification.verified,
            "details": verification.details,
            "error": verification.error,
        }

        # Update active app state
        self.set_active_application(app_name)
        if hasattr(adapter, "get_playback_status"):
            try:
                status_fn = getattr(adapter, "get_playback_status")
                media_info = await status_fn(page)
                self.contextual_resolver.record_media_state(
                    title=media_info.get("title"),
                    query=params.get("query"),
                )
            except Exception:
                pass

        return Ok(payload)
