"""Venice provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``venice`` provider
extension (16 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin


@dataclass(frozen=True, slots=True)
class VeniceProvider(ProviderPlugin):
    """Venice provider descriptor."""

    id: str = "venice"
    name: str = "Venice"
    kind: str = "provider"
    default_model: str = "venice-uncensored"
    max_output_tokens: int = 8192
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Provider init hook (auth + config). Stub in Phase 5.15."""
        return None

    async def complete(self, messages, **kwargs):  # type: ignore[override]
        """Streaming completion hook. Stub in Phase 5.15."""
        from jarvis_sdk import Result

        return Result.err("provider_stub", "venice provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            'venice-uncensored',
        ]


venice_provider = VeniceProvider()
entry = venice_provider
