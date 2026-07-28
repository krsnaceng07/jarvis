"""Vydra provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``vydra`` provider
extension (15 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin


@dataclass(frozen=True, slots=True)
class VydraProvider(ProviderPlugin):
    """Vydra provider descriptor."""

    id: str = "vydra"
    name: str = "Vydra"
    kind: str = "provider"
    default_model: str = "vydra-pro"
    max_output_tokens: int = 8192
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Provider init hook (auth + config). Stub in Phase 5.15."""
        return None

    async def complete(self, messages, **kwargs):  # type: ignore[override]
        """Streaming completion hook. Stub in Phase 5.15."""
        from jarvis_sdk import Result

        return Result.err("provider_stub", "vydra provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            'vydra-pro',
        ]


vydra_provider = VydraProvider()
entry = vydra_provider
