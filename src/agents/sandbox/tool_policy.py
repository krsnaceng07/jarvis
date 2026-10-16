"""jarvis.agents.sandbox.tool_policy — Sandbox tool policy and group expansion.

Mirrors OpenClaw's ``src/agents/agent-tools.policy.ts`` and
``docs/gateway/sandbox-vs-tool-policy-vs-elevated.md``:
- Expands group:* shorthands (group:runtime, group:fs, group:web, etc.).
- Evaluates tools.sandbox.tools allow/deny lists.
- Enforces the hard security rule: deny ALWAYS wins.
"""

from __future__ import annotations

from typing import Any

# Canonical OpenClaw tool group mappings
TOOL_GROUPS: dict[str, set[str]] = {
    "group:runtime": {"exec", "process", "code_execution", "bash"},
    "group:fs": {"read", "write", "edit", "apply_patch", "ls", "find", "grep"},
    "group:sessions": {
        "sessions",
        "sessions_list",
        "sessions_history",
        "sessions_search",
        "conversations_list",
        "conversations_send",
        "conversations_turn",
        "sessions_send",
        "sessions_spawn",
        "sessions_yield",
        "subagents",
        "session_status",
        "suggest_task",
        "dismiss_task",
    },
    "group:memory": {
        "memory_search",
        "memory_get",
        "memory_store",
        "memory_recall",
        "memory_forget",
    },
    "group:web": {"web_search", "x_search", "web_fetch"},
    "group:ui": {"browser", "screen", "terminal", "canvas", "progress_card", "show_widget"},
    "group:automation": {"heartbeat_respond", "cron", "gateway"},
    "group:messaging": {"message", "send_message"},
    "group:nodes": {"nodes", "computer"},
    "group:agents": {
        "agents_list",
        "get_goal",
        "create_goal",
        "update_goal",
        "progress_card",
        "ask_user",
        "skill_workshop",
    },
    "group:media": {"image", "image_generate", "music_generate", "video_generate", "tts"},
}


def expand_tool_policy_items(items: list[str] | set[str] | None) -> set[str]:
    """Expand tool names and group:* entries into a flat set of tool names."""
    if not items:
        return set()

    expanded: set[str] = set()
    for item in items:
        raw = str(item).strip()
        if not raw:
            continue
        if raw in TOOL_GROUPS:
            expanded.update(TOOL_GROUPS[raw])
        else:
            expanded.add(raw)
    return expanded


def evaluate_sandbox_tool_policy(
    tool_name: str,
    policy: dict[str, Any] | None = None,
    *,
    is_sandboxed: bool = True,
) -> tuple[bool, str | None]:
    """Evaluate whether tool_name is permitted in the current sandbox context.

    Parameters
    ----------
    tool_name:
        Name of the requested tool (e.g. "exec", "read", "browser").
    policy:
        Optional sandbox tool policy dictionary containing "allow" and/or "deny".
        (Usually extracted from ``tools.sandbox.tools``).
    is_sandboxed:
        Whether the current session/turn is operating inside a sandbox.

    Returns
    -------
    tuple[bool, str | None]
        (is_allowed, denial_reason)
    """
    if not is_sandboxed:
        return True, None

    if not policy or not isinstance(policy, dict):
        # By default in sandbox, all standard tools are permitted unless restricted
        return True, None

    raw_allow = policy.get("allow")
    raw_deny = policy.get("deny")

    denied_set = expand_tool_policy_items(
        raw_deny if isinstance(raw_deny, (list, set, tuple)) else None
    )
    allowed_set = expand_tool_policy_items(
        raw_allow if isinstance(raw_allow, (list, set, tuple)) else None
    )

    # 1. Deny always wins
    if tool_name in denied_set:
        return False, f"Tool '{tool_name}' is blocked by sandbox tool policy (deny list)."

    # 2. If allow list is non-empty, everything else is blocked
    if allowed_set and tool_name not in allowed_set:
        return False, f"Tool '{tool_name}' is not in the sandbox tool policy allow list."

    return True, None
