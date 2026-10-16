"""jarvis.agents.embedded_agent_runner.run.llm_idle_timeout — wrap LLM streams with idle-timeout detection.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/llm-idle-timeout.ts``.

Public surface:

Constants:

- :data:`DEFAULT_LLM_IDLE_TIMEOUT_MS`
- :data:`SELF_HOSTED_LLM_IDLE_TIMEOUT_MS`
- :data:`CLOUD_LLM_FIRST_EVENT_TIMEOUT_MS`
- :data:`LOCAL_LLM_FIRST_EVENT_TIMEOUT_MS`
- :data:`CRON_LLM_IDLE_TIMEOUT_MS`
- :data:`LOCAL_PROVIDER_AUTH_MARKERS`
- :data:`SELF_HOSTED_PROVIDER_ID_PREFIXES`

Functions:

- :func:`is_local_provider_base_url`
- :func:`is_explicit_local_hostname_base_url`
- :func:`is_bare_provider_hostname_base_url`
- :func:`is_self_hosted_provider_id`
- :func:`has_local_provider_auth_marker`
- :func:`is_ollama_cloud_model`
- :func:`resolve_runtime_model_locality`
- :func:`resolve_llm_idle_timeout_ms`
- :func:`resolve_llm_first_event_timeout_ms`
- :func:`stream_with_idle_timeout` (async)

Phase 7.6b-3 — focused minimal port.

The OpenClaw source is tightly coupled to the @openclaw/ai runtime,
stream-compat, and stream-iterator-wrapper layers. The Python port
keeps the public surface and delegates the heavy stream-wrapping to
installable hooks so the host can plug in the real layers as they
land.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional, Set
from urllib.parse import urlparse


#: Default idle timeout for LLM streaming responses in milliseconds.
#: Mirrors :data:`DEFAULT_LLM_IDLE_TIMEOUT_MS` (``llm-idle-timeout.ts:21``).
DEFAULT_LLM_IDLE_TIMEOUT_MS: int = 120_000


#: Idle timeout for self-hosted providers. Mirrors
#: :data:`SELF_HOSTED_LLM_IDLE_TIMEOUT_MS` (``llm-idle-timeout.ts:22``).
SELF_HOSTED_LLM_IDLE_TIMEOUT_MS: int = 300_000


#: First-event timeout for cloud providers. Mirrors
#: :data:`CLOUD_LLM_FIRST_EVENT_TIMEOUT_MS` (``llm-idle-timeout.ts:23``).
CLOUD_LLM_FIRST_EVENT_TIMEOUT_MS: int = DEFAULT_LLM_IDLE_TIMEOUT_MS


#: First-event timeout for local providers. Mirrors
#: :data:`LOCAL_LLM_FIRST_EVENT_TIMEOUT_MS` (``llm-idle-timeout.ts:24``).
LOCAL_LLM_FIRST_EVENT_TIMEOUT_MS: int = 300_000


#: Idle timeout for cron-triggered runs. Mirrors
#: :data:`CRON_LLM_IDLE_TIMEOUT_MS` (``llm-idle-timeout.ts:27``).
CRON_LLM_IDLE_TIMEOUT_MS: int = 60_000


#: Auth markers for local providers. Mirrors
#: :data:`LOCAL_PROVIDER_AUTH_MARKERS` (``llm-idle-timeout.ts:28``).
LOCAL_PROVIDER_AUTH_MARKERS: Set[str] = {"custom-local", "ollama-local"}


#: Self-hosted provider id prefixes. Mirrors
#: :data:`SELF_HOSTED_PROVIDER_ID_PREFIXES` (``llm-idle-timeout.ts:29``).
SELF_HOSTED_PROVIDER_ID_PREFIXES: tuple = (
    "ollama",
    "lmstudio",
    "vllm",
    "sglang",
    "llama-cpp",
)


#: Max timer-safe timeout (mirrors ``MAX_TIMER_TIMEOUT_MS`` from
#: ``normalization-core/number-coercion``).
MAX_TIMER_TIMEOUT_MS: int = 2_147_483_647  # int32 max


# ---------------------------------------------------------------------------
# Pure helpers (ported as-is)
# ---------------------------------------------------------------------------


def is_local_provider_base_url(base_url: str) -> bool:
    """Return True when the URL is loopback / private / `.local`.

    Mirrors :func:`isLocalProviderBaseUrl`
    (``llm-idle-timeout.ts:58-108``).
    """
    if not isinstance(base_url, str) or not base_url:
        return False
    try:
        host = urlparse(base_url).hostname or ""
    except Exception:
        return False
    host = host.lower()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if (
        host == "localhost"
        or host == "0.0.0.0"
        or host == "::1"
        or host == "::ffff:7f00:1"
        or host == "::ffff:127.0.0.1"
        or host.endswith(".local")
    ):
        return True
    # IPv6 unique local + link-local
    if re.match(r"^f[cd][0-9a-f]{2}:", host) or re.match(r"^fe[89ab][0-9a-f]:", host):
        return True
    # IPv4 literal strict parse
    if not re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
        return False
    try:
        octets = [int(part) for part in host.split(".")]
    except Exception:
        return False
    if any((not isinstance(p, int)) or p < 0 or p > 255 for p in octets):
        return False
    a, b = octets[0], octets[1]
    return (
        a == 127
        or a == 10
        or (a == 172 and 16 <= b <= 31)
        or (a == 192 and b == 168)
        or (a == 100 and 64 <= b <= 127)
    )


def is_explicit_local_hostname_base_url(base_url: str) -> bool:
    """Return True when the host is an explicit local-hostname alias.

    Mirrors :func:`isExplicitLocalHostnameBaseUrl`
    (``llm-idle-timeout.ts:110-...``).
    """
    if not isinstance(base_url, str) or not base_url:
        return False
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except Exception:
        return False
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if host in (
        "docker.orb.internal",
        "host.docker.internal",
        "host.orb.internal",
        "gateway.docker.internal",
        "kubernetes.default",
        "kubernetes.default.svc",
    ):
        return True
    return host.endswith(".internal") or host.endswith(".lan")


def is_bare_provider_hostname_base_url(base_url: str) -> bool:
    """Return True when the host is a bare provider name (no TLD).

    Mirrors :func:`isBareProviderHostnameBaseUrl`
    (``llm-idle-timeout.ts``).
    """
    if not isinstance(base_url, str) or not base_url:
        return False
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    # `localhost` and well-known loopback hostnames are not "bare
    # provider hostnames" — they are local-hostname aliases and have
    # their own detection path.
    if host == "localhost" or host == "ip6-localhost" or host == "ip6-loopback":
        return False
    # Bare hostname = one label, no dots
    return "." not in host and not host.endswith(".local")


def is_self_hosted_provider_id(provider: Optional[str]) -> bool:
    """Return True when the provider id matches a self-hosted prefix.

    Mirrors :func:`isSelfHostedProviderId`
    (``llm-idle-timeout.ts``).
    """
    if not isinstance(provider, str) or not provider:
        return False
    return any(
        provider.startswith(prefix) for prefix in SELF_HOSTED_PROVIDER_ID_PREFIXES
    )


def has_local_provider_auth_marker(api_key: Any) -> bool:
    """Return True when ``api_key`` carries a local-provider marker.

    Mirrors :func:`hasLocalProviderAuthMarker`
    (``llm-idle-timeout.ts``).
    """
    if not isinstance(api_key, str) or not api_key:
        return False
    return any(marker in api_key for marker in LOCAL_PROVIDER_AUTH_MARKERS)


def is_ollama_cloud_model(
    model: Optional[Dict[str, Any]],
) -> bool:
    """Return True when the model targets Ollama's cloud service.

    Mirrors :func:`isOllamaCloudModel`
    (``llm-idle-timeout.ts``).
    """
    if not isinstance(model, dict):
        return False
    model_id = model.get("id") or ""
    provider = model.get("provider") or ""
    if not provider.startswith("ollama"):
        return False
    return "cloud" in model_id.lower() or model_id.lower().startswith("cloud-")


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for ``findConfiguredProviderConfig`` from the OpenClaw source.
_FIND_CONFIGURED_PROVIDER_CONFIG: Callable[[Dict[str, Any], str], Any] = (
    lambda _config, _provider: None
)


def set_find_configured_provider_config_hook(
    hook: Callable[[Dict[str, Any], str], Any],
) -> None:
    """Install a custom findConfiguredProviderConfig hook."""
    global _FIND_CONFIGURED_PROVIDER_CONFIG
    _FIND_CONFIGURED_PROVIDER_CONFIG = hook


#: Hook for ``getLastToolActivityMs`` from
#: ``tool-activity-heartbeat.ts``.
_GET_LAST_TOOL_ACTIVITY_MS: Callable[[], Optional[int]] = lambda: None


def set_get_last_tool_activity_ms_hook(
    hook: Callable[[], Optional[int]],
) -> None:
    """Install a custom getLastToolActivityMs hook."""
    global _GET_LAST_TOOL_ACTIVITY_MS
    _GET_LAST_TOOL_ACTIVITY_MS = hook


#: Hook for ``onToolActivity`` from ``tool-activity-heartbeat.ts``.
_ON_TOOL_ACTIVITY: Callable[[Callable[[], None]], None] = lambda _cb: None


def set_on_tool_activity_hook(
    hook: Callable[[Callable[[], None]], None],
) -> None:
    """Install a custom onToolActivity hook."""
    global _ON_TOOL_ACTIVITY
    _ON_TOOL_ACTIVITY = hook


#: Hook for ``onLlmRequestActivity`` from
#: ``@openclaw/ai/internal/runtime``.
_ON_LLM_REQUEST_ACTIVITY: Callable[[Callable[[], None]], None] = lambda _cb: None


def set_on_llm_request_activity_hook(
    hook: Callable[[Callable[[], None]], None],
) -> None:
    """Install a custom onLlmRequestActivity hook."""
    global _ON_LLM_REQUEST_ACTIVITY
    _ON_LLM_REQUEST_ACTIVITY = hook


#: Hook for the create-stream-iterator-wrapper step.
_CREATE_STREAM_ITERATOR_WRAPPER: Callable[[Dict[str, Any]], Any] = (
    lambda _params: None
)


def set_create_stream_iterator_wrapper_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom createStreamIteratorWrapper hook."""
    global _CREATE_STREAM_ITERATOR_WRAPPER
    _CREATE_STREAM_ITERATOR_WRAPPER = hook


