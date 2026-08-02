"""jarvis.agents.embedded_agent_runner.run.runtime_context_prompt — build runtime context prompt fragments + custom session messages.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/runtime-context-prompt.ts``.

Public surface:

Constants:

- :data:`OPENCLAW_RUNTIME_EVENT_USER_PROMPT`
- :data:`INTERNAL_RUNTIME_CONTEXT_BEGIN`
- :data:`INTERNAL_RUNTIME_CONTEXT_END`
- :data:`OPENCLAW_NEXT_TURN_RUNTIME_CONTEXT_HEADER`
- :data:`OPENCLAW_RUNTIME_CONTEXT_CUSTOM_TYPE`
- :data:`OPENCLAW_RUNTIME_CONTEXT_NOTICE`
- :data:`OPENCLAW_RUNTIME_EVENT_HEADER`

Types:

- :data:`RuntimeContextCustomMessage`

Functions:

- :func:`build_current_inbound_prompt`
- :func:`resolve_runtime_context_prompt_parts`
- :func:`build_runtime_context_custom_message`

Phase 7.6b-4 — focused minimal port.

The OpenClaw source is tightly coupled to the
``internal-runtime-context`` module which holds the begin/end
markers, headers, and the extractor. The Python port keeps the
public surface and re-uses the OpenClaw constant values directly.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional


#: Default runtime-event user prompt. Mirrors
#: :data:`OPENCLAW_RUNTIME_EVENT_USER_PROMPT`
#: (``runtime-context-prompt.ts:15``).
OPENCLAW_RUNTIME_EVENT_USER_PROMPT: str = "Continue the OpenClaw runtime event."


#: Internal runtime context begin marker. Mirrors
#: :data:`INTERNAL_RUNTIME_CONTEXT_BEGIN` from
#: ``internal-runtime-context.ts``.
INTERNAL_RUNTIME_CONTEXT_BEGIN: str = "<<<BEGIN_OPENCLAW_RUNTIME_CONTEXT>>>"


#: Internal runtime context end marker. Mirrors
#: :data:`INTERNAL_RUNTIME_CONTEXT_END` from
#: ``internal-runtime-context.ts``.
INTERNAL_RUNTIME_CONTEXT_END: str = "<<<END_OPENCLAW_RUNTIME_CONTEXT>>>"


#: Next-turn runtime context header. Mirrors
#: :data:`OPENCLAW_NEXT_TURN_RUNTIME_CONTEXT_HEADER` from
#: ``internal-runtime-context.ts``.
OPENCLAW_NEXT_TURN_RUNTIME_CONTEXT_HEADER: str = (
    "[OpenClaw next-turn runtime context]\n"
)


#: Custom message type for runtime-context. Mirrors
#: :data:`OPENCLAW_RUNTIME_CONTEXT_CUSTOM_TYPE` from
#: ``internal-runtime-context.ts``.
OPENCLAW_RUNTIME_CONTEXT_CUSTOM_TYPE: str = "openclaw.runtimeContext"


#: Runtime context notice (used as a placeholder in user-visible
#: prompts). Mirrors :data:`OPENCLAW_RUNTIME_CONTEXT_NOTICE` from
#: ``internal-runtime-context.ts``.
OPENCLAW_RUNTIME_CONTEXT_NOTICE: str = (
    "[OpenClaw runtime context — not part of the user prompt]"
)


#: Runtime event header (used in custom user messages). Mirrors
#: :data:`OPENCLAW_RUNTIME_EVENT_HEADER` from
#: ``internal-runtime-context.ts``.
OPENCLAW_RUNTIME_EVENT_HEADER: str = "[OpenClaw runtime event]"


#: Custom transcript message that carries runtime context. Mirrors
#: :class:`RuntimeContextCustomMessage` (``runtime-context-prompt.ts:26-33``).
RuntimeContextCustomMessage = Dict[str, Any]


#: Runtime-context prompt-parts result. Mirrors
#: :class:`RuntimeContextPromptParts` (``runtime-context-prompt.ts:17-23``).
RuntimeContextPromptParts = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the extract-internal-runtime-context step.
_EXTRACT_INTERNAL_RUNTIME_CONTEXT: Callable[[str], Optional[str]] = (
    lambda text: _default_extract_internal_runtime_context(text)
)


def set_extract_internal_runtime_context_hook(
    hook: Callable[[str], Optional[str]],
) -> None:
    """Install a custom extractInternalRuntimeContext hook."""
    global _EXTRACT_INTERNAL_RUNTIME_CONTEXT
    _EXTRACT_INTERNAL_RUNTIME_CONTEXT = hook


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_INTERNAL_CONTEXT_PATTERN: "re.Pattern[str]" = re.compile(
    re.escape(INTERNAL_RUNTIME_CONTEXT_BEGIN)
    + r"(.*?)"
    + re.escape(INTERNAL_RUNTIME_CONTEXT_END),
    re.DOTALL,
)


def _default_extract_internal_runtime_context(text: str) -> Optional[str]:
    """Return the runtime-context body between begin/end markers.

    Mirrors :func:`extractInternalRuntimeContext` from
    ``internal-runtime-context.ts``.
    """
    if not isinstance(text, str):
        return None
    match = _INTERNAL_CONTEXT_PATTERN.search(text)
    if not match:
        return None
    return match.group(1).strip()


def _split_last_prompt_occurrence(
    text: str, prompt: str
) -> Optional[Dict[str, str]]:
    if not isinstance(text, str) or not isinstance(prompt, str):
        return None
    index = text.rfind(prompt)
    if index == -1:
        return None
    return {
        "before": text[:index],
        "after": text[index + len(prompt):],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_current_inbound_prompt(
    params: Dict[str, Any],
) -> str:
    """Combine inbound context and the current prompt using the channel joiner.

    Mirrors :func:`buildCurrentInboundPrompt`
    (``runtime-context-prompt.ts:46-63``).
    """
    context = params.get("context")
    prompt = params.get("prompt") or ""
    prefer_resumable = bool(params.get("preferResumableText", False))
    if context is not None:
        if prefer_resumable:
            # Resumable text wins when present, otherwise fall back
            # to the regular context text.
            context_text = context.get("resumableText")
            if not isinstance(context_text, str) or not context_text:
                context_text = context.get("text")
        else:
            context_text = context.get("text")
    else:
        context_text = None
    prefix = (context_text or "").strip() if isinstance(context_text, str) else ""
    if not prefix:
        return prompt
    if not prompt:
        return prefix
    joiner = (context.get("promptJoiner") if context else None) or "\n\n"
    return joiner.join([prefix, prompt])


def resolve_runtime_context_prompt_parts(
    params: Dict[str, Any],
) -> RuntimeContextPromptParts:
    """Resolve the runtime-context prompt parts.

    Mirrors :func:`resolveRuntimeContextPromptParts`
    (``runtime-context-prompt.ts:...``).
    """
    prompt = params.get("prompt") or ""
    model_prompt = params.get("modelPrompt")
    runtime_context = params.get("runtimeContext")
    runtime_only = bool(params.get("runtimeOnly", False))
    runtime_system_context = params.get("runtimeSystemContext")

    extracted = _EXTRACT_INTERNAL_RUNTIME_CONTEXT(prompt) if prompt else None
    if extracted is not None and not runtime_context:
        runtime_context = extracted
    if model_prompt and prompt:
        split = _split_last_prompt_occurrence(model_prompt, prompt)
        if split is not None:
            runtime_context = (
                (runtime_context + "\n\n" + split["after"].strip())
                if runtime_context
                else split["after"].strip()
            )
            runtime_only = True
    if runtime_context:
        if runtime_only:
            user_visible_prompt = (
                params.get("modelPrompt")
                if model_prompt and prompt
                else prompt
            )
            runtime_block = (
                INTERNAL_RUNTIME_CONTEXT_BEGIN
                + "\n"
                + runtime_context
                + "\n"
                + INTERNAL_RUNTIME_CONTEXT_END
            )
            prompt = (
                (user_visible_prompt + "\n\n" + runtime_block)
                if user_visible_prompt
                else runtime_block
            )
        else:
            prompt = (
                INTERNAL_RUNTIME_CONTEXT_BEGIN
                + "\n"
                + runtime_context
                + "\n"
                + INTERNAL_RUNTIME_CONTEXT_END
                + "\n\n"
                + prompt
            )
    return {
        "prompt": prompt,
        "modelPrompt": model_prompt,
        "runtimeContext": runtime_context,
        "runtimeOnly": runtime_only,
        "runtimeSystemContext": runtime_system_context,
    }


def build_runtime_context_custom_message(
    params: Dict[str, Any],
) -> RuntimeContextCustomMessage:
    """Build a hidden custom transcript message carrying runtime context.

    Mirrors :func:`buildRuntimeContextCustomMessage`
    (``runtime-context-prompt.ts:...``).
    """
    runtime_context = params.get("runtimeContext") or ""
    timestamp = params.get("timestamp")
    if not isinstance(timestamp, (int, float)):
        timestamp = int(time.time() * 1000)
    return {
        "role": "custom",
        "customType": OPENCLAW_RUNTIME_CONTEXT_CUSTOM_TYPE,
        "content": runtime_context,
        "display": False,
        "details": {
            "source": "openclaw-runtime-context",
            "runtimeContextCarrier": True,
        },
        "timestamp": int(timestamp),
    }


__all__ = [
    "INTERNAL_RUNTIME_CONTEXT_BEGIN",
    "INTERNAL_RUNTIME_CONTEXT_END",
    "OPENCLAW_NEXT_TURN_RUNTIME_CONTEXT_HEADER",
    "OPENCLAW_RUNTIME_CONTEXT_CUSTOM_TYPE",
    "OPENCLAW_RUNTIME_CONTEXT_NOTICE",
    "OPENCLAW_RUNTIME_EVENT_HEADER",
    "OPENCLAW_RUNTIME_EVENT_USER_PROMPT",
    "RuntimeContextCustomMessage",
    "RuntimeContextPromptParts",
    "build_current_inbound_prompt",
    "build_runtime_context_custom_message",
    "resolve_runtime_context_prompt_parts",
    "set_extract_internal_runtime_context_hook",
]
