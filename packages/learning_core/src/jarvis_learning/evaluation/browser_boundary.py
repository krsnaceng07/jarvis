"""jarvis_learning.evaluation.browser_boundary — Dual-Mode Browser & Tab Continuity.

Enforces:
1. INV-P9-SAFE-002: Mode A (Read-only observation) vs Mode B (Virtual simulator).
2. Sanitized observation without exposing direct browser/CDP debug endpoints.
3. Session continuity: YouTube tab reuse without duplicate tab creation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BrowserTabMetadata:
    """Sanitized metadata snapshot of a browser tab."""

    tab_id: str
    title: str
    url: str
    domain: str
    is_active: bool = False


@dataclass
class VirtualBrowserState:
    """In-memory virtual browser state for safe shadow candidate execution."""

    tabs: dict[str, BrowserTabMetadata] = field(default_factory=dict)
    active_tab_id: str | None = None
    navigation_history: list[dict[str, str]] = field(default_factory=list)
    simulated_clicks: list[dict[str, Any]] = field(default_factory=list)

    def find_tab_by_domain(self, domain_keyword: str) -> BrowserTabMetadata | None:
        """Find existing open tab matching domain keyword (e.g. 'youtube.com' or 'youtube')."""
        kw = domain_keyword.lower()
        for tab in self.tabs.values():
            if kw in tab.url.lower() or kw in tab.title.lower() or kw in tab.domain.lower():
                return tab
        return None

    def open_or_reuse_tab(self, url: str, title: str = "") -> tuple[BrowserTabMetadata, bool]:
        """Open a new tab or reuse existing matching tab (Session Continuity).

        Returns (tab_metadata, was_reused: bool).
        """
        # Check domain to see if matching tab is already open
        domain = url.split("/")[2] if "://" in url else url.split("/")[0]
        existing = self.find_tab_by_domain(domain)

        if existing:
            # Reuse existing tab: update URL/title without creating duplicate tab
            updated = BrowserTabMetadata(
                tab_id=existing.tab_id,
                title=title or existing.title,
                url=url,
                domain=domain,
                is_active=True,
            )
            self.tabs[existing.tab_id] = updated
            self.active_tab_id = existing.tab_id
            self.navigation_history.append(
                {"tab_id": existing.tab_id, "action": "REUSE", "url": url}
            )
            logger.info("Session Continuity: Reused existing tab %s for %s", existing.tab_id, url)
            return updated, True

        # Open new tab
        new_tab_id = f"tab_{len(self.tabs) + 1}"
        new_tab = BrowserTabMetadata(
            tab_id=new_tab_id,
            title=title or domain,
            url=url,
            domain=domain,
            is_active=True,
        )
        self.tabs[new_tab_id] = new_tab
        self.active_tab_id = new_tab_id
        self.navigation_history.append({"tab_id": new_tab_id, "action": "OPEN", "url": url})
        return new_tab, False

    def simulate_click(self, selector: str) -> dict[str, Any]:
        """Simulate click in virtual DOM without live side-effects."""
        record = {"action": "click", "selector": selector, "tab_id": self.active_tab_id}
        self.simulated_clicks.append(record)
        return {"status": "success", "simulated": True, "selector": selector}
