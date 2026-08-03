"""jarvis.agents.embedded_agent_runner.system_prompt — build/install embedded-agent system prompts.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/system-prompt.ts``.

Public surface:

- :func:`build_embedded_system_prompt`
- :func:`apply_system_prompt_to_session`

Phase 7.6h-4 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# Installable hooks ---------------------------------------------------------

_build_embedded_system_prompt_hook = None
_apply_system_prompt_to_session_hook = None


def set_build_embedded_system_prompt_hook(fn) -> None:
    global _build_embedded_system_prompt_hook
    _build_embedded_system_prompt_hook = fn


def set_apply_system_prompt_to_session_hook(fn) -> None:
    global _apply_system_prompt_to_session_hook
    _apply_system_prompt_to_session_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_embedded_system_prompt(params: Dict[str, Any]) -> str:
    """Build the system prompt for an embedded agent run.

    Mirrors :func:`buildEmbeddedSystemPrompt` (``system-prompt.ts``).
    """
    if _build_embedded_system_prompt_hook is not None:
        v = _build_embedded_system_prompt_hook(params)
        return v if isinstance(v, str) else ""
    # Focused minimal port: produce a deterministic identifier-string so
    # downstream code can verify a prompt was generated. The full system-prompt
    # assembly lives in `system_prompt_config.py` (jarvis_sdk).
    runtime = params.get("runtimeInfo") or {}
    tool_names = [getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None) for t in (params.get("tools") or [])]
    tool_names = [n for n in tool_names if n]
    return (
        f"# embedded-agent prompt\n"
        f"model={runtime.get('model', '')}\n"
        f"provider={runtime.get('provider', '')}\n"
        f"host={runtime.get('host', '')}\n"
        f"tools={','.join(tool_names)}\n"
        f"workspace={params.get('workspaceDir', '')}\n"
    )


def apply_system_prompt_to_session(session: Any, system_prompt: str) -> None:
    """Install the built prompt onto an agent session.

    Mirrors :func:`applySystemPromptToSession` (``system-prompt.ts``).
    """
    if _apply_system_prompt_to_session_hook is not None:
        _apply_system_prompt_to_session_hook(session, system_prompt)
        return
    setter = getattr(session, "setBaseSystemPrompt", None)
    if callable(setter):
        try:
            setter((system_prompt or "").strip())
        except Exception:
            pass


__all__ = [
    "build_embedded_system_prompt",
    "apply_system_prompt_to_session",
    "set_build_embedded_system_prompt_hook",
    "set_apply_system_prompt_to_session_hook",
]
