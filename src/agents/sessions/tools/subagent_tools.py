"""jarvis.agents.sessions.tools.subagent_tools
Implements the canonical OpenClaw subagent tools: sessions_spawn, sessions_yield, and subagents.

Matches OpenClaw parity:
- src/agents/tools/sessions-spawn-tool.ts
- src/agents/tools/sessions-yield-tool.ts
- src/agents/tools/subagents-tool.ts
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.subagents import (
    MultiAgentOrchestrator,
    SpawnSubagentParams,
    SubagentController,
    SubagentRegistry,
    SubagentRole,
    SubagentRunner,
    SubagentSpawner,
    SubagentSpawnContextMode,
)

from .tool_definition_wrapper import AgentTool


# Global default instances for standard tool calls
_default_registry = SubagentRegistry.get_instance()
_default_spawner = SubagentSpawner(registry=_default_registry)
_default_runner = SubagentRunner(registry=_default_registry)
_default_controller = SubagentController(registry=_default_registry, spawner=_default_spawner)
_default_orchestrator = MultiAgentOrchestrator(spawner=_default_spawner, registry=_default_registry)


def get_default_spawner() -> SubagentSpawner:
    return _default_spawner


def get_default_controller() -> SubagentController:
    return _default_controller


def get_default_orchestrator() -> MultiAgentOrchestrator:
    return _default_orchestrator


# ============================================================================
# sessions_spawn
# ============================================================================


def create_sessions_spawn_tool_definition() -> dict:
    return {
        "name": "sessions_spawn",
        "label": "Sessions",
        "description": "Spawn an isolated or forked sub-agent session for background work.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The primary task description or instructions.",
                },
                "instructions": {"type": "string", "description": "Alias for task."},
                "taskName": {
                    "type": "string",
                    "description": "Stable target alias; starts lowercase letter; then lowercase/digit/_/-.",
                },
                "label": {"type": "string", "description": "Short task title shown in lists."},
                "runtime": {
                    "type": "string",
                    "enum": ["subagent", "acp"],
                    "description": "Runtime for the subagent.",
                },
                "agentId": {"type": "string", "description": "Target agent identity."},
                "model": {"type": "string", "description": "Override model for the child."},
                "thinking": {"type": "string", "description": "Override thinking for the child."},
                "runTimeoutSeconds": {
                    "type": "number",
                    "description": "Override timeout in seconds.",
                },
                "thread": {"type": "boolean", "description": "Bind to a chat thread."},
                "sandbox": {
                    "type": "string",
                    "enum": ["inherit", "require"],
                    "description": "Enforce sandbox.",
                },
                "context": {
                    "type": "string",
                    "enum": ["fork", "isolated"],
                    "description": "Context mode ('isolated' or 'fork').",
                },
                "parent_session_key": {
                    "type": "string",
                    "description": "Caller parent session key.",
                },
                "parent_depth": {"type": "integer", "description": "Current caller spawn depth."},
                "cwd": {"type": "string", "description": "Child working directory."},
                "attachments": {"type": "array", "description": "Optional file attachments."},
            },
            "required": [],
        },
    }


async def run_sessions_spawn_tool(
    tool_call_id: str | dict[str, Any],
    args: dict[str, Any] | None = None,
    signal: Any = None,
    on_update: Any = None,
    ctx: Any = None,
) -> dict[str, Any]:
    # Handle arity difference if called directly or via tool definition wrapper
    if isinstance(tool_call_id, dict) and args is None:
        params_dict = tool_call_id
    else:
        params_dict = args or {}

    task = (params_dict.get("task") or params_dict.get("instructions") or "").strip()

    if not task:
        return {
            "content": [
                {"type": "text", "text": "Error: sessions_spawn requires 'task' or 'instructions'."}
            ],
            "details": {"status": "error", "error": "Missing task description"},
        }

    task_name = params_dict.get("taskName") or params_dict.get("task_name") or ""
    label = params_dict.get("label") or ""
    model = params_dict.get("model")
    thinking = params_dict.get("thinking")
    timeout = float(
        params_dict.get("runTimeoutSeconds") or params_dict.get("timeout_seconds") or 60.0
    )
    raw_ctx = params_dict.get("context", "isolated").lower()
    ctx_mode = (
        SubagentSpawnContextMode.FORK if raw_ctx == "fork" else SubagentSpawnContextMode.ISOLATED
    )
    parent_key = params_dict.get("parent_session_key") or "desktop:hud"
    parent_depth = int(params_dict.get("parent_depth") or 0)
    cwd = params_dict.get("cwd")
    attachments = params_dict.get("attachments")

    spawn_params = SpawnSubagentParams(
        task=task,
        label=label,
        task_name=task_name,
        model=model,
        thinking=thinking,
        run_timeout_seconds=timeout,
        context=ctx_mode,
        parent_session_key=parent_key,
        parent_depth=parent_depth,
        cwd=cwd,
        attachments=attachments,
    )

    result = await _default_spawner.spawn(
        spawn_params,
        runner_factory=lambda rec, tools: _default_runner.run(rec, tools),
    )

    result_payload = result.to_dict()
    text_repr = json.dumps(result_payload)
    return {
        "content": [{"type": "text", "text": text_repr}],
        "details": result_payload,
    }


def create_sessions_spawn_tool() -> AgentTool:
    tool = create_sessions_spawn_tool_definition()
    tool["parameters"] = tool.pop("inputSchema", {})
    tool["execute"] = run_sessions_spawn_tool
    return tool


# ============================================================================
# sessions_yield
# ============================================================================


def create_sessions_yield_tool_definition() -> dict:
    return {
        "name": "sessions_yield",
        "label": "Yield",
        "description": "End the current turn and wait for follow-up sub-agent results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Private context for the resumed turn.",
                },
                "acknowledgment": {
                    "type": "string",
                    "description": "Optional waiting reply for interactive user turn.",
                },
                "reason": {"type": "string", "description": "Optional reason for yielding."},
            },
            "required": [],
        },
    }


async def run_sessions_yield_tool(
    tool_call_id: str | dict[str, Any],
    args: dict[str, Any] | None = None,
    signal: Any = None,
    on_update: Any = None,
    ctx: Any = None,
) -> dict[str, Any]:
    if isinstance(tool_call_id, dict) and args is None:
        params_dict = tool_call_id
    else:
        params_dict = args or {}

    msg = params_dict.get("message") or params_dict.get("reason") or "Turn yielded."
    ack = params_dict.get("acknowledgment")

    details = {"status": "yielded", "message": msg}
    if ack:
        details["acknowledgment"] = ack

    return {
        "content": [{"type": "text", "text": f"Turn yielded. {msg}"}],
        "details": details,
    }


def create_sessions_yield_tool() -> AgentTool:
    tool = create_sessions_yield_tool_definition()
    tool["parameters"] = tool.pop("inputSchema", {})
    tool["execute"] = run_sessions_yield_tool
    return tool


# ============================================================================
# subagents
# ============================================================================


def create_subagents_tool_definition() -> dict:
    return {
        "name": "subagents",
        "label": "Subagents",
        "description": "List or cancel background work in this session tree.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "cancel"],
                    "description": "The action to perform (list or cancel).",
                },
                "taskId": {
                    "type": "string",
                    "description": "Required when action is cancel (task ID or run ID).",
                },
                "recentMinutes": {
                    "type": "integer",
                    "description": "Minutes of history to include in list (default 30).",
                },
                "caller_session_key": {
                    "type": "string",
                    "description": "Session key of the caller.",
                },
                "caller_role": {
                    "type": "string",
                    "description": "Role of the caller ('main', 'orchestrator', 'leaf').",
                },
            },
            "required": ["action"],
        },
    }


async def run_subagents_tool(
    tool_call_id: str | dict[str, Any],
    args: dict[str, Any] | None = None,
    signal: Any = None,
    on_update: Any = None,
    ctx: Any = None,
) -> dict[str, Any]:
    if isinstance(tool_call_id, dict) and args is None:
        params_dict = tool_call_id
    else:
        params_dict = args or {}

    action = (params_dict.get("action") or "list").lower()
    caller_key = params_dict.get("caller_session_key") or "desktop:hud"
    raw_role = params_dict.get("caller_role") or "main"
    try:
        caller_role = SubagentRole(raw_role)
    except ValueError:
        caller_role = SubagentRole.MAIN

    if action == "list":
        recent_mins = int(params_dict.get("recentMinutes") or 30)
        runs = _default_controller.list_controlled_runs(caller_key, recent_minutes=recent_mins)
        payload = {
            "status": "ok",
            "action": "list",
            "total": len(runs),
            "tasks": runs,
        }
        return {
            "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
            "details": payload,
        }

    if action == "cancel":
        task_id = params_dict.get("taskId") or params_dict.get("task_id")
        if not task_id:
            return {
                "content": [
                    {"type": "text", "text": "Error: taskId is required when action is 'cancel'."}
                ],
                "details": {"status": "error", "error": "Missing taskId"},
            }

        ok, msg = _default_controller.cancel_run(
            task_id, caller_session_key=caller_key, caller_role=caller_role
        )
        payload = {
            "status": "cancelled" if ok else "forbidden",
            "taskId": task_id,
            "message": msg,
        }
        return {
            "content": [{"type": "text", "text": msg}],
            "details": payload,
        }

    return {
        "content": [{"type": "text", "text": f"Error: Unsupported subagents action '{action}'."}],
        "details": {"status": "error", "error": f"Unsupported action {action}"},
    }


def create_subagents_tool() -> AgentTool:
    tool = create_subagents_tool_definition()
    tool["parameters"] = tool.pop("inputSchema", {})
    tool["execute"] = run_subagents_tool
    return tool


__all__ = [
    "create_sessions_spawn_tool",
    "create_sessions_spawn_tool_definition",
    "create_sessions_yield_tool",
    "create_sessions_yield_tool_definition",
    "create_subagents_tool",
    "create_subagents_tool_definition",
    "get_default_controller",
    "get_default_orchestrator",
    "get_default_spawner",
    "run_sessions_spawn_tool",
    "run_sessions_yield_tool",
    "run_subagents_tool",
]
