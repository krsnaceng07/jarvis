"""Teams Meetings extension package."""

from __future__ import annotations

from .config import TeamsMeetingsConfig, resolve_teams_meetings_config
from .node_invoke_policy import (
    TeamsMeetingsChromeNodeInvokePolicy,
    create_teams_meetings_chrome_node_invoke_policy,
)
from .runtime import TeamsMeetingsRuntime
from .teams_url import (
    is_consumer_teams_url,
    is_valid_teams_host,
    is_work_teams_url,
    normalize_teams_url,
)

__all__ = [
    "TeamsMeetingsChromeNodeInvokePolicy",
    "TeamsMeetingsConfig",
    "TeamsMeetingsRuntime",
    "create_teams_meetings_chrome_node_invoke_policy",
    "is_consumer_teams_url",
    "is_valid_teams_host",
    "is_work_teams_url",
    "normalize_teams_url",
    "resolve_teams_meetings_config",
]
