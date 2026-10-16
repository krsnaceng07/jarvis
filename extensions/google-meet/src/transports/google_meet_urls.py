"""Google Meet URL manipulation and tab recovery heuristics."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

MEET_CODE_PATH_RE = re.compile(r"^/([a-z]{3}-[a-z]{4}-[a-z]{3})(?:/)?$", re.IGNORECASE)
SIGNIN_RE = re.compile(r"sign in|google accounts|meet", re.IGNORECASE)


def force_meet_english_ui(url: str) -> str:
    """Pin the page language to English while preserving query parameters."""
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        query["hl"] = ["en"]
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
    except Exception:
        return url


def normalize_meet_url_for_reuse(url: str | None) -> str | None:
    """Normalize Meet URL for session reuse matching."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.hostname.lower() != "meet.google.com"
        ):
            return None
        match = MEET_CODE_PATH_RE.match(parsed.path)
        if not match:
            return None
        return f"https://meet.google.com/{match.group(1).lower()}"
    except Exception:
        return None


def is_same_meet_url_for_reuse(a: str | None, b: str | None) -> bool:
    """Check if two Meet URLs point to the same meeting code."""
    norm_a = normalize_meet_url_for_reuse(a)
    norm_b = normalize_meet_url_for_reuse(b)
    return bool(norm_a and norm_b and norm_a == norm_b)


def is_english_meet_tab(url: str | None) -> bool:
    """Check if URL is a meet.google.com tab with ?hl=en."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.hostname.lower() != "meet.google.com"
        ):
            return False
        query = parse_qs(parsed.query)
        hl = query.get("hl", [])
        return bool(hl and hl[0].lower() == "en")
    except Exception:
        return False


def read_meet_auth_user(url: str | None) -> str | None:
    """Read authuser query param if present."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        authuser = query.get("authuser")
        return authuser[0] if authuser else None
    except Exception:
        return None


def is_recoverable_meet_tab(tab: dict[str, Any], url: str | None = None) -> bool:
    """Check if a browser tab is an existing Meet tab or Google sign-in page."""
    tab_url = str(tab.get("url") or "")
    tab_title = str(tab.get("title") or "")
    if url:
        return is_same_meet_url_for_reuse(tab_url, url)
    if normalize_meet_url_for_reuse(tab_url) is not None:
        return True
    return tab_url.startswith("https://accounts.google.com/") and bool(SIGNIN_RE.search(tab_title))


def is_google_meet_page_url(url: str | None) -> bool:
    """Check if URL points to a Google Meet domain page."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return bool(parsed.hostname and parsed.hostname.lower() == "meet.google.com")
    except Exception:
        return False
