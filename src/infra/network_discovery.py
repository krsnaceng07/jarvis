"""src.infra.network_discovery — best-effort LAN and network discovery helpers.

OpenClaw parity: mirrors ``src/infra/network-discovery-display.ts``.

Display helpers are best-effort wrappers around network interface probes.
Startup and config output keep rendering even when interface discovery fails.

Public surface
--------------
``pick_best_effort_primary_lan_ipv4``
    Best-effort LAN IPv4 for display. Returns None on failure.
``inspect_best_effort_network``
    Returns host, LAN IP, and whether it is a loopback/unknown address.
``resolve_best_effort_bind_host_for_display``
    Resolve the gateway bind host for display, with a safe fallback.
"""

from __future__ import annotations

import socket


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _summarize_network_error(error: Exception) -> str:
    msg = str(error).strip()
    return msg if msg else "network interface discovery failed"


def _pick_primary_lan_ipv4() -> str | None:
    """Attempt to determine the primary LAN IPv4 address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Does not actually send any packet.
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            # Exclude loopback.
            if ip.startswith("127.") or ip == "::1":
                return None
            return ip
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def pick_best_effort_primary_lan_ipv4() -> str | None:
    """Return the primary LAN IPv4, or None when discovery fails.

    Mirrors ``pickBestEffortPrimaryLanIPv4``.
    """
    try:
        return _pick_primary_lan_ipv4()
    except Exception:
        return None


def inspect_best_effort_network() -> dict[str, str | None]:
    """Return a dict with ``host``, ``ip``, and ``warning`` keys.

    Useful for startup diagnostics. ``ip`` is None when discovery fails;
    ``warning`` contains a human-readable error string in that case.
    """
    host = socket.gethostname()
    try:
        ip = _pick_primary_lan_ipv4()
        return {"host": host, "ip": ip, "warning": None}
    except Exception as exc:
        return {"host": host, "ip": None, "warning": _summarize_network_error(exc)}


def resolve_best_effort_bind_host_for_display(
    bind_mode: str,
    custom_bind_host: str | None = None,
    warning_prefix: str | None = None,
) -> dict[str, str | None]:
    """Resolve the gateway bind host string for display.

    Mirrors ``resolveBestEffortGatewayBindHostForDisplay``.

    Returns ``{"bindHost": "...", "warning": None | "..."}`` dict.
    Falls back to a safe placeholder when resolution fails.
    """
    try:
        # For ``lan`` mode, bind to 0.0.0.0 (all interfaces).
        if bind_mode == "lan":
            ip = _pick_primary_lan_ipv4() or "0.0.0.0"
            return {"bindHost": ip, "warning": None}
        if bind_mode == "custom" and custom_bind_host:
            return {"bindHost": custom_bind_host.strip(), "warning": None}
        # Default / localhost mode.
        return {"bindHost": "127.0.0.1", "warning": None}
    except Exception as exc:
        prefix = (warning_prefix or "").strip()
        warning = f"{prefix}: {_summarize_network_error(exc)}." if prefix else None
        fallback = {
            "lan": "0.0.0.0",
            "custom": (custom_bind_host or "").strip() or "0.0.0.0",
        }.get(bind_mode, "127.0.0.1")
        return {"bindHost": fallback, "warning": warning}


__all__ = [
    "inspect_best_effort_network",
    "pick_best_effort_primary_lan_ipv4",
    "resolve_best_effort_bind_host_for_display",
]
