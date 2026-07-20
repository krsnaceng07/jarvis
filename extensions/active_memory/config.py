"""config — operator-facing config schema for active-memory.

OpenClaw parity: mirrors ``extensions/active-memory/config.ts``.

Surface
-------
- ``normalize_plugin_config(raw, cfg)`` →
  ``ResolvedActiveRecallPluginConfig``: validates the
  operator's config dict, fills in defaults, clamps integer
  ranges, and picks the right ``toolsAllow`` list based on
  the active memory slot (``memory-core`` vs
  ``memory-lancedb``).
- ``apply_cli_runtime_recall_timeout_default(cfg,
  cli_dispatch_eligible)``: bumps ``timeoutMs`` to
  ``DEFAULT_CLI_RUNTIME_RECALL_TIMEOUT_MS`` (45s) when the
  recall is eligible for CLI-backend dispatch (CLI spawn +
  MCP handshake + tool roundtrips take 14-20s; the plain
  15s default would time out most of them). Explicit
  operator config always wins.
- ``has_deprecated_model_fallback_policy(raw)`` → ``bool``:
  detects the deprecated ``modelFallbackPolicy`` config key
  so we can warn the operator (the field is no longer
  consumed by the runtime; ``modelFallback`` is a
  chain-resolution last-resort, not a runtime failover).
- Test-helper setters: ``set_minimum_timeout_ms_for_tests``,
  ``set_setup_grace_timeout_ms_for_tests``,
  ``reset_active_memory_config_for_tests``.

The file is intentionally side-effect-free (module-level
state is limited to the test-helper variables, which are
mutated only via the ``*_for_tests`` setters).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jarvis_sdk import (
    as_optional_record,
    is_path_inside,
    normalize_lowercase_string_or_empty,
    normalize_string_entries,
    parse_strict_positive_integer,
)

from .types import (
    ACTIVE_MEMORY_RESERVED_TOOLS_ALLOW,
    DEFAULT_ACTIVE_MEMORY_TOOLS_ALLOW,
    DEFAULT_CACHE_TTL_MS,
    DEFAULT_CIRCUIT_BREAKER_COOLDOWN_MS,
    DEFAULT_CIRCUIT_BREAKER_MAX_TIMEOUTS,
    DEFAULT_CLI_RUNTIME_RECALL_TIMEOUT_MS,
    DEFAULT_MAX_SUMMARY_CHARS,
    DEFAULT_MIN_TIMEOUT_MS,
    DEFAULT_QMD_SEARCH_MODE,
    DEFAULT_QUERY_MODE,
    DEFAULT_RECENT_ASSISTANT_CHARS,
    DEFAULT_RECENT_ASSISTANT_TURNS,
    DEFAULT_RECENT_USER_CHARS,
    DEFAULT_RECENT_USER_TURNS,
    DEFAULT_SETUP_GRACE_TIMEOUT_MS,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_TRANSCRIPT_DIR,
    LANCEDB_ACTIVE_MEMORY_TOOLS_ALLOW,
    MAX_ACTIVE_MEMORY_TOOLS_ALLOW,
    MAX_SETUP_GRACE_TIMEOUT_MS,
    MAX_TIMEOUT_MS,
    ActiveMemoryChatType,
    ActiveMemoryFastMode,
    ActiveMemoryModelFallbackPolicy,
    ActiveMemoryPromptStyle,
    ActiveMemoryQmdSearchMode,
    ActiveMemoryQueryMode,
    ActiveMemoryThinkingLevel,
    ResolvedActiveRecallPluginConfig,
)

# ── Module-level test-helper state ─────────────────────────────────

_minimum_timeout_ms: int = DEFAULT_MIN_TIMEOUT_MS
_setup_grace_timeout_ms: int = DEFAULT_SETUP_GRACE_TIMEOUT_MS


def set_minimum_timeout_ms_for_tests(value: int) -> None:
    """Test helper: set the floor for the ``timeoutMs`` clamp."""
    global _minimum_timeout_ms
    _minimum_timeout_ms = value


def set_setup_grace_timeout_ms_for_tests(value: int) -> None:
    """Test helper: set the default for ``setupGraceTimeoutMs``."""
    global _setup_grace_timeout_ms
    _setup_grace_timeout_ms = max(0, int(value))


def reset_active_memory_config_for_tests() -> None:
    """Test helper: restore the module-level defaults."""
    global _minimum_timeout_ms, _setup_grace_timeout_ms
    _minimum_timeout_ms = DEFAULT_MIN_TIMEOUT_MS
    _setup_grace_timeout_ms = DEFAULT_SETUP_GRACE_TIMEOUT_MS


# ── Helpers ────────────────────────────────────────────────────────


def _clamp_int(
    value: int | float | None,
    fallback: int,
    *,
    lo: int,
    hi: int,
) -> int:
    """Clamp ``value`` to ``[lo, hi]``; fall back to ``fallback``.

    Mirrors OpenClaw's ``clampInt`` helper.
    """
    if value is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return fallback
    if value != value:  # NaN check
        return fallback
    floored = int(value)
    if floored < lo:
        return lo
    if floored > hi:
        return hi
    return floored


def _parse_optional_positive_int(value: Any, fallback: int) -> int:
    """Parse ``value`` as a positive int; fall back on bad input.

    Mirrors OpenClaw's ``parseOptionalPositiveInt``. Falls
    back when the value is missing, zero, negative, or
    unparseable. Returns the parsed int otherwise.
    """
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value if value > 0 else fallback
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return fallback
        return int(value) if value > 0 else fallback
    if isinstance(value, str):
        parsed = parse_strict_positive_integer(value)
        return parsed if parsed is not None else fallback
    return fallback


def _normalize_chat_id_list(value: Any) -> list[str]:
    """Normalize a list of chat/user ids.

    Mirrors OpenClaw's ``normalizeChatIdList``. Lower-cases,
    trims, deduplicates; non-string entries are dropped.
    """
    if not isinstance(value, list | tuple):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        trimmed = entry.strip().lower()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        out.append(trimmed)
    return out


def _normalize_configured_tools_allow(value: Any) -> list[str] | None:
    """Normalize the operator's ``toolsAllow`` list.

    Mirrors OpenClaw's ``normalizeConfiguredToolsAllow``.
    Skips reserved entries (``*`` and core agent tools) and
    caps the result at ``MAX_ACTIVE_MEMORY_TOOLS_ALLOW``
    (32).
    """
    if not isinstance(value, list | tuple):
        return None
    seen: set[str] = set()
    out: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        normalized = normalize_lowercase_string_or_empty(entry)
        if not normalized or _is_reserved_tools_allow_entry(normalized) or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
        if len(out) >= MAX_ACTIVE_MEMORY_TOOLS_ALLOW:
            break
    return out if out else None


def _is_reserved_tools_allow_entry(value: str) -> bool:
    """True if ``value`` is a reserved tools-allow entry.

    Mirrors OpenClaw's ``isReservedActiveMemoryToolsAllowEntry``.
    Reserved entries are wildcards (``*``) and OpenClaw's
    core agent tools. Operators can still pin memory_search /
    memory_get / memory_recall individually.
    """
    normalized = value.strip().lower()
    if normalized.startswith("group:"):
        return True
    return normalized in ACTIVE_MEMORY_RESERVED_TOOLS_ALLOW


def _resolve_default_tools_allow(cfg: Any) -> list[str]:
    """Return the per-memory-provider default tools-allow list.

    Mirrors OpenClaw's ``resolveDefaultToolsAllow``. LanceDB
    memory uses ``memory_recall``; built-in ``memory-core``
    uses ``memory_search`` + ``memory_get``.
    """
    plugins = as_optional_record(getattr(cfg, "get", lambda *_: None)("plugins"))
    if not isinstance(plugins, dict):
        return list(DEFAULT_ACTIVE_MEMORY_TOOLS_ALLOW)
    slots = as_optional_record(plugins.get("slots"))
    if isinstance(slots, dict) and slots.get("memory") == "memory-lancedb":
        return list(LANCEDB_ACTIVE_MEMORY_TOOLS_ALLOW)
    return list(DEFAULT_ACTIVE_MEMORY_TOOLS_ALLOW)


def _resolve_tools_allow(
    plugin_tools_allow: Any,
    cfg: Any,
) -> list[str]:
    """Pick the effective ``toolsAllow`` list.

    Mirrors OpenClaw's ``resolveToolsAllow``. The operator's
    list wins when present and well-formed; otherwise the
    per-memory-provider default is used.
    """
    return _normalize_configured_tools_allow(plugin_tools_allow) or _resolve_default_tools_allow(
        cfg
    )


def _normalize_prompt_text(value: Any) -> str | None:
    """Trim a prompt-override / prompt-append text value.

    Mirrors OpenClaw's ``normalizePromptConfigText``. Returns
    ``None`` for non-string / empty input.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _resolve_qmd_search_mode(value: Any) -> ActiveMemoryQmdSearchMode:
    """Return the QMD search mode; fall back to the default.

    Mirrors OpenClaw's ``resolveQmdSearchMode``. Accepts the
    four canonical values; any other input falls back to
    ``DEFAULT_QMD_SEARCH_MODE`` (``"search"``).
    """
    if value in ("inherit", "search", "vsearch", "query"):
        return value  # type: ignore[return-value]
    return DEFAULT_QMD_SEARCH_MODE  # type: ignore[return-value]


