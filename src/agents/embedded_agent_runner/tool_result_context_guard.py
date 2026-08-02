"""jarvis.agents.embedded_agent_runner.tool_result_context_guard — context-engine loop + tool-result guard.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/tool-result-context-guard.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`mark_transcript_prompt_text` — attach a non-enumerable
  marker to a message so the prompt-text can be restored later.
- :func:`get_transcript_prompt_text` — read back the marker set
  by :func:`mark_transcript_prompt_text`.
- :func:`strip_transcript_prompt_marker` — return a copy of the
  message with the marker removed.
- :func:`install_context_engine_loop_hook` — install the
  context-engine loop hook on the agent. Returns a dispose
  function. Delegates the heavy loop logic to an installable
  handler.
- :func:`install_tool_result_context_guard` — install the
  tool-result context guard on the agent. Returns a dispose
  function. Delegates the heavy truncation logic to an
  installable handler.

Phase 7.4c — focused minimal port.

The OpenClaw source is 600+ lines and tightly coupled to the
context engine, message repair, and safeguard-mid-turn-precheck
layers. The Python port keeps the public surface and the marker
helpers but delegates the heavy install hooks to installable
handlers so the host can plug in the real context-engine +
safeguard layers as they land.

The marker storage uses a private non-enumerable Symbol-style key
(``__jarvis_transcript_prompt_text__``) on the message object so
the marker never leaks into the provider's tool/JSON serialization.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: The internal marker key for transcript prompt text. Mirrors
#: :data:`TRANSCRIPT_PROMPT_TEXT_KEY`` from the OpenClaw source.
#: The Python port uses a private name (not a Symbol) because
#: Python doesn't have Symbol semantics; callers should treat
#: the key as opaque.
_TRANSCRIPT_PROMPT_TEXT_KEY = "__jarvis_transcript_prompt_text__"


def mark_transcript_prompt_text(
    message: Any,
    text: str,
) -> None:
    """Attach a non-enumerable marker to ``message``.

    Mirrors :func:`markTranscriptPromptText``
    (``tool-result-context-guard.ts:57-63``).
    """
    if message is None:
        return
    if isinstance(message, dict):
        message[_TRANSCRIPT_PROMPT_TEXT_KEY] = text
    else:
        try:
            setattr(message, _TRANSCRIPT_PROMPT_TEXT_KEY, text)
        except (AttributeError, TypeError):
            # Last-ditch: attach as a class attribute via the
            # message's __dict__.
            try:
                message.__dict__[_TRANSCRIPT_PROMPT_TEXT_KEY] = text
            except Exception:
                pass


def get_transcript_prompt_text(
    message: Any,
) -> Optional[str]:
    """Read back the marker set by :func:`mark_transcript_prompt_text`.

    Mirrors :func:`getTranscriptPromptText``
    (``tool-result-context-guard.ts:65-68``).
    """
    if message is None:
        return None
    value: Any
    if isinstance(message, dict):
        value = message.get(_TRANSCRIPT_PROMPT_TEXT_KEY)
    else:
        value = getattr(message, _TRANSCRIPT_PROMPT_TEXT_KEY, None)
    return value if isinstance(value, str) else None


def strip_transcript_prompt_marker(
    message: Any,
) -> Any:
    """Return a copy of ``message`` with the marker removed.

    Mirrors :func:`stripTranscriptPromptMarker``
    (``tool-result-context-guard.ts:109-116``).
    """
    if message is None:
        return message
    if get_transcript_prompt_text(message) is None:
        return message
    if isinstance(message, dict):
        out = dict(message)
        out.pop(_TRANSCRIPT_PROMPT_TEXT_KEY, None)
        return out
    try:
        out_dict = {
            k: v
            for k, v in vars(message).items()
            if k != _TRANSCRIPT_PROMPT_TEXT_KEY
        }
        new_message = type(message).__new__(type(message))
        new_message.__dict__.update(out_dict)
        return new_message
    except Exception:
        return message


def project_transcript_prompt_messages(
    messages: List[Any],
    cache: Dict[int, Any],
) -> List[Any]:
    """Restore transcript prompt text on each message.

    Mirrors :func:`projectTranscriptPromptMessages``
    (``tool-result-context-guard.ts:118-129``).
    """
    changed = False
    projected: List[Any] = []
    for message in messages:
        next_message = _restore_transcript_prompt_text(message, cache)
        if next_message is not message:
            changed = True
        projected.append(next_message)
    return projected if changed else messages


def _restore_transcript_prompt_text(
    message: Any,
    cache: Dict[int, Any],
) -> Any:
    if message is None:
        return message
    msg_id = id(message)
    if msg_id in cache:
        return cache[msg_id]
    text = get_transcript_prompt_text(message)
    if text is None:
        return message
    role = None
    if isinstance(message, dict):
        role = message.get("role")
    else:
        role = getattr(message, "role", None)
    if role != "user":
        return message
    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    if isinstance(content, str):
        new_message = {k: v for k, v in message.items() if k != _TRANSCRIPT_PROMPT_TEXT_KEY} if isinstance(message, dict) else message
        if isinstance(new_message, dict):
            new_message["content"] = text
        cache[msg_id] = new_message
        return new_message
    if isinstance(content, list):
        restored = False

        def _restore_block(block: Any) -> Any:
            nonlocal restored
            if restored:
                return block
            if not block or not isinstance(block, dict):
                return block
            if block.get("type") != "text" or not isinstance(block.get("text"), str):
                return block
            restored = True
            return {**block, "text": text}

        next_content = [_restore_block(block) for block in content]
        if restored:
            if isinstance(message, dict):
                new_message = {
                    k: v
                    for k, v in message.items()
                    if k != _TRANSCRIPT_PROMPT_TEXT_KEY
                }
                new_message["content"] = next_content
            else:
                new_message = message
            cache[msg_id] = new_message
            return new_message
    return message


def strip_transcript_prompt_markers(
    messages: List[Any],
) -> List[Any]:
    """Strip the transcript-prompt marker from each message.

    Mirrors :func:`stripTranscriptPromptMarkers``
    (``tool-result-context-guard.ts:131-139``).
    """
    changed = False
    stripped: List[Any] = []
    for message in messages:
        next_message = strip_transcript_prompt_marker(message)
        if next_message is not message:
            changed = True
        stripped.append(next_message)
    return stripped if changed else messages


#: Context-engine loop hook handler. The host installs the real
#: implementation when the context-engine layer lands. The
#: default returns a no-op dispose function.
_CONTEXT_ENGINE_LOOP_HOOK_HANDLER: Optional[
    Callable[[Dict[str, Any]], Callable[[], None]]
] = None


def set_context_engine_loop_hook_handler(
    handler: Optional[Callable[[Dict[str, Any]], Callable[[], None]]],
) -> None:
    """Install a custom context-engine loop hook handler."""
    global _CONTEXT_ENGINE_LOOP_HOOK_HANDLER
    _CONTEXT_ENGINE_LOOP_HOOK_HANDLER = handler


def install_context_engine_loop_hook(
    params: Dict[str, Any],
) -> Callable[[], None]:
    """Install the context-engine loop hook on the agent.

    Mirrors :func:`installContextEngineLoopHook``
    (``tool-result-context-guard.ts:323-466``).

    Returns a dispose function. The Python port delegates the
    heavy loop logic to the installed handler; the default is a
    no-op dispose.
    """
    if _CONTEXT_ENGINE_LOOP_HOOK_HANDLER is None:
        return lambda: None
    return _CONTEXT_ENGINE_LOOP_HOOK_HANDLER(params)


#: Tool-result context guard handler. The host installs the real
#: implementation when the safeguard layer lands. The default
#: returns a no-op dispose function.
_TOOL_RESULT_CONTEXT_GUARD_HANDLER: Optional[
    Callable[[Dict[str, Any]], Callable[[], None]]
] = None


def set_tool_result_context_guard_handler(
    handler: Optional[Callable[[Dict[str, Any]], Callable[[], None]]],
) -> None:
    """Install a custom tool-result context guard handler."""
    global _TOOL_RESULT_CONTEXT_GUARD_HANDLER
    _TOOL_RESULT_CONTEXT_GUARD_HANDLER = handler


def install_tool_result_context_guard(
    params: Dict[str, Any],
) -> Callable[[], None]:
    """Install the tool-result context guard on the agent.

    Mirrors :func:`installToolResultContextGuard``
    (``tool-result-context-guard.ts:468-568``).

    Returns a dispose function. The Python port delegates the
    heavy truncation logic to the installed handler; the default
    is a no-op dispose.
    """
    if _TOOL_RESULT_CONTEXT_GUARD_HANDLER is None:
        return lambda: None
    return _TOOL_RESULT_CONTEXT_GUARD_HANDLER(params)


__all__ = [
    "get_transcript_prompt_text",
    "install_context_engine_loop_hook",
    "install_tool_result_context_guard",
    "mark_transcript_prompt_text",
    "project_transcript_prompt_messages",
    "set_context_engine_loop_hook_handler",
    "set_tool_result_context_guard_handler",
    "strip_transcript_prompt_marker",
    "strip_transcript_prompt_markers",
]
