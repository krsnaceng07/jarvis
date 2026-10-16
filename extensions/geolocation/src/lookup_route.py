"""HTTP lookup route handler for geolocation.

OpenClaw parity: mirrors extensions/geolocation/src/lookup-route.ts.
"""

from __future__ import annotations

import asyncio
import ipaddress
from typing import Any, Callable

from .config import GeolocationSettings
from .database_store import GeolocationDatabase
from .lookup import project_geolocation_record

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("fc00::/7"),  # IPv6 Unique Local
    ipaddress.ip_network("fe80::/10"),  # IPv6 Link Local
    ipaddress.ip_network("::1/128"),  # IPv6 Loopback
]


def is_private_or_loopback_ip(ip_str: str) -> bool:
    """Check if the IP is private, loopback, link-local, or Carrier-Grade NAT (CGNAT)."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in PRIVATE_NETWORKS)
    except ValueError:
        return False


def is_valid_ip(ip_str: str) -> bool:
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False


class GeolocationLookupHandler:
    def __init__(
        self,
        load_database: Callable[[], Any],
        settings: GeolocationSettings,
        logger: Any = None,
    ):
        self.load_database = load_database
        self.settings = settings
        self.logger = logger

    async def handle_request(
        self, path: str, query_params: dict[str, str | list[str]]
    ) -> tuple[int, dict[str, Any]]:
        ip_raw = query_params.get("ip", "")
        ip = ip_raw[0] if isinstance(ip_raw, list) else str(ip_raw)
        ip = ip.strip()

        if not ip or not is_valid_ip(ip):
            return 400, {"error": "ip must be a valid IPv4 or IPv6 address"}

        # Private, loopback, link-local, and carrier-grade-NAT addresses are absent
        # from every geolocation database, so answering them here keeps a tailnet or
        # LAN-only deployment from ever downloading one.
        if is_private_or_loopback_ip(ip):
            return 200, {
                "found": False,
                "attribution": self.settings["attribution"],
            }

        try:
            db_or_coro = self.load_database()
            if asyncio.iscoroutine(db_or_coro) or hasattr(db_or_coro, "__await__"):
                database: GeolocationDatabase = await db_or_coro
            else:
                database = db_or_coro  # type: ignore[assignment]
            location = project_geolocation_record(database.lookup(ip))
            res: dict[str, Any] = {
                "found": bool(location),
                "attribution": self.settings["attribution"],
            }
            if location:
                res.update(location)
            return 200, res
        except Exception as err:
            # A missing database is an availability problem, never a lookup answer:
            # reporting "not found" here would read as "this IP has no location".
            if self.logger and hasattr(self.logger, "warn"):
                self.logger.warn(f"geolocation: lookup unavailable: {err}")
            return 503, {"error": "geolocation database unavailable"}


def create_geolocation_lookup_handler(
    load_database: Callable[[], Any],
    settings: GeolocationSettings,
    logger: Any = None,
) -> GeolocationLookupHandler:
    return GeolocationLookupHandler(load_database, settings, logger)
