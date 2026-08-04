"""jarvis.config.port_defaults — default port ranges for gateway/services.

OpenClaw parity: mirrors ``openclaw-main/src/config/port-defaults.ts``.
"""
from __future__ import annotations

#: Default browser-CDP sidecar port range start.
DEFAULT_BROWSER_CDP_PORT_RANGE_START = 18800
#: Default browser-CDP sidecar port range end (inclusive).
DEFAULT_BROWSER_CDP_PORT_RANGE_END = 18899
#: Span of the default browser-CDP sidecar port range.
DEFAULT_BROWSER_CDP_PORT_RANGE_SPAN = (
    DEFAULT_BROWSER_CDP_PORT_RANGE_END - DEFAULT_BROWSER_CDP_PORT_RANGE_START
)


def _is_valid_port(port: int) -> bool:
    try:
        n = float(port)
    except (TypeError, ValueError):
        return False
    return n == n and n > 0 and n <= 65535  # NaN check + range


def _clamp_port(port, fallback: int) -> int:
    return int(port) if _is_valid_port(port) else int(fallback)


def _derive_port(base, offset: int, fallback: int) -> int:
    return _clamp_port(base + offset, fallback)


def derive_default_browser_cdp_port_range(browser_control_port: int) -> dict:
    """Derive the browser-CDP sidecar range from the browser-control port when it fits.

    Mirrors :func:`deriveDefaultBrowserCdpPortRange`
    (``shared/config/port-defaults.ts`).
    """
    start = _derive_port(browser_control_port, 9, DEFAULT_BROWSER_CDP_PORT_RANGE_START)
    end = start + DEFAULT_BROWSER_CDP_PORT_RANGE_SPAN
    if end <= 65535:
        return {"start": start, "end": end}
    # Preserve the full expected range width; wrapping or clamping only the end
    # would make the dynamic range smaller than callers advertise.
    return {
        "start": DEFAULT_BROWSER_CDP_PORT_RANGE_START,
        "end": DEFAULT_BROWSER_CDP_PORT_RANGE_END,
    }


__all__ = [
    "DEFAULT_BROWSER_CDP_PORT_RANGE_START",
    "DEFAULT_BROWSER_CDP_PORT_RANGE_END",
    "DEFAULT_BROWSER_CDP_PORT_RANGE_SPAN",
    "derive_default_browser_cdp_port_range",
]
