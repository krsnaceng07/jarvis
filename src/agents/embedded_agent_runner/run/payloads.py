"""jarvis.agents.embedded_agent_runner.run.payloads — build embedded-run payload objects.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/payloads.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`RECOVERABLE_TOOL_ERROR_KEYWORDS` — tuple of recoverable
  tool-error keyword prefixes.
- :data:`ToolMetaEntry` — TypedDict for tool-meta entries.
- :data:`ToolErrorWarningPolicy` — TypedDict for the tool-error
  warning policy.
- :func:`build_embedded_run_payloads` — build the final reply
  payloads for an embedded run.

Phase 7.6a — focused minimal port.

The OpenClaw source is 880+ lines and tightly coupled to the
auto-reply, chat-message-content, exec-tool detection, and
reply-directive parsing layers. The Python port keeps the
public surface and delegates the heavy payload-building to an
installable handler so the host can plug in the real layers
as they land.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple


#: Recoverable tool-error keywords. Mirrors
#: :data:`RECOVERABLE_TOOL_ERROR_KEYWORDS``
#: (``payloads.ts:71-79``).
RECOVERABLE_TOOL_ERROR_KEYWORDS: Tuple[str, ...] = (
    "required",
    "missing",
    "invalid",
    "must be",
    "must have",
    "needs",
    "requires",
)


#: Tool-meta entry shape. Mirrors ``ToolMetaEntry``
#: (``payloads.ts:65``).
ToolMetaEntry = Dict[str, Any]


#: Tool-error warning policy shape. Mirrors
#: :class:`ToolErrorWarningPolicy`` (``payloads.ts:66-69``).
ToolErrorWarningPolicy = Dict[str, Any]


#: Build-embedded-run-payload handler. The host installs the
#: real :func:`buildEmbeddedRunPayloads`` when the payload
#: layer lands. The default returns an empty list.
_BUILD_EMBEDDED_RUN_PAYLOADS: Callable[[Dict[str, Any]], List[Any]] = (
    lambda _params: []
)


def set_build_embedded_run_payloads_hook(
    hook: Callable[[Dict[str, Any]], List[Any]],
) -> None:
    """Install a custom build-embedded-run-payload handler."""
    global _BUILD_EMBEDDED_RUN_PAYLOADS
    _BUILD_EMBEDDED_RUN_PAYLOADS = hook


#: Sanitize-assistant-visible-stream-text hook. The host installs
#: the real :func:`sanitizeAssistantVisibleStreamText`` when the
#: assistant-visible-text layer lands. The default is a no-op.
_SANITIZE_ASSISTANT_VISIBLE_STREAM_TEXT: Callable[[str], str] = (
    lambda text: text
)


def set_sanitize_assistant_visible_stream_text_hook(
    hook: Callable[[str], str],
) -> None:
    """Install a custom sanitize-assistant-visible-stream-text hook."""
    global _SANITIZE_ASSISTANT_VISIBLE_STREAM_TEXT
    _SANITIZE_ASSISTANT_VISIBLE_STREAM_TEXT = hook


#: Build-source-reply-payload-state hook.
_BUILD_SOURCE_REPLY_PAYLOAD_STATE: Callable[
    [Dict[str, Any]], Dict[str, Any]
] = (
    lambda _params: {
        "replyItems": [],
        "hasSourceReplyPayload": False,
        "deliveredSourceReplyViaMessageTool": False,
        "explicitFinalSourceReply": None,
        "completedSourceReplyViaMessageTool": False,
    }
)


def set_build_source_reply_payload_state_hook(
    hook: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Install a custom build-source-reply-payload-state hook."""
    global _BUILD_SOURCE_REPLY_PAYLOAD_STATE
    _BUILD_SOURCE_REPLY_PAYLOAD_STATE = hook


#: Format-user-facing-assistant-error-text hook.
_FORMAT_USER_FACING_ASSISTANT_ERROR_TEXT: Callable[
    [Dict[str, Any], Dict[str, Any]], Optional[str]
] = (
    lambda _assistant, _options: None
)


def set_format_user_facing_assistant_error_text_hook(
    hook: Callable[[Dict[str, Any], Dict[str, Any]], Optional[str]],
) -> None:
    """Install a custom format-user-facing-assistant-error-text hook."""
    global _FORMAT_USER_FACING_ASSISTANT_ERROR_TEXT
    _FORMAT_USER_FACING_ASSISTANT_ERROR_TEXT = hook


#: Format-tool-aggregate hook.
_FORMAT_TOOL_AGGREGATE: Callable[[List[Any]], str] = (
    lambda _entries: ""
)


def set_format_tool_aggregate_hook(
    hook: Callable[[List[Any]], str],
) -> None:
    """Install a custom format-tool-aggregate hook."""
    global _FORMAT_TOOL_AGGREGATE
    _FORMAT_TOOL_AGGREGATE = hook


def build_embedded_run_payloads(
    params: Dict[str, Any],
) -> List[Any]:
    """Build the final reply payloads for an embedded run.

    Mirrors :func:`buildEmbeddedRunPayloads``
    (``payloads.ts:516-...``).

    The Python port delegates the heavy payload assembly to an
    installable handler; the default returns an empty list. The
    few helpers (``sanitizeAssistantVisibleStreamText``,
    ``buildSourceReplyPayloadState``) are also installable so
    the host can shape the output as needed.
    """
    return _BUILD_EMBEDDED_RUN_PAYLOADS(params)


def is_recoverable_tool_error(message: str) -> bool:
    """Return True if ``message`` contains a recoverable tool-error keyword.

    Mirrors the OpenClaw source's recoverable-keyword check.
    """
    if not isinstance(message, str):
        return False
    lowered = message.lower()
    return any(keyword in lowered for keyword in RECOVERABLE_TOOL_ERROR_KEYWORDS)


__all__ = [
    "RECOVERABLE_TOOL_ERROR_KEYWORDS",
    "ToolErrorWarningPolicy",
    "ToolMetaEntry",
    "build_embedded_run_payloads",
    "is_recoverable_tool_error",
    "set_build_embedded_run_payloads_hook",
    "set_build_source_reply_payload_state_hook",
    "set_format_tool_aggregate_hook",
    "set_format_user_facing_assistant_error_text_hook",
    "set_sanitize_assistant_visible_stream_text_hook",
]
