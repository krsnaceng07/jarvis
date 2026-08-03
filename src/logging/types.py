"""jarvis.logging.types — logger settings contracts.

OpenClaw parity: mirrors ``openclaw-main/src/logging/types.ts``.

Public surface:

- :class:`LoggerSettings`
- :class:`ConsoleStyle`
"""
from __future__ import annotations

from typing import Any, Dict, Optional


#: Console output style: pretty, compact, or json.
ConsoleStyle = str  # "pretty" | "compact" | "json"


class LoggerSettings:
    """User-configurable logger settings after config/env normalization."""

    def __init__(
        self,
        level: Optional[str] = None,
        file: Optional[str] = None,
        max_file_bytes: Optional[int] = None,
        console_level: Optional[str] = None,
        console_style: Optional[str] = None,
    ) -> None:
        self.level = level
        self.file = file
        self.max_file_bytes = max_file_bytes
        self.console_level = console_level
        self.console_style = console_style

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.level is not None:
            out["level"] = self.level
        if self.file is not None:
            out["file"] = self.file
        if self.max_file_bytes is not None:
            out["maxFileBytes"] = self.max_file_bytes
        if self.console_level is not None:
            out["consoleLevel"] = self.console_level
        if self.console_style is not None:
            out["consoleStyle"] = self.console_style
        return out


__all__ = ["LoggerSettings", "ConsoleStyle"]
