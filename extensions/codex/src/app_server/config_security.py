"""Connection security predicates for the Codex app-server runtime."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlparse

from extensions.codex.src.app_server.config import (
    CodexAppServerConnectionClass,
    CodexAppServerTransportMode,
)


def _is_loopback_websocket_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"ws", "wss"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def infer_codex_app_server_connection_class(
    *, transport: CodexAppServerTransportMode, url: str | None
) -> CodexAppServerConnectionClass:
    if transport != "websocket":
        return "local-loopback"
    return "local-loopback" if url and _is_loopback_websocket_url(url) else "remote"


def assert_codex_app_server_connection_security(
    *,
    transport: CodexAppServerTransportMode,
    url: str | None,
    auth_token: str | None,
    headers: dict[str, str],
) -> None:
    """Require identity-bearing auth for non-loopback WebSocket servers."""
    connection_class = infer_codex_app_server_connection_class(transport=transport, url=url)
    has_authorization_header = any(
        key.strip().lower() == "authorization" and bool(value.strip())
        for key, value in headers.items()
    )
    if connection_class == "remote" and not (auth_token or has_authorization_header):
        raise ValueError(
            "remote Codex app-server WebSocket URLs require appServer.authToken "
            "or an Authorization header"
        )


def resolve_codex_app_server_network_proxy(
    config: dict[str, Any] | None,
    sandbox: str,
) -> dict[str, Any] | None:
    """Build OpenClaw's deterministic Codex permissions-profile patch."""
    if not isinstance(config, dict) or config.get("enabled") is not True:
        return None
    filesystem_mode = (
        "read"
        if config.get("baseProfile") == "read-only"
        or (not config.get("baseProfile") and sandbox == "read-only")
        else "write"
    )
    network: dict[str, Any] = {"enabled": True}
    for source, target in (
        ("mode", "mode"),
        ("proxyUrl", "proxy_url"),
        ("socksUrl", "socks_url"),
        ("enableSocks5", "enable_socks5"),
        ("enableSocks5Udp", "enable_socks5_udp"),
        ("allowUpstreamProxy", "allow_upstream_proxy"),
        ("allowLocalBinding", "allow_local_binding"),
        ("dangerouslyAllowNonLoopbackProxy", "dangerously_allow_non_loopback_proxy"),
        ("dangerouslyAllowAllUnixSockets", "dangerously_allow_all_unix_sockets"),
    ):
        value = config.get(source)
        if isinstance(value, bool) or isinstance(value, str) and value.strip():
            network[target] = value.strip() if isinstance(value, str) else value
    for source, target, allowed in (
        ("domains", "domains", {"allow", "deny"}),
        ("unixSockets", "unix_sockets", {"allow", "none"}),
    ):
        value = config.get(source)
        if isinstance(value, dict):
            cleaned = {
                str(key).strip(): permission
                for key, permission in value.items()
                if isinstance(key, str) and key.strip() and permission in allowed
            }
            if cleaned:
                network[target] = cleaned
    profile = {
        "filesystem": {
            ":minimal": "read",
            ":project_roots": {".": filesystem_mode},
        },
        "network": network,
    }
    profile_name = config.get("profileName")
    if not isinstance(profile_name, str) or not profile_name.strip():
        stable_profile = json.dumps(
            {"version": 1, "profile": profile},
            sort_keys=True,
            separators=(",", ":"),
        )
        profile_name = (
            f"openclaw-network-{hashlib.sha256(stable_profile.encode()).hexdigest()[:16]}"
        )
    profile_name = profile_name.strip()
    patch = {
        "features.network_proxy.enabled": True,
        "default_permissions": profile_name,
        "permissions": {profile_name: profile},
    }
    return {
        "profileName": profile_name,
        "configFingerprint": hashlib.sha256(
            json.dumps(patch, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "configPatch": patch,
    }


__all__ = [
    "assert_codex_app_server_connection_security",
    "infer_codex_app_server_connection_class",
    "resolve_codex_app_server_network_proxy",
]
