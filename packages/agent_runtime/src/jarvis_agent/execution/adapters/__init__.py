"""Execution adapters package for Track 3.2."""

from jarvis_agent.execution.adapters.base import (
    AdapterExecutionOutput,
    BaseExecutionAdapter,
)
from jarvis_agent.execution.adapters.browser import BrowserAdapter, BrowserTabState
from jarvis_agent.execution.adapters.channels import ChannelAdapter
from jarvis_agent.execution.adapters.desktop import DesktopAdapter
from jarvis_agent.execution.adapters.filesystem import FilesystemAdapter
from jarvis_agent.execution.adapters.process import ProcessAdapter
from jarvis_agent.execution.adapters.system import SystemAdapter

__all__ = [
    "AdapterExecutionOutput",
    "BaseExecutionAdapter",
    "BrowserAdapter",
    "BrowserTabState",
    "ChannelAdapter",
    "DesktopAdapter",
    "FilesystemAdapter",
    "ProcessAdapter",
    "SystemAdapter",
]
