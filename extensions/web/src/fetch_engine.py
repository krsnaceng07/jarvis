"""HTTP fetching logic, including SSRF policy enforcement and header sanitization."""

import httpx
import ipaddress
import socket
import os
import re
from typing import Dict, Tuple
from urllib.parse import urlparse
from .config import ResolvedWebFetchConfig

# Forbidden headers
FORBIDDEN_HEADERS = {
    "accept",
    "accept-language",
    "user-agent",
    "content-length",
    "transfer-encoding",
    "connection",
    "upgrade",
}


def sanitize_headers(raw_headers: Dict[str, str]) -> Dict[str, str]:
    """Sanitize and collapse custom request headers."""
    sanitized: Dict[str, str] = {}

    for name, value in raw_headers.items():
        name_lower = name.lower()

        # Drop forbidden headers
        if name_lower in FORBIDDEN_HEADERS:
            continue

        # Validate HTTP token for header name
        if not re.match(r"^[!#$%&'*+.^_`|~0-9a-zA-Z-]+$", name):
            continue

        # Validate header value (no CR, LF, NUL, > U+00FF)
        if any(ord(c) > 0xFF or c in "\r\n\0" for c in value):
            continue

        # Environment substitution (only for exact matches or ${VAR} format if needed)
        # Assuming simple resolution
        def replacer(match: re.Match) -> str:
            env_var = match.group(1)
            return os.environ.get(env_var, f"${{{env_var}}}")

        if "${" in value:
            value = re.sub(r"\$\{([^}]+)\}", replacer, value)

        # Case insensitive collapsing - later entries overwrite
        # To strictly do this, we maintain the original case of the last seen
        sanitized[name_lower] = (name, value)

    return {k: v for _, (k, v) in sanitized.items()}


def is_host_allowed(host: str, config: ResolvedWebFetchConfig) -> bool:
    """Enforce SSRF policy on the host."""
    # Allow explicit hostnames
    if host in config.ssrfPolicy.allowedHostnames:
        return True

    try:
        # Resolve to IP to check ranges
        # If useTrustedEnvProxy is True, we skip strict local DNS pinning block
        # but OpenClaw says "it lets the proxy resolve DNS instead of doing local DNS pinning."
        if config.useTrustedEnvProxy:
            return True

        ip = socket.gethostbyname(host)
        ip_obj = ipaddress.ip_address(ip)

        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_link_local:
            if config.ssrfPolicy.dangerouslyAllowPrivateNetwork:
                return True

            if ip_obj.version == 4 and config.ssrfPolicy.allowRfc2544BenchmarkRange:
                # 198.18.0.0/15
                if ipaddress.IPv4Network("198.18.0.0/15").overlaps(
                    ipaddress.IPv4Network(f"{ip}/32")
                ):
                    return True

            if ip_obj.version == 6 and config.ssrfPolicy.allowIpv6UniqueLocalRange:
                # fc00::/7
                if ipaddress.IPv6Network("fc00::/7").overlaps(ipaddress.IPv6Network(f"{ip}/128")):
                    return True

            return False

    except socket.gaierror:
        # Host could not be resolved. Will fail during fetch.
        pass

    return True


async def perform_fetch(url: str, config: ResolvedWebFetchConfig) -> Tuple[bytes, httpx.Response]:
    """Execute the fetch with constraints."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}. http(s) only.")

    if not is_host_allowed(parsed.hostname or "", config):
        raise ValueError(f"SSRF policy blocked host: {parsed.hostname}")

    headers = {"User-Agent": config.userAgent, "Accept-Language": "en-US,en;q=0.9"}

    custom_headers = sanitize_headers(config.headers)
    headers.update(custom_headers)

    transport = httpx.AsyncHTTPTransport(retries=0)
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=True,
        max_redirects=config.maxRedirects,
        timeout=config.timeoutSeconds,
    ) as client:
        response = await client.get(url, headers=headers)

        # Read the content iteratively to enforce maxResponseBytes
        content_bytes = bytearray()
        async for chunk in response.aiter_bytes():
            content_bytes.extend(chunk)
            if len(content_bytes) > config.maxResponseBytes:
                # Truncate
                content_bytes = content_bytes[: config.maxResponseBytes]
                break

        return bytes(content_bytes), response
