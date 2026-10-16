"""JARVIS Amazon Bedrock provider extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import AmazonBedrockProvider, amazon_bedrock_provider, entry

__all__ = [
    "AmazonBedrockProvider",
    "amazon_bedrock_provider",
    "entry",
]
