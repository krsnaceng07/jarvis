"""jarvis.config.types_mcp — MCP server and tool approval config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.mcp.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Codex MCP tool approval mode.
McpCodexToolApprovalMode = Literal["auto", "prompt", "approve"]
#: MCP transport kind.
McpTransport = Literal["stdio", "sse", "streamable-http"]
#: MCP HTTP auth mode.
McpAuth = Literal["oauth"]


class McpServerCodexConfig(TypedDict, total=False):
    agents: list
    defaultToolsApprovalMode: str
    default_tools_approval_mode: str


class McpServerToolFilterConfig(TypedDict, total=False):
    include: list
    exclude: list


class McpServerOauthConfig(TypedDict, total=False):
    authProfileId: str
    scope: str
    redirectUrl: str
    clientMetadataUrl: str


class McpServerConfig(TypedDict, total=False):
    enabled: bool
    command: str
    args: list
    env: dict
    cwd: str
    workingDirectory: str
    url: str
    transport: str
    headers: dict
    connectionTimeoutMs: int
    connectTimeout: int
    requestTimeoutMs: int
    timeout: int
    supportsParallelToolCalls: bool
    auth: str
    oauth: McpServerOauthConfig
    sslVerify: bool
    ssl_verify: bool
    clientCert: str
    client_cert: str
    clientKey: str
    client_key: str
    toolFilter: McpServerToolFilterConfig
    codex: McpServerCodexConfig


class McpAppsConfig(TypedDict, total=False):
    enabled: bool
    sandboxOrigin: str
    sandboxPort: int


class McpConfig(TypedDict, total=False):
    servers: dict
    apps: McpAppsConfig
    sessionIdleTtlMs: int


__all__ = [
    "McpCodexToolApprovalMode",
    "McpTransport",
    "McpAuth",
    "McpServerCodexConfig",
    "McpServerToolFilterConfig",
    "McpServerOauthConfig",
    "McpServerConfig",
    "McpAppsConfig",
    "McpConfig",
]
