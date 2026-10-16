"""CDP (Chrome DevTools Protocol) connection and helper utilities."""

from urllib.parse import urlparse


def redact_cdp_url(url: str) -> str:
    """Redact passwords and tokens from CDP URLs."""
    try:
        parsed = urlparse(url)
        if not parsed.hostname:
            return url

        redacted = f"{parsed.scheme}://"
        if parsed.username:
            redacted += parsed.username
            if parsed.password:
                redacted += ":***"
            redacted += "@"

        redacted += parsed.hostname
        if parsed.port:
            redacted += f":{parsed.port}"

        redacted += parsed.path
        if parsed.query:
            redacted += f"?{parsed.query}"

        return redacted
    except Exception:
        return "<invalid-url>"


def parse_browser_http_url(url: str) -> dict:
    """Parse a browser HTTP URL, checking for ports."""
    parsed = urlparse(url)
    port = parsed.port if parsed.port else 80 if parsed.scheme == "http" else 443
    return {
        "hostname": parsed.hostname,
        "port": port,
        "scheme": parsed.scheme,
    }
