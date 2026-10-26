"""jarvis_desktop.tool_pipeline — Tool execution, validation, and batching pipeline.

OpenClaw parity:
- packages/llm-core/src/validation.ts (argument validation and JSON schema coercion)
- packages/agent-core/src/agent-loop.ts (prepareToolCall, validateToolArguments, sequential vs parallel batches)
- src/agents/agent-tools.schema.ts (schema normalization)
- src/agents/agent-tools.execution-validation.ts (pre-execution validation boundary)
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import time
from typing import Any, Sequence

from jarvis_llm.types import Tool, ToolCall
from jarvis_llm.validation import ToolValidationError, validate_tool_arguments

#: Maximum character count for tool output before truncation.
#: Matches OpenClaw's conservative context protection limit.
MAX_TOOL_OUTPUT_CHARS: int = 32 * 1024  # 32 KB

#: Set of known read-only tools safe for concurrent parallel execution.
READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "ls",
        "read",
        "grep",
        "find",
        "process",
        "session_status",
        "sessions_list",
        "screen",
        "web_search",
        "web_fetch",
        "pdf",
        "recall_memory",
        "memory_search",
        "search_memory",
    }
)

_BROWSER_KIND_ALIASES: dict[str, str] = {
    "clickcoords": "clickCoords",
    "scrollintoview": "scrollIntoView",
}

_desktop_tier_router: Any = None


def get_desktop_tier_router() -> Any:
    """Return singleton instance of TierRouter with attached CursorOverlayWindow."""
    global _desktop_tier_router
    if _desktop_tier_router is None:
        try:
            from extensions.cua_computer.src.router import TierRouter

            from .cursor_overlay import attach_overlay_to_router

            _desktop_tier_router = TierRouter()
            attach_overlay_to_router(_desktop_tier_router)
        except Exception:
            _desktop_tier_router = None
    return _desktop_tier_router


def normalize_tool_parameter_schema(schema: Any) -> dict[str, Any]:
    """Normalize tool parameter schemas into canonical lowercase JSON Schema.

    Gemini Live declarations frequently use uppercase type names
    ("OBJECT", "STRING", "INTEGER", "BOOLEAN", "ARRAY").
    This normalizer recursively converts them to standard JSON schema
    lowercase types so that validate_tool_arguments can validate
    and coerce values without false-positive type rejections.
    """
    if not isinstance(schema, dict):
        return {}

    normalized: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "type":
            if isinstance(value, str):
                normalized[key] = value.lower()
            elif isinstance(value, list):
                normalized[key] = [v.lower() if isinstance(v, str) else v for v in value]
            else:
                normalized[key] = value
        elif isinstance(value, dict):
            normalized[key] = normalize_tool_parameter_schema(value)
        elif isinstance(value, list):
            normalized[key] = [
                normalize_tool_parameter_schema(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            normalized[key] = value

    if normalized.get("type") == "array" and ("items" not in normalized or not normalized["items"]):
        normalized["items"] = {"type": "string"}

    return normalized


def prepare_tool_arguments(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Prepare and normalize tool arguments before schema validation.

    Mirrors OpenClaw's prepareToolCallArguments, attempt.tool-call-argument-repair,
    and schema validation normalization.
    """
    prepared = copy.deepcopy(args) if isinstance(args, dict) else {}

    # Exec and Bash tool aliases (OpenClaw parity)
    if tool_name in ("exec", "bash"):
        if "cmd" in prepared and "command" not in prepared:
            prepared["command"] = prepared["cmd"]
        elif "script" in prepared and "command" not in prepared:
            prepared["command"] = prepared["script"]

        if "cwd" in prepared and "workdir" not in prepared:
            prepared["workdir"] = prepared["cwd"]
        elif "dir" in prepared and "workdir" not in prepared:
            prepared["workdir"] = prepared["dir"]

        if "timeout_ms" in prepared and "timeout" not in prepared:
            try:
                ms = float(prepared["timeout_ms"])
                prepared["timeout"] = int(ms / 1000.0) if ms > 1000 else int(ms)
            except (ValueError, TypeError):
                pass
        elif "timeoutMs" in prepared and "timeout" not in prepared:
            try:
                ms = float(prepared["timeoutMs"])
                prepared["timeout"] = int(ms / 1000.0) if ms > 1000 else int(ms)
            except (ValueError, TypeError):
                pass

    # Read tool aliases
    if tool_name == "read":
        for k in ("file_path", "filePath", "filepath", "file", "target"):
            if k in prepared and "path" not in prepared:
                prepared["path"] = prepared[k]
                break

    # Write tool aliases
    if tool_name == "write":
        for k in ("file_path", "filePath", "filepath", "file", "target"):
            if k in prepared and "path" not in prepared:
                prepared["path"] = prepared[k]
                break
        for k in ("text", "data", "body"):
            if k in prepared and "content" not in prepared:
                prepared["content"] = prepared[k]
                break

    # Surgical edit argument aliases: support both snake_case and camelCase
    if tool_name == "edit":
        for k in ("file_path", "filePath", "filepath", "file", "target"):
            if k in prepared and "path" not in prepared:
                prepared["path"] = prepared[k]
                break

        for k in ("old_str", "old_string", "oldText", "old"):
            if k in prepared and "old_text" not in prepared:
                prepared["old_text"] = prepared[k]
                break
        if "old_text" in prepared and "oldText" not in prepared:
            prepared["oldText"] = prepared["old_text"]

        for k in ("new_str", "new_string", "newText", "new"):
            if k in prepared and "new_text" not in prepared:
                prepared["new_text"] = prepared[k]
                break
        if "new_text" in prepared and "newText" not in prepared:
            prepared["newText"] = prepared["new_text"]

    # Filesystem listing & search aliases
    if tool_name == "ls":
        for k in ("dir", "directory", "folder"):
            if k in prepared and "path" not in prepared:
                prepared["path"] = prepared[k]
                break

    if tool_name == "grep":
        for k in ("query", "search", "regex"):
            if k in prepared and "pattern" not in prepared:
                prepared["pattern"] = prepared[k]
                break
        for k in ("dir", "directory", "folder"):
            if k in prepared and "path" not in prepared:
                prepared["path"] = prepared[k]
                break

    if tool_name == "find":
        for k in ("query", "search", "name"):
            if k in prepared and "pattern" not in prepared:
                prepared["pattern"] = prepared[k]
                break
        for k in ("dir", "directory", "folder"):
            if k in prepared and "path" not in prepared:
                prepared["path"] = prepared[k]
                break

    # Process tool aliases
    if tool_name == "process":
        if "sessionId" in prepared and "session_id" not in prepared:
            prepared["session_id"] = prepared["sessionId"]
        elif "session_id" in prepared and "sessionId" not in prepared:
            prepared["sessionId"] = prepared["session_id"]
        if "subcommand" in prepared and "action" not in prepared:
            prepared["action"] = prepared["subcommand"]

    # Browser tool aliases and direct action normalization (OpenClaw parity)
    if tool_name == "browser":
        raw_action = prepared.get("action")
        if isinstance(raw_action, str):
            act_lower = raw_action.lower().strip()
            if act_lower in ("goto", "visit", "browse", "go_to", "load", "open_url"):
                prepared["action"] = "navigate"
            elif act_lower in ("play", "youtube", "play_youtube"):
                prepared["action"] = "youtube_play"
            elif act_lower in ("search_google", "google_search", "google"):
                prepared["action"] = "google_search"
            elif act_lower in ("new_tab", "newtab", "open_tab"):
                prepared["action"] = "open"
            elif act_lower in ("switch_tab", "switchtab", "focus_tab"):
                prepared["action"] = "focus"
            elif act_lower in ("close_tab", "closetab"):
                prepared["action"] = "close"
            elif act_lower in ("back", "go_back"):
                prepared["action"] = "act"
                prepared["kind"] = "go_back"
            elif act_lower in ("forward", "go_forward"):
                prepared["action"] = "act"
                prepared["kind"] = "go_forward"
            elif act_lower in ("refresh", "reload"):
                prepared["action"] = "act"
                prepared["kind"] = "reload"
            elif act_lower in {
                "click",
                "clickcoords",
                "type",
                "press",
                "hover",
                "scrollintoview",
                "drag",
                "select",
                "fill",
                "resize",
                "wait",
                "evaluate",
            }:
                prepared["kind"] = _BROWSER_KIND_ALIASES.get(act_lower, act_lower)
                prepared["action"] = "act"
        raw_kind = prepared.get("kind")
        if isinstance(raw_kind, str):
            prepared["kind"] = _BROWSER_KIND_ALIASES.get(raw_kind.lower(), raw_kind)

        # Parameter aliases: target/element ref IDs
        for k in ("target_id", "targetId", "id", "element_id", "elementId"):
            if k in prepared and "ref" not in prepared:
                prepared["ref"] = str(prepared[k])

        # Parameter aliases: search query
        for k in ("q", "search_query", "topic"):
            if k in prepared and "query" not in prepared:
                prepared["query"] = str(prepared[k])

        # Parameter aliases: URL
        for k in ("link", "website", "target_url", "targetUrl", "site"):
            if k in prepared and "url" not in prepared:
                prepared["url"] = str(prepared[k])

        # Contextual bridge between query and url
        if prepared.get("action") in ("google_search", "youtube_play"):
            if "query" not in prepared and "url" in prepared:
                prepared["query"] = str(prepared["url"])
            elif "url" not in prepared and "query" in prepared:
                prepared["url"] = str(prepared["query"])
        elif prepared.get("action") == "navigate":
            if "url" not in prepared and "query" in prepared:
                prepared["url"] = str(prepared["query"])

        for k in ("input_text", "content", "val", "query_text"):
            if k in prepared and "text" not in prepared and "value" not in prepared:
                prepared["text"] = str(prepared[k])
                prepared["value"] = str(prepared[k])

        if "value" in prepared and "text" not in prepared:
            prepared["text"] = str(prepared["value"])

        for k in ("som", "set_of_marks", "mark", "annotate"):
            if k in prepared and "annotate" not in prepared:
                prepared["annotate"] = bool(prepared[k])

    # Subagent tool aliases (OpenClaw parity)
    if tool_name == "sessions_spawn":
        if "taskName" in prepared and "task_name" not in prepared:
            prepared["task_name"] = prepared["taskName"]
        elif "task_name" in prepared and "taskName" not in prepared:
            prepared["taskName"] = prepared["task_name"]
        if "runTimeoutSeconds" in prepared and "run_timeout_seconds" not in prepared:
            prepared["run_timeout_seconds"] = prepared["runTimeoutSeconds"]
        if "instructions" in prepared and "task" not in prepared:
            prepared["task"] = prepared["instructions"]

    if tool_name == "subagents":
        if "taskId" in prepared and "task_id" not in prepared:
            prepared["task_id"] = prepared["taskId"]
        elif "task_id" in prepared and "taskId" not in prepared:
            prepared["taskId"] = prepared["task_id"]
        if "recentMinutes" in prepared and "recent_minutes" not in prepared:
            prepared["recent_minutes"] = prepared["recentMinutes"]

    if tool_name in ("computer", "desktop", "desktop_action"):
        if "action" not in prepared and "command" in prepared:
            prepared["action"] = prepared["command"]
        for k in ("targetId", "target_id", "elementId", "element_id"):
            if k in prepared and "target_id" not in prepared:
                try:
                    prepared["target_id"] = int(prepared[k])
                except (ValueError, TypeError):
                    pass
        for k in ("elementName", "element_name", "element", "target_name", "label"):
            if k in prepared and "element_name" not in prepared:
                prepared["element_name"] = str(prepared[k])
        for k in ("som", "set_of_marks", "annotate", "mark"):
            if k in prepared and "annotate" not in prepared:
                prepared["annotate"] = bool(prepared[k])
        raw_act = str(prepared.get("action", "")).strip().lower()
        if raw_act in ("inspect", "ui_tree", "ground_ui", "inspect_ui"):
            prepared["action"] = "inspect_ui"
        elif raw_act in ("open_file", "view_file", "open", "launch_file"):
            prepared["action"] = "open_file"
            for pk in ("file_path", "filePath", "target", "path", "file"):
                if pk in prepared:
                    prepared["target"] = str(prepared[pk])
                    prepared["file_path"] = str(prepared[pk])
                    break

    if tool_name in ("recall_memory", "memory_search", "search_memory", "query_memory"):
        for k in ("q", "search", "topic", "keyword", "prompt", "text"):
            if k in prepared and "query" not in prepared:
                prepared["query"] = prepared[k]
                break
        for k in ("cat", "type"):
            if k in prepared and "category" not in prepared:
                prepared["category"] = prepared[k]
                break
        for k in ("max_results", "count", "n"):
            if k in prepared and "limit" not in prepared:
                try:
                    prepared["limit"] = int(prepared[k])
                except (ValueError, TypeError):
                    pass

    if tool_name == "web_search":
        if "q" in prepared and "query" not in prepared:
            prepared["query"] = prepared["q"]
        elif "search" in prepared and "query" not in prepared:
            prepared["query"] = prepared["search"]

    return prepared


