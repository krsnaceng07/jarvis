"""jarvis.auto_reply.reply.reply_elevated - Resolves elevated command permissions based on global, agent, and allowlist policies.

OpenClaw parity: mirrors
``openclaw-main/src/auto-reply/reply/reply-elevated.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jarvis.agents.agent_scope import resolve_agent_config
from jarvis.auto_reply.sender_identity import should_use_from_as_sender_fallback
from jarvis.channels.inbound_context import MsgContext

from .elevated_allowlist_matcher import (
    AllowFromFormatter,
    add_formatted_tokens,
    build_mutable_tokens,
    matches_formatted_tokens,
    matches_mutable_tokens,
    parse_explicit_elevated_allow_entry,
    strip_sender_prefix,
)


@dataclass
class ElevatedPermissionsDecision:
    enabled: bool
    allowed: bool
    failures: list[dict[str, str]]


def resolve_elevated_allowlist(
    allow_from: dict[str, Any] | None,
    provider: str,
    fallback_allow_from: list[str | int] | None = None,
) -> list[str | int] | None:
    """Resolves provider-specific elevated allowlist entries with fallback defaults."""
    if not allow_from:
        return fallback_allow_from
    value = allow_from.get(provider)
    if isinstance(value, list):
        return value
    return fallback_allow_from


def resolve_allow_from_formatter(cfg: Any, provider: str, account_id: str | None = None) -> AllowFromFormatter:
    """Resolves the channel formatter used before matching allowFrom entries.
    For now, defaults to string normalization since channel plugin config is not fully implemented in Jarvis.
    """
    def default_formatter(values: list[str]) -> list[str]:
        return [str(v).strip() for v in values if v]
        
    return default_formatter


def is_approved_elevated_sender(
    provider: str,
    ctx: MsgContext,
    format_allow_from: AllowFromFormatter,
    allow_from: dict[str, Any] | None = None,
    fallback_allow_from: list[str | int] | None = None,
) -> bool:
    """Checks whether the inbound sender matches configured elevated allowFrom gates."""
    raw_allow = resolve_elevated_allowlist(allow_from, provider, fallback_allow_from)
    if not raw_allow or len(raw_allow) == 0:
        return False

    allow_tokens = [str(entry).strip() for entry in raw_allow if entry]
    if len(allow_tokens) == 0:
        return False

    if "*" in allow_tokens:
        return True

    sender_id_tokens: set[str] = set()
    sender_from_tokens: set[str] = set()
    sender_e164_tokens: set[str] = set()

    sender_id = (ctx.get("SenderId") or "").strip()
    sender_from = (ctx.get("From") or "").strip()
    sender_e164 = (ctx.get("SenderE164") or "").strip()
    chat_type = ctx.get("ChatType")

    if sender_id:
        stripped = strip_sender_prefix(sender_id)
        values = [sender_id, stripped] if stripped else [sender_id]
        add_formatted_tokens(
            format_allow_from=format_allow_from,
            values=[v for v in values if v],
            tokens=sender_id_tokens,
        )

    if sender_from and should_use_from_as_sender_fallback(sender_from, chat_type):
        stripped = strip_sender_prefix(sender_from)
        values = [sender_from, stripped] if stripped else [sender_from]
        add_formatted_tokens(
            format_allow_from=format_allow_from,
            values=[v for v in values if v],
            tokens=sender_from_tokens,
        )

    if sender_e164:
        add_formatted_tokens(
            format_allow_from=format_allow_from,
            values=[sender_e164],
            tokens=sender_e164_tokens,
        )

    sender_identity_tokens: set[str] = sender_id_tokens | sender_from_tokens | sender_e164_tokens

    # Identity fields use channel formatting; mutable labels use normalized text matching.
    sender_name_tokens = build_mutable_tokens(ctx.get("SenderName"))
    sender_username_tokens = build_mutable_tokens(ctx.get("SenderUsername"))
    sender_tag_tokens = build_mutable_tokens(ctx.get("SenderTag"))

    for entry in allow_tokens:
        explicit_entry = parse_explicit_elevated_allow_entry(entry)
        if not explicit_entry:
            if matches_formatted_tokens(
                format_allow_from=format_allow_from,
                value=entry,
                tokens=sender_identity_tokens,
                include_stripped=True,
            ):
                return True
            continue

        field = explicit_entry["field"]
        value = explicit_entry["value"]
        
        if field == "id" and matches_formatted_tokens(
            format_allow_from=format_allow_from,
            value=value,
            tokens=sender_id_tokens,
            include_stripped=True,
        ):
            return True
        elif field == "from" and matches_formatted_tokens(
            format_allow_from=format_allow_from,
            value=value,
            tokens=sender_from_tokens,
            include_stripped=True,
        ):
            return True
        elif field == "e164" and matches_formatted_tokens(
            format_allow_from=format_allow_from,
            value=value,
            tokens=sender_e164_tokens,
            include_stripped=False,
        ):
            return True
        elif field == "name" and matches_mutable_tokens(value, sender_name_tokens):
            return True
        elif field == "username" and matches_mutable_tokens(value, sender_username_tokens):
            return True
        elif field == "tag" and matches_mutable_tokens(value, sender_tag_tokens):
            return True

    return False


def resolve_elevated_permissions(
    cfg: Any,
    agent_id: str,
    provider: str,
    ctx: MsgContext,
) -> ElevatedPermissionsDecision:
    """Resolves whether elevated tools are enabled and allowed for the inbound sender."""
    global_config = getattr(cfg.tools, "elevated", None) if hasattr(cfg, "tools") else None
    agent_cfg = resolve_agent_config(cfg, agent_id)
    agent_config = getattr(agent_cfg.tools, "elevated", None) if agent_cfg and hasattr(agent_cfg, "tools") else None

    # In Jarvis, missing enabled implies True per OpenClaw default
    global_enabled = getattr(global_config, "enabled", True) if global_config else True
    agent_enabled = getattr(agent_config, "enabled", True) if agent_config else True
    
    enabled = global_enabled and agent_enabled
    failures: list[dict[str, str]] = []
    
    if not global_enabled:
        failures.append({"gate": "enabled", "key": "tools.elevated.enabled"})
    if not agent_enabled:
        failures.append({"gate": "enabled", "key": "agents.list[].tools.elevated.enabled"})
        
    if not enabled:
        return ElevatedPermissionsDecision(enabled=enabled, allowed=False, failures=failures)
        
    if not provider:
        failures.append({"gate": "provider", "key": "ctx.Provider"})
        return ElevatedPermissionsDecision(enabled=enabled, allowed=False, failures=failures)

    fallback_allow_from = None # Fallback allow from provider plugins not fully ported to Jarvis yet
    
    format_allow_from = resolve_allow_from_formatter(
        cfg=cfg,
        provider=provider,
        account_id=ctx.get("AccountId"),
    )
    
    global_allow_from = getattr(global_config, "allowFrom", None) if global_config else None
    global_allowed = is_approved_elevated_sender(
        provider=provider,
        ctx=ctx,
        format_allow_from=format_allow_from,
        allow_from=global_allow_from,
        fallback_allow_from=fallback_allow_from,
    )
    
    if not global_allowed:
        failures.append({
            "gate": "allowFrom",
            "key": f"tools.elevated.allowFrom.{provider}",
        })
        return ElevatedPermissionsDecision(enabled=enabled, allowed=False, failures=failures)

    agent_allow_from = getattr(agent_config, "allowFrom", None) if agent_config else None
    if agent_allow_from:
        agent_allowed = is_approved_elevated_sender(
            provider=provider,
            ctx=ctx,
            format_allow_from=format_allow_from,
            allow_from=agent_allow_from,
            fallback_allow_from=fallback_allow_from,
        )
    else:
        agent_allowed = True
        
    if not agent_allowed:
        failures.append({
            "gate": "allowFrom",
            "key": f"agents.list[].tools.elevated.allowFrom.{provider}",
        })

    return ElevatedPermissionsDecision(
        enabled=enabled,
        allowed=global_allowed and agent_allowed,
        failures=failures,
    )
