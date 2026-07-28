"""Anthropic provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``anthropic`` provider
extension (50 files in the OpenClaw source). The Python
port ships a focused ``ProviderPlugin`` stub so the
extension is loadable + discoverable; the full streaming
+ tool-use + multi-account + image-input surface lands
incrementally in Phase 5.16+ (the provider port).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin


@dataclass(frozen=True, slots=True)
class AnthropicProvider(ProviderPlugin):
    """Anthropic provider descriptor.

    Mirrors the OpenClaw ``anthropicProvider`` export: the
    LLM client reads this descriptor to discover the
    available models + the streaming contract.
    """

    id: str = "anthropic"
    name: str = "Anthropic"
    kind: str = "provider"
    default_model: str = "claude-sonnet-4-6"
    max_output_tokens: int = 8192
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Provider init hook (auth + config). Stub in Phase 5.15."""
        # Real implementation lands in Phase 5.16 (the provider port).
        return None

    async def complete(self, messages, **kwargs):  # type: ignore[override]
        """Streaming completion hook. Stub in Phase 5.15.

        Returns a ``Result.err`` with a ``not_implemented`` code
        so callers can detect that the surface is not yet wired
        without crashing.
        """
        from jarvis_sdk import Result

        return Result.err("provider_stub", "anthropic provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [self.default_model]


anthropic_provider = AnthropicProvider()
entry = anthropic_provider
