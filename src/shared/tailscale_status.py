"""jarvis.shared.tailscale_status — Tailscale status parsers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/tailscale-status.ts``.

Focused minimal port: uses plain dict validation instead of zod schemas.
Callers needing strict schema validation can wrap the JSON parser.
"""
from __future__ import annotations

import json
import re
from typing import Awaitable, Callable, Dict, List, Optional, TypedDict


class TailscaleStatusCommandResult(TypedDict, total=False):
    code: int
    stdout: str


TailscaleStatusCommandRunner = Callable[
    [List[str], dict], Awaitable[TailscaleStatusCommandResult]
]


#: Candidate command paths to try for Tailscale status queries.
TAILSCALE_STATUS_COMMAND_CANDIDATES = (
    "tailscale",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
)


_LOOPBACK_HOST_RE = re.compile(r"^127(?:\.\d{1,3}){3}$")
_DNS_TRAILING_DOT_RE = re.compile(r"\.$")
_PURE_IPV4_OR_IPV6_RE = re.compile(r"^[\d.:]+$")


def _parse_possibly_noisy_status(raw: str) -> Optional[dict]:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start:end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _extract_tailnet_host_from_status_json(raw: str) -> Optional[str]:
    parsed = _parse_possibly_noisy_status(raw)
    if not parsed:
        return None
    self_ = parsed.get("Self") if isinstance(parsed.get("Self"), dict) else None
    if self_:
        dns = self_.get("DNSName")
        if isinstance(dns, str) and dns:
            return _DNS_TRAILING_DOT_RE.sub("", dns)
        ips = self_.get("TailscaleIPs")
        if isinstance(ips, list) and ips:
            first = ips[0]
            if isinstance(first, str):
                return first
    return None


def _parse_loopback_proxy_port(proxy: str) -> Optional[int]:
    trimmed = proxy.strip()
    if re.fullmatch(r"\d+", trimmed):
        return int(trimmed)
    normalized = trimmed if "://" in trimmed else f"http://{trimmed}"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(normalized)
    except ValueError:
        return None
    host = parsed.hostname or ""
    host = host.strip("[]").lower() if host else ""
    is_loopback = host in ("localhost", "::1") or bool(_LOOPBACK_HOST_RE.match(host))
    if not is_loopback:
        return None
    try:
        port = int(parsed.port)
    except (TypeError, ValueError):
        return None
    if 1 <= port <= 65535:
        return port
    return None


def _collect_serve_gateway_urls(
    config: dict, gateway_port: int, allow_funnel: Dict[str, bool]
) -> List[str]:
    urls: List[str] = []
    web = config.get("Web") if isinstance(config, dict) else None
    if not isinstance(web, dict):
        return urls
    for host_port, web_server in web.items():
        if not isinstance(web_server, dict):
            continue
        allow_funnel_for_host = allow_funnel.get(host_port, False)
        handlers = web_server.get("Handlers") or {}
        handler = handlers.get("/") if isinstance(handlers, dict) else None
        proxy = handler.get("Proxy") if isinstance(handler, dict) else None
        if not proxy or _parse_loopback_proxy_port(proxy) != gateway_port:
            continue
        if allow_funnel_for_host:
            continue
        from urllib.parse import urlparse
        try:
            endpoint = urlparse(f"https://{host_port}")
        except ValueError:
            continue
        port = endpoint.port or 443
        tcp = config.get("TCP") if isinstance(config, dict) else None
        if not isinstance(tcp, dict):
            continue
        port_cfg = tcp.get(str(port))
        if not isinstance(port_cfg, dict) or port_cfg.get("HTTPS") is not True:
            continue
        host = endpoint.hostname or ""
        if host:
            urls.append(f"wss://{endpoint.netloc}")
    return urls


def _extract_serve_gateway_urls(raw: str, gateway_port: int) -> List[str]:
    parsed = _parse_possibly_noisy_status(raw)
    if not parsed:
        return []
    allow_funnel = parsed.get("AllowFunnel") if isinstance(parsed.get("AllowFunnel"), dict) else {}
    urls = _collect_serve_gateway_urls(parsed, gateway_port, allow_funnel)
    return sorted(set(urls))


def resolve_tailscale_published_host(params: dict) -> Optional[str]:
    """Resolve the host published to clients for tailnet or Tailscale Serve modes.

    Mirrors :func:`resolveTailscalePublishedHost`
    (``shared/tailscale-status.ts``).
    """
    tailnet_host = (params.get("tailnetHost") or "").strip() if isinstance(params.get("tailnetHost"), str) else None
    if not tailnet_host:
        return None
    service_name: Optional[str] = None
    if params.get("tailscaleMode") == "serve":
        sn = params.get("serviceName")
        if isinstance(sn, str) and sn.strip():
            service_name = sn.strip()
    if not service_name:
        return tailnet_host
    if _PURE_IPV4_OR_IPV6_RE.match(tailnet_host):
        return None
    bare = service_name.replace("svc:", "", 1)
    parts = tailnet_host.split(".")
    suffix = ".".join(parts[1:]) if len(parts) > 1 else ""
    if not suffix:
        return None
    return f"{bare}.{suffix}"


async def resolve_tailnet_host_with_runner(
    run_command_with_timeout: Optional[TailscaleStatusCommandRunner] = None,
) -> Optional[str]:
    """Run known Tailscale status commands and return first DNS or tailnet IP.

    Mirrors :func:`resolveTailnetHostWithRunner`
    (``shared/tailscale-status.ts``).
    """
    if not run_command_with_timeout:
        return None
    for candidate in TAILSCALE_STATUS_COMMAND_CANDIDATES:
        try:
            result = await run_command_with_timeout(
                [candidate, "status", "--json"],
                {"timeoutMs": 5000},
            )
        except Exception:
            continue
        if result.get("code") != 0:
            continue
        raw = (result.get("stdout") or "").strip()
        if not raw:
            continue
        host = _extract_tailnet_host_from_status_json(raw)
        if host:
            return host
    return None


async def resolve_tailscale_serve_gateway_urls_with_runner(
    gateway_port: int,
    run_command_with_timeout: Optional[TailscaleStatusCommandRunner] = None,
) -> List[str]:
    """Find HTTPS Serve routes whose root proxy targets this gateway port.

    Mirrors :func:`resolveTailscaleServeGatewayUrlsWithRunner`
    (``shared/tailscale-status.ts``).
    """
    if not run_command_with_timeout:
        return []
    for candidate in TAILSCALE_STATUS_COMMAND_CANDIDATES:
        try:
            result = await run_command_with_timeout(
                [candidate, "serve", "status", "--json"],
                {"timeoutMs": 5000},
            )
        except Exception:
            continue
        if result.get("code") != 0:
            continue
        raw = (result.get("stdout") or "").strip()
        if not raw:
            continue
        urls = _extract_serve_gateway_urls(raw, gateway_port)
        if urls:
            return urls
    return []


__all__ = [
    "TailscaleStatusCommandResult",
    "TailscaleStatusCommandRunner",
    "TAILSCALE_STATUS_COMMAND_CANDIDATES",
    "resolve_tailscale_published_host",
    "resolve_tailnet_host_with_runner",
    "resolve_tailscale_serve_gateway_urls_with_runner",
]