def _resolve_thinking_level(thinking: Any) -> ActiveMemoryThinkingLevel:
    """Return the thinking level; fall back to ``"off"``.

    Mirrors OpenClaw's ``resolveThinkingLevel``. Accepts the
    eight canonical values; any other input falls back to
    ``"off"``.
    """
    if thinking in (
        "off",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "adaptive",
        "max",
    ):
        return thinking  # type: ignore[return-value]
    return "off"


def _normalize_active_memory_fast_mode(
    fast_mode: Any,
) -> ActiveMemoryFastMode | None:
    """Return the fast-mode value; ``None`` for unparseable input.

    Mirrors OpenClaw's ``normalizeActiveMemoryFastMode``.
    Accepts ``True``, ``False``, or ``"auto"``; returns
    ``None`` for any other value.
    """
    if isinstance(fast_mode, bool) or fast_mode == "auto":
        return fast_mode  # type: ignore[return-value]
    return None


def _resolve_prompt_style(
    prompt_style: Any,
    query_mode: ActiveMemoryQueryMode,
) -> ActiveMemoryPromptStyle:
    """Return the prompt style; fall back based on ``queryMode``.

    Mirrors OpenClaw's ``resolvePromptStyle``. Accepts the
    six canonical values; falls back to a style that matches
    the active ``queryMode`` (``strict`` for ``message``,
    ``contextual`` for ``full``, ``balanced`` for ``recent``
    / default).
    """
    if prompt_style in (
        "balanced",
        "strict",
        "contextual",
        "recall-heavy",
        "precision-heavy",
        "preference-only",
    ):
        return prompt_style  # type: ignore[return-value]
    if query_mode == "message":
        return "strict"
    if query_mode == "full":
        return "contextual"
    return "balanced"


