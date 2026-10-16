"""Codex conversation-binding lifecycle hooks.

OpenClaw parity: mirrors `extensions/codex/src/conversation-binding-hooks.ts`.

Handles two events fired by the JARVIS runtime when a conversation's
channel binding is being established or has resolved:

- `inbound_claim` — fired before a session starts; the hook inspects the
  inbound binding context, looks up any existing Codex thread binding stored
  for this session, and decides whether to attach a native thread.
- `conversation_binding_resolved` — fired after the channel has fully
  resolved the conversation binding; the hook persists the resolved binding
  identity back into the keyed state store so future turns can find it.
"""

from __future__ import annotations

from typing import Any, Callable


# ---------------------------------------------------------------------------
# inbound_claim handler
# ---------------------------------------------------------------------------


def handle_codex_conversation_inbound_claim(
    event: dict[str, Any],
    ctx: dict[str, Any],
    *,
    binding_store: Any,
    plugin_config: Any,
    config: Any,
    resume_codex_cli_session_on_node: Callable[[dict[str, Any]], Any] | None = None,
) -> None:
    """Handle the `inbound_claim` event for the Codex plugin.

    OpenClaw parity: mirrors `handleCodexConversationInboundClaim`
    (`conversation-binding-hooks.ts`).

    The hook resolves the best-match Codex thread binding for the inbound
    session and attaches it to the claim context so the harness can resume
    the native Codex thread rather than starting a new one.  When no stored
    binding is found the claim proceeds with a fresh thread (the default).
    """
    session_id: str | None = _read_str(event, "sessionId") or _read_str(ctx, "sessionId")
    if not session_id:
        return

    # Look up stored binding for this session.
    stored = None
    if hasattr(binding_store, "read_binding"):
        try:
            stored = binding_store.read_binding(session_id)
        except Exception:
            stored = None
    elif isinstance(binding_store, dict):
        stored = binding_store.get(session_id)

    if not stored or not isinstance(stored, dict):
        return

    thread_id: str | None = stored.get("threadId")
    if not thread_id:
        return

    # Attach the known thread to the claim context so the harness reuses it.
    claim = event.get("claim") or ctx.get("claim")
    if isinstance(claim, dict):
        claim.setdefault("threadId", thread_id)
    elif hasattr(claim, "thread_id") and not getattr(claim, "thread_id", None):
        try:
            object.__setattr__(claim, "thread_id", thread_id)
        except (AttributeError, TypeError):
            pass


# ---------------------------------------------------------------------------
# conversation_binding_resolved handler
# ---------------------------------------------------------------------------


def handle_codex_conversation_binding_resolved(
    event: dict[str, Any],
    *,
    binding_store: Any,
) -> None:
    """Handle the `conversation_binding_resolved` event for the Codex plugin.

    OpenClaw parity: mirrors `handleCodexConversationBindingResolved`
    (`conversation-binding-hooks.ts`).

    Persists the resolved binding identity (session id + thread id) back into
    the binding store so future turns and `session_end` retirement can find
    the canonical thread reference without re-resolving from scratch.
    """
    session_id: str | None = _read_str(event, "sessionId")
    thread_id: str | None = _read_str(event, "threadId") or _read_str(event, "nativeThreadId")
    if not session_id or not thread_id:
        return

    record: dict[str, Any] = {"threadId": thread_id}
    for key in ("cwd", "model", "provider"):
        if _read_str(event, key):
            record[key] = event[key]

    if hasattr(binding_store, "update_binding"):
        try:
            binding_store.update_binding(session_id, record)
        except Exception:
            pass
    elif isinstance(binding_store, dict):
        binding_store[session_id] = record


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _read_str(obj: Any, key: str) -> str | None:
    if isinstance(obj, dict):
        val = obj.get(key)
    else:
        val = getattr(obj, key, None)
    return val.strip() if isinstance(val, str) and val.strip() else None


__all__ = [
    "handle_codex_conversation_inbound_claim",
    "handle_codex_conversation_binding_resolved",
]
