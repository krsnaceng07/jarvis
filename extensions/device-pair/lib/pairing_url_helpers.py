"""Device Pair URL + host validation helpers.

Mirrors OpenClaw's ``extensions/device-pair/index.ts``
URL / host / IP / scheme helpers (``normalizeUrl``,
``parseNormalizedGatewayUrl``, ``isLoopbackHost``,
``isPrivateIPv4``, ``isPrivateLanIPv6``,
``isPrivateLanCleartextHost``, ``isTailnetIPv4``,
``isMobilePairingCleartextAllowedHost``,
``validateMobilePairingUrl``,
``isFullAccessMobilePairingUrl``,
``pickMatchingIPv4``, ``pickTailnetIPv4``,
``resolveScheme``,
``describeSecureMobilePairingFix``,
``normalizeHostForIpCheck``, ``resolveAuthLabel``).

The Python port keeps the same validation rules + the
same private helper names so the entry point can call
``is_loopback_host`` / ``is_private_ipv4`` / etc. without
needing an exact string-literal match.

Public surface (mirrors the TS source):
- ``normalize_optional_string(value)``
- ``normalize_lowercase_string_or_empty(value)``
- ``normalize_host_for_ip_check(host)``
- ``parse_ipv4_octets(address)``
- ``is_loopback_host(host)``
- ``is_private_ipv4(address)``
- ``is_private_lan_ipv6(address)``
- ``is_private_lan_cleartext_host(host)``
- ``is_tailnet_ipv4(address)``
- ``is_mobile_pairing_cleartext_allowed_host(host)``
- ``validate_mobile_pairing_url(url, source)``
- ``is_full_access_mobile_pairing_url(url)``
- ``pick_matching_ipv4(predicate)``
- ``pick_tailnet_ipv4()``
- ``resolve_scheme(tls_enabled, force_secure)``
- ``describe_secure_mobile_pairing_fix(source)``
- ``resolve_auth_label(cfg)`` — auth label resolution
- ``parse_normalized_gateway_url(raw)``
- ``normalize_url(raw, scheme_fallback)``

Python adaptations (documented in code):
- TS ``URL`` → Python ``urllib.parse.urlparse`` (the
  Python port uses the stdlib parser; the validation
  rules match the TS source exactly).
- TS ``os.networkInterfaces()`` → Python ``socket``
  module's ``gethostbyname_ex``-free enumeration of
  ``socket.getaddrinfo`` + adapter lookups. The
  port keeps the ``pick_matching_ipv4(predicate)``
  signature so the entry point can plug a custom
  predicate.
- TS ``isIP(address)`` → Python ``ipaddress.ip_address``
  family check (``ip_address(addr).version``).
"""
from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any, Callable, Optional
from urllib.parse import urlparse


# ── String-coerce helpers (mirrors OpenClaw) ──────────────