#: Hook for the finite-seconds-to-timer-safe-milliseconds step.
_FINITE_SECONDS_TO_TIMER_SAFE_MILLISECONDS: Callable[[float], int] = (
    lambda seconds: int(seconds * 1000) if seconds > 0 else 0
)


def set_finite_seconds_to_timer_safe_milliseconds_hook(
    hook: Callable[[float], int],
) -> None:
    """Install a custom finiteSecondsToTimerSafeMilliseconds hook."""
    global _FINITE_SECONDS_TO_TIMER_SAFE_MILLISECONDS
    _FINITE_SECONDS_TO_TIMER_SAFE_MILLISECONDS = hook


#: Hook for the clamp-timer-timeout-ms step.
_CLAMP_TIMER_TIMEOUT_MS: Callable[[int], int] = lambda ms: min(max(0, int(ms)), MAX_TIMER_TIMEOUT_MS)


def set_clamp_timer_timeout_ms_hook(
    hook: Callable[[int], int],
) -> None:
    """Install a custom clampTimerTimeoutMs hook."""
    global _CLAMP_TIMER_TIMEOUT_MS
    _CLAMP_TIMER_TIMEOUT_MS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_runtime_model_locality(
    params: Optional[Dict[str, Any]] = None,
) -> str:
    """Return the locality label for the runtime model.

    Mirrors :func:`resolveRuntimeModelLocality`
    (``llm-idle-timeout.ts``).

    Returns one of: ``"local"`` / ``"self-hosted"`` / ``"cloud"``.
    """
    params = params or {}
    model = params.get("model") or {}
    provider = model.get("provider") or ""
    base_url = model.get("baseUrl") or ""
    config = params.get("config")
    api_key = model.get("apiKey")

    if has_local_provider_auth_marker(api_key):
        return "local"
    # Ollama-cloud check must run before the self-hosted check: an
    # ollama model id that includes "cloud" is a cloud model, not a
    # self-hosted one, even though the provider id starts with
    # "ollama".
    if is_ollama_cloud_model(model):
        return "cloud"
    if is_self_hosted_provider_id(provider):
        return "self-hosted"
    if is_local_provider_base_url(base_url):
        return "local"
    if is_explicit_local_hostname_base_url(base_url):
        return "local"
    if config is not None and provider:
        provider_config = _FIND_CONFIGURED_PROVIDER_CONFIG(config, provider)
        if provider_config:
            if provider_config.get("localService"):
                return "local"
            if provider_config.get("apiKey"):
                return "local" if has_local_provider_auth_marker(
                    provider_config.get("apiKey")
                ) else "cloud"
    return "cloud"


