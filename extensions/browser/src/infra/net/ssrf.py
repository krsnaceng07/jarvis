"""SSRF policy helpers for Browser network/navigation guards."""

import ipaddress
import socket
from urllib.parse import urlparse
from typing import Optional

from ...config import BrowserSsrFPolicy


class SsrFBlockedError(Exception):
    """Exception raised when a request is blocked by SSRF policy."""

    pass


def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
        )
    except ValueError:
        return False


def _is_loopback_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_loopback
    except ValueError:
        return False


def is_private_network_allowed_by_policy(url: str, policy: Optional[BrowserSsrFPolicy]) -> bool:
    """Check if the given URL is allowed by the SSRF policy."""
    if not policy:
        return True  # Default to allow if no policy (or implement strict default based on config)

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False

        # Try to resolve hostname to IP
        try:
            ip = socket.gethostbyname(hostname)
        except socket.gaierror:
            ip = hostname  # fallback to testing the hostname if it's already an IP

        if _is_loopback_ip(ip) and not policy.get("allowLoopback", False):
            return False

        if _is_private_ip(ip):
            # Check if hostname or IP is in allowed list
            allowed_hosts = policy.get("allowedHostnames", [])
            if hostname in allowed_hosts or ip in allowed_hosts:
                return True
            # We skip CIDR checks for simplicity in this port, but they would go here
            return False

        return True
    except Exception:
        return False


def check_url_against_policy(url: str, policy: Optional[BrowserSsrFPolicy]) -> None:
    """Raise SsrFBlockedError if the URL violates the policy."""
    if not is_private_network_allowed_by_policy(url, policy):
        raise SsrFBlockedError(f"Navigation to {url} is blocked by SSRF policy.")
