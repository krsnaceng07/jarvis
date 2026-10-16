"""File Transfer tool definitions and registrations."""

from __future__ import annotations

import base64
from typing import Any

from .operations import fetch_dir, fetch_file, list_dir, write_file
from .policy import check_path_policy


async def execute_file_fetch_tool(params: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Execute file_fetch tool."""
    path_val = params.get("path") or params.get("filePath")
    if not path_val:
        return {"error": "Missing required parameter 'path'"}

    max_bytes = params.get("maxBytes", 16 * 1024 * 1024)
    node_id = params.get("nodeId", "local")

    allowed, reason = check_path_policy(node_id, "read", str(path_val))
    if not allowed:
        return {"error": reason or "Permission denied"}

    try:
        res = fetch_file(str(path_val), max_bytes=max_bytes)
        return {"content": [{"type": "text", "text": res["content"]}], "details": res}
    except Exception as err:
        return {"error": str(err)}


async def execute_file_write_tool(params: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Execute file_write tool."""
    path_val = params.get("path") or params.get("filePath")
    content = params.get("content")
    if not path_val or content is None:
        return {"error": "Missing required parameters 'path' and 'content'"}

    is_base64 = params.get("isBase64", False)
    overwrite = params.get("overwrite", True)
    node_id = params.get("nodeId", "local")

    allowed, reason = check_path_policy(node_id, "write", str(path_val))
    if not allowed:
        return {"error": reason or "Permission denied"}

    try:
        res = write_file(str(path_val), content, is_base64=is_base64, overwrite=overwrite)
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Successfully wrote {res['bytesWritten']} bytes to {res['path']}",
                }
            ],
            "details": res,
        }
    except Exception as err:
        return {"error": str(err)}


async def execute_dir_list_tool(params: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Execute dir_list tool."""
    path_val = params.get("path") or params.get("dirPath") or "."
    recursive = params.get("recursive", False)
    max_depth = params.get("maxDepth", 5)
    node_id = params.get("nodeId", "local")

    allowed, reason = check_path_policy(node_id, "list", str(path_val))
    if not allowed:
        return {"error": reason or "Permission denied"}

    try:
        res = list_dir(str(path_val), recursive=recursive, max_depth=max_depth)
        summary = f"Found {res['count']} entries in {res['path']}"
        return {"content": [{"type": "text", "text": summary}], "details": res}
    except Exception as err:
        return {"error": str(err)}


async def execute_dir_fetch_tool(params: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Execute dir_fetch tool."""
    path_val = params.get("path") or params.get("dirPath")
    if not path_val:
        return {"error": "Missing required parameter 'path'"}

    archive_format = params.get("format", "zip")
    node_id = params.get("nodeId", "local")

    allowed, reason = check_path_policy(node_id, "archive", str(path_val))
    if not allowed:
        return {"error": reason or "Permission denied"}

    try:
        raw_zip = fetch_dir(str(path_val), archive_format=archive_format)
        encoded = base64.b64encode(raw_zip).decode("ascii")
        return {
            "content": [{"type": "text", "text": f"Archive generated ({len(raw_zip)} bytes)"}],
            "details": {"bytes": len(raw_zip), "data": encoded, "format": archive_format},
        }
    except Exception as err:
        return {"error": str(err)}


def register_file_transfer_tools(api: Any) -> None:
    """Register file transfer tools with the plugin API."""
    if hasattr(api, "register_tool"):
        api.register_tool(
            name="file_fetch",
            description="Fetch file contents from local system or paired node.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "path": {"type": "STRING", "description": "File path to fetch."},
                    "maxBytes": {"type": "NUMBER", "description": "Maximum bytes to read."},
                    "nodeId": {"type": "STRING", "description": "Target node ID."},
                },
                "required": ["path"],
            },
            execute=execute_file_fetch_tool,
        )
        api.register_tool(
            name="file_write",
            description="Write file contents on local system or paired node.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "path": {"type": "STRING", "description": "File path to write."},
                    "content": {"type": "STRING", "description": "File content."},
                    "isBase64": {
                        "type": "BOOLEAN",
                        "description": "Whether content is base64 encoded.",
                    },
                    "overwrite": {
                        "type": "BOOLEAN",
                        "description": "Whether to overwrite existing file.",
                    },
                    "nodeId": {"type": "STRING", "description": "Target node ID."},
                },
                "required": ["path", "content"],
            },
            execute=execute_file_write_tool,
        )
        api.register_tool(
            name="dir_list",
            description="List directory contents on local system or paired node.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "path": {"type": "STRING", "description": "Directory path."},
                    "recursive": {"type": "BOOLEAN", "description": "Scan recursively."},
                    "maxDepth": {
                        "type": "NUMBER",
                        "description": "Maximum depth for recursive scan.",
                    },
                    "nodeId": {"type": "STRING", "description": "Target node ID."},
                },
            },
            execute=execute_dir_list_tool,
        )
        api.register_tool(
            name="dir_fetch",
            description="Fetch a directory archive as a zip package.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "path": {"type": "STRING", "description": "Directory path to package."},
                    "format": {"type": "STRING", "description": "Archive format (zip)."},
                    "nodeId": {"type": "STRING", "description": "Target node ID."},
                },
                "required": ["path"],
            },
            execute=execute_dir_fetch_tool,
        )
