"""session_policy — eligibility, harness-skip, chat-type resolution.

OpenClaw parity: mirrors ``extensions/active-memory/session-policy.ts``.

Phase 4.2a ships the eligibility helpers and the session
toggle store. The ``/active-memory`` slash command itself
lives in 4.2c (it depends on the entry point); this module
exposes the building blocks so 4.2c can wire them up.

Surface
-------
- **Session toggle store** — keyed-store-backed
  enable/disable per session key.
  - ``is_session_active_memory_disabled(params)`` → ``bool``
  - ``set_session_active_memory_disabled(params)`` → ``None``
- **Chat-type resolution + filters** — determine the
  conversation's chat type (``direct`` | ``group`` |
  ``channel`` | ``explicit``) from the session key + provider,
  then apply the operator's allow/deny lists.
  - ``resolve_chat_type(ctx)`` → ``str | None``
  - ``is_allowed_chat_type(config, ctx)`` → ``bool``
  - ``is_allowed_chat_id(config, ctx)`` → ``bool``
  - ``is_private_recall_destination(ctx)`` → ``bool`` (true
    for ``direct`` and ``explicit`` only).
- **Eligible interactive session** — checks the
  ``trigger==user`` flag, blocks dreaming-narrative session
  keys, and requires a channel id (or webchat).
  - ``is_eligible_interactive_session(ctx)`` → ``bool``
- **Harness-skip** — refuses to run active-memory on
  harness/test sessions (deterministic by session-key
  ``harness:`` prefix, OR the per-agent session row is
  ``modelSelectionLocked``, OR the host can't read the
  session row at all).
  - ``should_skip_active_memory_for_harness_session(params)`` → ``bool``
- **Plugin enable/disable** — the global ``enabled`` flag
  plus the per-plugin ``active-memory`` allow/deny in
  ``config.plugins``.
  - ``is_active_memory_globally_enabled(cfg)`` → ``bool``
  - ``is_active_memory_plugin_enabled(cfg)`` → ``bool``
  - ``is_enabled_for_agent(config, agent_id)`` → ``bool``
- **Remember across conversations** — per-agent flag the
  host tracks, separate from active-memory itself.
  - ``has_remember_across_conversations_agent(cfg)`` → ``bool``
  - ``should_remember_across_conversations(cfg, agent_id)`` → ``bool``
- **Admin gating** — guards the ``--global`` slash command.
  - ``lacks_admin_to_mutate_active_memory_global(params)`` → ``bool``
- **Config mutation** — produces a new config dict with the
  ``active-memory.enabled`` flag flipped.
  - ``update_active_memory_global_enabled_in_config(cfg, enabled)``
- **Command session key resolution** — used by the slash
  command to find the active session when the operator
  didn't pass ``--session``.
  - ``resolve_command_session_key(params)`` → ``str | None``
- **Help text** — the ``/active-memory help`` reply.
  - ``format_active_memory_command_help()`` → ``str``
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any

from jarvis_sdk import (
    normalize_plugins_config,
    parse_agent_session_key,
    parse_thread_session_suffix,
    resolve_plugin_config_object,
    resolve_remember_across_conversations,
)

from .types import (
    DEFAULT_AGENT_ID,
    ActiveMemoryChatType,
    ActiveMemoryToggleEntry,
    ResolvedActiveRecallPluginConfig,
)

_log = logging.getLogger("extensions.active_memory.session_policy")


# ── Session toggle store ──────────────────────────────────────────


def _active_memory_toggle_key(session_key: str) -> str:
    """Hash a session key for the toggle store.

    Mirrors OpenClaw's ``activeMemoryToggleKey``. SHA-256
    of the UTF-8-encoded key.
    """
    return hashlib.sha256(session_key.encode("utf-8")).hexdigest()


def _open_session_toggle_store(api: Any) -> Any:
    """Open the per-session toggle store.

    Mirrors OpenClaw's ``openActiveMemoryToggleStore``. Uses
    the host's keyed-store surface (``api.runtime.state.open_keyed_store``);
    the host's default implementation is a no-op so the
    plugin falls back to in-process state when the host
    hasn't wired a real store yet.
    """
    runtime = getattr(api, "runtime", None)
    state = getattr(runtime, "state", None) if runtime is not None else None
    open_fn = getattr(state, "open_keyed_store", None) if state is not None else None
    if not callable(open_fn):
        return None
    try:
        return open_fn(
            {
                "namespace": "session-toggles",
                "maxEntries": 10_000,
            }
        )
    except Exception as exc:
        _log.debug("open_session_toggle_store: open failed: %s", exc)
        return None


async def is_session_active_memory_disabled(params: dict[str, Any]) -> bool:
    """Return True if active-memory is disabled for ``sessionKey``.

    Mirrors OpenClaw's ``isSessionActiveMemoryDisabled``.
    Returns ``False`` for missing keys; ``True`` when the
    toggle store has a ``{disabled: True}`` entry.
    """
    session_key = (
        (params.get("sessionKey") or "").strip()
        if isinstance(params.get("sessionKey"), str)
        else ""
    )
    if not session_key:
        return False
    api = params.get("api")
    store = _open_session_toggle_store(api) if api is not None else None
    if store is None:
        return _in_process_is_disabled(session_key)
    try:
        stored = await _lookup_toggle(store, _active_memory_toggle_key(session_key))
    except Exception as exc:
        _log.debug("is_session_active_memory_disabled: lookup failed: %s", exc)
        return _in_process_is_disabled(session_key)
    if stored is None:
        return _in_process_is_disabled(session_key)
    return stored.get("disabled") is True


async def set_session_active_memory_disabled(params: dict[str, Any]) -> None:
    """Set the active-memory enable/disable flag for ``sessionKey``.

    Mirrors OpenClaw's ``setSessionActiveMemoryDisabled``.
    When ``disabled`` is False, deletes the entry (the
    absence of an entry is the "enabled" default).
    """
    session_key = params.get("sessionKey")
    disabled = params.get("disabled", False) is True
    if not isinstance(session_key, str) or not session_key.strip():
        return
    api = params.get("api")
    store = _open_session_toggle_store(api) if api is not None else None
    if store is None:
        _in_process_set_disabled(session_key, disabled)
        return
    try:
        if disabled:
            entry: ActiveMemoryToggleEntry = {  # type: ignore[typeddict-item]
                "sessionKey": session_key,
                "disabled": True,
                "updatedAt": _now_ms(),
            }
            await _register_toggle(
                store,
                _active_memory_toggle_key(session_key),
                entry,
            )
        else:
            await _delete_toggle(store, _active_memory_toggle_key(session_key))
        _in_process_set_disabled(session_key, disabled)
    except Exception as exc:
        _log.debug("set_session_active_memory_disabled: write failed: %s", exc)


# In-process fallback for when the host hasn't wired a
# keyed store yet (Phase 4.2a — keyed store is opt-in).
_in_process_toggle: dict[str, bool] = {}


def _in_process_is_disabled(session_key: str) -> bool:
    return _in_process_toggle.get(session_key, False)


def _in_process_set_disabled(session_key: str, disabled: bool) -> None:
    if disabled:
        _in_process_toggle[session_key] = True
    else:
        _in_process_toggle.pop(session_key, None)


def _reset_in_process_toggles_for_tests() -> None:
    _in_process_toggle.clear()


# Async store helpers — the host's keyed store exposes
# ``lookup`` / ``register`` / ``delete`` as coroutines; we
# bridge with ``asyncio.run`` for the in-process case and
# pass through for the host's surface.
import asyncio  # noqa: E402


async def _lookup_toggle(store: Any, key: str) -> dict[str, Any] | None:
    lookup = getattr(store, "lookup", None)
    if lookup is None:
        return None
    result = lookup(key)
    if asyncio.iscoroutine(result):
        result = await result
    if isinstance(result, dict):
        return result
    return None


async def _register_toggle(store: Any, key: str, entry: Any) -> None:
    register = getattr(store, "register", None)
    if register is None:
        return
    result = register(key, entry)
    if asyncio.iscoroutine(result):
        await result


async def _delete_toggle(store: Any, key: str) -> None:
    delete = getattr(store, "delete", None)
    if delete is None:
        return
    result = delete(key)
    if asyncio.iscoroutine(result):
        await result


# ── Plugin enable/disable ──────────────────────────────────────────


def is_active_memory_globally_enabled(cfg: Any) -> bool:
    """Return True if ``active-memory`` is enabled at the plugin level.

    Mirrors OpenClaw's ``isActiveMemoryGloballyEnabled``.
    Checks both the legacy ``plugins.entries.active-memory.enabled``
    and the new ``plugins.entries.active-memory.config.enabled``
    (the latter wins).
    """
    if not isinstance(cfg, dict):
        return True
    entries = (
        cfg.get("plugins", {}).get("entries", {}) if isinstance(cfg.get("plugins"), dict) else {}
    )
    if not isinstance(entries, dict):
        return True
    entry = entries.get("active-memory")
    if isinstance(entry, dict) and entry.get("enabled") is False:
        return False
    plugin_config = resolve_plugin_config_object(cfg, "active-memory")
    return not (plugin_config and plugin_config.get("enabled") is False)


def is_active_memory_plugin_enabled(cfg: Any) -> bool:
    """Return True if ``active-memory`` is in the plugin allow/deny set.

    Mirrors OpenClaw's ``isActiveMemoryPluginEnabled``.
    Honors ``plugins.enabled``, ``plugins.deny``, and
    ``plugins.allow`` (the latter only when non-empty).
    """
    if not isinstance(cfg, dict):
        return True
    plugins = cfg.get("plugins")
    if not isinstance(plugins, dict):
        return True
    normalized = normalize_plugins_config(plugins)
    if not normalized.enabled:
        return False
    if "active-memory" in normalized.deny:
        return False
    if normalized.allow and "active-memory" not in normalized.allow:
        return False
    return normalized.entries.get("active-memory", {}).get("enabled") is not False


def is_enabled_for_agent(
    config: ResolvedActiveRecallPluginConfig,
    agent_id: str | None,
) -> bool:
    """Return True if ``config`` is enabled for ``agent_id``.

    Mirrors OpenClaw's ``isEnabledForAgent``. When the
    operator pinned ``config.agents`` to a specific list,
    only those agents are eligible. An empty list means
    "all agents".
    """
    if not config.get("enabled", True):
        return False
    if not agent_id:
        return False
    agents = config.get("agents") or ()
    if not agents:
        return True
    return agent_id in agents


# ── Remember across conversations ──────────────────────────────────


def has_remember_across_conversations_agent(cfg: Any) -> bool:
    """Return True if any agent in ``cfg`` has the flag set.

    Mirrors OpenClaw's ``hasRememberAcrossConversationsAgent``.
    """
    if not isinstance(cfg, dict):
        return False
    agents = cfg.get("agents")
    if not isinstance(agents, dict):
        return False
    listing = agents.get("list")
    if not isinstance(listing, list) or not listing:
        agent_ids = ["main"]
    else:
        agent_ids = [
            entry["id"]
            for entry in listing
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        ]
        if not agent_ids:
            agent_ids = ["main"]
    return any(resolve_remember_across_conversations(cfg, agent_id) for agent_id in agent_ids)


def should_remember_across_conversations(cfg: Any, agent_id: str) -> bool:
    """Per-agent ``Remember across conversations`` check.

    Mirrors OpenClaw's ``shouldRememberAcrossConversations``.
    Reads the per-agent flag the host tracks.
    """
    return resolve_remember_across_conversations(cfg, agent_id)


# ── Config mutation ────────────────────────────────────────────────


def update_active_memory_global_enabled_in_config(
    cfg: Any,
    enabled: bool,
) -> dict[str, Any]:
    """Return a new config dict with the global flag flipped.

    Mirrors OpenClaw's ``updateActiveMemoryGlobalEnabledInConfig``.
    Mutates the ``plugins.entries["active-memory"]`` slot;
    the ``config.enabled`` sub-flag drives the per-plugin
    toggle. Other plugin entries are preserved.
    """
    cfg_dict: dict[str, Any] = cfg if isinstance(cfg, dict) else {}
    plugins_obj: Any = cfg_dict.get("plugins")
    plugins: dict[str, Any] = plugins_obj if isinstance(plugins_obj, dict) else {}
    entries_obj: Any = plugins.get("entries")
    entries_raw: Any = entries_obj if isinstance(entries_obj, dict) else {}
    entries: dict[str, Any] = dict(entries_raw)  # type: ignore[arg-type]
    existing = entries.get("active-memory")
    if not isinstance(existing, dict):
        existing = {}
    existing_config_obj: Any = existing.get("config")
    existing_config: dict[str, Any] = (
        existing_config_obj if isinstance(existing_config_obj, dict) else {}
    )
    new_entry: dict[str, Any] = dict(existing)
    new_entry["enabled"] = True
    new_entry["config"] = {**existing_config, "enabled": bool(enabled)}
    entries["active-memory"] = new_entry

    new_plugins: dict[str, Any] = dict(plugins)
    new_plugins["entries"] = entries
    return {**cfg_dict, "plugins": new_plugins}


# ── Admin gating ───────────────────────────────────────────────────


def lacks_admin_to_mutate_active_memory_global(params: dict[str, Any]) -> bool:
    """Return True if the caller cannot mutate the global flag.

    Mirrors OpenClaw's ``lacksAdminToMutateActiveMemoryGlobal``.
    When the host provides ``gatewayClientScopes``, the
    caller must hold ``operator.admin``. Otherwise the
    caller must be the operator (``senderIsOwner``).
    """
    scopes = params.get("gatewayClientScopes")
    if isinstance(scopes, list | tuple):
        return "operator.admin" not in scopes
    return params.get("senderIsOwner") is not True


ACTIVE_MEMORY_GLOBAL_MUTATION_ADMIN_REQUIRED_TEXT_VALUE: str = (
    "⚠️ /active-memory global enable/disable changes require owner or operator.admin."
)
# Re-export the constant under OpenClaw's exact name for parity.
ACTIVE_MEMORY_GLOBAL_MUTATION_ADMIN_REQUIRED_TEXT = (
    ACTIVE_MEMORY_GLOBAL_MUTATION_ADMIN_REQUIRED_TEXT_VALUE
)


# ── Command session key resolution ────────────────────────────────


def resolve_command_session_key(params: dict[str, Any]) -> str | None:
    """Resolve the session key for the ``/active-memory`` command.

    Mirrors OpenClaw's ``resolveCommandSessionKey``. Uses the
    explicit ``sessionKey`` if present; otherwise walks
    ``config.agents`` (or the default agent) to find a
    canonical session key for the given ``sessionId``.
    """
    explicit = params.get("sessionKey")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    api = params.get("api")
    config = params.get("config") or {}
    session_id = params.get("sessionId")
    if api is None or not isinstance(session_id, str):
        return None
    configured_agents = config.get("agents") if isinstance(config, dict) else []
    if not isinstance(configured_agents, list) or not configured_agents:
        configured_agents = [DEFAULT_AGENT_ID]
    for agent_id in configured_agents:
        if not isinstance(agent_id, str):
            continue
        resolved = _resolve_canonical_session_key(api, agent_id, session_id)
        if resolved:
            return resolved
    return None


def _resolve_canonical_session_key(
    api: Any,
    agent_id: str,
    session_id: str | None,
) -> str | None:
    """Bridge to ``session.ts::resolveCanonicalSessionKeyFromSessionId``.

    Phase 4.2a: the host doesn't yet implement this; the
    fallback is the session-id-as-key shape. Phase 4.2b
    (with ``session.ts``) will replace this stub.
    """
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    return f"agent:{agent_id}:{session_id.strip()}"


# ── Help text ──────────────────────────────────────────────────────


def format_active_memory_command_help() -> str:
    """Format the ``/active-memory help`` reply.

    Mirrors OpenClaw's ``formatActiveMemoryCommandHelp``.
    """
    return (
        "Active Memory session toggle:\n"
        "/active-memory status\n"
        "/active-memory on\n"
        "/active-memory off\n"
        "\n"
        "Global config toggle:\n"
        "/active-memory status --global\n"
        "/active-memory on --global\n"
        "/active-memory off --global"
    )


# ── Harness-skip ───────────────────────────────────────────────────


def _is_agent_harness_session_key(session_key: str) -> bool:
    """True if the session key is harness-shaped (test/CI).

    Mirrors OpenClaw's ``isAgentHarnessSessionKey``. The
    OpenClaw convention is ``agent:<agentId>:harness:...``;
    the unprefixed form is also accepted.
    """
    normalized = session_key.strip().lower()
    parsed = parse_agent_session_key(normalized)
    rest = parsed["rest"] if parsed else normalized
    return rest.startswith("harness:")


def should_skip_active_memory_for_harness_session(params: dict[str, Any]) -> bool:
    """Return True if active-memory should be skipped for this session.

    Mirrors OpenClaw's ``shouldSkipActiveMemoryForHarnessSession``.
    Returns ``True`` when the session key is harness-shaped
    OR the per-agent session row has ``modelSelectionLocked``,
    OR the host can't read the session row at all. The
    last case is conservative: recall is optional, and
    crossing a harness/model boundary with an independently
    selected model is unsafe.
    """
    session_key = params.get("sessionKey")
    if not isinstance(session_key, str) or not session_key.strip():
        return False
    api = params.get("api")
    if api is None:
        return True
    runtime = getattr(api, "runtime", None)
    agent_runtime = getattr(runtime, "agent", None) if runtime is not None else None
    session_api = getattr(agent_runtime, "session", None) if agent_runtime is not None else None
    get_entry = getattr(session_api, "get_session_entry", None) if session_api is not None else None
    if not callable(get_entry):
        # Can't read the session row — skip.
        return True
    try:
        entry = get_entry(
            {
                **({"agentId": params["agentId"]} if params.get("agentId") else {}),
                "sessionKey": session_key,
                "readConsistency": "latest",
            }
        )
    except Exception:
        return True
    if entry is None:
        # Missing session key — fall back to the harness-shape check.
        return _is_agent_harness_session_key(session_key)
    return bool(getattr(entry, "get", lambda *_: None)("modelSelectionLocked")) is True


# ── Eligibility + chat type ────────────────────────────────────────


def is_eligible_interactive_session(ctx: dict[str, Any]) -> bool:
    """Return True if the session is eligible for active-memory.

    Mirrors OpenClaw's ``isEligibleInteractiveSession``. Checks:
    - ``ctx["trigger"] == "user"`` (skip scheduled / harness)
    - session key is not a ``dreaming-narrative-...`` key
    - either ``sessionKey`` or ``sessionId`` is present
    - webchat provider OR a non-empty channel id
    """
    if ctx.get("trigger") != "user":
        return False
    session_key = (ctx.get("sessionKey") or "") if isinstance(ctx.get("sessionKey"), str) else ""
    # Block dreaming-narrative session keys. OpenClaw uses two
    # canonical forms: bare ``dreaming-narrative-...`` or
    # ``agent:<agentId>:dreaming-narrative-...``. We only block
    # when the trailing segment matches the phased
    # ``-light/-rem/-deep`` suffix so unrelated session keys
    # that happen to contain the substring are not blocked.
    if _is_dreaming_narrative_key(session_key):
        return False
    if not ctx.get("sessionKey") and not ctx.get("sessionId"):
        return False
    provider = (ctx.get("messageProvider") or "").strip().lower()
    if provider == "webchat":
        return True
    channel_id = (ctx.get("channelId") or "").strip()
    return bool(channel_id)


def _is_dreaming_narrative_key(session_key: str) -> bool:
    """Return True if the session key is a dreaming-narrative key.

    Mirrors OpenClaw's regex (light/REM/deep phases).
    """
    lowered = session_key.lower()
    return bool(
        re.match(r"^dreaming-narrative-(light|rem|deep)-", lowered)
        or re.match(r"^agent:[^:]+:dreaming-narrative-(light|rem|deep)-", lowered)
    )


def resolve_chat_type(ctx: dict[str, Any]) -> ActiveMemoryChatType | None:
    """Resolve the chat type from a session context.

    Mirrors OpenClaw's ``resolveChatType``. Walks the
    session key for known markers (``direct``, ``group``,
    ``channel``, ``explicit``) and falls back to the
    provider when no marker is present. Returns ``None``
    when the type is ambiguous.
    """
    raw_session_key = ctx.get("sessionKey")
    if not isinstance(raw_session_key, str):
        return None
    parsed_suffix = parse_thread_session_suffix(raw_session_key)
    base_session_key = (parsed_suffix.get("baseSessionKey") or raw_session_key).strip().lower()
    if base_session_key:
        if base_session_key.startswith("agent:") and base_session_key.split(":")[2:3] == [
            "explicit"
        ]:
            return "explicit"
        if ":group:" in base_session_key:
            return "group"
        if ":channel:" in base_session_key:
            return "channel"
        if ":direct:" in base_session_key or ":dm:" in base_session_key:
            return "direct"
        main_key = (ctx.get("mainKey") or "").strip().lower() or "main"
        parts = base_session_key.split(":")
        if len(parts) == 3 and parts[0] == "agent" and (parts[2] == main_key or parts[2] == "main"):
            provider = (ctx.get("messageProvider") or "").strip().lower()
            channel_id = (ctx.get("channelId") or "").strip()
            if provider and provider != "webchat" and channel_id:
                return "direct"
    provider = (ctx.get("messageProvider") or "").strip().lower()
    if provider == "webchat":
        return "direct"
    return None


def is_allowed_chat_type(
    config: ResolvedActiveRecallPluginConfig,
    ctx: dict[str, Any],
) -> bool:
    """Return True if the chat type is in the operator's allow list.

    Mirrors OpenClaw's ``isAllowedChatType``. When the
    operator pins ``allowedChatTypes`` to specific values,
    only those chat types are eligible. An empty list
    means "no chat types allowed".
    """
    chat_type = resolve_chat_type(ctx)
    if chat_type is None:
        return False
    allowed = config.get("allowedChatTypes") or []
    return chat_type in allowed


def is_private_recall_destination(ctx: dict[str, Any]) -> bool:
    """Return True if the destination is private (direct/explicit).

    Mirrors OpenClaw's ``isPrivateRecallDestination``.
    """
    chat_type = resolve_chat_type(ctx)
    return chat_type in ("direct", "explicit")


def _resolve_conversation_id(ctx: dict[str, Any]) -> str | None:
    """Best-effort extraction of the peer id from a session key.

    Mirrors OpenClaw's ``resolveConversationId``. Supports
    the five canonical shapes:
    - agent:<agentId>:direct:<peerId>
    - agent:<agentId>:<channel>:direct:<peerId>
    - agent:<agentId>:<channel>:<accountId>:direct:<peerId>
    - agent:<agentId>:<channel>:group:<peerId>
    - agent:<agentId>:<channel>:channel:<peerId>

    Returns ``None`` for sessions that don't embed a peer id
    (e.g. dmScope=main ``agent:<agentId>:<mainKey>`` sessions).
    """
    raw = ctx.get("sessionKey")
    if not isinstance(raw, str) or not raw.strip():
        return None
    base = parse_thread_session_suffix(raw).get("baseSessionKey") or raw
    base = base.strip()
    if not base:
        return None
    parsed = parse_agent_session_key(base)
    if parsed is None:
        return None
    rest_parts = [p for p in parsed["rest"].split(":") if p]
    if len(rest_parts) < 2:
        return None
    for index in range(len(rest_parts) - 1):
        token = rest_parts[index]
        if token in ("direct", "dm", "group", "channel"):
            tail = ":".join(rest_parts[index + 1 :]).strip()
            return tail or None
    return None


def is_allowed_chat_id(
    config: ResolvedActiveRecallPluginConfig,
    ctx: dict[str, Any],
) -> bool:
    """Apply allowedChatIds + deniedChatIds filters.

    Mirrors OpenClaw's ``isAllowedChatId``. When both lists
    are empty, returns ``True``. When ``allowedChatIds`` is
    non-empty but the session has no peer id (e.g. webchat
    default session), the session is skipped.
    """
    has_allow = bool(config.get("allowedChatIds"))
    has_deny = bool(config.get("deniedChatIds"))
    if not has_allow and not has_deny:
        return True
    raw_channel_id = ctx.get("channelId")
    channel_id = (
        raw_channel_id.strip().lower()
        if isinstance(raw_channel_id, str) and raw_channel_id.strip()
        else None
    )
    conversation_id = _resolve_conversation_id(ctx) or channel_id
    if has_allow:
        if not conversation_id:
            return False
        if conversation_id not in (config.get("allowedChatIds") or ()):
            return False
    return not (has_deny and conversation_id and conversation_id in (config.get("deniedChatIds") or ()))


# ── Misc helpers ───────────────────────────────────────────────────


def _now_ms() -> int:
    return _now_ms_value()


def _now_ms_value() -> int:
    return int(time.time() * 1000)


__all__ = [
    "ACTIVE_MEMORY_GLOBAL_MUTATION_ADMIN_REQUIRED_TEXT",
    "format_active_memory_command_help",
    "has_remember_across_conversations_agent",
    "is_active_memory_globally_enabled",
    "is_active_memory_plugin_enabled",
    "is_allowed_chat_id",
    "is_allowed_chat_type",
    "is_eligible_interactive_session",
    "is_enabled_for_agent",
    "is_private_recall_destination",
    "is_session_active_memory_disabled",
    "lacks_admin_to_mutate_active_memory_global",
    "resolve_chat_type",
    "resolve_command_session_key",
    "set_session_active_memory_disabled",
    "should_remember_across_conversations",
    "should_skip_active_memory_for_harness_session",
    "update_active_memory_global_enabled_in_config",
]
