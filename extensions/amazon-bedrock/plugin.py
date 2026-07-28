"""Amazon Bedrock provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``amazon-bedrock`` provider
extension (100 files in the OpenClaw source).
The Python port ships a focused ``ProviderPlugin`` stub so
the extension is loadable + discoverable; the full streaming
+ tool-use surface lands in Phase 5.16+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin


@dataclass(frozen=True, slots=True)
class AmazonBedrockProvider(ProviderPlugin):
    """Amazon Bedrock provider descriptor."""

    id: str = "amazon-bedrock"
    name: str = "Amazon Bedrock"
    kind: str = "provider"
    default_model: str = "anthropic.claude-3-5-sonnet"
    max_output_tokens: int = 8192
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Provider init hook (auth + config). Stub in Phase 5.15."""
        return None

    async def complete(self, messages, **kwargs):  # type: ignore[override]
        """Streaming completion hook. Stub in Phase 5.15."""
        from jarvis_sdk import Result

        return Result.err("provider_stub", "amazon-bedrock provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            'anthropic.claude-3-5-sonnet',
            'meta.llama3-70b',
        ]


amazon_bedrock_provider = AmazonBedrockProvider()
entry = amazon_bedrock_provider
