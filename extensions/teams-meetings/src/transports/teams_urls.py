"""Teams Meetings URL matching, reuse heuristics, and tab recovery."""

from __future__ import annotations

import urllib.parse
from typing import Any

from ..teams_url import is_valid_teams_host, normalize_teams_url


def normalize_teams_url_for_reuse(url: str | None) -> str | None:
    if not url:
        return None
    try:
        norm = normalize_teams_url(url)
        parsed = urllib.parse.urlparse(norm)
        # Match base host + path without query parameters for tab reuse
        return f"{parsed.scheme}://{(parsed.hostname or '').lower()}{parsed.path.rstrip('/')}"
    except Exception:
        return None


def is_same_teams_url_for_reuse(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    norm_a = normalize_teams_url_for_reuse(a)
    norm_b = normalize_teams_url_for_reuse(b)
    return bool(norm_a and norm_b and norm_a == norm_b)


def is_recoverable_teams_tab(tab: Any, requested_url: str | None = None) -> bool:
    tab_url = getattr(tab, "url", None) or (tab.get("url") if isinstance(tab, dict) else None) or ""
    if not tab_url:
        return False
    try:
        parsed = urllib.parse.urlparse(str(tab_url).strip())
        host = (parsed.hostname or "").lower()
        if not is_valid_teams_host(host):
            return False
        if requested_url:
            return is_same_teams_url_for_reuse(tab_url, requested_url)
        return True
    except Exception:
        return False