def _normalize_chat_types(value: Any) -> list[ActiveMemoryChatType]:
    """Filter the operator's ``allowedChatTypes`` to canonical values.

    Mirrors OpenClaw's ``allowedChatTypes`` filter inside
    ``normalizePluginConfig``.
    """
    if not isinstance(value, list | tuple):
        return []
    out: list[ActiveMemoryChatType] = []
    for entry in value:
        if entry in ("direct", "group", "channel", "explicit"):
            out.append(entry)  # type: ignore[arg-type]
    return out


# ── Public API ─────────────────────────────────────────────────────


def has_deprecated_model_fallback_policy(plugin_config: Any) -> bool:
    """Return True if ``plugin_config`` has a deprecated policy key.

    Mirrors OpenClaw's ``hasDeprecatedModelFallbackPolicy``.
    The ``modelFallbackPolicy`` key is no longer consumed by
    the runtime; ``modelFallback`` is a chain-resolution
    last-resort, not a runtime failover. We surface a
    warning so operators don't debug a non-existent failover.
    """
    record = as_optional_record(plugin_config)
    if record is None:
        return False
    return "modelFallbackPolicy" in record


def normalize_plugin_config(
    plugin_config: Any,
    cfg: Any = None,
) -> ResolvedActiveRecallPluginConfig:
    """Normalize the operator's plugin config into the resolved shape.

    Mirrors OpenClaw's ``normalizePluginConfig``. Returns a
    ``ResolvedActiveRecallPluginConfig`` (TypedDict) with
    all fields populated. Operator input is validated;
    unknown keys are silently dropped; bad-value types fall
    back to safe defaults.
    """
    raw = as_optional_record(plugin_config) or {}
    qmd_raw = as_optional_record(raw.get("qmd"))
    allowed_chat_types = _normalize_chat_types(raw.get("allowedChatTypes"))

    timeout_value = _parse_optional_positive_int(raw.get("timeoutMs"), DEFAULT_TIMEOUT_MS)
    timeout_is_default = raw.get("timeoutMs") is None or raw.get("timeoutMs") is None
    timeout_clamped = _clamp_int(
        timeout_value,
        DEFAULT_TIMEOUT_MS,
        lo=_minimum_timeout_ms,
        hi=MAX_TIMEOUT_MS,
    )

    setup_grace = _clamp_int(
        raw.get("setupGraceTimeoutMs"),
        _setup_grace_timeout_ms,
        lo=0,
        hi=MAX_SETUP_GRACE_TIMEOUT_MS,
    )

    query_mode_value = raw.get("queryMode")
    if query_mode_value in ("message", "recent", "full"):
        query_mode: ActiveMemoryQueryMode = query_mode_value  # type: ignore[assignment]
    else:
        query_mode = DEFAULT_QUERY_MODE

    policy_value = raw.get("modelFallbackPolicy")
    if policy_value == "resolved-only":
        policy: ActiveMemoryModelFallbackPolicy = "resolved-only"
    else:
        policy = "default-remote"

    resolved: ResolvedActiveRecallPluginConfig = {  # type: ignore[typeddict-item]
        "enabled": raw.get("enabled", True) is True,
        "agents": normalize_string_entries(raw.get("agents")),
        "model": (
            raw["model"].strip()
            if isinstance(raw.get("model"), str) and raw["model"].strip()
            else None
        ),
        "modelFallback": (
            raw["modelFallback"].strip()
            if isinstance(raw.get("modelFallback"), str) and raw["modelFallback"].strip()
            else None
        ),
        "modelFallbackPolicy": policy,
        "allowedChatTypes": allowed_chat_types if allowed_chat_types else ["direct"],
        "allowedChatIds": _normalize_chat_id_list(raw.get("allowedChatIds")),
        "deniedChatIds": _normalize_chat_id_list(raw.get("deniedChatIds")),
        "thinking": _resolve_thinking_level(raw.get("thinking")),
        "fastMode": _normalize_active_memory_fast_mode(raw.get("fastMode")),
        "promptStyle": _resolve_prompt_style(raw.get("promptStyle"), query_mode),
        "toolsAllow": _resolve_tools_allow(raw.get("toolsAllow"), cfg),
        "promptOverride": _normalize_prompt_text(raw.get("promptOverride")),
        "promptAppend": _normalize_prompt_text(raw.get("promptAppend")),
        "timeoutMs": timeout_clamped,
        "timeoutMsIsDefault": timeout_is_default,
        "setupGraceTimeoutMs": setup_grace,
        "queryMode": query_mode,
        "maxSummaryChars": _clamp_int(
            raw.get("maxSummaryChars"),
            DEFAULT_MAX_SUMMARY_CHARS,
            lo=40,
            hi=1000,
        ),
        "recentUserTurns": _clamp_int(
            raw.get("recentUserTurns"),
            DEFAULT_RECENT_USER_TURNS,
            lo=0,
            hi=4,
        ),
        "recentAssistantTurns": _clamp_int(
            raw.get("recentAssistantTurns"),
            DEFAULT_RECENT_ASSISTANT_TURNS,
            lo=0,
            hi=3,
        ),
        "recentUserChars": _clamp_int(
            raw.get("recentUserChars"),
            DEFAULT_RECENT_USER_CHARS,
            lo=40,
            hi=1000,
        ),
        "recentAssistantChars": _clamp_int(
            raw.get("recentAssistantChars"),
            DEFAULT_RECENT_ASSISTANT_CHARS,
            lo=40,
            hi=1000,
        ),
        "logging": raw.get("logging") is True,
        "cacheTtlMs": _clamp_int(
            raw.get("cacheTtlMs"),
            DEFAULT_CACHE_TTL_MS,
            lo=1000,
            hi=120_000,
        ),
        "circuitBreakerMaxTimeouts": _clamp_int(
            raw.get("circuitBreakerMaxTimeouts"),
            DEFAULT_CIRCUIT_BREAKER_MAX_TIMEOUTS,
            lo=1,
            hi=20,
        ),
        "circuitBreakerCooldownMs": _clamp_int(
            raw.get("circuitBreakerCooldownMs"),
            DEFAULT_CIRCUIT_BREAKER_COOLDOWN_MS,
            lo=5000,
            hi=600_000,
        ),
        "persistTranscripts": raw.get("persistTranscripts") is True,
        "transcriptDir": _normalize_transcript_dir(raw.get("transcriptDir")),
        "qmd": {
            "searchMode": _resolve_qmd_search_mode(qmd_raw.get("searchMode") if qmd_raw else None),
        },
    }
    return resolved


