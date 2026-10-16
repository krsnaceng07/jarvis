"""jarvis.config.plugin_auto_enable_types — plugin auto-enable type definitions.

OpenClaw parity: mirrors
``openclaw-main/src/config/plugin-auto-enable.types.ts``.
"""
from __future__ import annotations

from typing import Dict, List, TypedDict


#: Reasons a configured surface can cause a plugin to be auto-enabled.
#: The Python port collapses the discriminated union into a dict shape;
#: the public ``kind`` field is always present.
PluginAutoEnableCandidate = dict


class PluginAutoEnableResult(TypedDict, total=False):
    """Outcome of a plugin auto-enable pass."""

    config: dict
    changes: List[str]
    autoEnabledReasons: Dict[str, List[str]]


__all__ = [
    "PluginAutoEnableCandidate",
    "PluginAutoEnableResult",
]
