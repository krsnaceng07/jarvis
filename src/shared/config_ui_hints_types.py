"""jarvis.shared.config_ui_hints_types — config UI hint types.

OpenClaw parity: mirrors ``openclaw-main/src/shared/config-ui-hints-types.ts``.
"""
from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class ConfigUiHint(TypedDict, total=False):
    """UI metadata attached to a config schema path.

    Mirrors :type:`ConfigUiHint` (``shared/config-ui-hints-types.ts``).
    """
    label: str
    help: str
    tags: List[str]
    group: str
    order: int
    advanced: bool
    sensitive: bool
    placeholder: str
    itemTemplate: Any


#: Config UI hints keyed by dotted config path, with ``*`` matching dynamic segments.
ConfigUiHints = Dict[str, ConfigUiHint]


__all__ = ["ConfigUiHint", "ConfigUiHints"]
