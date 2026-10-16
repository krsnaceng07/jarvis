"""Configuration definitions for the Web plugin."""

from dataclasses import dataclass, field
from typing import TypedDict, Dict, List, Optional, Any


class WebFetchSsrfPolicyConfig(TypedDict, total=False):
    dangerouslyAllowPrivateNetwork: bool
    allowedHostnames: List[str]
    allowRfc2544BenchmarkRange: bool
    allowIpv6UniqueLocalRange: bool


class WebFetchConfig(TypedDict, total=False):
    enabled: bool
    provider: Optional[str]
    maxChars: int
    maxCharsCap: int
    maxResponseBytes: int
    timeoutSeconds: int
    cacheTtlMinutes: int
    maxRedirects: int
    useTrustedEnvProxy: bool
    readability: bool
    userAgent: str
    headers: Dict[str, str]
    ssrfPolicy: WebFetchSsrfPolicyConfig


@dataclass(frozen=True)
class ResolvedWebFetchSsrfPolicy:
    dangerouslyAllowPrivateNetwork: bool = False
    allowedHostnames: List[str] = field(default_factory=list)
    allowRfc2544BenchmarkRange: bool = True
    allowIpv6UniqueLocalRange: bool = True


@dataclass(frozen=True)
class ResolvedWebFetchConfig:
    enabled: bool = True
    provider: Optional[str] = None
    maxChars: int = 20000
    maxCharsCap: int = 20000
    maxResponseBytes: int = 750000
    timeoutSeconds: int = 30
    cacheTtlMinutes: int = 15
    maxRedirects: int = 3
    useTrustedEnvProxy: bool = False
    readability: bool = True
    userAgent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    headers: Dict[str, str] = field(default_factory=dict)
    ssrfPolicy: ResolvedWebFetchSsrfPolicy = field(default_factory=ResolvedWebFetchSsrfPolicy)


def resolve_web_fetch_config(raw: WebFetchConfig | Dict[str, Any] | None) -> ResolvedWebFetchConfig:
    if raw is None:
        raw = {}

    ssrf_raw = raw.get("ssrfPolicy", {})
    ssrf = ResolvedWebFetchSsrfPolicy(
        dangerouslyAllowPrivateNetwork=ssrf_raw.get("dangerouslyAllowPrivateNetwork", False),
        allowedHostnames=ssrf_raw.get("allowedHostnames", []),
        allowRfc2544BenchmarkRange=ssrf_raw.get("allowRfc2544BenchmarkRange", True),
        allowIpv6UniqueLocalRange=ssrf_raw.get("allowIpv6UniqueLocalRange", True),
    )

    max_response_bytes = raw.get("maxResponseBytes", 750000)
    # Clamp to 32000-10000000
    max_response_bytes = max(32000, min(10000000, max_response_bytes))

    return ResolvedWebFetchConfig(
        enabled=raw.get("enabled", True),
        provider=raw.get("provider"),
        maxChars=raw.get("maxChars", 20000),
        maxCharsCap=raw.get("maxCharsCap", 20000),
        maxResponseBytes=max_response_bytes,
        timeoutSeconds=raw.get("timeoutSeconds", 30),
        cacheTtlMinutes=raw.get("cacheTtlMinutes", 15),
        maxRedirects=raw.get("maxRedirects", 3),
        useTrustedEnvProxy=raw.get("useTrustedEnvProxy", False),
        readability=raw.get("readability", True),
        userAgent=raw.get(
            "userAgent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ),
        headers=raw.get("headers", {}),
        ssrfPolicy=ssrf,
    )
