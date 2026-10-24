"""packages/net_policy/src/jarvis_net_policy/resilient_dns.py

Resilient DNS Resolver with In-Memory Caching, DNS-over-HTTPS (DoH) Direct-IP
Fallback, and Static Google Anycast Routing.

Solves Windows [Errno 11001] getaddrinfo failed errors caused by transient local
DNS drops, IPv6 routing glitches, or router/ISP DNS timeouts.
"""

from __future__ import annotations

import json
import logging
import socket
import ssl
import threading
import time
import urllib.request
from typing import Any

logger = logging.getLogger("jarvis.net_policy.dns")

# Globally stable Google Anycast IPv4 endpoints for Google APIs
GOOGLE_FALLBACK_IPS: dict[str, list[str]] = {
    "generativelanguage.googleapis.com": [
        "172.217.112.4",
        "172.217.114.4",
        "172.217.115.4",
        "172.217.116.4",
        "172.217.117.4",
        "172.217.118.4",
        "172.217.119.4",
    ],
    "googleapis.com": [
        "172.217.112.4",
        "172.217.115.4",
        "172.217.116.4",
    ],
    "accounts.google.com": [
        "172.217.112.4",
        "172.217.115.4",
    ],
}

# Public DNS over HTTPS direct IP endpoints (no DNS required to reach them)
DOH_ENDPOINTS: list[tuple[str, str]] = [
    # (IP-based URL, Host header)
    ("https://8.8.8.8/resolve?name={host}&type=A", "dns.google"),
    ("https://1.1.1.1/dns-query?name={host}&type=A", "cloudflare-dns.com"),
]


