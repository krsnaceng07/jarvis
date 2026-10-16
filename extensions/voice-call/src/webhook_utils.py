"""Webhook URL reachability, validation, and resolution utilities for Voice Call."""

from __future__ import annotations

import ipaddress
import urllib.parse
from typing import Any


def is_provider_unreachable_webhook_url(webhook_url: str | None) -> bool:
    """Check if a webhook URL points to local, loopback, private, or unreachable network space.

    Twilio, Telnyx, and Plivo require publicly reachable HTTPS/HTTP endpoints.
    Returns True if the URL is unreachable by public carriers (e.g. localhost, private IP).
    """
    if not webhook_url or not isinstance(webhook_url, str):
        return True

    url_str = webhook_url.strip()
    if not url_str:
        return True

    try:
        parsed = urllib.parse.urlparse(url_str)
        if parsed.scheme not in ("http", "https"):
            return True

        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            return True

        if hostname in ("localhost", "localhost.localdomain", "0.0.0.0", "::") or hostname.endswith(
            ".localhost"
        ):
            return True

        # Check IP address classes
        try:
            ip = ipaddress.ip_address(hostname)
            return bool(
                ip.is_private
                or ip.is_loopback
                or ip.is_unspecified
                or ip.is_link_local
                or ip.is_reserved
            )
        except ValueError:
            # Domain name (e.g. example.ngrok.app, voice.example.com)
            return False
    except Exception:
        return True


def resolve_public_webhook_url(
    *,
    public_url: str | None = None,
    tunnel: dict[str, Any] | None = None,
    tailscale: dict[str, Any] | None = None,
) -> str | None:
    """Resolve the effective public webhook URL from direct config, tunnel, or Tailscale.

    Returns the public URL string, or None if none configured or if only loopback/disabled.
    """
    if public_url:
        trimmed = public_url.strip()
        if trimmed:
            return trimmed

    if tunnel and isinstance(tunnel, dict):
        provider = str(tunnel.get("provider") or "").strip().lower()
        tunnel_url = str(tunnel.get("url") or "").strip()
        if provider and provider != "none":
            if tunnel_url:
                return tunnel_url
            return f"tunnel://{provider}"

    if tailscale and isinstance(tailscale, dict):
        mode = str(tailscale.get("mode") or "").strip().lower()
        target = str(tailscale.get("target") or tailscale.get("url") or "").strip()
        if mode and mode != "off":
            if target:
                return target
            return f"tailscale://{mode}"

    return None