_TRANSCRIPT_DIR_SAFE_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")


def _normalize_transcript_dir(value: Any) -> str:
    """Normalize the operator's ``transcriptDir``.

    Mirrors OpenClaw's ``normalizeTranscriptDir``. Trims,
    strips path separators, and falls back to the default
    when no safe name remains.
    """
    if not isinstance(value, str):
        return DEFAULT_TRANSCRIPT_DIR
    raw = value.strip()
    if not raw:
        return DEFAULT_TRANSCRIPT_DIR
    parts = raw.replace("\\", "/").split("/")
    safe_parts = [p for p in (segment.strip() for segment in parts) if p and p not in {".", ".."}]
    if not safe_parts:
        return DEFAULT_TRANSCRIPT_DIR
    joined = "/".join(safe_parts)
    if not _TRANSCRIPT_DIR_SAFE_RE.match(joined):
        return DEFAULT_TRANSCRIPT_DIR
    return joined


def apply_cli_runtime_recall_timeout_default(
    config: ResolvedActiveRecallPluginConfig,
    cli_dispatch_eligible: bool,
) -> ResolvedActiveRecallPluginConfig:
    """Bump ``timeoutMs`` to the CLI-runtime default when eligible.

    Mirrors OpenClaw's ``applyCliRuntimeRecallTimeoutDefault``.
    CLI-backed recalls (CLI spawn + MCP handshake + tool
    roundtrips) take 14-20s; the plain 15s default would
    time out most of them. API-key routes that keep the
    direct passthrough also keep the plain default.

    Explicit operator config (``timeoutMsIsDefault=False``)
    always wins — the helper returns the input unchanged.
    """
    if not config.get("timeoutMsIsDefault", True):
        return config
    if config.get("timeoutMs", DEFAULT_TIMEOUT_MS) >= DEFAULT_CLI_RUNTIME_RECALL_TIMEOUT_MS:
        return config
    if not cli_dispatch_eligible:
        return config
    bumped = dict(config)
    bumped["timeoutMs"] = DEFAULT_CLI_RUNTIME_RECALL_TIMEOUT_MS
    return bumped  # type: ignore[return-value]


