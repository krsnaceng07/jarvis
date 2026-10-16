"""Zoom Meetings URL validation, normalization, and conversion utilities."""

from __future__ import annotations

import re
import urllib.parse

ZOOM_BASE_HOSTS = ("zoom.us", "zoomgov.com", "zoom.com")


def is_valid_zoom_host(host: str | None) -> bool:
    """Check if the hostname belongs to Zoom (e.g. zoom.us, us02web.zoom.us, example.zoom.us, zoomgov.com)."""
    if not host:
        return False
    h = host.strip().lower()
    return any(h == bh or h.endswith(f".{bh}") for bh in ZOOM_BASE_HOSTS)


def extract_meeting_id(path: str) -> str | None:
    """Extract numeric or vanity meeting ID from Zoom URL path."""
    clean_path = path.strip()
    # Match /j/<id>, /wc/join/<id>, /wc/<id>/join, /my/<name>, /postattendee?mn=<id>
    j_match = re.search(r"/(?:j|wc/join|wc)/([a-zA-Z0-9]+)", clean_path)
    if j_match:
        return j_match.group(1)

    my_match = re.search(r"/my/([a-zA-Z0-9._-]+)", clean_path)
    if my_match:
        return my_match.group(1)

    return None


def extract_passcode(query_or_url: str) -> str | None:
    """Extract meeting passcode (pwd parameter) from URL query."""
    if not query_or_url:
        return None
    try:
        parsed = urllib.parse.urlparse(query_or_url)
        query = parsed.query if parsed.query else query_or_url
        params = urllib.parse.parse_qs(query)
        pwd = params.get("pwd", [None])[0]
        if pwd:
            return pwd.strip()
    except Exception:
        pass
    return None


def normalize_zoom_url(raw_url: str | None) -> str:
    """Validate and normalize a Zoom meeting URL into canonical HTTPS form."""
    if not raw_url or not str(raw_url).strip():
        raise ValueError("Zoom meeting URL is required")

    url_str = str(raw_url).strip()
    if not url_str.startswith("http://") and not url_str.startswith("https://"):
        url_str = f"https://{url_str}"

    try:
        parsed = urllib.parse.urlparse(url_str)
    except Exception as err:
        raise ValueError(f"Invalid Zoom meeting URL: {raw_url}") from err

    host = (parsed.hostname or "").lower()
    if not is_valid_zoom_host(host):
        raise ValueError(
            f"Unsupported Zoom meeting host '{host}'. Expected zoom.us, zoomgov.com, or subdomain."
        )

    path = parsed.path or "/"
    meeting_id = extract_meeting_id(path)
    if not meeting_id:
        # Check query parameters (e.g. ?mn=123456789)
        params = urllib.parse.parse_qs(parsed.query)
        mn = params.get("mn", [None])[0]
        if mn:
            meeting_id = mn.strip()

    if not meeting_id:
        raise ValueError(
            f"Invalid Zoom meeting URL path '{path}'. Expected meeting ID in path (e.g. /j/<id>)."
        )

    return urllib.parse.urlunparse(
        (
            "https",
            host + (f":{parsed.port}" if parsed.port and parsed.port != 443 else ""),
            path,
            parsed.params,
            parsed.query,
            "",
        )
    )


def to_zoom_web_app_url(raw_url: str, guest_name: str | None = None) -> str:
    """Transform standard Zoom join link into direct Zoom Web Client URL (app.zoom.us/wc/join/<id>)."""
    norm = normalize_zoom_url(raw_url)
    parsed = urllib.parse.urlparse(norm)
    host = parsed.hostname or "app.zoom.us"

    meeting_id = extract_meeting_id(parsed.path)
    if not meeting_id:
        params = urllib.parse.parse_qs(parsed.query)
        meeting_id = params.get("mn", [""])[0]

    pwd = extract_passcode(parsed.query)

    # Web client host determination
    if host.endswith(".zoomgov.com") or host == "zoomgov.com":
        wc_host = "app.zoomgov.com"
    elif host == "zoom.us" or host == "zoom.com" or host.startswith("us0"):
        wc_host = "app.zoom.us"
    else:
        # Subdomain web client (e.g. example.zoom.us -> example.zoom.us/wc/join/<id>)
        wc_host = host

    query_dict: dict[str, str] = {}
    if pwd:
        query_dict["pwd"] = pwd
    if guest_name:
        query_dict["uname"] = guest_name

    query_str = urllib.parse.urlencode(query_dict) if query_dict else ""
    web_path = f"/wc/join/{meeting_id}"

    return urllib.parse.urlunparse(
        (
            "https",
            wc_host,
            web_path,
            "",
            query_str,
            "",
        )
    )


def is_zoom_url(url: str | None) -> bool:
    """Return True if url is a valid Zoom meeting URL."""
    if not url:
        return False
    try:
        normalize_zoom_url(url)
        return True
    except Exception:
        return False
