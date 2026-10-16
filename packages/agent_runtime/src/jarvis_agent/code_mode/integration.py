from typing import Any, List

from .code_mode_control_tools import CODE_MODE_EXEC_TOOL_NAME, CODE_MODE_WAIT_TOOL_NAME


def get_code_mode_tools(catalog: List[Any]) -> List[Any]:
    """Return the tool definitions for exec and wait based on the current catalog.

    In code mode, the model only sees these two tools.
    """
    exec_tool = {
        "name": CODE_MODE_EXEC_TOOL_NAME,
        "description": "Execute a JavaScript program to automate calling tools. Use this to perform complex logic, search for tools, and invoke APIs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "The JavaScript source code to execute.",
                }
            },
            "required": ["source"],
        },
    }

    wait_tool = {
        "name": CODE_MODE_WAIT_TOOL_NAME,
        "description": "Wait for pending tool requests to complete and resume execution.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    }

    return [exec_tool, wait_tool]


def filter_tools_for_code_mode(catalog: List[Any], code_mode_enabled: bool) -> List[Any]:
    """Return the final list of tools for the payload based on Code Mode configuration."""
    if not code_mode_enabled:
        return catalog

    return get_code_mode_tools(catalog)