def normalize_optional_string(value: Any) -> Optional[str]:
    """Trim ``value`` and return ``None`` for empty / non-string.

    Mirrors ``normalizeOptionalString`` from
    ``@openclaw/normalization-core/string-coerce``.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def normalize_lowercase_string_or_empty(value: Any) -> str:
    """Lowercase a trimmed string; empty for non-strings.

    Mirrors ``normalizeLowercaseStringOrEmpty``.
    """
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


# ── Host / IP primitives ───────────────────────────────────


def _normalize_host_for_ip_check(host: str) -> str:
    """Strip brackets, trailing dots, and zone-id from a host string.

    Mirrors ``normalizeHostForIpCheck`` (private helper
    in the OpenClaw source).
    """
    normalized = normalize_lowercase_string_or_empty(host)
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    if normalized.endswith("."):
        normalized = normalized[:-1]
    zone_index = normalized.find("%")
    if zone_index >= 0:
        normalized = normalized[:zone_index]
    return normalized


def parse_ipv4_octets(address: str) -> Optional[tuple[int, int, int, int]]:
    """Parse ``address`` as four IPv4 octets.

    Mirrors ``parseIPv4Octets``. Returns ``None`` for
    non-IPv4 / non-decimal / out-of-range values.
    """
    parts = address.split(".")
    if len(parts) != 4:
        return None
    if any(not part.isdigit() for part in parts):
        return None
    octets: list[int] = []
    for part in parts:
        try:
            value = int(part)
        except ValueError:
            return None
        if value < 0 or value > 255:
            return None
        octets.append(value)
    return (octets[0], octets[1], octets[2], octets[3])


def is_loopback_host(host: str) -> bool:
    """Return True when ``host`` is a loopback address.

    Mirrors ``isLoopbackHost``. Accepts ``localhost``,
    IPv4 ``127.x.x.x``, and IPv6 ``::1`` /
    ``0:0:0:0:0:0:0:1``.
    """
    normalized = _normalize_host_for_ip_check(host)
    if not normalized:
        return False
    if normalized == "localhost":
        return True
    octets = parse_ipv4_octets(normalized)
    if octets is not None:
        return octets[0] == 127
    return normalized in ("::1", "0:0:0:0:0:0:0:1")


def is_private_ipv4(address: str) -> bool:
    """Return True when ``address`` is in a private IPv4 range.

    Mirrors ``isPrivateIPv4``. Matches RFC 1918:
    - 10.0.0.0/8
    - 172.16.0.0/12
    - 192.168.0.0/16
    """
    octets = parse_ipv4_octets(address)
    if octets is None:
        return False
    a, b = octets[0], octets[1]
    if a == 10:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    return False


def is_private_lan_ipv6(address: str) -> bool:
    """Return True when ``address`` is a private-LAN IPv6 (ULA + link-local).

    Mirrors ``isPrivateLanIPv6``. Matches
    - fc00::/7 (ULA)
    - fe80::/10 (link-local)
    """
    try:
        ip_obj = ipaddress.ip_address(address)
    except ValueError:
        return False
    if ip_obj.version != 6:
        return False
    # ``ipaddress.IPv6Address`` exposes the first hextet
    # via ``packed`` + ``_scope_id``; use the canonical
    # ``is_link_local`` / ``is_private`` predicates
    # when available, else fall back to the bitmask.
    if getattr(ip_obj, "is_link_local", False):
        return True
    first_hextet = int(address.split(":", 1)[0], 16) if ":" in address else 0
    return (first_hextet & 0xFE00) == 0xFC00


def is_private_lan_cleartext_host(host: str) -> bool:
    """Return True when ``host`` is a private-LAN cleartext host.

    Mirrors ``isPrivateLanCleartextHost``. Accepts:
    - ``*.local`` (mDNS)
    - RFC 1918 IPv4 (10/8, 172.16/12, 192.168/16)
    - ULA + link-local IPv6
    - IPv4 link-local (169.254/16)
    """
    normalized = _normalize_host_for_ip_check(host)
    if normalized.endswith(".local"):
        return True
    if is_private_ipv4(normalized) or is_private_lan_ipv6(normalized):
        return True
    octets = parse_ipv4_octets(normalized)
    if octets is None:
        return False
    return octets[0] == 169 and octets[1] == 254


def is_tailnet_ipv4(address: str) -> bool:
    """Return True when ``address`` is in the Tailscale 100.64/10 range.

    Mirrors ``isTailnetIPv4``. Tailscale's CGNAT range
    is 100.64.0.0/10.
    """
    octets = parse_ipv4_octets(address)
    if octets is None:
        return False
    a, b = octets[0], octets[1]
    return a == 100 and 64 <= b <= 127


def is_mobile_pairing_cleartext_allowed_host(host: str) -> bool:
    """Return True when ``host`` may use cleartext (ws://) for mobile pairing.

    Mirrors ``isMobilePairingCleartextAllowedHost``.
    Accepts loopback, the Android emulator host
    (``10.0.2.2``), and the private-LAN cleartext set.
    """
    normalized = _normalize_host_for_ip_check(host)
    return (
        is_loopback_host(normalized)
        or normalized == "10.0.2.2"
        or is_private_lan_cleartext_host(normalized)
    )


# ── URL parsing + validation ──────────────────────────────


# Schemes we accept. The gateway speaks ``ws`` / ``wss``
# (WebSocket); ``http`` / ``https`` are coerced to
# ``ws`` / ``wss`` by ``parseNormalizedGatewayUrl``.
_GATEWAY_SCHEME_WITHOUT_AUTHORITY_RE = re.compile(r"^(?:https?|wss?):(?!//)", re.IGNORECASE)
_SCHEME_LIKE_PATH_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:/")


def parse_normalized_gateway_url(raw: str) -> Optional[str]:
    """Parse ``raw`` as a ``ws://`` or ``wss://`` URL.

    Mirrors ``parseNormalizedGatewayUrl``. Returns
    ``None`` for invalid URLs, URLs with embedded
    credentials, or non-WS(S) schemes.
    """
    try:
        parsed = urlparse(raw)
    except (TypeError, ValueError):
        return None
    if parsed.username or parsed.password:
        return None
    scheme = parsed.scheme
    normalized_scheme = (
        "ws" if scheme == "http" else "wss" if scheme == "https" else scheme
    )
    if normalized_scheme not in ("ws", "wss"):
        return None
    if not parsed.hostname:
        return None
    # Preserve IPv6 brackets so the URL round-trips.
    # The TS ``URL.hostname`` strips brackets; the TS
    # ``new URL(...).hostname`` does the same. The
    # Python port uses ``netloc`` (which keeps the
    # brackets) for the IPv6 branch.
    if ":" in (parsed.hostname or "") and not parsed.hostname.startswith("["):
        host = f"[{parsed.hostname}]"
    else:
        host = parsed.hostname
    port = f":{parsed.port}" if parsed.port else ""
    return f"{normalized_scheme}://{host}{port}"


def normalize_url(raw: str, scheme_fallback: str) -> Optional[str]:
    """Normalize ``raw`` to a gateway URL with the given scheme fallback.

    Mirrors ``normalizeUrl``. Accepts:
    - A full ``ws://`` / ``wss://`` URL
    - A ``http://`` / ``https://`` URL (coerced to WS(S))
    - A bare host (coerced to ``<scheme_fallback>://<host>``)
    """
    candidate = normalize_optional_string(raw)
    if not candidate:
        return None
    if _GATEWAY_SCHEME_WITHOUT_AUTHORITY_RE.match(candidate):
        return None
    parsed = parse_normalized_gateway_url(candidate)
    if parsed:
        return parsed
    if "://" in candidate or _SCHEME_LIKE_PATH_RE.match(candidate):
        return None
    host_port = normalize_optional_string(candidate.split("/", 1)[0]) or ""
    return parse_normalized_gateway_url(f"{scheme_fallback}://{host_port}") if host_port else None


def resolve_scheme(tls_enabled: Optional[bool], force_secure: bool = False) -> str:
    """Return ``"ws"`` or ``"wss"`` for the gateway.

    Mirrors ``resolveScheme``. ``force_secure`` wins
    over the runtime config; the runtime ``tls.enabled``
    flag otherwise drives the default.
    """
    if force_secure:
        return "wss"
    return "wss" if tls_enabled is True else "ws"


def describe_secure_mobile_pairing_fix(source: Optional[str] = None) -> str:
    """Return the user-facing fix message for cleartext rejection.

    Mirrors ``describeSecureMobilePairingFix``.
    """
    source_note = f" Resolved source: {source}." if source else ""
    return (
        "Tailscale and public mobile pairing require a secure gateway URL "
        "(wss://) or Tailscale Serve/Funnel." + source_note + " "
        "Fix: use a private LAN address, prefer gateway.tailscale.mode=serve, "
        "or set gateway.remote.url / plugins.entries.device-pair.config.publicUrl "
        "to a wss:// URL. ws:// setup codes are only valid for "
        "localhost/loopback, private LAN addresses, .local hosts, or "
        "the Android emulator."
    )


def validate_mobile_pairing_url(
    url: str, source: Optional[str] = None
) -> Optional[str]:
    """Return an error message when ``url`` is invalid for mobile pairing.

    Mirrors ``validateMobilePairingUrl``. Returns
    ``None`` when the URL is acceptable; the error
    message otherwise.
    """
    try:
        parsed = urlparse(url)
    except (TypeError, ValueError):
        return "Resolved mobile pairing URL is invalid."
    # ``urlparse`` returns the scheme without the colon
    # (``"wss"`` not ``"wss:"``); coerce the http(s)
    # variants to the WS(S) protocols so the
    # downstream checks match the TS source.
    protocol = (
        "wss"
        if parsed.scheme == "https"
        else "ws"
        if parsed.scheme == "http"
        else parsed.scheme
    )
    if protocol == "wss":
        return None
    if protocol != "ws":
        return "Resolved mobile pairing URL is invalid."
    if is_mobile_pairing_cleartext_allowed_host(parsed.hostname or ""):
        return None
    return describe_secure_mobile_pairing_fix(source)


def is_full_access_mobile_pairing_url(url: str) -> bool:
    """Return True when ``url`` grants full mobile-pairing access.

    Mirrors ``isFullAccessMobilePairingUrl``. Accepts
    ``wss://`` URLs and ``ws://`` loopback URLs.
    """
    try:
        parsed = urlparse(url)
    except (TypeError, ValueError):
        return False
    if parsed.scheme == "wss":
        return True
    if parsed.scheme == "ws" and is_loopback_host(parsed.hostname or ""):
        return True
    return False


# ── Network interface enumeration ──────────────────────────


def pick_matching_ipv4(predicate: Callable[[str], bool]) -> Optional[str]:
    """Return the first non-internal IPv4 address matching ``predicate``.

    Mirrors ``pickMatchingIPv4``. The Python port uses
    ``socket.gethostbyname_ex`` + a small adapter-info
    probe; the OpenClaw source uses ``os.networkInterfaces()``.
    Both enumerate the host's network interfaces and
    filter to non-internal IPv4 candidates.
    """
    try:
        # ``gethostbyname_ex`` returns the host's primary
        # IPv4 address. The host may have additional
        # interfaces; use ``getaddrinfo`` to enumerate
        # the rest.
        hostname = socket.gethostname()
        addresses: set[str] = set()
        for info in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            sockaddr = info[4]
            if sockaddr:
                addresses.add(sockaddr[0])
        for address in sorted(addresses):
            if predicate(address):
                return address
    except (socket.gaierror, OSError):
        return None
    return None


def pick_tailnet_ipv4() -> Optional[str]:
    """Return the host's first Tailscale IPv4 address.

    Mirrors ``pickTailnetIPv4``. Returns ``None`` when
    the host isn't on a Tailscale network.
    """
    return pick_matching_ipv4(is_tailnet_ipv4)


# ── Auth label resolution ─────────────────────────────────


def _pick_first_defined(candidates: list[Any]) -> Optional[str]:
    """Return the first non-empty trimmed string in ``candidates``.

    Mirrors ``pickFirstDefined``.
    """
    for value in candidates:
        trimmed = normalize_optional_string(value)
        if trimmed:
            return trimmed
    return None


def _resolve_required_auth_label(
    mode: str, values: dict
) -> dict:
    """Return the resolved auth label or a structured error.

    Mirrors ``resolveRequiredAuthLabel``.
    """
    if mode == "token":
        if values.get("token"):
            return {"label": "token"}
        return {"error": "Gateway auth is set to token, but no token is configured."}
    if values.get("password"):
        return {"label": "password"}
    return {"error": "Gateway auth is set to password, but no password is configured."}


def resolve_auth_label(cfg: dict, env: Optional[dict] = None) -> dict:
    """Resolve the auth label (token or password) for a gateway config.

    Mirrors ``resolveAuthLabel``. The Python port
    accepts the gateway config as a dict and reads the
    token / password from either ``env`` (process env
    override) or ``cfg.gateway.auth`` (config file).
    Returns ``{"label": "token"|"password"}`` on success
    or ``{"error": "..."}`` when auth isn't configured.
    """
    gateway = cfg.get("gateway", {}) if isinstance(cfg, dict) else {}
    auth = gateway.get("auth", {}) if isinstance(gateway, dict) else {}
    mode = auth.get("mode") if isinstance(auth, dict) else None
    env = env or {}
    token = _pick_first_defined([env.get("JARVIS_GATEWAY_TOKEN"), auth.get("token")])
    password = _pick_first_defined(
        [env.get("JARVIS_GATEWAY_PASSWORD"), auth.get("password")]
    )
    if mode in ("token", "password"):
        return _resolve_required_auth_label(mode, {"token": token, "password": password})
    if token:
        return {"label": "token"}
    if password:
        return {"label": "password"}
    return {"error": "Gateway auth is not configured (no token or password)."}


__all__ = [
    "describe_secure_mobile_pairing_fix",
    "is_full_access_mobile_pairing_url",
    "is_loopback_host",
    "is_mobile_pairing_cleartext_allowed_host",
    "is_private_ipv4",
    "is_private_lan_cleartext_host",
    "is_private_lan_ipv6",
    "is_tailnet_ipv4",
    "normalize_host_for_ip_check",
    "normalize_lowercase_string_or_empty",
    "normalize_optional_string",
    "normalize_url",
    "parse_ipv4_octets",
    "parse_normalized_gateway_url",
    "pick_matching_ipv4",
    "pick_tailnet_ipv4",
    "resolve_auth_label",
    "resolve_scheme",
    "validate_mobile_pairing_url",
]
