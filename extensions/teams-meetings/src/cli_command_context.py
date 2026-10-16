"""CLI command context and runtime resolution for Teams Meetings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class TeamsMeetingsCliContext:
    config: dict[str, Any] = field(default_factory=dict)
    runtime: Any = None
    json_mode: bool = False
    call_gateway: Callable[..., Any] | None = None
