"""Anthropic Vertex provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``anthropic-vertex`` provider
extension (20 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin


@dataclass(frozen=True, slots=True)
class AnthropicVertexProvider(ProviderPlugin):
    """Anthropic Vertex provider descriptor."""

    id: str = "anthropic-vertex"
    name: str = "Anthropic Vertex"
    kind: str = "provider"
    default_model: str = "claude-3-5-sonnet@20241022"
    max_output_tokens: int = 8192
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Provider init hook (auth + config). Stub in Phase 5.15."""
        return None

    async def complete(self, messages, **kwargs):  # type: ignore[override]
        """Streaming completion hook. Stub in Phase 5.15."""
        from jarvis_sdk import Result

        return Result.err("provider_stub", "anthropic-vertex provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            'claude-3-5-sonnet@20241022',
        ]


anthropic_vertex_provider = AnthropicVertexProvider()
entry = anthropic_vertex_provider