def resolve_safe_transcript_dir(
    base_sessions_dir: str,
    transcript_dir: str,
) -> str:
    """Resolve ``transcript_dir`` against ``base_sessions_dir`` safely.

    Mirrors OpenClaw's ``resolveSafeTranscriptDir``. Refuses
    absolute paths, paths containing ``:`` (drive letters on
    Windows), and paths that escape ``base_sessions_dir``.
    """
    normalized = transcript_dir.strip()
    if not normalized or ":" in normalized or os.path.isabs(normalized):
        return str(Path(base_sessions_dir).resolve() / DEFAULT_TRANSCRIPT_DIR)
    resolved_base = str(Path(base_sessions_dir).resolve())
    candidate = str(Path(resolved_base) / normalized)
    if not is_path_inside(resolved_base, candidate):
        return str(Path(resolved_base).resolve() / DEFAULT_TRANSCRIPT_DIR)
    return candidate


def to_safe_transcript_agent_dir_name(agent_id: str) -> str:
    """URL-encode an agent id for use as a directory name.

    Mirrors OpenClaw's ``toSafeTranscriptAgentDirName``.
    """
    encoded = agent_id.strip()
    # Python's urllib.parse.quote is equivalent to OpenClaw's
    # encodeURIComponent for the default safe set.

    encoded = quote(encoded, safe="")
    return encoded if encoded else "unknown-agent"


