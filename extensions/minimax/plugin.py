"""Minimax provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``minimax`` provider
extension (41 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin


@dataclass(frozen=True, slots=True)
class MinimaxProvider(ProviderPlugin):
    """Minimax provider descriptor."""

    id: str = "minimax"
    name: str = "Minimax"
    kind: str = "provider"
    default_model: str = "MiniMax-pro"
    max_output_tokens: int = 8192
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Provider init hook (auth + config). Stub in Phase 5.15."""
        return None

    async def complete(self, messages, **kwargs):  # type: ignore[override]
        """Streaming completion hook. Stub in Phase 5.15."""
        from jarvis_sdk import Result

        return Result.err("provider_stub", "minimax provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            'MiniMax-pro',
        ]


minimax_provider = MinimaxProvider()
entry = minimax_provider