def resolve_llm_idle_timeout_ms(
    params: Optional[Dict[str, Any]] = None,
) -> int:
    """Resolve the LLM idle-timeout in milliseconds.

    Mirrors :func:`resolveLlmIdleTimeoutMs`
    (``llm-idle-timeout.ts``).
    """
    params = params or {}
    locality = resolve_runtime_model_locality(params)
    trigger = params.get("trigger") or ""
    if trigger == "cron":
        return CRON_LLM_IDLE_TIMEOUT_MS
    if locality in ("local", "self-hosted"):
        return SELF_HOSTED_LLM_IDLE_TIMEOUT_MS
    config = params.get("config")
    if config is not None:
        # Try to read from config; default to base constant.
        configured = (config.get("llm") or {}).get("idleTimeoutMs")
        if isinstance(configured, (int, float)) and configured > 0:
            return int(configured)
    return DEFAULT_LLM_IDLE_TIMEOUT_MS


def resolve_llm_first_event_timeout_ms(
    params: Optional[Dict[str, Any]] = None,
) -> int:
    """Resolve the LLM first-event timeout in milliseconds.

    Mirrors :func:`resolveLlmFirstEventTimeoutMs`
    (``llm-idle-timeout.ts``).
    """
    params = params or {}
    locality = resolve_runtime_model_locality(params)
    if locality in ("local", "self-hosted"):
        return LOCAL_LLM_FIRST_EVENT_TIMEOUT_MS
    return CLOUD_LLM_FIRST_EVENT_TIMEOUT_MS


