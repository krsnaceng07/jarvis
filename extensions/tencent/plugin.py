"""Tencent Hunyuan provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``tencent`` provider
extension (16 files in the OpenClaw source).
The Python port ships a focused ``ProviderPlugin`` stub so
the extension is loadable + discoverable; the full streaming
+ tool-use surface lands in Phase 5.16+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin


@dataclass(frozen=True, slots=True)
class TencentHunyuanProvider(ProviderPlugin):
    """Tencent Hunyuan provider descriptor."""

    id: str = "tencent"
    name: str = "Tencent Hunyuan"
    kind: str = "provider"
    default_model: str = "hunyuan-pro"
    max_output_tokens: int = 8192
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Provider init hook (auth + config). Stub in Phase 5.15."""
        return None

    async def complete(self, messages, **kwargs):  # type: ignore[override]
        """Streaming completion hook. Stub in Phase 5.15."""
        from jarvis_sdk import Result

        return Result.err("provider_stub", "tencent provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            'hunyuan-pro',
        ]


tencent_provider = TencentHunyuanProvider()
entry = tencent_provider
