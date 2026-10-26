"""packages/net_policy/src/jarvis_net_policy/__init__.py

Network security policies, SSRF prevention, sensitive URL redaction, and Resilient DNS.
"""

from __future__ import annotations

import ipaddress
import urllib.parse

from .resilient_dns import (
    ResilientDNSResolver,
    disable_resilient_dns,
    enable_resilient_dns,
    get_resilient_dns_resolver,
    is_internet_connected,
)
from .windows_socket_patch import (
    install_asyncio_resilience_handler,
    patch_windows_asyncio_connection_lost,
)

# Proactively patch Windows ProactorEventLoop on module import
patch_windows_asyncio_connection_lost()


def is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_reserved
    except ValueError:
        return False


def redact_sensitive_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.password:
        netloc = f"{parsed.username}:***@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    return url


__all__ = [
    "is_private_ip",
    "redact_sensitive_url",
    "ResilientDNSResolver",
    "enable_resilient_dns",
    "disable_resilient_dns",
    "get_resilient_dns_resolver",
    "is_internet_connected",
    "install_asyncio_resilience_handler",
    "patch_windows_asyncio_connection_lost",
]
