"""Diffs Language Pack infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``diffs-language-pack`` infra
extension (8 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class DiffsLanguagePackPlugin(Plugin):
    """Diffs Language Pack infra descriptor."""

    id: str = "diffs-language-pack"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Syntax-highlight language pack for diffs."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


diffs_language_pack_plugin = DiffsLanguagePackPlugin()
entry = diffs_language_pack_plugin