def resolve_persistent_transcript_base_dir(api: Any, agent_id: str) -> str:
    """Resolve the persistent transcript base dir for ``agent_id``.

    Mirrors OpenClaw's ``resolvePersistentTranscriptBaseDir``.
    Returns ``<state_dir>/plugins/active-memory/transcripts/agents/<encoded>``.
    Falls back to ``<home>/.jarvis/...`` when ``state_dir`` is
    not provided by the host.
    """

    state_dir = ""
    try:
        if getattr(api, "runtime", None) is not None:
            state_dir = api.runtime.state.resolve_state_dir()
    except Exception:
        state_dir = ""
    if not state_dir:
        state_dir = str(Path.home() / ".jarvis")
    safe = quote(agent_id.strip(), safe="") or "unknown-agent"
    return str(Path(state_dir) / "plugins" / "active-memory" / "transcripts" / "agents" / safe)


def is_missing_registered_memory_tools_error(
    error: Any,
    tools_allow: list[str] | tuple[str, ...] | None = None,
) -> bool:
    """Detect the host's "no callable tools after allowlist" error.

    Mirrors OpenClaw's ``isMissingRegisteredMemoryToolsError``.
    The host raises a typed error when the operator's
    ``toolsAllow`` filter excludes the only memory tool the
    backend registered. We use the same error string to
    recognize the case in ``recall.ts``.
    """
    allow = tools_allow if tools_allow is not None else list(DEFAULT_ACTIVE_MEMORY_TOOLS_ALLOW)
    if not isinstance(error, BaseException):
        return False
    message = str(error).strip()
    prefix = "No callable tools remain after resolving explicit tool allowlist ("
    suffix = (
        "); no registered tools matched. Fix the allowlist or enable the "
        "plugin that registers the requested tool."
    )
    if not message.startswith(prefix) or not message.endswith(suffix):
        return False
    sources = message[len(prefix) : -len(suffix)]
    source_parts = [s.strip() for s in sources.split(";") if s.strip()]
    runtime_source = f"runtime toolsAllow: {', '.join(allow)}"
    return runtime_source in source_parts


__all__ = [
    "apply_cli_runtime_recall_timeout_default",
    "has_deprecated_model_fallback_policy",
    "is_missing_registered_memory_tools_error",
    "normalize_plugin_config",
    "reset_active_memory_config_for_tests",
    "resolve_persistent_transcript_base_dir",
    "resolve_safe_transcript_dir",
    "set_minimum_timeout_ms_for_tests",
    "set_setup_grace_timeout_ms_for_tests",
    "to_safe_transcript_agent_dir_name",
]
