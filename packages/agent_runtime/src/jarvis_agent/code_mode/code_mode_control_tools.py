CODE_MODE_EXEC_TOOL_NAME = "exec"
CODE_MODE_WAIT_TOOL_NAME = "wait"


def is_code_mode_control_tool(tool_name: str) -> bool:
    """Return True if the tool name is a code mode control tool (exec or wait)."""
    return tool_name in (CODE_MODE_EXEC_TOOL_NAME, CODE_MODE_WAIT_TOOL_NAME)


def mark_code_mode_control_tool(tool_def: dict) -> dict:
    """Mark a tool definition as a code mode control tool.

    This matches the OpenClaw pattern of attaching a symbol or flag
    so the system knows this tool is part of the code mode host boundary.
    """
    if "metadata" not in tool_def:
        tool_def["metadata"] = {}
    tool_def["metadata"]["isCodeModeControlTool"] = True
    return tool_def
