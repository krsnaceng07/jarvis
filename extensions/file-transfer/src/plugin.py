"""File Transfer plugin entrypoint.

Registers file_fetch, dir_list, dir_fetch, file_write tools and CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin
from .tools import register_file_transfer_tools


@dataclass(frozen=True, slots=True)
class FileTransferPlugin(Plugin):
    """File Transfer extension plugin."""

    id: str = "file-transfer"
    kind: str = "tools"
    version: str = "0.1.0"
    description: str = "Fetch, list, and write files on paired nodes and local system."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Register file transfer tools and doctor."""
        register_file_transfer_tools(ctx)


file_transfer_plugin = FileTransferPlugin()
entry = file_transfer_plugin
