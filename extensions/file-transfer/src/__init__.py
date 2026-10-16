"""File Transfer extension package."""

from __future__ import annotations

from .cli import handle_file_transfer_cli, repair_file_transfer_config
from .operations import fetch_dir, fetch_file, list_dir, write_file
from .plugin import FileTransferPlugin, entry, file_transfer_plugin
from .policy import (
    MAX_FILE_BYTES,
    LiteralGrant,
    NodePolicyConfig,
    check_path_policy,
    is_path_contained_in,
    normalize_path_for_policy,
)
from .tools import (
    execute_dir_fetch_tool,
    execute_dir_list_tool,
    execute_file_fetch_tool,
    execute_file_write_tool,
    register_file_transfer_tools,
)

__all__ = [
    "FileTransferPlugin",
    "LiteralGrant",
    "MAX_FILE_BYTES",
    "NodePolicyConfig",
    "check_path_policy",
    "entry",
    "execute_dir_fetch_tool",
    "execute_dir_list_tool",
    "execute_file_fetch_tool",
    "execute_file_write_tool",
    "fetch_dir",
    "fetch_file",
    "file_transfer_plugin",
    "handle_file_transfer_cli",
    "is_path_contained_in",
    "list_dir",
    "normalize_path_for_policy",
    "register_file_transfer_tools",
    "repair_file_transfer_config",
    "write_file",
]
