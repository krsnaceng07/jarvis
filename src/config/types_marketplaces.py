"""jarvis.config.types_marketplaces — marketplace feed + package source types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.marketplaces.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Verification modes for marketplace feeds.
MarketplaceVerificationMode = Literal["unsigned", "signed"]
#: Source profile types.
MarketplaceSourceType = Literal["npm", "clawhub", "git"]


class MarketplaceFeedKeyConfig(TypedDict, total=False):
    keyId: str
    publicKey: str


class MarketplaceFeedVerificationConfig(TypedDict, total=False):
    mode: str
    keys: list
    threshold: int


class MarketplaceFeedProfileConfig(TypedDict, total=False):
    url: str
    verification: MarketplaceFeedVerificationConfig


class MarketplaceSourceProfileConfig(TypedDict, total=False):
    type: str


class MarketplacesConfig(TypedDict, total=False):
    feeds: dict
    sources: dict


__all__ = [
    "MarketplaceVerificationMode",
    "MarketplaceSourceType",
    "MarketplaceFeedKeyConfig",
    "MarketplaceFeedVerificationConfig",
    "MarketplaceFeedProfileConfig",
    "MarketplaceSourceProfileConfig",
    "MarketplacesConfig",
]