async def stream_with_idle_timeout(
    params: Dict[str, Any],
) -> Any:
    """Wrap a stream with idle-timeout detection.

    Mirrors :func:`streamWithIdleTimeout`
    (``llm-idle-timeout.ts``).
    """
    # Minimal focused port: delegate to the iterator-wrapper hook.
    return _CREATE_STREAM_ITERATOR_WRAPPER(
        {
            "params": dict(params or {}),
            "idleTimeoutMs": resolve_llm_idle_timeout_ms(params),
            "firstEventTimeoutMs": resolve_llm_first_event_timeout_ms(params),
        }
    )


__all__ = [
    "CLOUD_LLM_FIRST_EVENT_TIMEOUT_MS",
    "CRON_LLM_IDLE_TIMEOUT_MS",
    "DEFAULT_LLM_IDLE_TIMEOUT_MS",
    "LOCAL_LLM_FIRST_EVENT_TIMEOUT_MS",
    "LOCAL_PROVIDER_AUTH_MARKERS",
    "MAX_TIMER_TIMEOUT_MS",
    "SELF_HOSTED_LLM_IDLE_TIMEOUT_MS",
    "SELF_HOSTED_PROVIDER_ID_PREFIXES",
    "has_local_provider_auth_marker",
    "is_bare_provider_hostname_base_url",
    "is_explicit_local_hostname_base_url",
    "is_local_provider_base_url",
    "is_ollama_cloud_model",
    "is_self_hosted_provider_id",
    "resolve_llm_first_event_timeout_ms",
    "resolve_llm_idle_timeout_ms",
    "resolve_runtime_model_locality",
    "set_clamp_timer_timeout_ms_hook",
    "set_create_stream_iterator_wrapper_hook",
    "set_find_configured_provider_config_hook",
    "set_finite_seconds_to_timer_safe_milliseconds_hook",
    "set_get_last_tool_activity_ms_hook",
    "set_on_llm_request_activity_hook",
    "set_on_tool_activity_hook",
    "stream_with_idle_timeout",
]
