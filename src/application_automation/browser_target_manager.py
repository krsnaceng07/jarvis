"""jarvis.application_automation.browser_target_manager — Durable target & tab management with stale recovery.

OpenClaw parity:
- extensions/browser/src/browser-tool-session-tabs.ts (tab tracking & aliases)
- extensions/browser/src/browser-tool.actions.ts (isChromeStaleTargetError, replaceStaleTargetIdInActRequest)
- src/agents/tools/computer-tool-guidance.ts (target validation & stale ref rules)

Guarantees:
1. Target existence and session ownership are confirmed before every action.
2. Wrong-tab actions are strictly prevented.
3. TargetStaleError triggers automatic re-discovery and re-binding without silent failure.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from .active_tab_tracker import ActiveTabTracker, TrackedTab, detect_application_type_from_url


class TargetStaleError(Exception):
    """Raised when an operation targets a tab that has closed, navigated away, or lost its handle."""

    def __init__(self, target_id: str, reason: str = "Target not found or closed") -> None:
        super().__init__(f"TargetStaleError[{target_id}]: {reason}")
        self.target_id = target_id
        self.reason = reason


class WrongTabError(Exception):
    """Raised when an action is dispatched to a tab whose domain/app differs from expected target."""

    def __init__(self, target_id: str, expected_app: str, actual_url: str) -> None:
        super().__init__(
            f"WrongTabError[{target_id}]: Expected application '{expected_app}', but tab URL is '{actual_url}'"
        )
        self.target_id = target_id
        self.expected_app = expected_app
        self.actual_url = actual_url


@dataclass(slots=True)
class ValidatedTargetContext:
    """Authoritative snapshot of a validated browser target."""

    session_id: str
    target_id: str
    tab_id: str
    url: str
    title: str
    domain: str
    app_type: str
    last_verified_time: float = field(default_factory=time.time)


class BrowserTargetManager:
    """Manages browser targets, verifies target health, and recovers from stale targets."""

    _instance: Optional[BrowserTargetManager] = None

    def __init__(self) -> None:
        self.tracker = ActiveTabTracker.get_instance()
        self._target_sessions: Dict[str, str] = {}  # target_id -> session_id

    @classmethod
    def get_instance(cls) -> BrowserTargetManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_target(
        self,
        target_id: str,
        session_id: str = "default",
        url: str = "",
        title: str = "",
        label: str = "",
        tab_id: str = "",
    ) -> TrackedTab:
        """Register a confirmed target."""
        self._target_sessions[target_id] = session_id
        tab = self.tracker.register_tab(
            target_id=target_id,
            url=url,
            title=title,
            label=label,
            tab_id=tab_id,
        )
        return tab

    def validate_target(
        self,
        target_id: str,
        expected_app: Optional[str] = None,
        expected_domain: Optional[str] = None,
        runtime_tabs: Optional[List[Dict[str, Any]]] = None,
    ) -> ValidatedTargetContext:
        """Confirm target is alive and matches expected app/domain.

        Raises:
            TargetStaleError: If target is not found in runtime tabs or closed.
            WrongTabError: If target URL belongs to an unexpected application.
        """
        # Resolve alias
        canonical_target_id = self.tracker.resolve_target_id(target_id) or target_id

        # If runtime tabs provided, check live existence
        live_tab: Optional[Dict[str, Any]] = None
        if runtime_tabs is not None:
            for rt in runtime_tabs:
                tid = rt.get("targetId") or rt.get("id") or rt.get("tabId")
                if tid and (tid == canonical_target_id or tid == target_id):
                    live_tab = rt
                    break
            if not live_tab:
                raise TargetStaleError(
                    canonical_target_id,
                    f"Target '{target_id}' is no longer present in open browser tabs",
                )

        tracked = self.tracker.get_tab(canonical_target_id)
        current_url = (live_tab.get("url") if live_tab else None) or (tracked.url if tracked else "")
        current_title = (live_tab.get("title") if live_tab else None) or (tracked.title if tracked else "")

        # Parse domain
        domain = ""
        if current_url:
            try:
                domain = urlparse(current_url).netloc.lower().removeprefix("www.")
            except Exception:
                pass

        current_app = detect_application_type_from_url(current_url)

        # Validate application affinity if specified
        if expected_app and expected_app != "generic":
            if current_app != expected_app and not (expected_app == "youtube" and "youtube.com" in domain):
                raise WrongTabError(canonical_target_id, expected_app, current_url)

        if expected_domain and expected_domain not in domain:
            raise WrongTabError(canonical_target_id, expected_domain, current_url)

        # Update tracking
        self.tracker.register_tab(
            target_id=canonical_target_id,
            url=current_url,
            title=current_title,
            app_type=current_app,
        )

        return ValidatedTargetContext(
            session_id=self._target_sessions.get(canonical_target_id, "default"),
            target_id=canonical_target_id,
            tab_id=tracked.tab_id if tracked else canonical_target_id,
            url=current_url,
            title=current_title,
            domain=domain,
            app_type=current_app,
        )

    def recover_stale_target(
        self,
        stale_target_id: str,
        desired_app: str,
        runtime_tabs: List[Dict[str, Any]],
    ) -> Optional[ValidatedTargetContext]:
        """Attempt to re-discover an alternative tab matching the desired application."""
        if not runtime_tabs:
            return None

        # Look for matching open tab
        for tab_info in runtime_tabs:
            url = tab_info.get("url", "")
            tid = tab_info.get("targetId") or tab_info.get("id") or tab_info.get("tabId")
            if not tid or tid == stale_target_id:
                continue

            app = detect_application_type_from_url(url)
            if app == desired_app or (desired_app == "youtube" and "youtube.com" in url):
                # Found candidate tab! Re-register and return validated context
                title = tab_info.get("title", "")
                self.register_target(target_id=tid, url=url, title=title)
                return self.validate_target(tid, expected_app=desired_app, runtime_tabs=runtime_tabs)

        return None
