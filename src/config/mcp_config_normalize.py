"""jarvis.config.mcp_config_normalize — MCP server config normalizer.

OpenClaw parity: mirrors
``openclaw-main/src/config/mcp-config-normalize.ts``.
"""
from __future__ import annotations

from typing import Any, Dict


#: Maps CLI-native MCP type aliases to OpenClaw HTTP transport names.
CLI_MCP_TYPE_TO_OPENCLAW_TRANSPORT: Dict[str, str] = {
    "http": "streamable-http",
    "streamable-http": "streamable-http",
    "sse": "sse",
    "stdio": "stdio",
}


def _is_record(value) -> bool:
    return isinstance(value, dict) and not isinstance(value, (list, tuple, str, bytes, set))


def _normalize_mcp_string(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def resolve_openclaw_mcp_transport_alias(value) -> str:
    """Map CLI-native MCP type aliases to OpenClaw HTTP transport names.

    Mirrors :func:`resolveOpenClawMcpTransportAlias`
    (``shared/config/mcp-config-normalize.ts`).
    """
    mapped = CLI_MCP_TYPE_TO_OPENCLAW_TRANSPORT.get(_normalize_mcp_string(value))
    return mapped if mapped in ("sse", "streamable-http") else ""


def is_known_cli_mcp_type_alias(value) -> bool:
    """Return whether a raw MCP ``type`` value is a legacy CLI alias OpenClaw can rewrite.

    Mirrors :func:`isKnownCliMcpTypeAlias`
    (``shared/config/mcp-config-normalize.ts`).
    """
    return _normalize_mcp_string(value) in CLI_MCP_TYPE_TO_OPENCLAW_TRANSPORT


#: Snake-case / legacy alias keys that get normalized to canonical camelCase.
_LEGACY_KEY_MAP = {
    "connect_timeout": "connectTimeout",
    "supports_parallel_tool_calls": "supportsParallelToolCalls",
    "ssl_verify": "sslVerify",
    "client_cert": "clientCert",
    "client_key": "clientKey",
}


def canonicalize_configured_mcp_server(server: dict) -> dict:
    """Convert operator-friendly MCP server aliases into canonical config keys.

    Mirrors :func:`canonicalizeConfiguredMcpServer`
    (``shared/config/mcp-config-normalize.ts`).
    """
    if not isinstance(server, dict):
        return {}
    next_: dict = dict(server)
    transport_alias = resolve_openclaw_mcp_transport_alias(next_.get("type"))
    # ``transport`` is OpenClaw's canonical field; legacy ``type`` only fills a gap.
    if not isinstance(next_.get("transport"), str) and transport_alias:
        next_["transport"] = transport_alias
    if is_known_cli_mcp_type_alias(next_.get("type")):
        next_.pop("type", None)
    for legacy, canonical in _LEGACY_KEY_MAP.items():
        if legacy in next_ and canonical not in next_:
            next_[canonical] = next_.pop(legacy)
    return next_


def normalize_configured_mcp_servers(value) -> Dict[str, dict]:
    """Return a cloned map of object-shaped MCP server configs, dropping invalid entries.

    Mirrors :func:`normalizeConfiguredMcpServers`
    (``shared/config/mcp-config-normalize.ts`).
    """
    if not _is_record(value):
        return {}
    return {
        name: dict(server) for name, server in value.items() if _is_record(server)
    }


__all__ = [
    "CLI_MCP_TYPE_TO_OPENCLAW_TRANSPORT",
    "resolve_openclaw_mcp_transport_alias",
    "is_known_cli_mcp_type_alias",
    "canonicalize_configured_mcp_server",
    "normalize_configured_mcp_servers",
]
