"""jarvis_desktop.tool_pipeline — Tool execution, validation, and batching pipeline.

OpenClaw parity:
- packages/llm-core/src/validation.ts (argument validation and JSON schema coercion)
- packages/agent-core/src/agent-loop.ts (prepareToolCall, validateToolArguments, sequential vs parallel batches)
- src/agents/agent-tools.schema.ts (schema normalization)
- src/agents/agent-tools.execution-validation.ts (pre-execution validation boundary)
"""

from __future__ import annotations

import copy
import json
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
        "system_info",
        "web_search",
        "web_fetch",
        "pdf",
    }
)

_BROWSER_KIND_ALIASES: dict[str, str] = {
    "clickcoords": "clickCoords",
    "scrollintoview": "scrollIntoView",
}


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

    return normalized


def prepare_tool_arguments(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Prepare and normalize tool arguments before schema validation.

    Mirrors OpenClaw's prepareToolCallArguments and prepareArguments
    compatibility shims.
    """
    prepared = copy.deepcopy(args) if isinstance(args, dict) else {}

    # Surgical edit argument aliases: support both snake_case and camelCase
    if tool_name == "edit":
        if "old_text" in prepared and "oldText" not in prepared:
            prepared["oldText"] = prepared["old_text"]
        elif "oldText" in prepared and "old_text" not in prepared:
            prepared["old_text"] = prepared["oldText"]

        if "new_text" in prepared and "newText" not in prepared:
            prepared["newText"] = prepared["new_text"]
        elif "newText" in prepared and "new_text" not in prepared:
            prepared["new_text"] = prepared["newText"]

    # Browser tool aliases and direct action normalization (OpenClaw parity)
    if tool_name == "browser":
        raw_action = prepared.get("action")
        if isinstance(raw_action, str) and raw_action.lower() in {
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
            prepared["kind"] = _BROWSER_KIND_ALIASES.get(raw_action.lower(), raw_action)
            prepared["action"] = "act"
        raw_kind = prepared.get("kind")
        if isinstance(raw_kind, str):
            prepared["kind"] = _BROWSER_KIND_ALIASES.get(raw_kind.lower(), raw_kind)

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

    if tool_name == "audio":
        if "volume" in prepared and "percent" not in prepared:
            prepared["percent"] = prepared["volume"]
        elif "value" in prepared and "percent" not in prepared:
            prepared["percent"] = prepared["value"]

    if tool_name == "system_info":
        if "type" in prepared and "action" not in prepared:
            prepared["action"] = prepared["type"]

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
    - other coding tools (write, edit, mkdir): 30s
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

    if tool_name in ("write", "edit", "mkdir", "remove_path", "rename_path", "open_path"):
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
        "name": "mkdir",
        "description": (
            "Create a directory or folder on the host PC (e.g. 'E:\\my_folder' or 'C:\\Users\\...\\Downloads\\new_dir'). "
            "Creates all parent directories automatically if needed. "
            "Use this tool whenever the user asks to create a folder or directory. "
            "Verified on disk upon creation."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {
                    "type": "STRING",
                    "description": "Path of the directory/folder to create (absolute e.g. 'E:\\my_folder' or relative).",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "remove_path",
        "description": (
            "Remove or delete a file or directory/folder on the host PC (e.g. 'E:\\my_folder' or 'C:\\Users\\...\\file.txt'). "
            "If the path is a directory, recursive=true (default) deletes the directory and all of its contents. "
            "Use this tool whenever the user asks to delete or remove a file or folder. "
            "Verified on disk upon removal."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {
                    "type": "STRING",
                    "description": "Path of the file or directory/folder to remove (absolute or relative).",
                },
                "recursive": {
                    "type": "BOOLEAN",
                    "description": "If true and path is a directory, remove recursively with all contents (default: true).",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "rename_path",
        "description": (
            "Rename or move a file or directory/folder on the host PC (e.g. rename 'E:\\old_folder' to 'E:\\new_folder'). "
            "Use this tool whenever the user asks to rename or move a file or folder. "
            "Verified on disk upon renaming."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "old_path": {
                    "type": "STRING",
                    "description": "Current path of the file or directory/folder to rename.",
                },
                "new_path": {
                    "type": "STRING",
                    "description": "New path or new name for the file or directory/folder.",
                },
            },
            "required": ["old_path", "new_path"],
        },
    },
    {
        "name": "open_path",
        "description": (
            "Open a local folder, file, drive, or application on the host PC using Windows File Explorer or default application. "
            "Examples: target='explorer', target='terminal', target='notepad', target='calc', target='E:\\', target='Downloads', target='C:\\Users\\...\\Desktop'. "
            "Use this tool whenever the user asks to open File Explorer, open a terminal, explore a drive, open a local folder/file, or launch an app. "
            "Do NOT use the browser tool for local folders or File Explorer."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "target": {
                    "type": "STRING",
                    "description": (
                        "The folder path, drive (e.g. 'E:\\', 'C:\\'), user directory ('Downloads', 'Desktop', 'Documents'), "
                        "application name ('explorer', 'terminal', 'notepad', 'calc'), or file path to open."
                    ),
                },
            },
            "required": ["target"],
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
        "name": "set_task_goal",
        "description": (
            "Initialize or update a multi-step task with a goal and sequence of steps. "
            "Maintains continuous task context across conversation turns."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {
                    "type": "STRING",
                    "description": "Overall objective of the task.",
                },
                "steps": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Ordered list of step descriptions to execute.",
                },
            },
            "required": ["goal"],
        },
    },
    {
        "name": "sessions_spawn",
        "description": (
            "Spawn an isolated or forked sub-agent session for background work. "
            "Use this tool whenever work requires multi-step research, long execution, "
            "or when parallel exploration is needed without blocking the main conversational turn."
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
                    "description": "Optional brief waiting reply to speak to the user (e.g. 'Working on that in the background, sir.').",
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
            "Author, create, inspect, and manage workspace skills (SKILL.md). "
            "Use this tool whenever the user asks to save a new skill, create a reusable capability, "
            "or manage agent skills."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action: 'create' (create new skill), 'apply' (commit proposal), 'list' (list skills), 'inspect' (read skill).",
                },
                "name": {
                    "type": "STRING",
                    "description": "Short identifier for the skill (e.g. 'git_release_manager', 'daily_briefing').",
                },
                "description": {
                    "type": "STRING",
                    "description": "Short description of what the skill does (under 160 bytes).",
                },
                "content": {
                    "type": "STRING",
                    "description": "The markdown content of the SKILL.md file with YAML frontmatter.",
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
        "name": "whatsapp_send_message",
        "description": (
            "Send an exact message to a WhatsApp contact or group on the host PC. "
            "Automatically unminimizes and restores WhatsApp to the active foreground, "
            "searches contact, opens chat, and verifies message delivery. "
            "Use this tool whenever the user asks to send a WhatsApp message."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "recipient": {
                    "type": "STRING",
                    "description": "Name of the person, contact, or group on WhatsApp.",
                },
                "message": {
                    "type": "STRING",
                    "description": "Exact text message to type and send.",
                },
            },
            "required": ["recipient", "message"],
        },
    },
    {
        "name": "whatsapp_open",
        "description": (
            "Restore, unminimize, and bring WhatsApp Desktop to the active foreground. "
            "Use this tool whenever the user asks to open or show WhatsApp."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "desktop",
        "description": (
            "Production-grade desktop application automation and UI control for Windows. "
            "Controls WhatsApp Desktop, Visual Studio Code, Antigravity IDE, Office (Word, PowerPoint, Excel), "
            "Windows Calculator, Windows Settings, File Explorer, and any desktop window. "
            "Actions: "
            "1. 'whatsapp_send': Send message on WhatsApp (params: recipient, message). "
            "2. 'whatsapp_search': Search chat/contact (params: query). "
            "3. 'whatsapp_call': Voice or video call (params: recipient, call_type). "
            "4. 'focus_app': Bring application to front without duplicate windows (params: app_name). "
            "5. 'calculate': Windows Calculator computation (params: expression). "
            "6. 'vscode_action': VS Code command/file/terminal (params: sub_action, path, command, code). "
            "7. 'office_action': Microsoft Word/PPT/Excel (params: app, sub_action, text, path). "
            "8. 'explorer_action': File Explorer (params: sub_action, path, name, query). "
            "9. 'auto_control': Let JARVIS choose browser DOM, app adapter, accessibility, or mouse/keyboard control. "
            "10. 'click', 'type', 'press_key', 'hotkey', 'scroll', 'drag', 'wait', 'screenshot': Direct desktop controls. "
            "11. 'continuity_resolve': Resolve pronoun/continuation requests ('send it', 'save it', 'pathaideu')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "Desktop action: 'whatsapp_send', 'whatsapp_search', 'whatsapp_call', 'focus_app', "
                        "'calculate', 'vscode_action', 'office_action', 'explorer_action', 'auto_control', "
                        "'click', 'double_click', 'right_click', 'type', 'press_key', 'hotkey', 'scroll', "
                        "'drag', 'wait', 'screenshot'. To send a WhatsApp message, MUST set action='whatsapp_send'."
                    ),
                    "enum": [
                        "whatsapp_send",
                        "whatsapp_search",
                        "whatsapp_call",
                        "focus_app",
                        "calculate",
                        "vscode_action",
                        "office_action",
                        "explorer_action",
                        "auto_control",
                        "click",
                        "double_click",
                        "right_click",
                        "type",
                        "press_key",
                        "hotkey",
                        "scroll",
                        "drag",
                        "wait",
                        "screenshot",
                        "continuity_resolve",
                    ],
                },
                "app_name": {
                    "type": "STRING",
                    "description": "Target application: 'whatsapp', 'vscode', 'antigravity', 'calculator', 'word', 'powerpoint', 'excel', 'settings', 'explorer'.",
                },
                "recipient": {
                    "type": "STRING",
                    "description": "Contact or chat name for messaging.",
                },
                "message": {
                    "type": "STRING",
                    "description": "Message text to type and send.",
                },
                "expression": {
                    "type": "STRING",
                    "description": "Math expression for calculator.",
                },
                "command": {
                    "type": "STRING",
                    "description": "VS Code command or natural-language user command.",
                },
                "path": {
                    "type": "STRING",
                    "description": "File or folder path.",
                },
                "text": {
                    "type": "STRING",
                    "description": "Text to insert or type.",
                },
                "x": {
                    "type": "INTEGER",
                    "description": "X coordinate for mouse click.",
                },
                "y": {
                    "type": "INTEGER",
                    "description": "Y coordinate for mouse click.",
                },
                "key": {
                    "type": "STRING",
                    "description": "Key name (e.g. 'enter', 'escape', 'tab').",
                },
                "keys": {
                    "type": "ARRAY",
                    "description": "Key combo for hotkey (e.g. ['ctrl', 's']).",
                    "items": {"type": "STRING"},
                },
                "selector": {
                    "type": "STRING",
                    "description": "DOM/CSS selector for browser automation when available.",
                },
                "ref": {
                    "type": "STRING",
                    "description": "Opaque DOM/accessibility element reference from a prior observation.",
                },
                "url": {
                    "type": "STRING",
                    "description": "Web URL for browser DOM automation.",
                },
                "direction": {
                    "type": "STRING",
                    "description": "Scroll direction: up, down, left, or right.",
                },
                "amount": {
                    "type": "INTEGER",
                    "description": "Scroll wheel amount or other action magnitude.",
                },
                "duration": {
                    "type": "NUMBER",
                    "description": "Human input duration or wait seconds.",
                },
                "confirmed": {
                    "type": "BOOLEAN",
                    "description": "True if dangerous action was explicitly confirmed by user.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "audio",
        "description": (
            "Control and inspect host PC master volume and mute status on Windows. "
            "Supported actions: "
            "1. 'get_volume': Read current volume % and mute status from Windows Core Audio. "
            "2. 'set_volume': Set master volume to an exact percentage (0 to 100). "
            "3. 'adjust_volume': Increment or decrement master volume by delta percent (e.g. +10, -15). "
            "4. 'mute': Mute system audio. "
            "5. 'unmute': Unmute system audio. "
            "6. 'toggle_mute': Toggle mute state. "
            "Always verified via hardware readback."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Audio action: 'get_volume', 'set_volume', 'adjust_volume', 'mute', 'unmute', 'toggle_mute'.",
                },
                "percent": {
                    "type": "INTEGER",
                    "description": "Target volume percentage (0 to 100) for set_volume.",
                },
                "delta": {
                    "type": "INTEGER",
                    "description": "Percentage adjustment (e.g. 10 for +10, -15 for -15) for adjust_volume.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "system_info",
        "description": (
            "Inspect ground-truth host system information, real-time clock, resources, and processes. "
            "Actions: "
            "1. 'summary': Combined overview of clock, CPU, RAM, disk, battery, and top processes. "
            "2. 'clock': Precise local time, date, day of week, UTC offset, and IANA timezone. "
            "3. 'metrics': CPU %, memory %, disk %, battery %, network IPs. "
            "4. 'processes': List top active running processes. "
            "Use this tool whenever the user asks for the current time, date, or system resource stats."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action: 'summary', 'clock', 'metrics', or 'processes'.",
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Max processes to return (default 8).",
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
    from src.application_automation.tools.youtube_tools import YOUTUBE_TOOL_DECLARATIONS

    CODING_TOOL_DECLARATIONS.extend(YOUTUBE_TOOL_DECLARATIONS)
except Exception:
    pass

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

try:
    from src.agents.sessions.tools.channel_tools import CHANNEL_TOOL_DECLARATIONS

    CODING_TOOL_DECLARATIONS.extend(CHANNEL_TOOL_DECLARATIONS)
except Exception:
    pass


_LAST_WHATSAPP_SEND: dict[str, Any] = {
    "time": 0.0,
    "recipient": "",
    "message": "",
    "idempotency_key": "",
}


async def execute_auto_control(args: dict[str, Any]) -> str:
    """Route a high-level computer-control task through the best available channel."""

    from src.desktop_automation import ControlChannel, DesktopRuntime, build_control_plan

    plan = build_control_plan(args)
    evidence: dict[str, Any] = {
        "channel": plan.channel.value,
        "action": plan.action,
        "reason": plan.reason,
        "risk": plan.risk.value,
        "requires_visual_verification": plan.requires_visual_verification,
    }

    if plan.channel is ControlChannel.BROWSER_DOM:
        try:
            from extensions.browser.src.browser_tool import BrowserTool

            browser = BrowserTool()
            result = await browser.execute("desktop_auto_control", plan.params)
            payload = result.details if result.details is not None else {}
            if result.content:
                first = result.content[0]
                payload = payload or {"text": getattr(first, "text", "")}
            return json.dumps(
                {
                    "ok": True,
                    "route": evidence,
                    "result": payload,
                    "next": "Re-observe the DOM or live visual stream before the next dependent step.",
                },
                ensure_ascii=False,
            )
        except Exception as err:
            evidence["browser_dom_error"] = str(err)

    runtime = DesktopRuntime.get_instance()
    if plan.channel is ControlChannel.ACCESSIBILITY:
        evidence["accessibility_status"] = (
            "not_available_in_this_host_slice; falling back to foreground human input if possible"
        )

    target_app = str(plan.params.get("app_name") or plan.params.get("application") or "").strip()
    target_app = target_app or runtime.context.active_application or "generic"
    res = await runtime.execute_action(target_app, plan.action, plan.params)
    return json.dumps(
        {
            "ok": res.ok,
            "route": evidence,
            "result": {
                "action": res.action,
                "application": res.application,
                "effect": res.effect.value,
                "verified": res.verified,
                "evidence": res.evidence,
                "error": res.error,
                "output_text": res.output_text,
            },
            "next": "Use the live visual stream or another observation before continuing."
            if res.ok
            else "Retry through a more specific app/browser route or ask only if the target is ambiguous.",
        },
        ensure_ascii=False,
    )


async def execute_desktop_action(args: dict[str, Any]) -> str:
    """Execute desktop automation action through DesktopRuntime with safety and continuity."""
    from src.desktop_automation import DesktopRuntime, TaskContinuity

    runtime = DesktopRuntime.get_instance()
    action = str(args.get("action", "")).strip().lower()
    app_name = str(args.get("app_name") or args.get("application") or "").strip().lower()

    if action in ("auto_control", "human_control", "computer_control"):
        return await execute_auto_control(args)

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

    # 1. Natural-language task continuity resolution
    utterance = args.get("utterance") or args.get("command")
    if utterance and (not action or action == "continuity_resolve"):
        resolver = TaskContinuity(runtime.context)
        resolved = resolver.resolve_utterance(str(utterance))
        if resolved:
            action = resolved.get("action", action)
            app_name = resolved.get("application", app_name)
            args.update(resolved)

    # 2. WhatsApp shortcuts via DesktopRuntime
    if action.startswith("whatsapp_"):
        sub_action = action.replace("whatsapp_", "")
        if sub_action in ("send", "send_message"):
            import time

            recipient = str(args.get("recipient") or args.get("target") or "").strip()
            msg = str(args.get("message") or args.get("text") or "").strip()
            idempotency_key = str(
                args.get("idempotency_key")
                or args.get("_tool_call_id")
                or args.get("_turn_id")
                or ""
            ).strip()
            now = time.time()
            if (
                idempotency_key
                and _LAST_WHATSAPP_SEND.get("idempotency_key") == idempotency_key
                and _LAST_WHATSAPP_SEND.get("recipient") == recipient
                and _LAST_WHATSAPP_SEND.get("message") == msg
                and (now - float(_LAST_WHATSAPP_SEND.get("time", 0.0))) < 6.0
            ):
                return (
                    f"SUCCESS: WhatsApp message sent to '{recipient}'. "
                    f"[TASK FULFILLED: This matching message was already sent recently; "
                    f"do not repeat this action. Confirm to the user via voice that the message was sent.]"
                )
        res = await runtime.execute_action("whatsapp", sub_action, args)
        if res.ok:
            if sub_action in ("send", "send_message"):
                import time

                recipient = args.get("recipient") or args.get("target") or "the recipient"
                _LAST_WHATSAPP_SEND["time"] = time.time()
                _LAST_WHATSAPP_SEND["recipient"] = str(recipient).strip()
                _LAST_WHATSAPP_SEND["message"] = str(
                    args.get("message") or args.get("text") or ""
                ).strip()
                _LAST_WHATSAPP_SEND["idempotency_key"] = str(
                    args.get("idempotency_key")
                    or args.get("_tool_call_id")
                    or args.get("_turn_id")
                    or ""
                ).strip()
                return (
                    f"SUCCESS: WhatsApp message sent to '{recipient}'. "
                    f"[TASK FULFILLED: The requested message has been sent to '{recipient}'. "
                    f"DO NOT invoke 'desktop' or 'open_path' again for this message. "
                    f"Confirm to the user via voice that the message was sent.]"
                )
            return res.output_text or (
                f"WhatsApp {sub_action} completed successfully. [ACTION COMPLETED: Do not repeat this call.]"
            )
        return f"WhatsApp error: {res.error}"

    # 3. Focus application
    if action in ("focus_app", "focus", "open_app"):
        target_app = app_name or str(args.get("target") or "")
        adapter = runtime.get_adapter(target_app)
        if adapter:
            focused = await adapter.ensure_running_and_focused()
            return f"Focused {adapter.app_name}." if focused else f"Could not focus {target_app}."
        wins = runtime.window_detector.find_windows_by_title(target_app)
        if wins:
            await runtime.window_manager.focus_window_async(wins[0].hwnd)
            return f"Focused window '{wins[0].title}'."
        return f"Application or window '{target_app}' not found."

    # 4. Calculate shortcut
    if action in ("calculate", "calc"):
        res = await runtime.execute_action("calculator", "calculate", args)
        return res.output_text or (
            f"Calculated: {res.evidence.get('result')}"
            if res.ok
            else f"Calculation error: {res.error}"
        )

    # 5. VS Code action
    if action == "vscode_action":
        sub_act = str(args.get("sub_action") or "run_command")
        res = await runtime.execute_action("vscode", sub_act, args)
        return f"VS Code {sub_act} completed." if res.ok else f"VS Code error: {res.error}"

    # 6. Office action
    if action == "office_action":
        suite = str(args.get("app") or "word").lower()
        sub_act = str(args.get("sub_action") or "insert_text")
        res = await runtime.execute_action(suite, sub_act, args)
        return f"Office {suite} {sub_act} completed." if res.ok else f"Office error: {res.error}"

    # 7. Explorer action
    if action == "explorer_action":
        sub_act = str(args.get("sub_action") or "navigate")
        res = await runtime.execute_action("explorer", sub_act, args)
        return f"Explorer {sub_act} completed." if res.ok else f"Explorer error: {res.error}"

    # 8. Standard desktop actions (click, type, press_key, hotkey, screenshot)
    target_app = app_name or runtime.context.active_application or "generic"
    res = await runtime.execute_action(target_app, action, args)
    if res.requires_confirmation:
        return f"CONFIRMATION REQUIRED: {res.confirmation_prompt}"
    if res.ok:
        return (
            res.output_text or f"Desktop action '{action}' executed successfully on {target_app}."
        )
    return f"Desktop action '{action}' failed: {res.error}"


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

    # 3. Active Desktop Context (Window & App)
    try:
        from src.desktop_automation import DesktopRuntime
        from src.desktop_automation.core.control_strategy import format_control_plan_for_prompt

        parts.append(format_control_plan_for_prompt())
        runtime = DesktopRuntime.get_instance()
        desktop_ctx = runtime.context.format_for_prompt()
        if desktop_ctx:
            parts.append(desktop_ctx)
    except Exception:
        pass

    # 4. Intent & application action from decision engine
    if decision_engine:
        try:
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

            from src.application_automation.contextual_resolver import ContextualResolver

            app_action = ContextualResolver().resolve_utterance(text)
            if app_action and app_action.is_contextual:
                parts.append(
                    f"[APPLICATION ACTION: App '{app_action.app_type}'. Command: '{app_action.action_name}'. {app_action.explanation}]"
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
    if name == "mkdir":
        path = args.get("path", "")
        return ExecutionVerifier.verify_filesystem_path(path, must_be_dir=True)
    if name == "remove_path":
        path = args.get("path", "")
        return ExecutionVerifier.verify_filesystem_removal(path)
    if name == "rename_path":
        old_p = args.get("old_path", "")
        new_p = args.get("new_path", "")
        return ExecutionVerifier.verify_filesystem_rename(old_p, new_p)
    if name == "open_path":
        target = args.get("target", "")
        out_l = output_text.lower()
        is_err = "failed" in out_l or "error" in out_l or "could not" in out_l
        is_pending = "pending_window" in out_l or "no foreground window was verified" in out_l
        return VerificationOutcome(
            status="failed" if is_err else ("pending" if is_pending else "verified"),
            verified=not is_err and not is_pending,
            tool_name="open_path",
            target_resource=target,
            error=output_text if is_err or is_pending else None,
        )
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
    if name == "audio":
        exp_pct = args.get("percent")
        exp_mute = (
            True
            if args.get("action") == "mute"
            else (False if args.get("action") == "unmute" else None)
        )
        return ExecutionVerifier.verify_audio_action(
            action=args.get("action", ""),
            expected_volume=int(exp_pct) if exp_pct is not None else None,
            expected_mute=exp_mute,
        )
    if name == "system_info":
        return ExecutionVerifier.verify_system_info(
            action=args.get("action", "summary"), output_text=output_text
        )
    if name == "web_search":
        return ExecutionVerifier.verify_web_search(
            query=args.get("query", ""), output_text=output_text
        )
    if name.startswith("youtube_"):
        out_l = output_text.lower()
        is_err = "error:" in out_l or "failed" in out_l or "could not" in out_l
        return VerificationOutcome(
            status="failed" if is_err else "verified",
            verified=not is_err,
            tool_name=name,
            target_resource=str(args.get("query") or args.get("title") or "youtube"),
            error=output_text if is_err else None,
        )
    if name == "desktop":
        action = str(args.get("action", ""))
        target = str(args.get("app_name") or args.get("target") or "")
        return ExecutionVerifier.verify_desktop_action(action, target, output_text)
    if name.startswith("whatsapp_"):
        recip = str(args.get("recipient") or args.get("target") or "")
        return ExecutionVerifier.verify_messaging_action("whatsapp", recip, output_text)
    if name in ("sessions_spawn", "sessions_yield", "subagents"):
        target_res = str(args.get("task_name") or args.get("task_id") or args.get("task") or "")
        return ExecutionVerifier.verify_subagent_action(name, target_res, output_text)
    if name == "set_task_goal":
        goal = str(args.get("goal") or "")
        return ExecutionVerifier.verify_generic_tool(name, output_text, goal)
    return ExecutionVerifier.verify_generic_tool(name, output_text)
