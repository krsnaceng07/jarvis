"""jarvis.config.types_cli — CLI config type definitions.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.cli.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict

#: CLI banner tagline mode.
CliBannerTaglineMode = Literal["random", "default", "off"]


class CliBannerConfig(TypedDict, total=False):
    taglineMode: str


class CliConfig(TypedDict, total=False):
    banner: CliBannerConfig


__all__ = [
    "CliBannerTaglineMode",
    "CliBannerConfig",
    "CliConfig",
]