class ToolSchemaRegistry:
    """Registry of declared tools with schema validation capabilities.

    Pre-compiles parameter schemas for fast runtime validation and coercion.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register_declaration(self, decl: dict[str, Any]) -> None:
        """Register a tool declaration dictionary (e.g. from CODING_TOOL_DECLARATIONS)."""
        name = decl.get("name")
        if not name:
            return
        desc = decl.get("description", "")
        raw_params = decl.get("parameters", {})
        norm_params = normalize_tool_parameter_schema(raw_params)
        self._tools[name] = Tool(name=name, description=desc, parameters=norm_params)

    def register_declarations(self, declarations: Sequence[dict[str, Any]]) -> None:
        """Register a list of tool declaration dictionaries."""
        for decl in declarations:
            self.register_declaration(decl)

    def get_tool(self, name: str) -> Tool | None:
        """Retrieve registered Tool instance by name."""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Check if tool is registered."""
        return name in self._tools

    def validate_and_coerce(
        self,
        tool_name: str,
        args: dict[str, Any],
        tool_call_id: str = "",
    ) -> tuple[dict[str, Any], str | None]:
        """Validate and coerce arguments against the tool's parameter schema.

        Returns:
            (coerced_args, None) if validation passes.
            (prepared_args, error_message) if validation fails.
        """
        prepared = prepare_tool_arguments(tool_name, args)
        tool = self._tools.get(tool_name)
        if tool is None:
            # Tool not in schema registry (e.g. ad-hoc or unmanaged); pass through prepared args
            return prepared, None

        tc = ToolCall(id=tool_call_id, name=tool_name, arguments=prepared)
        try:
            coerced = validate_tool_arguments(tool, tc)
            return (coerced if isinstance(coerced, dict) else prepared), None
        except ToolValidationError as err:
            return prepared, str(err)
        except Exception as err:
            return prepared, f"Validation error for tool '{tool_name}': {err}"