class ResilientDNSResolver:
    """Thread-safe resilient DNS resolver wrapping socket.getaddrinfo."""

    def __init__(self, cache_ttl: float = 3600.0) -> None:
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, list[str]]] = {}
        self._lock = threading.Lock()
        self._orig_getaddrinfo = socket.getaddrinfo
        self._is_hooked = False
        self._ssl_ctx = ssl.create_default_context()

    @property
    def is_enabled(self) -> bool:
        return self._is_hooked

    def cache_host_ips(self, host: str, ips: list[str]) -> None:
        """Store resolved IPs for a host."""
        if not host or not ips:
            return
        with self._lock:
            self._cache[host.lower()] = (time.time(), list(ips))

    def get_cached_ips(self, host: str) -> list[str] | None:
        """Retrieve non-expired cached IPs for a host."""
        host_key = host.lower()
        with self._lock:
            entry = self._cache.get(host_key)
            if not entry:
                return None
            ts, ips = entry
            if time.time() - ts < self._cache_ttl:
                return list(ips)
            # Expired, but keep as fallback if needed
            return list(ips)

    def resolve_doh(self, host: str, timeout: float = 2.0) -> list[str]:
        """Resolve host via DNS-over-HTTPS using direct IP endpoints."""
        for url_template, host_hdr in DOH_ENDPOINTS:
            try:
                url = url_template.format(host=host)
                headers = {
                    "Host": host_hdr,
                    "Accept": "application/dns-json",
                    "User-Agent": "JARVIS-ResilientDNS/1.0",
                }
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                        answers = data.get("Answer", [])
                        ips = [
                            a["data"].strip()
                            for a in answers
                            if a.get("type") == 1 and "data" in a
                        ]
                        if ips:
                            logger.info("ResilientDNS: resolved %s via DoH -> %s", host, ips)
                            return ips
            except Exception as e:
                logger.debug("ResilientDNS: DoH query to %s failed: %s", url_template, e)
                continue
        return []

    def resolve_fallback_ips(self, host: str) -> list[str]:
        """Resolve host using (1) Cache -> (2) DoH -> (3) Static Anycast."""
        host_key = host.lower()

        # 1. In-memory cache
        cached = self.get_cached_ips(host_key)
        if cached:
            logger.info("ResilientDNS: using cached IPs for %s -> %s", host, cached)
            return cached

        # 2. DNS over HTTPS
        doh_ips = self.resolve_doh(host_key)
        if doh_ips:
            self.cache_host_ips(host_key, doh_ips)
            return doh_ips

        # 3. Known static Google Anycast endpoints
        if host_key in GOOGLE_FALLBACK_IPS:
            static_ips = GOOGLE_FALLBACK_IPS[host_key]
            logger.info("ResilientDNS: using static Anycast IPs for %s -> %s", host, static_ips)
            self.cache_host_ips(host_key, static_ips)
            return static_ips

        return []

    def getaddrinfo(
        self,
        host: Any,
        port: Any,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[Any]:
        """Replacement for socket.getaddrinfo with transparent resilience."""
        # If host is an IP address literal, None, or integer, pass through directly
        if not isinstance(host, str) or not host:
            return self._orig_getaddrinfo(host, port, family, type, proto, flags)

        # First, attempt native system resolution
        try:
            results = self._orig_getaddrinfo(host, port, family, type, proto, flags)
            # Record resolved IPv4 addresses in cache for future fallback
            resolved_ips = [
                res[4][0]
                for res in results
                if len(res) >= 5 and isinstance(res[4], tuple) and len(res[4]) >= 1
            ]
            if resolved_ips:
                self.cache_host_ips(host, resolved_ips)
            return results
        except socket.gaierror as e:
            # Check if this is a known DNS resolution failure (e.g. 11001, -2, -3, etc.)
            err_code = getattr(e, "errno", None)
            logger.warning(
                "ResilientDNS: native getaddrinfo failed for '%s' (errno=%s: %s). Attempting resilient fallback...",
                host,
                err_code,
                e,
            )

            fallback_ips = self.resolve_fallback_ips(host)
            if fallback_ips:
                all_results: list[Any] = []
                for ip in fallback_ips:
                    try:
                        # Translate IP literal into native sockaddr structures using orig_getaddrinfo
                        ip_results = self._orig_getaddrinfo(ip, port, family, type, proto, flags)
                        all_results.extend(ip_results)
                    except Exception:
                        continue
                if all_results:
                    logger.info(
                        "ResilientDNS: successfully bypassed getaddrinfo failure for '%s' with %d address(es).",
                        host,
                        len(all_results),
                    )
                    return all_results

            # Fallback exhausted; re-raise original failure
            raise

    def enable(self) -> None:
        """Hook socket.getaddrinfo with resilient resolver."""
        with self._lock:
            if not self._is_hooked:
                self._orig_getaddrinfo = socket.getaddrinfo
                socket.getaddrinfo = self.getaddrinfo
                self._is_hooked = True
                logger.info("ResilientDNS: hooked into socket.getaddrinfo successfully.")

    def disable(self) -> None:
        """Restore original socket.getaddrinfo."""
        with self._lock:
            if self._is_hooked:
                socket.getaddrinfo = self._orig_getaddrinfo
                self._is_hooked = False
                logger.info("ResilientDNS: unhooked socket.getaddrinfo.")


_GLOBAL_RESOLVER: ResilientDNSResolver | None = None
_GLOBAL_LOCK = threading.Lock()


def get_resilient_dns_resolver() -> ResilientDNSResolver:
    """Return singleton ResilientDNSResolver."""
    global _GLOBAL_RESOLVER
    with _GLOBAL_LOCK:
        if _GLOBAL_RESOLVER is None:
            _GLOBAL_RESOLVER = ResilientDNSResolver()
        return _GLOBAL_RESOLVER


def enable_resilient_dns() -> ResilientDNSResolver:
    """Enable resilient DNS resolution globally across the process."""
    resolver = get_resilient_dns_resolver()
    resolver.enable()
    return resolver


def disable_resilient_dns() -> None:
    """Disable resilient DNS resolution globally."""
    resolver = get_resilient_dns_resolver()
    resolver.disable()


def is_internet_connected(timeout: float = 1.5) -> bool:
    """Fast probe to check if external internet routing is available."""
    for host, port in [("8.8.8.8", 53), ("1.1.1.1", 53), ("208.67.222.222", 53)]:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            continue
    return False
