"""jarvis.config.types_provider_request — provider HTTP transport config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.provider-request.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Auth override modes for provider requests.
ProviderRequestAuthMode = Literal["provider-default", "authorization-bearer", "header"]


class ConfiguredProviderRequestTls(TypedDict, total=False):
    """TLS material and verification knobs."""

    ca: object
    cert: object
    key: object
    passphrase: object
    serverName: str
    insecureSkipVerify: bool


class ConfiguredProviderRequestAuth(TypedDict, total=False):
    """Authentication override applied to provider requests."""

    mode: str
    token: object
    headerName: str
    value: object
    prefix: str


class ConfiguredProviderRequestProxy(TypedDict, total=False):
    """Proxy selection for provider requests."""

    mode: str
    url: str
    tls: ConfiguredProviderRequestTls


class ConfiguredProviderRequest(TypedDict, total=False):
    """Shared provider request overrides used by model providers and media/tool providers."""

    headers: dict
    auth: ConfiguredProviderRequestAuth
    proxy: ConfiguredProviderRequestProxy
    tls: ConfiguredProviderRequestTls


class ConfiguredModelProviderRequest(ConfiguredProviderRequest, total=False):
    """Model-provider request overrides plus the private-network opt-in."""

    allowPrivateNetwork: bool


__all__ = [
    "ProviderRequestAuthMode",
    "ConfiguredProviderRequestTls",
    "ConfiguredProviderRequestAuth",
    "ConfiguredProviderRequestProxy",
    "ConfiguredProviderRequest",
    "ConfiguredModelProviderRequest",
]
