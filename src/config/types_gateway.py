"""jarvis.config.types_gateway — gateway runtime and networking config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.gateway.ts``.

Focused minimal port: TypedDict shapes + Literal unions for the
``GatewayConfig`` family. Cross-references to other types are preserved
as :data:`dict` aliases.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Gateway bind-address policy for local server startup.
GatewayBindMode = Literal["auto", "lan", "loopback", "custom", "tailnet"]


class GatewayTlsConfig(TypedDict, total=False):
    """Gateway TLS config."""
    enabled: bool
    autoGenerate: bool
    certPath: str
    keyPath: str
    caPath: str


class WideAreaDiscoveryConfig(TypedDict, total=False):
    """Wide-area DNS-SD discovery settings."""
    enabled: bool
    domain: str


#: mDNS/Bonjour metadata exposure level.
MdnsDiscoveryMode = Literal["off", "minimal", "full"]


class MdnsDiscoveryConfig(TypedDict, total=False):
    """Local mDNS/Bonjour discovery settings."""
    mode: str  # MdnsDiscoveryMode


class DiscoveryConfig(TypedDict, total=False):
    """Network discovery settings."""
    wideArea: WideAreaDiscoveryConfig
    mdns: MdnsDiscoveryConfig


#: Talk realtime execution mode.
TalkRealtimeMode = Literal["realtime", "stt-tts", "transcription"]


#: Talk realtime transport.
TalkRealtimeTransport = Literal["webrtc", "provider-websocket", "gateway-relay", "managed-room"]


#: Talk realtime brain strategy.
TalkRealtimeBrain = Literal["agent-consult", "direct-tools", "none"]


#: Talk realtime consult routing.
TalkRealtimeConsultRouting = Literal["provider-direct", "force-agent-consult"]


#: Talk consult thinking level.
TalkConsultThinkingLevel = Literal[
    "off", "minimal", "low", "medium", "high", "xhigh", "adaptive", "max", "ultra",
]


class TalkProviderConfig(TypedDict, total=False):
    """Talk provider-owned config."""
    apiKey: object  # SecretInput
    # Provider-specific fields (open index signature in TS)
    # [key: string]: unknown — preserved as catch-all dict access in Python


class TalkRealtimeConfig(TypedDict, total=False):
    """Talk realtime voice session config."""
    provider: str
    providers: dict
    model: str
    speakerVoice: str
    speakerVoiceId: str
    voice: str  # deprecated
    instructions: str
    mode: str  # TalkRealtimeMode
    transport: str  # TalkRealtimeTransport
    vadThreshold: float
    silenceDurationMs: int
    prefixPaddingMs: int
    reasoningEffort: str
    brain: str  # TalkRealtimeBrain
    consultRouting: str  # TalkRealtimeConsultRouting


class ResolvedTalkConfig(TypedDict):
    """Resolved Talk TTS provider config."""
    provider: str
    config: TalkProviderConfig


class TalkConfig(TypedDict, total=False):
    """Talk / voice config."""
    provider: str
    providers: dict
    realtime: TalkRealtimeConfig
    consultThinkingLevel: str  # TalkConsultThinkingLevel
    consultFastMode: bool
    speechLocale: str
    interruptOnSpeech: bool
    silenceTimeoutMs: int


#: Gateway Control UI embed sandbox.
GatewayControlUiEmbedSandbox = Literal["strict", "scripts", "trusted"]


class GatewayControlUiConfig(TypedDict, total=False):
    """Gateway Control UI config."""
    enabled: bool
    basePath: str
    root: str
    toolTitles: bool
    embedSandbox: str  # GatewayControlUiEmbedSandbox
    allowExternalEmbedUrls: bool
    chatMessageMaxWidth: str
    allowedOrigins: list
    dangerouslyAllowHostHeaderOriginFallback: bool
    allowInsecureAuth: bool
    dangerouslyDisableDeviceAuth: bool


#: Gateway authentication strategy.
GatewayAuthMode = Literal["none", "token", "password", "trusted-proxy"]


class GatewayTrustedProxyDeviceAutoApproveConfig(TypedDict, total=False):
    """Auto-approve new browser devices through trusted proxy."""
    enabled: bool
    scopes: list


class GatewayTrustedProxyConfig(TypedDict, total=False):
    """Trusted reverse proxy auth config."""
    userHeader: str
    requiredHeaders: list
    allowUsers: list
    allowLoopback: bool
    deviceAutoApprove: GatewayTrustedProxyDeviceAutoApproveConfig


class GatewayAuthRateLimitConfig(TypedDict, total=False):
    """Auth rate limit config."""
    maxAttempts: int
    windowMs: int
    lockoutMs: int
    exemptLoopback: bool


class GatewayAuthConfig(TypedDict, total=False):
    """Gateway auth config."""
    mode: str  # GatewayAuthMode
    token: object  # SecretInput
    password: object  # SecretInput
    allowTailscale: bool
    rateLimit: GatewayAuthRateLimitConfig
    trustedProxy: GatewayTrustedProxyConfig


#: Tailscale exposure mode.
GatewayTailscaleMode = Literal["off", "serve", "funnel"]


class GatewayTailscaleConfig(TypedDict, total=False):
    """Tailscale exposure config."""
    mode: str  # GatewayTailscaleMode
    resetOnExit: bool
    serviceName: str
    preserveFunnel: bool


#: Remote gateway transport.
GatewayRemoteTransport = Literal["ssh", "direct"]


#: macOS SSH host-key policy.
GatewayRemoteSshHostKeyPolicy = Literal["strict", "openssh"]


class GatewayRemoteConfig(TypedDict, total=False):
    """Remote gateway config."""
    url: str
    transport: str  # GatewayRemoteTransport
    remotePort: int
    token: object  # SecretInput
    password: object  # SecretInput
    tlsFingerprint: str
    sshTarget: str
    sshIdentity: str
    sshHostKeyPolicy: str  # GatewayRemoteSshHostKeyPolicy


class GatewayTerminalConfig(TypedDict, total=False):
    """Operator terminal config."""
    enabled: bool
    shell: str
    detachedSessionTimeoutSeconds: int


#: Gateway config reload strategy.
GatewayReloadMode = Literal["off", "restart", "hot", "hybrid"]


class GatewayReloadConfig(TypedDict, total=False):
    """Config reload config."""
    mode: str  # GatewayReloadMode
    debounceMs: int
    deferralTimeoutMs: int


class GatewayHttpChatCompletionsConfig(TypedDict, total=False):
    """OpenAI-compatible /v1/chat/completions config."""
    enabled: bool
    maxBodyBytes: int
    maxImageParts: int
    # … other OpenAI-compat fields


class GatewayHttpEndpointConfig(TypedDict, total=False):
    """Per-endpoint HTTP config (chat, responses, embeddings, etc.)."""
    chatCompletions: GatewayHttpChatCompletionsConfig


class GatewayConfig(TypedDict, total=False):
    """Top-level gateway config."""
    enabled: bool
    bind: str  # GatewayBindMode
    host: str
    port: int
    tls: GatewayTlsConfig
    auth: GatewayAuthConfig
    tailscale: GatewayTailscaleConfig
    remote: GatewayRemoteConfig
    terminal: GatewayTerminalConfig
    controlUi: GatewayControlUiConfig
    http: GatewayHttpEndpointConfig
    reload: GatewayReloadConfig
    trustedProxies: list
    allowRealIpFallback: bool
    nodes: dict
    nodePairing: dict
    plugins: dict
    rateLimit: dict
    log: dict
    webchat: dict
    canvasHost: dict
    # Catch-all for plugin-added fields
    # [key: string]: unknown — Python port consumers use dict access


__all__ = [
    "GatewayBindMode",
    "GatewayTlsConfig",
    "WideAreaDiscoveryConfig",
    "MdnsDiscoveryMode",
    "MdnsDiscoveryConfig",
    "DiscoveryConfig",
    "TalkRealtimeMode",
    "TalkRealtimeTransport",
    "TalkRealtimeBrain",
    "TalkRealtimeConsultRouting",
    "TalkConsultThinkingLevel",
    "TalkProviderConfig",
    "TalkRealtimeConfig",
    "ResolvedTalkConfig",
    "TalkConfig",
    "GatewayControlUiEmbedSandbox",
    "GatewayControlUiConfig",
    "GatewayAuthMode",
    "GatewayTrustedProxyDeviceAutoApproveConfig",
    "GatewayTrustedProxyConfig",
    "GatewayAuthRateLimitConfig",
    "GatewayAuthConfig",
    "GatewayTailscaleMode",
    "GatewayTailscaleConfig",
    "GatewayRemoteTransport",
    "GatewayRemoteSshHostKeyPolicy",
    "GatewayRemoteConfig",
    "GatewayTerminalConfig",
    "GatewayReloadMode",
    "GatewayReloadConfig",
    "GatewayHttpChatCompletionsConfig",
    "GatewayHttpEndpointConfig",
    "GatewayConfig",
]
