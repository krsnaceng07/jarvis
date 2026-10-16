"""jarvis.config.group_scope_tree — canonical group policy scope tree resolver.

OpenClaw parity: mirrors
``openclaw-main/src/config/group-scope-tree.ts``.

Focused minimal port: scope tree + override resolution. The deeper
``resolveChannelGroups`` and ``resolveToolsBySender`` helpers are
delegated to caller-provided callables.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, TypedDict


MarkdownTableMode = str
GroupToolPolicyConfig = dict
GroupToolPolicyBySenderConfig = dict


class ScopeNode(TypedDict, total=False):
    requireMention: bool
    tools: GroupToolPolicyConfig
    toolsBySender: GroupToolPolicyBySenderConfig
    introHint: str


class ScopeTree(TypedDict, total=False):
    defaults: ScopeNode
    scopes: dict  # str -> ScopeNode


ScopePath = List[str]


def encode_scope_segment(value: str) -> str:
    return f"{len(value)}:{value}"


def scope_key(*segments) -> str:
    return "/".join(f"{prefix}:{encode_scope_segment(value)}" for prefix, value in segments)


def build_channel_groups_scope_tree(
    cfg: Any,
    channel: str,
    account_id: Optional[str] = None,
    *,
    resolve_channel_groups: Optional[Callable[[Any, str, Optional[str]], Optional[dict]]] = None,
) -> ScopeTree:
    """Build a flat-key scope tree from ``groups`` config.

    Mirrors :func:`buildChannelGroupsScopeTree`
    (``shared/config/group-scope-tree.ts``).
    """
    if not callable(resolve_channel_groups):
        return {"scopes": {}}
    groups = resolve_channel_groups(cfg, channel, account_id) or {}
    # The wildcard config is the fallback node, not a matchable exact scope.
    defaults = groups.get("*") if isinstance(groups, dict) else None
    scopes = {k: v for k, v in (groups or {}).items() if k != "*"}
    out: ScopeTree = {"scopes": scopes}
    if defaults is not None:
        out["defaults"] = defaults
    return out


def resolve_scope_key_case_insensitive(
    tree: ScopeTree, key: Optional[str]
) -> Optional[str]:
    """Return the canonical scope key (case-insensitive) or ``None``."""
    if not key:
        return None
    scopes = tree.get("scopes") or {}
    if key in scopes:
        return key
    target = key.strip().lower()
    for candidate in scopes.keys():
        if isinstance(candidate, str) and candidate.lower() == target:
            return candidate
    return None


def _resolve_from_scopes(tree, path, resolve_node):
    for key in reversed(path or []):
        if key is None:
            continue
        scopes = tree.get("scopes") or {}
        if key not in scopes:
            continue
        node = scopes.get(key)
        if not node:
            continue
        value = resolve_node(node)
        if value is not None:
            return value
    defaults = tree.get("defaults")
    if defaults:
        return resolve_node(defaults)
    return None


def resolve_scope_require_mention(params: dict) -> bool:
    """Resolve requireMention using config precedence + optional runtime override.

    Mirrors :func:`resolveScopeRequireMention`
    (``shared/config/group-scope-tree.ts``).
    """
    tree = params.get("tree") or {}
    path = params.get("path") or []
    override = params.get("requireMentionOverride")
    override_order = params.get("overrideOrder") or "after-config"
    configured = _resolve_from_scopes(
        tree, path, lambda node: node.get("requireMention") if isinstance(node, dict) else None
    )
    if override_order == "before-config" and isinstance(override, bool):
        return override
    if isinstance(configured, bool):
        return configured
    if override_order != "before-config" and isinstance(override, bool):
        return override
    if params.get("configuredScopeDefaultsToNoMention") and any(
        isinstance(k, str) and k in (tree.get("scopes") or {}) for k in path
    ):
        return False
    return True


def resolve_scope_tools_policy(params: dict):
    """Resolve the per-scope tool policy (delegates sender merge to caller).

    Mirrors :func:`resolveScopeToolsPolicy`
    (``shared/config/group-scope-tree.ts``).
    """
    tree = params.get("tree") or {}
    path = params.get("path") or []
    sender_id = params.get("senderId")
    sender_name = params.get("senderName")
    sender_username = params.get("senderUsername")
    sender_e164 = params.get("senderE164")
    message_provider = params.get("messageProvider")
    resolve_tools_by_sender = params.get("resolveToolsBySender")

    def _resolve(node):
        if not isinstance(node, dict):
            return None
        if callable(resolve_tools_by_sender):
            merged = resolve_tools_by_sender({
                "toolsBySender": node.get("toolsBySender"),
                "senderId": sender_id,
                "senderName": sender_name,
                "senderUsername": sender_username,
                "senderE164": sender_e164,
                "messageProvider": message_provider,
            })
            if merged is not None:
                return merged
        return node.get("tools")

    return _resolve_from_scopes(tree, path, _resolve)


def resolve_scope_intro_hint(params: dict):
    """Resolve the per-scope intro hint.

    Mirrors :func:`resolveScopeIntroHint`
    (``shared/config/group-scope-tree.ts``).
    """
    tree = params.get("tree") or {}
    path = params.get("path") or []
    return _resolve_from_scopes(
        tree, path, lambda node: node.get("introHint") if isinstance(node, dict) else None
    )


__all__ = [
    "ScopeNode",
    "ScopeTree",
    "ScopePath",
    "encode_scope_segment",
    "scope_key",
    "build_channel_groups_scope_tree",
    "resolve_scope_key_case_insensitive",
    "resolve_scope_require_mention",
    "resolve_scope_tools_policy",
    "resolve_scope_intro_hint",
]