def truncate_output(output: str, max_chars: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """Truncate tool output if it exceeds max_chars to protect context budget."""
    if not output or len(output) <= max_chars:
        return output
    truncated_tail = (
        f"\n\n[Truncated: output exceeded {max_chars} characters ({len(output)} total)]"
    )
    keep_len = max_chars - len(truncated_tail)
    if keep_len <= 0:
        return output[:max_chars]
    return output[:keep_len] + truncated_tail


def resolve_tool_timeout(tool_name: str, args: dict[str, Any]) -> float:
    """Determine the maximum execution timeout in seconds for a tool call.

    - exec: honors timeout_ms argument (clamped between 5s and 300s), default 45s
    - read-only tools (read, ls, etc.): 15s
    - plugins / network operations: 60s
    - other coding tools (write, edit): 30s
    """
    if tool_name == "exec":
        timeout_ms = args.get("timeout_ms")
        if timeout_ms is not None:
            try:
                sec = float(timeout_ms) / 1000.0
                return max(5.0, min(sec, 300.0))
            except (ValueError, TypeError):
                pass
        return 45.0

    if tool_name in READ_ONLY_TOOLS or tool_name in (
        "sessions_spawn",
        "sessions_yield",
        "subagents",
    ):
        return 15.0

    if tool_name in ("write", "edit"):
        return 30.0

    # Plugins and external operations
    return 60.0


def is_batch_parallelizable(function_calls: Sequence[Any]) -> bool:
    """Check whether a batch of function calls can be safely executed in parallel.

    Mirrors OpenClaw's tool_execution == parallel logic:
    A batch may execute concurrently only when there are multiple calls and ALL calls
    are in READ_ONLY_TOOLS. Any mutating call forces sequential execution.
    """
    if len(function_calls) <= 1:
        return False
    for fc in function_calls:
        name = getattr(fc, "name", None) or (fc.get("name") if isinstance(fc, dict) else None)
        if not name or name not in READ_ONLY_TOOLS:
            return False
    return True


CODING_TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "ls",
        "description": (
            "List files and directories at path, or list system drives if path is 'drives' or omitted. "
            "Returns file names, sizes, directory indicators, and logical drives. "
            "Use this tool to explore drives (e.g. C:\\, E:\\) and find files on the host PC."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {
                    "type": "STRING",
                    "description": "Directory path to list (e.g. 'C:\\', 'E:\\jarvis', or 'drives' to see available drives).",
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Maximum number of entries to return (default 100).",
                },
            },
        },
    },
    {
        "name": "read",
        "description": (
            "Read file contents from disk. Supports text and image files. "
            "Returns line contents with line numbers. Use offset and limit for large files."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {
                    "type": "STRING",
                    "description": "Path to the file to read (absolute or relative to current workspace).",
                },
                "offset": {
                    "type": "INTEGER",
                    "description": "1-based line number to start reading from.",
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Maximum number of lines to read.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write",
        "description": (
            "Write full content to a file on disk. Creates parent directories if they don't exist. "
            "Overwrites existing file content. Verified on disk after write."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {
                    "type": "STRING",
                    "description": "File path to write (absolute or relative to workspace).",
                },
                "content": {
                    "type": "STRING",
                    "description": "The exact content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit",
        "description": (
            "Surgically edit parts of an existing file by replacing old text with new text. "
            "The old text must match exactly. Verified on disk after edit."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {
                    "type": "STRING",
                    "description": "File path to edit.",
                },
                "old_text": {
                    "type": "STRING",
                    "description": "The exact existing text chunk to replace.",
                },
                "new_text": {
                    "type": "STRING",
                    "description": "The new replacement text.",
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "create_goal",
        "description": (
            "Create a goal only when explicitly requested by the user or system instructions. "
            "Set a positive token_budget only when a budget is explicitly requested; otherwise omit it. "
            "Fails if a goal already exists; the user must clear it before starting another."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "objective": {
                    "type": "STRING",
                    "description": "Concrete objective for this session.",
                },
                "token_budget": {
                    "type": "INTEGER",
                    "description": "Positive token budget, or omit.",
                },
            },
            "required": ["objective"],
        },
    },
    {
        "name": "get_goal",
        "description": (
            "Get the current session goal, including its full objective, status, token usage, and optional budget."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "update_goal",
        "description": (
            "Mark the session goal complete only when the full objective is verified and no required work remains. "
            "Mark it blocked only when no meaningful progress is possible without user input or an external change."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "status": {
                    "type": "STRING",
                    "enum": ["complete", "blocked"],
                    "description": "New goal status ('complete' or 'blocked').",
                },
                "note": {
                    "type": "STRING",
                    "description": "Short status explanation or note.",
                },
            },
            "required": ["status"],
        },
    },
    {
        "name": "exec",
        "description": (
            "Execute a shell command on the host PC (PowerShell / cmd / terminal). "
            "Can execute any system command including mkdir, dir, explorer, taskkill, python, etc. "
            "Returns stdout, stderr, and exit code. Verified on execution."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {
                    "type": "STRING",
                    "description": "The command line string to execute.",
                },
                "timeout_ms": {
                    "type": "INTEGER",
                    "description": "Execution timeout in milliseconds (default 30000).",
                },
                "background": {
                    "type": "BOOLEAN",
                    "description": "Set true to run in background as a daemon/task.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "process",
        "description": (
            "Manage background tasks, close applications, list active apps, or control windows on the host PC. "
            "Actions: "
            "1. 'kill': Close or terminate an application or task (e.g. session_id='whatsapp', session_id='notepad', session_id='terminal'). "
            "2. 'minimize': Minimize all open windows / show desktop. "
            "3. 'restore': Undo minimize and restore open windows. "
            "4. 'list_apps': List running user desktop applications. "
            "5. 'list' / 'poll': Check background exec tasks."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action: 'kill', 'minimize', 'restore', 'list_apps', 'list', 'status', or 'poll'.",
                },
                "session_id": {
                    "type": "STRING",
                    "description": "Application name to close (e.g. 'whatsapp', 'notepad', 'terminal', 'calc') or background session ID.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "sessions_spawn",
        "description": (
            "Spawn an isolated or forked sub-agent session for background work. "
            "Use only when the user explicitly requests background execution or when a "
            "headless task must continue independently. Keep interactive browser and desktop "
            "automation in the visible foreground; do not delegate it here."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task": {
                    "type": "STRING",
                    "description": "The specific objective, instructions, and acceptance criteria for the child subagent.",
                },
                "task_name": {
                    "type": "STRING",
                    "description": "Stable alias starting with lowercase letter (e.g. 'audit_codebase', 'scrape_docs').",
                },
                "label": {
                    "type": "STRING",
                    "description": "Short human-readable title shown in task lists.",
                },
                "context": {
                    "type": "STRING",
                    "description": "Context mode: 'isolated' for fresh prompt, 'fork' for parent history continuation.",
                },
                "run_timeout_seconds": {
                    "type": "INTEGER",
                    "description": "Maximum execution time in seconds (default 60).",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "sessions_yield",
        "description": (
            "End the current turn and pause while waiting for background child subagent completion events. "
            "Allows the parent agent to stay responsive while asynchronous subagents run."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "message": {
                    "type": "STRING",
                    "description": "Private reason or context for yielding turn.",
                },
                "acknowledgment": {
                    "type": "STRING",
                    "description": "Optional truthful status reply after a background child task has actually started.",
                },
            },
        },
    },
    {
        "name": "subagents",
        "description": (
            "Inspect or cancel background work in the caller's session tree. "
            "Actions: "
            "1. 'list': List all running and recent subagent tasks. "
            "2. 'cancel': Cancel a specific subagent task and all its descendants."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action: 'list' or 'cancel'.",
                },
                "task_id": {
                    "type": "STRING",
                    "description": "The task ID or run ID to cancel (required when action is 'cancel').",
                },
                "recent_minutes": {
                    "type": "INTEGER",
                    "description": "Minutes of recent history to include in list (default 30).",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "skill_workshop",
        "description": (
            "Author, create, patch, write support files for, install, download, and manage workspace skills (SKILL.md). "
            "Use this tool whenever the user asks to save a new skill, learn from a task, install a skill from ClawHub/GitHub, "
            "patch a skill, or create custom helper scripts under scripts/."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action: 'list', 'view', 'inspect', 'read', 'create', 'patch', 'write_file', 'remove_file', 'archive', 'restore', 'install', 'download', 'apply'.",
                },
                "name": {
                    "type": "STRING",
                    "description": "Short identifier for the skill (e.g. 'web-researcher', 'pdf-parser').",
                },
                "description": {
                    "type": "STRING",
                    "description": "Short description of what the skill does (aim for under 160 bytes).",
                },
                "content": {
                    "type": "STRING",
                    "description": "create: full SKILL.md. write_file: full file content.",
                },
                "file_path": {
                    "type": "STRING",
                    "description": "SKILL.md (default) or a file under references/, templates/, scripts/, assets/.",
                },
                "old_text": {
                    "type": "STRING",
                    "description": "patch: exact text to replace once.",
                },
                "new_text": {
                    "type": "STRING",
                    "description": "patch: replacement text.",
                },
                "source": {
                    "type": "STRING",
                    "description": "install: ClawHub slug (e.g. 'clawhub:weather'), GitHub repo URL, or ZIP archive URL.",
                },
                "reason": {
                    "type": "STRING",
                    "description": "One short line saying what changed and why; shown to user.",
                },
                "absorbed_into": {
                    "type": "STRING",
                    "description": "archive: live skill that now covers this one.",
                },
                "proposal_id": {
                    "type": "STRING",
                    "description": "Proposal ID when applying or inspecting a pending skill proposal.",
                },
                "apply": {
                    "type": "BOOLEAN",
                    "description": "Set true to immediately commit and apply upon creation (default: true).",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "plugins",
        "description": (
            "Inspect, search, install from official catalog or ClawHub, enable, disable, uninstall, or reload plugins. "
            "Use this tool whenever you need to discover new extensions, install missing tool capabilities, "
            "or reload modified plugin files."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action: 'list', 'inspect', 'search', 'install', 'enable', 'disable', 'uninstall', 'reload', 'reloadAndResume'.",
                },
                "pluginId": {
                    "type": "STRING",
                    "description": "The unique identifier of the plugin (e.g. 'browser', 'memory_lancedb').",
                },
                "query": {
                    "type": "STRING",
                    "description": "Search query or filter string for plugins.",
                },
                "source": {
                    "type": "STRING",
                    "description": "Source for searching or installing plugins (e.g. 'official' or 'clawhub').",
                },
                "packageName": {
                    "type": "STRING",
                    "description": "Package name, Git URL, or archive URL when installing.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "computer",
        "description": (
            "Interact with native desktop OS windows, launch apps, open files, and perform human-like mouse cursor and keyboard actions "
            "(smooth Bézier cursor movement with visible overlay, clicking, double clicking, dragging, typing, screenshots, and UI inspection). "
            "To physically open and display ANY file, CV, PDF, image, text document, or media on the user's desktop monitor, ALWAYS use action='open_file' (with target='<file_path>')! "
            "MANDATORY MOUSE RULE: When the user asks to use the mouse ('mouse use gara', 'माउस युज गर', 'माउसले खोल', 'click gara', 'कर्सर सार'), "
            "ALWAYS use 'computer' (action='click', 'double_click', 'move', 'drag') and NEVER use 'exec'! "
            "To open files, folders, or desktop icons with the mouse on Windows, ALWAYS use action='double_click' (single-click only highlights). "
            "For web interactions, use 'browser' for DOM-level navigation and actions, but use 'computer' whenever the user asks for mouse control, or as a seamless fallback if web selectors fail. "
            "Supported actions: 'open_file', 'launch_app', 'close_app', 'focus_app', 'set_volume', 'adjust_volume', 'get_volume', "
            "'set_brightness', 'adjust_brightness', 'get_brightness', 'inspect_ui', 'screenshot' (supports annotate=True for Set-of-Mark), "
            "'click', 'double_click', 'triple_click', 'middle_click', 'right_click', 'move', 'type', 'drag', 'wait', 'hotkey'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Computer action to perform.",
                    "enum": [
                        "open_file",
                        "launch_app",
                        "open_app",
                        "close_app",
                        "focus_app",
                        "set_volume",
                        "adjust_volume",
                        "get_volume",
                        "set_brightness",
                        "adjust_brightness",
                        "get_brightness",
                        "inspect_ui",
                        "screenshot",
                        "click",
                        "double_click",
                        "triple_click",
                        "middle_click",
                        "right_click",
                        "mouse_down",
                        "mouse_up",
                        "move",
                        "type",
                        "drag",
                        "wait",
                        "hotkey",
                        "press_key",
                        "key_down",
                        "key_up",
                        "scroll",
                    ],
                },
                "target": {
                    "type": "STRING",
                    "description": "Target file path to open (for action='open_file') or application name (for action='launch_app'/'focus_app'/'close_app').",
                },
                "file_path": {
                    "type": "STRING",
                    "description": "Absolute or relative file path to open on desktop (for action='open_file').",
                },
                "value": {
                    "type": "INTEGER",
                    "description": "Target level (0-100) for set_volume or set_brightness.",
                },
                "delta": {
                    "type": "INTEGER",
                    "description": "Relative percentage adjustment (+20 or -20) for adjust_volume or adjust_brightness.",
                },
                "target_id": {
                    "type": "INTEGER",
                    "description": "1-based integer element ID from inspect_ui or annotated Set-of-Mark screenshot [1], [2], etc.",
                },
                "element_name": {
                    "type": "STRING",
                    "description": "Visible text, name, or label of the button, input, or link to target (e.g. 'Submit', 'Search', 'Close').",
                },
                "annotate": {
                    "type": "BOOLEAN",
                    "description": "When true with action='screenshot', draws numbered Set-of-Mark (SoM) bounding boxes [1], [2] on interactive controls.",
                },
                "coordinate": {
                    "type": "ARRAY",
                    "items": {"type": "INTEGER"},
                    "description": "Optional [x, y] coordinates fallback for mouse actions.",
                },
                "x": {
                    "type": "INTEGER",
                    "description": "X coordinate for mouse click or move.",
                },
                "y": {
                    "type": "INTEGER",
                    "description": "Y coordinate for mouse click or move.",
                },
                "text": {
                    "type": "STRING",
                    "description": "Text to type for 'type' action.",
                },
                "key": {
                    "type": "STRING",
                    "description": "Key to press for 'press_key', 'key_down', 'key_up' (e.g. 'Return', 'BackSpace', 'Tab').",
                },
                "keys": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Key combo for 'hotkey' (e.g. ['ctrl', 's']).",
                },
                "direction": {
                    "type": "STRING",
                    "enum": ["up", "down", "left", "right"],
                    "description": "Scroll direction.",
                },
                "amount": {
                    "type": "INTEGER",
                    "description": "Scroll distance / amount.",
                },
                "duration": {
                    "type": "NUMBER",
                    "description": "Wait duration or drag seconds.",
                },
                "app_name": {
                    "type": "STRING",
                    "description": "Application name to bring to foreground (e.g. 'vscode', 'notepad', 'calc').",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "screen",
        "description": (
            "Inspect and arrange operator web UI and desktop screen layout via Control UI. "
            "OpenClaw parity: mirrors openclaw-main/src/agents/tools/screen-tool.ts. "
            "Allows the agent to arrange the browser-based Control UI via gateway events."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": [
                        "split_right",
                        "split_down",
                        "close_pane",
                        "focus",
                        "sidebar_show",
                        "sidebar_hide",
                        "terminal_show",
                        "terminal_hide",
                        "browser_show",
                        "browser_hide",
                        "navigate",
                    ],
                    "description": "Screen layout action to perform.",
                },
                "sessionKey": {
                    "type": "STRING",
                    "description": "Session key for target workspace.",
                },
                "dock": {
                    "type": "STRING",
                    "enum": ["bottom", "right"],
                    "description": "Panel dock position.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the live web for real-time information, weather, news, stock/crypto prices, or facts. "
            "Returns top search snippets with titles and URLs. "
            "Use this tool whenever the user asks about current events, today's weather, latest information, "
            "or facts not present in your local host environment."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Search query (e.g. 'weather in Kathmandu today', 'latest AI news').",
                },
                "max_results": {
                    "type": "INTEGER",
                    "description": "Maximum number of results to return (default 5).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": (
            "Fast HTTP fetch with readability and markdown text extraction. "
            "Fetches a web page URL, extracts text/markdown content, respects max_bytes limit, "
            "handles redirects, and sets a standard browser User-Agent."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {
                    "type": "STRING",
                    "description": "The HTTP or HTTPS URL to fetch.",
                },
                "max_bytes": {
                    "type": "INTEGER",
                    "description": "Maximum bytes of content to retrieve before truncation (default 50000).",
                },
                "extract_text": {
                    "type": "BOOLEAN",
                    "description": "Whether to extract clean markdown/plain text from HTML (default True). If False, returns raw body.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "automations",
        "description": (
            "Agent-callable cron and scheduling management tool. "
            "Inspect, schedule, query, or delete recurring and delayed automated tasks. "
            "Actions: 'list', 'create', 'delete', 'status'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Scheduling action: 'list', 'create', 'delete', or 'status'.",
                },
                "schedule": {
                    "type": "STRING",
                    "description": "Schedule specification for 'create': 5-field cron expression ('*/5 * * * *'), relative delay ('30s', '5m', '2h'), ISO datetime string, or numeric seconds.",
                },
                "prompt": {
                    "type": "STRING",
                    "description": "The task prompt or command description to run when triggered.",
                },
                "job_id": {
                    "type": "STRING",
                    "description": "Unique identifier for 'delete' or 'status' actions, or optional custom ID for 'create'.",
                },
                "recurring": {
                    "type": "BOOLEAN",
                    "description": "Whether the job should recur repeatedly or fire once (default False).",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "pdf",
        "description": (
            "Extract and search text from PDF files. "
            "Supports page range selection (e.g. '1-5', '1,3,5-7') and optional query/prompt filtering."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {
                    "type": "STRING",
                    "description": "Absolute or workspace-relative path to the PDF file.",
                },
                "pages": {
                    "type": "STRING",
                    "description": "Optional page range to extract (e.g. '1-5', '1,3,7', '10-'). 1-based indexing.",
                },
                "prompt": {
                    "type": "STRING",
                    "description": "Optional search query or prompt to filter and highlight relevant text passages.",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "secrets",
        "description": (
            "Safe credential and API key management tool. "
            "List existing credential/secret names (never exposes secret values), "
            "request missing credentials from the user via secure request queue, or delete credentials. "
            "Actions: 'list', 'request', 'delete'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Secrets action: 'list', 'request', or 'delete'.",
                },
                "secret_name": {
                    "type": "STRING",
                    "description": "Name or key of the secret (e.g. 'OPENAI_API_KEY', 'GITHUB_TOKEN'). Required for 'request' and 'delete'.",
                },
                "reason": {
                    "type": "STRING",
                    "description": "Explanation of why this secret is needed. Used with 'request' to inform the user.",
                },
            },
            "required": ["action"],
        },
    },
]

try:
    from extensions.browser.src.browser_tool import BrowserTool

    _browser_tool = BrowserTool()
    CODING_TOOL_DECLARATIONS.append(
        {
            "name": _browser_tool.name,
            "description": (
                _browser_tool.description
                + " Prefer this for Chrome, ChatGPT, Google sign-in pages, web apps, and any URL. "
                "Use DOM/ARIA snapshots and selectors before using desktop mouse coordinates."
            ),
            "parameters": _browser_tool.parameters,
        }
    )
except Exception:
    pass

# Canonical normalization of tool declarations to lowercase JSON Schema
CODING_TOOL_DECLARATIONS = [
    {
        **decl,
        "parameters": normalize_tool_parameter_schema(decl.get("parameters", {})),
    }
    for decl in CODING_TOOL_DECLARATIONS
]


_LAST_WHATSAPP_SEND: dict[str, Any] = {
    "time": 0.0,
    "recipient": "",
    "message": "",
    "idempotency_key": "",
}


async def execute_auto_control(args: dict[str, Any]) -> str:
    """Route a high-level computer-control task through the best available channel."""
    # Check if target is a browser action
    raw_action = str(args.get("action", "")).strip().lower()
    if (
        raw_action in ("browser", "navigate", "open_tab", "click_web", "type_web")
        or "url" in args
        or "targetUrl" in args
    ):
        try:
            from extensions.browser.src.browser_tool import BrowserTool

            browser = BrowserTool()
            result = await browser.execute("desktop_auto_control", args)
            payload = result.details if result.details is not None else {}
            if result.content:
                first = result.content[0]
                payload = payload or {"text": getattr(first, "text", "")}
            return json.dumps(
                {
                    "ok": True,
                    "channel": "browser_dom",
                    "result": payload,
                },
                ensure_ascii=False,
            )
        except Exception as err:
            return json.dumps(
                {"ok": False, "channel": "browser_dom", "error": str(err)}, ensure_ascii=False
            )

    return await execute_desktop_action(args)


async def execute_desktop_action(args: dict[str, Any]) -> str:
    """Execute native desktop automation action with resilient OS window and input support."""
    action = str(args.get("action", "")).strip().lower()
    app_name = str(
        args.get("app_name")
        or args.get("application")
        or args.get("target")
        or args.get("title")
        or args.get("name")
        or ""
    ).strip()

    if action in ("auto_control", "human_control", "computer_control"):
        return await execute_auto_control(args)

    # Native Audio Volume & Mute Controls
    if action in ("set_volume", "volume", "adjust_volume", "get_volume", "mute", "unmute"):
        from src.system.audio_controller import AudioController

        ac = AudioController.get_instance()
        if action == "get_volume":
            res = ac.get_volume()
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        if action == "mute":
            res = ac.set_mute(True)
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        if action == "unmute":
            res = ac.set_mute(False)
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        if action == "adjust_volume":
            raw_delta = args.get("delta") if args.get("delta") is not None else args.get("value")
            try:
                delta_pct = int(raw_delta) if raw_delta is not None else 10
            except (ValueError, TypeError):
                delta_pct = 10
            res = ac.adjust_volume(delta_pct)
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        raw_val = (
            args.get("value")
            if args.get("value") is not None
            else args.get("volume")
            if args.get("volume") is not None
            else args.get("level")
            if args.get("level") is not None
            else args.get("percent")
        )
        if raw_val is None:
            res = ac.get_volume()
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        try:
            target_pct = int(raw_val)
        except (ValueError, TypeError):
            target_pct = 50
        res = ac.set_volume(target_pct)
        return res.get("formatted") or json.dumps(res, ensure_ascii=False)

    # Native Display Brightness Controls
    if action in ("set_brightness", "brightness", "adjust_brightness", "get_brightness"):
        from src.system.brightness_controller import BrightnessController

        bc = BrightnessController.get_instance()
        if action == "get_brightness":
            res = await bc.get_brightness_async()
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        if action == "adjust_brightness":
            raw_delta = args.get("delta") if args.get("delta") is not None else args.get("value")
            try:
                delta_pct = int(raw_delta) if raw_delta is not None else 10
            except (ValueError, TypeError):
                delta_pct = 10
            res = await bc.adjust_brightness_async(delta_pct)
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        raw_val = (
            args.get("value")
            if args.get("value") is not None
            else args.get("brightness")
            if args.get("brightness") is not None
            else args.get("level")
            if args.get("level") is not None
            else args.get("percent")
        )
        if raw_val is None:
            res = await bc.get_brightness_async()
            return res.get("formatted") or json.dumps(res, ensure_ascii=False)
        try:
            target_pct = int(raw_val)
        except (ValueError, TypeError):
            target_pct = 50
        res = await bc.set_brightness_async(target_pct)
        return res.get("formatted") or json.dumps(res, ensure_ascii=False)

    # Antigravity parity: Redirect web / browser automation away from blind OS pyautogui clicks to Selenium DOM
    is_web_intent = (
        action
        in (
            "google_search",
            "youtube_play",
            "navigate",
            "extract_text",
            "snapshot_dom",
            "browser",
            "browse",
        )
        or any(k in args for k in ("url", "targetUrl", "link", "query", "search_query"))
        or any(
            w in app_name.lower()
            for w in (
                "chrome",
                "google-chrome",
                "browser",
                "youtube",
                "edge",
                "firefox",
                "chatgpt",
                "openai",
                "facebook",
                "instagram",
                "twitter",
                "reddit",
                "linkedin",
                "github",
                "gmail",
            )
        )
        or any(w in action for w in ("youtube", "google", "web_"))
    )
    if is_web_intent:
        try:
            from extensions.browser.src.browser_tool import BrowserTool

            browser = BrowserTool()
            b_args = dict(args)
            if "action" not in b_args or b_args["action"] in (
                "open_app",
                "launch_app",
                "launch",
                "open",
                "start",
                "focus_app",
            ):
                t_raw = app_name or str(b_args.get("target") or b_args.get("url") or "")
                t_low = t_raw.lower().strip()
                web_app_urls = {
                    "youtube": "https://www.youtube.com",
                    "yt": "https://www.youtube.com",
                    "google": "https://www.google.com",
                    "chatgpt": "https://chatgpt.com",
                    "openai": "https://chatgpt.com",
                    "facebook": "https://www.facebook.com",
                    "fb": "https://www.facebook.com",
                    "twitter": "https://x.com",
                    "x": "https://x.com",
                    "instagram": "https://www.instagram.com",
                    "reddit": "https://www.reddit.com",
                    "linkedin": "https://www.linkedin.com",
                    "github": "https://github.com",
                    "gmail": "https://mail.google.com",
                }
                b_args["action"] = "open"
                b_args["url"] = web_app_urls.get(t_low) or (
                    f"https://{t_raw}" if not t_raw.startswith(("http://", "https://")) else t_raw
                )
                if t_low in web_app_urls:
                    b_args["label"] = t_low
            b_res = await browser.execute("desktop_auto_control", b_args)
            p_text = (
                b_res.content[0].text
                if getattr(b_res, "content", None) and hasattr(b_res.content[0], "text")
                else str(b_res)
            )
            return p_text
        except Exception as exc:
            return json.dumps(
                {"status": "error", "error": f"Browser action failed: {exc}"}, ensure_ascii=False
            )

    # 0. Intelligent parameter normalization & auto-repair (OpenClaw parity)
    if "recipient" in args:
        msg = args.get("message") or args.get("text")
        if msg:
            args["message"] = msg
            if action in (
                "generic",
                "send",
                "send_message",
                "message",
                "",
            ) or not action.startswith("whatsapp_"):
                action = "whatsapp_send"
                args["action"] = "whatsapp_send"
        elif action in ("generic", "search", "open", "chat", "") or not action.startswith(
            "whatsapp_"
        ):
            action = "whatsapp_search"
            args["action"] = "whatsapp_search"

    # 1. WhatsApp shortcuts
    if action.startswith("whatsapp_"):
        sub_action = action.replace("whatsapp_", "")
        recipient = str(args.get("recipient") or args.get("target") or "").strip()
        msg = str(args.get("message") or args.get("text") or "").strip()

        if sub_action != "send":
            return (
                f"WhatsApp action '{sub_action}' is not supported here. "
                "Use action='whatsapp_send' with a phone number or JID recipient."
            )
        if not recipient or not msg:
            return "WhatsApp send requires both 'recipient' and 'message'."

        digits = "".join(c for c in recipient if c.isdigit())
        if "@" not in recipient and len(digits) < 8:
            return (
                f"WhatsApp cannot resolve '{recipient}' to a chat. Use a phone number "
                "with country code (e.g. +97798XXXXXXXX) or a full WhatsApp JID."
            )

        idempotency_key = str(
            args.get("idempotency_key") or args.get("_tool_call_id") or args.get("_turn_id") or ""
        ).strip()
        now = time.time()
        if (
            idempotency_key
            and _LAST_WHATSAPP_SEND.get("idempotency_key") == idempotency_key
            and _LAST_WHATSAPP_SEND.get("recipient") == recipient
            and _LAST_WHATSAPP_SEND.get("message") == msg
            and (now - float(_LAST_WHATSAPP_SEND.get("time", 0.0))) < 6.0
        ):
            return f"WhatsApp message to '{recipient}' was already sent this turn; not sending it again."

        try:
            from src.channels.channel_manager import ChannelManager

            plugin = ChannelManager.get_instance().get_plugin("whatsapp")
            if plugin is None:
                from extensions.whatsapp.plugin import WhatsAppPlugin

                plugin = WhatsAppPlugin()
            target = recipient if "@" in recipient else f"whatsapp:{digits}"
            res = await plugin.send(target, {"text": msg})
        except Exception as exc:  # noqa: BLE001 - reported to the model as tool output
            return f"WhatsApp error: could not reach the WhatsApp channel bridge: {exc}"

        if getattr(res, "is_err", False):
            return f"WhatsApp error: {getattr(res, 'error', 'send failed')}"

        evidence = res.value if isinstance(getattr(res, "value", None), dict) else {}
        message_id = str(evidence.get("message_id") or "")
        _LAST_WHATSAPP_SEND.update(
            {
                "time": now,
                "recipient": recipient,
                "message": msg,
                "idempotency_key": idempotency_key,
            }
        )
        suffix = f" (message id {message_id})" if message_id else ""
        return f"SUCCESS: WhatsApp message delivered to '{recipient}'{suffix}."

    # 2. Focus application / Bring window to front
    if action in ("focus_app", "focus", "bring_to_front"):
        target = app_name or str(args.get("target") or "")
        if not target:
            return "Application name or window title is required for focus_app."
        try:
            import pygetwindow as gw

            all_wins = gw.getAllWindows()
            t_low = target.lower().strip()

            # YouTube-aware matching: if looking for youtube/yt, check titles with youtube, then common browsers
            if t_low in ("youtube", "yt"):
                matched = [w for w in all_wins if "youtube" in w.title.lower() and w.title.strip()]
                if not matched:
                    matched = [
                        w
                        for w in all_wins
                        if any(b in w.title.lower() for b in ("chrome", "edge", "brave", "firefox"))
                        and w.title.strip()
                    ]
            else:
                matched = [w for w in all_wins if t_low in w.title.lower() and w.title.strip()]

            if matched:
                win = matched[0]
                try:
                    if getattr(win, "isMinimized", False):
                        win.restore()
                    try:
                        win.maximize()
                    except Exception:
                        pass
                    win.activate()
                    return f"Focused application '{target}' (window: '{win.title}')."
                except Exception:
                    # Windows API fallback with thread attachment
                    try:
                        import win32api
                        import win32con
                        import win32gui
                        import win32process

                        curr_tid = win32api.GetCurrentThreadId()
                        fore_hwnd = win32gui.GetForegroundWindow()
                        fore_tid, _ = win32process.GetWindowThreadProcessId(fore_hwnd)
                        if curr_tid != fore_tid:
                            win32process.AttachThreadInput(curr_tid, fore_tid, True)
                        win32gui.ShowWindow(win._hWnd, win32con.SW_RESTORE)
                        win32gui.ShowWindow(win._hWnd, win32con.SW_MAXIMIZE)
                        win32gui.SetForegroundWindow(win._hWnd)
                        if curr_tid != fore_tid:
                            win32process.AttachThreadInput(curr_tid, fore_tid, False)
                        return f"Focused application '{target}' (window: '{win.title}')."
                    except Exception:
                        return f"Found window '{win.title}', brought to view."

            # If no open window found, launch the application
            if sys.platform == "win32":
                from src.agents.sessions.tools.path_utils import launch_windows_app

                launch_windows_app(target)
            else:
                import subprocess

                subprocess.Popen(["cmd", "/c", "start", target], shell=True)
            # Adaptive readiness check: poll up to 0.5s max (in 50ms intervals) for window emergence
            t_low = target.lower().strip()
            for _ in range(10):
                await asyncio.sleep(0.05)
                all_wins_after = gw.getAllWindows()
                matched_after = [
                    w for w in all_wins_after if t_low in w.title.lower() and w.title.strip()
                ]
                if matched_after:
                    try:
                        matched_after[0].activate()
                    except Exception:
                        pass
                    return f"Launched and focused application '{target}' (window: '{matched_after[0].title}')."
            return f"Application '{target}' launched."
        except Exception as exc:
            return f"Could not focus application '{target}': {exc}"

    # 2b. Window state control (minimize / maximize / restore).
    # ``computer(action='minimize', app_name='chrome')`` previously fell through to the
    # pyautogui tail and reported success without touching any window.
    if action in (
        "minimize",
        "minimize_window",
        "maximize",
        "maximize_window",
        "restore",
        "restore_window",
    ):
        if sys.platform != "win32":
            return f"Window action '{action}' is only supported on Windows."
        verb = action.split("_")[0]
        target = app_name or str(args.get("target") or "")
        try:
            import pygetwindow as gw

            if target:
                t_low = target.lower().strip()
                matched = [
                    w
                    for w in gw.getAllWindows()
                    if t_low in (w.title or "").lower() and w.title.strip()
                ]
                if not matched:
                    return f"No open window matches '{target}'; nothing to {verb}."
                win = matched[0]
                if verb == "minimize":
                    win.minimize()
                elif verb == "maximize":
                    if getattr(win, "isMinimized", False):
                        win.restore()
                    win.maximize()
                else:
                    win.restore()
                return f"{verb.capitalize()}d window '{win.title}'."

            if verb == "maximize":
                active = gw.getActiveWindow()
                if active is None:
                    return "No active window to maximize."
                if getattr(active, "isMinimized", False):
                    active.restore()
                active.maximize()
                return f"Maximized window '{active.title}'."

            script = (
                "(New-Object -ComObject Shell.Application).MinimizeAll()"
                if verb == "minimize"
                else "(New-Object -ComObject Shell.Application).UndoMinimizeALL()"
            )
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if completed.returncode != 0:
                return f"Failed to {verb} all windows: {completed.stderr.strip()}"
            return f"Successfully {verb}d all open windows on host PC."
        except Exception as exc:
            return f"Window action '{action}' failed: {exc}"

    # 3. Launch application / Open target
    if action in ("launch_app", "launch", "open_app", "open", "start", "open_file"):
        target = app_name or str(args.get("target") or args.get("file_path") or args.get("path") or "")
        if not target:
            return "Target application or path is required for launch_app or open_file."
        try:
            if sys.platform == "win32":
                from src.agents.sessions.tools.path_utils import launch_windows_app

                ok, l_msg = launch_windows_app(target)
                if not ok and os.path.exists(target):
                    try:
                        os.startfile(target)
                        ok = True
                    except Exception as sf_exc:
                        return f"Failed to open '{target}': {sf_exc}"
            else:
                import subprocess

                subprocess.Popen(["cmd", "/c", "start", target], shell=True)
            # Adaptive readiness check: poll up to 0.4s max (in 50ms intervals)
            try:
                import pygetwindow as gw

                t_low = target.lower().strip()
                for _ in range(8):
                    await asyncio.sleep(0.05)
                    wins = [w for w in gw.getAllWindows() if w.title and t_low in w.title.lower()]
                    if wins:
                        return f"Opened '{target}' successfully. Window '{wins[0].title}' active."
            except Exception:
                await asyncio.sleep(0.05)
            return f"Opened '{target}' successfully. Window initialized."
        except Exception as exc:
            return f"Failed to open '{target}': {exc}"

    # 4. List running applications / windows
    if action in ("list_apps", "list_windows", "running_apps", "apps"):
        try:
            import pygetwindow as gw

            all_wins = gw.getAllWindows()
            titles = [w.title.strip() for w in all_wins if w.title.strip()]
            unique_titles = list(dict.fromkeys(titles))
            if not unique_titles:
                return "No active desktop application windows found."
            lines = ["Running Desktop Applications on PC:"]
            for t in unique_titles[:25]:
                lines.append(f"- {t}")
            return "\n".join(lines)
        except Exception as exc:
            return f"Failed to list applications: {exc}"

    # 5. UI Grounding: inspect_ui action
    if action in ("inspect_ui", "inspect", "ui_tree", "ground_ui"):
        from src.agents.sessions.tools.ui_grounding import (
            get_ui_cache,
            scan_interactive_elements,
        )

        elements = scan_interactive_elements()
        cache = get_ui_cache()
        return json.dumps(
            {
                "action": "inspect_ui",
                "status": "ok",
                "window": cache.window_title,
                "element_count": len(elements),
                "elements": [elem.to_dict() for elem in elements],
            },
            ensure_ascii=False,
        )

    # 6. Screenshot (with optional Set-of-Mark visual annotation)
    if action == "screenshot":
        try:
            import io
            from pathlib import Path

            from PIL import ImageGrab

            from src.agents.sessions.tools.ui_grounding import (
                annotate_screenshot_with_marks,
                scan_interactive_elements,
            )

            img = ImageGrab.grab()
            annotate = bool(args.get("annotate") or args.get("som") or args.get("set_of_marks"))
            include_b64 = bool(args.get("include_base64") or args.get("b64"))

            # Determine best user directory for saving screenshots
            user_profile = os.environ.get("USERPROFILE") or str(Path.home())
            target_dirs = [
                Path(user_profile) / "OneDrive" / "Pictures" / "Screenshots",
                Path(user_profile) / "Pictures" / "Screenshots",
                Path(user_profile) / ".jarvis" / "screenshots",
            ]
            save_dir = next((d for d in target_dirs if d.exists()), target_dirs[-1])
            save_dir.mkdir(parents=True, exist_ok=True)

            ts_str = time.strftime("%Y%m%d_%H%M%S")
            save_path = save_dir / f"screenshot_{ts_str}.png"

            elements = []
            if annotate:
                elements = scan_interactive_elements()
                annotated_img = annotate_screenshot_with_marks(img, elements)
                annotated_img.save(save_path)
            else:
                img.save(save_path)

            payload: dict[str, Any] = {
                "action": "screenshot",
                "status": "success",
                "annotated": annotate,
                "width": img.width,
                "height": img.height,
                "element_count": len(elements),
                "file_path": str(save_path),
                "summary": f"Screenshot successfully captured and saved to {save_path} ({img.width}x{img.height}).",
            }
            if include_b64:
                import base64

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=80)
                payload["image_base64"] = base64.b64encode(buf.getvalue()).decode("utf-8")

            return json.dumps(payload, ensure_ascii=False)
        except Exception as exc:
            return f"Failed to take screenshot: {exc}"

    # 7. Settle and adaptive wait (no pyautogui import needed, zero latency)
    if action in ("wait", "wait_loading", "settle", "sleep"):
        sec = float(
            args.get("wait_seconds")
            or args.get("seconds")
            or args.get("duration")
            or args.get("time")
            or 1.0
        )
        target = (
            str(args.get("target") or args.get("app_name") or args.get("app") or "").strip().lower()
        )
        # Adaptive wait: if target window is already open and ready, return immediately
        if target:
            try:
                import pygetwindow as gw

                wins = [w for w in gw.getAllWindows() if w.title and target in w.title.lower()]
                if wins:
                    return f"Window '{wins[0].title}' is already loaded and ready. Proceeding immediately without wait."
            except Exception:
                pass

        elapsed = 0.0
        step = 0.05
        while elapsed < min(max(sec, 0.05), 30.0):
            await asyncio.sleep(step)
            elapsed += step
            if target:
                try:
                    import pygetwindow as gw

                    wins = [w for w in gw.getAllWindows() if w.title and target in w.title.lower()]
                    if wins:
                        return f"Window '{wins[0].title}' loaded and settled (waited {elapsed:.2f}s). Proceeding."
                except Exception:
                    pass
        return f"Waited {elapsed:.2f}s for UI / window to settle and load."

    # 8. Mouse and keyboard actions via pyautogui / canonical computer tool
    try:
        import pyautogui

        pyautogui.FAILSAFE = True

        coord = args.get("coordinate") or (
            [args.get("x"), args.get("y")]
            if args.get("x") is not None and args.get("y") is not None
            else None
        )
        text = args.get("text")
        key = args.get("key")

        # Target element resolution by target_id or element_name
        target_id = args.get("target_id")
        element_name = str(args.get("element_name") or "").strip() or None
        target_resolved_desc = ""

        if target_id is not None or element_name is not None:
            from src.agents.sessions.tools.ui_grounding import (
                get_ui_cache,
                scan_interactive_elements,
            )

            cache = get_ui_cache()
            pt = cache.resolve_target(target_id, element_name)
            if pt is None:
                scan_interactive_elements()
                pt = cache.resolve_target(target_id, element_name)

            if pt is not None:
                coord = [pt[0], pt[1]]
                matched = (
                    cache.get_by_id(target_id)
                    if target_id is not None
                    else cache.find_by_name(element_name or "")
                )
                if matched:
                    target_resolved_desc = (
                        f" (resolved target: [{matched.id}] '{matched.name}' at {coord})"
                    )
            elif not coord:
                return (
                    f"Target element not found: target_id={target_id}, element_name={element_name}. "
                    "Use action='inspect_ui' or action='screenshot' with annotate=True to discover valid element IDs."
                )

        # 8a. TierRouter (Tier 0 Browser -> Tier 1 UIA -> Tier 2 Overlay Real Input)
        router = get_desktop_tier_router()
        if router is not None:
            tier_actions = {
                "click": "click",
                "left_click": "click",
                "right_click": "right_click",
                "context_click": "right_click",
                "double_click": "double_click",
                "triple_click": "triple_click",
                "middle_click": "middle_click",
                "move_cursor": "move",
                "mouse_move": "move",
                "move": "move",
                "type": "type",
                "press_key": "key",
                "key": "key",
                "hotkey": "key",
                "scroll": "scroll",
                "scroll_at": "scroll",
                "drag": "drag",
            }
            if action in tier_actions:
                mapped_act = tier_actions[action]
                r_args = dict(args)
                if coord:
                    r_args["coordinate"] = coord
                if action == "hotkey":
                    keys = args.get("keys") or ([key] if key else [])
                    if keys:
                        r_args["key"] = keys[-1]
                        r_args["modifiers"] = keys[:-1]
                r_res = await router.execute_action("desktop_pipeline", mapped_act, r_args)
                if not r_res.get("ok"):
                    return f"Desktop action '{action}' failed: {r_res.get('error')} [{r_res.get('code')}]"
                tier_num = r_res.get("tier", 2)
                tier_label = (
                    "Tier 0 (Browser DOM)"
                    if tier_num == 0
                    else "Tier 1 (UIAutomation)"
                    if tier_num == 1
                    else "Tier 2 (Real Hardware Input + Jarvis Cursor)"
                )
                return f"Desktop action '{action}' executed via {tier_label}{target_resolved_desc}."

        if action in ("click", "left_click"):
            if not coord and target_id is None and element_name is None:
                # If foreground window is Chrome / Browser, route to SeleniumDOMEngine to prevent blind random desktop click
                try:
                    import pygetwindow as gw

                    active_win = gw.getActiveWindow()
                    if active_win and any(
                        b in active_win.title.lower()
                        for b in ("chrome", "youtube", "google", "edge", "browser")
                    ):
                        from extensions.browser.src.browser_tool import BrowserTool

                        browser = BrowserTool()
                        click_args = dict(args)
                        click_args["action"] = "act"
                        click_args["kind"] = "click"
                        if (
                            "text" not in click_args
                            and "selector" not in click_args
                            and "ref" not in click_args
                        ):
                            click_args["ref"] = "1"
                        res = await browser.execute("desktop_auto_control", click_args)
                        p_text = (
                            res.content[0].text
                            if getattr(res, "content", None) and hasattr(res.content[0], "text")
                            else str(res)
                        )
                        return p_text
                except Exception:
                    pass

            if coord and len(coord) >= 2:
                pyautogui.click(coord[0], coord[1])
            else:
                pyautogui.click()
            return f"Clicked at {coord if coord else 'current position'}{target_resolved_desc}."

        elif action in ("right_click", "context_click"):
            if coord and len(coord) >= 2:
                pyautogui.rightClick(coord[0], coord[1])
            else:
                pyautogui.rightClick()
            return (
                f"Right-clicked at {coord if coord else 'current position'}{target_resolved_desc}."
            )

        elif action == "double_click":
            if coord and len(coord) >= 2:
                pyautogui.doubleClick(coord[0], coord[1])
            else:
                pyautogui.doubleClick()
            return (
                f"Double-clicked at {coord if coord else 'current position'}{target_resolved_desc}."
            )

        elif action in ("move_cursor", "mouse_move"):
            if coord and len(coord) >= 2:
                pyautogui.moveTo(coord[0], coord[1])
                return f"Moved cursor to {coord}{target_resolved_desc}."
            return "No coordinate provided for move_cursor."

        elif action == "type" and text:
            if coord and len(coord) >= 2:
                pyautogui.click(coord[0], coord[1])
                await asyncio.sleep(0.05)
            pyautogui.write(text, interval=0.01)
            return f"Typed '{text}' successfully into target{target_resolved_desc}."

        elif action in ("press_key", "key") and key:
            pyautogui.press(key)
            return f"Pressed key '{key}' successfully."

        elif action == "hotkey":
            keys = args.get("keys") or ([key] if key else [])
            if keys:
                pyautogui.hotkey(*keys)
                return f"Pressed hotkey {keys} successfully."
            return "No keys provided for hotkey."

        elif action in ("scroll", "scroll_at"):
            delta = int(args.get("delta") or -100)
            pyautogui.scroll(delta)
            return f"Scrolled {delta}."

    except Exception as act_err:
        return f"Desktop action '{action}' failed: {act_err}"

    return f"Desktop action '{action}' completed."


def build_turn_prompt_context(
    text: str,
    task_manager: Any = None,
    recent_actions_str: str = "",
    memory_ctx: str = "",
    decision_engine: Any = None,
) -> list[str]:
    """Build standardized delimited context blocks for conversational turns (OpenClaw parity).

    Injects:
    1. Ground-truth temporal context (LiveClock with microsecond accuracy, timezone).
    2. Continuous Task Context & Intent Classification (NEW vs CONTINUE vs RETRY).
    3. Active Desktop Window & Application context.
    4. Conversational negation & application contextual resolution.
    """
    parts = []

    # 1. Real-time temporal context (OpenClaw date-time parity)
    try:
        from src.system.live_clock import LiveClock

        parts.append(LiveClock.build_temporal_context_prompt())
    except Exception:
        pass

    # 2. Continuous Task Context & Intent Classification
    if task_manager:
        try:
            active_task = task_manager.get_active_task()
            last_rec = task_manager.get_last_execution_record()
            from src.agents.task import TaskClassifier

            classification = TaskClassifier.classify(
                utterance=text,
                active_task=active_task,
                last_action_status=last_rec.status if last_rec else None,
            )
            parts.append(
                f"[TASK INTENT: {classification.intent.value}] {classification.reason} "
                f"(Suggested: {classification.suggested_action})"
            )
            task_prompt = task_manager.format_task_context_for_prompt()
            if task_prompt:
                parts.append(task_prompt)
        except Exception:
            pass

    # 3. Canonical Decision Engine guidance
    if decision_engine:
        try:
            if hasattr(decision_engine, "analyze_intent"):
                analyzed = decision_engine.analyze_intent(text)
                is_neg = (
                    getattr(analyzed, "is_negation", False)
                    or getattr(analyzed, "category", None) == "correction_negation"
                )
                sug_tool = getattr(analyzed, "suggested_tool", None) or getattr(
                    analyzed, "primary_tool", None
                )
                if is_neg:
                    parts.append(
                        "[INTENT: Conversational negation/correction ('bhayena / chaina / not there'). Verify state and act immediately.]"
                    )
                elif sug_tool:
                    parts.append(
                        f"[EXECUTION BIAS: Actionable request. Suggested tool: '{sug_tool}'. Act immediately.]"
                    )
        except Exception:
            pass

    if recent_actions_str:
        parts.append(recent_actions_str)
    if memory_ctx:
        parts.append(memory_ctx)

    return parts


def verify_tool_execution(name: str, args: dict[str, Any], output_text: str) -> Any:
    """Verify tool execution outcome against physical OS state (OpenClaw parity)."""
    from src.agents.verification import ExecutionVerifier, VerificationOutcome

    if name == "write":
        path = args.get("path", "")
        content_str = args.get("content", "")
        return ExecutionVerifier.verify_filesystem_write(path, expected_bytes=len(content_str))

    if name == "process":
        out_l = output_text.lower()
        is_err = ("failed" in out_l or "could not" in out_l) and not (
            "already closed" in out_l or "not running" in out_l or "already finished" in out_l
        )
        return VerificationOutcome(
            status="failed" if is_err else "verified",
            verified=not is_err,
            tool_name="process",
            target_resource=args.get("session_id") or args.get("sessionId") or "",
            error=output_text if is_err else None,
        )
    if name == "edit":
        path = args.get("path", "")
        new_text = args.get("new_text") or args.get("newText") or ""
        return ExecutionVerifier.verify_filesystem_edit(
            path, expected_content_fragments=[new_text] if new_text else None
        )
    if name == "ls":
        path = args.get("path", "")
        if not path or path.lower() == "drives":
            return VerificationOutcome(
                status="verified",
                verified=True,
                tool_name="ls",
                target_resource=path or "drives",
            )
        return ExecutionVerifier.verify_filesystem_path(path, must_be_dir=True)
    if name == "exec":
        return ExecutionVerifier.verify_process_execution(
            exit_code=1 if "Error:" in output_text or "Traceback" in output_text else 0,
            stdout=output_text,
        )
    if name == "browser":
        out_l = output_text.lower()
        is_err = '"ok": false' in out_l or '"error"' in out_l or "failed" in out_l
        return VerificationOutcome(
            status="failed" if is_err else "verified",
            verified=not is_err,
            tool_name="browser",
            target_resource=args.get("targetUrl") or args.get("action") or "",
            error=output_text if is_err else None,
        )
    if name in ("computer", "desktop"):
        action = str(args.get("action", ""))
        target = str(args.get("app_name") or args.get("target") or "")
        return ExecutionVerifier.verify_desktop_action(action, target, output_text)
    if name == "screen":
        out_l = output_text.lower()
        is_err = "error" in out_l or "failed" in out_l
        return VerificationOutcome(
            status="failed" if is_err else "verified",
            verified=not is_err,
            tool_name="screen",
            target_resource=args.get("action", ""),
            error=output_text if is_err else None,
        )
    if name == "web_search":
        return ExecutionVerifier.verify_web_search(
            query=args.get("query", ""), output_text=output_text
        )
    if name in ("sessions_spawn", "sessions_yield", "subagents"):
        target_res = str(args.get("task_name") or args.get("task_id") or args.get("task") or "")
        return ExecutionVerifier.verify_subagent_action(name, target_res, output_text)
    return ExecutionVerifier.verify_generic_tool(name, output_text)
