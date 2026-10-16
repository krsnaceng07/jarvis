"""jarvis.application_automation.active_tab_tracker — Tab identity & affinity tracker.

Mirrors OpenClaw's ``extensions/browser/src/browser-tool-session-tabs.ts``:
- Maintains durable tab aliases (label, tabId, targetId).
- Tracks application type and active foreground tab per session.
- Enables safe tab reuse without duplicate tab creation or destructive reloads.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


def detect_application_type_from_url(url: str) -> str:
    """Detect application category from page URL."""
    if not url:
        return "generic"
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower().removeprefix("www.")
        if "youtube.com" in host or "youtu.be" in host:
            return "youtube"
        if "spotify.com" in host:
            return "spotify"
        if "github.com" in host:
            return "github"
        if "google.com" in host:
            return "google"
        if "docs.google.com" in host:
            return "google_docs"
        return "web"
    except Exception:
        return "generic"


@dataclass(slots=True)
class TrackedTab:
    """Represents an active, tracked browser tab."""

    target_id: str
    url: str = ""
    title: str = ""
    label: str = ""
    tab_id: str = ""
    app_type: str = "generic"
    last_active_time: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def suggested_target_id(self) -> str:
        """OpenClaw parity: prefers label > tabId > targetId."""
        return self.label or self.tab_id or self.target_id

    @property
    def aliases(self) -> List[str]:
        """All valid identifiers that resolve to this tab."""
        items = [self.target_id, self.tab_id, self.label, self.suggested_target_id]
        return [x for x in dict.fromkeys(items) if x]


class ActiveTabTracker:
    """Registry tracking tab affinity, active applications, and tab handles."""

    _instance: Optional[ActiveTabTracker] = None

    def __init__(self) -> None:
        self._tabs: Dict[str, TrackedTab] = {}  # target_id -> TrackedTab
        self._alias_map: Dict[str, str] = {}    # alias -> target_id
        self._active_target_id: Optional[str] = None

    @classmethod
    def get_instance(cls) -> ActiveTabTracker:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_tab(
        self,
        target_id: str,
        url: str = "",
        title: str = "",
        label: str = "",
        tab_id: str = "",
        app_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrackedTab:
        """Register or update a tracked tab."""
        resolved_app = app_type or detect_application_type_from_url(url)
        tab = TrackedTab(
            target_id=target_id,
            url=url,
            title=title,
            label=label,
            tab_id=tab_id or target_id,
            app_type=resolved_app,
            last_active_time=time.time(),
            metadata=metadata or {},
        )

        self._tabs[target_id] = tab
        self._active_target_id = target_id

        # Update alias mappings
        for alias in tab.aliases:
            self._alias_map[alias.lower()] = target_id

        return tab

    def resolve_target_id(self, target_id_or_alias: str) -> Optional[str]:
        """Resolve any alias (label, tabId, suggestedTargetId) to canonical target_id."""
        if not target_id_or_alias:
            return self._active_target_id
        key = target_id_or_alias.strip().lower()
        return self._alias_map.get(key) or (target_id_or_alias if target_id_or_alias in self._tabs else None)

    def get_tab(self, target_id_or_alias: Optional[str] = None) -> Optional[TrackedTab]:
        """Retrieve tab by target_id or alias, or active tab if none specified."""
        if target_id_or_alias is None:
            tid = self._active_target_id
        else:
            tid = self.resolve_target_id(target_id_or_alias)
        return self._tabs.get(tid) if tid else None

    def touch_tab(self, target_id_or_alias: str) -> None:
        """Mark tab as recently used and active."""
        tid = self.resolve_target_id(target_id_or_alias)
        if tid and tid in self._tabs:
            self._tabs[tid].last_active_time = time.time()
            self._active_target_id = tid

    def untrack_tab(self, target_id_or_alias: str) -> None:
        """Untrack and remove tab registration."""
        tid = self.resolve_target_id(target_id_or_alias)
        if not tid or tid not in self._tabs:
            return
        tab = self._tabs.pop(tid)
        for alias in tab.aliases:
            self._alias_map.pop(alias.lower(), None)
        if self._active_target_id == tid:
            self._active_target_id = next(iter(self._tabs), None)

    def find_tab_by_app(self, app_type: str) -> Optional[TrackedTab]:
        """Find the most recently active tab matching the specified application type."""
        matching = [t for t in self._tabs.values() if t.app_type.lower() == app_type.lower()]
        if not matching:
            return None
        matching.sort(key=lambda t: t.last_active_time, reverse=True)
        return matching[0]

    def get_active_tab_for_app(self, app_type: str) -> Optional[TrackedTab]:
        """Convenience alias for find_tab_by_app."""
        return self.find_tab_by_app(app_type)


    def find_tab_by_domain(self, domain_or_url: str) -> Optional[TrackedTab]:
        """Find existing open tab matching hostname without trailing paths."""
        try:
            target_host = urlparse(domain_or_url).netloc.lower().removeprefix("www.")
            if not target_host and "/" not in domain_or_url:
                target_host = domain_or_url.lower().removeprefix("www.")
            if not target_host:
                return None

            for tab in sorted(self._tabs.values(), key=lambda t: t.last_active_time, reverse=True):
                tab_host = urlparse(tab.url).netloc.lower().removeprefix("www.")
                if tab_host and (tab_host == target_host or target_host in tab_host or tab_host in target_host):
                    return tab
        except Exception:
            pass
        return None

    def list_tabs(self) -> List[TrackedTab]:
        return sorted(self._tabs.values(), key=lambda t: t.last_active_time, reverse=True)

    def clear(self) -> None:
        self._tabs.clear()
        self._alias_map.clear()
        self._active_target_id = None
