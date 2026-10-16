"""jarvis.agents.embedded_agent_runner.system_prompt — build/install embedded-agent system prompts.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/system-prompt.ts``.

Public surface:

- :func:`build_embedded_system_prompt`
- :func:`apply_system_prompt_to_session`

Phase 7.6h-4 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..sessions.system_prompt import build_system_prompt as _build_session_system_prompt


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


def _convert_embedded_system_prompt_params_to_session_options(
    params: Dict[str, Any]
) -> Dict[str, Any]:
    runtime_info = params.get("runtimeInfo") or {}
    append_section = params.get("appendSystemPrompt") or ""
    runtime_lines: List[str] = []
    if isinstance(runtime_info, dict):
        for key in ("model", "provider", "host"):
            value = runtime_info.get(key)
            if value:
                runtime_lines.append(f"{key}={value}")
    if runtime_lines:
        runtime_append = "\n".join(runtime_lines)
        append_section = (
            f"{append_section}\n\nEmbedded runtime info:\n{runtime_append}"
            if append_section
            else f"Embedded runtime info:\n{runtime_append}"
        )

    tools = params.get("tools") or []
    selected_tools = [
        getattr(t, "name", None)
        if not isinstance(t, dict)
        else t.get("name")
        for t in tools
    ]
    selected_tools = [t for t in selected_tools if t]

    return {
        "cwd": params.get("workspaceDir", ""),
        "customPrompt": params.get("customPrompt"),
        "selectedTools": selected_tools,
        "toolSnippets": params.get("toolSnippets") or {},
        "promptGuidelines": params.get("promptGuidelines") or [],
        "appendSystemPrompt": append_section or None,
        "contextFiles": params.get("contextFiles") or [],
        "skills": params.get("skills") or [],
        "isFirstTurn": params.get("isFirstTurn", False),
    }


def build_embedded_system_prompt(params: Dict[str, Any]) -> str:
    """Build the system prompt for an embedded agent run.

    Mirrors :func:`buildEmbeddedSystemPrompt` (``system-prompt.ts``).
    """
    if _build_embedded_system_prompt_hook is not None:
        v = _build_embedded_system_prompt_hook(params)
        return v if isinstance(v, str) else ""
    try:
        return _build_session_system_prompt(
            _convert_embedded_system_prompt_params_to_session_options(
                params or {}
            )
        )
    except Exception:
        runtime = params.get("runtimeInfo") or {}
        tool_names = [
            getattr(t, "name", None)
            or (t.get("name") if isinstance(t, dict) else None)
            for t in (params.get("tools") or [])
        ]
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
