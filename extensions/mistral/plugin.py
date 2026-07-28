"""mistral provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``mistral`` provider
extension (17 files in the OpenClaw source).
The Python port ships a focused ``ProviderPlugin`` stub so
the extension is loadable + discoverable; the full streaming
+ tool-use + model-catalog surface lands incrementally in
Phase 5.16+ (the provider port).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin


@dataclass(frozen=True, slots=True)
class MistralProvider(ProviderPlugin):
    """mistral provider descriptor.

    Mirrors the OpenClaw ``mistralProvider`` export: the
    LLM client reads this descriptor to discover the
    available models + the streaming contract.
    """

    id: str = "mistral"
    name: str = "Mistral"
    kind: str = "provider"
    default_model: str = "mistral-large-latest"
    max_output_tokens: int = 8192
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Provider init hook (auth + config). Stub in Phase 5.15."""
        return None

    async def complete(self, messages, **kwargs):  # type: ignore[override]
        """Streaming completion hook. Stub in Phase 5.15."""
        from jarvis_sdk import Result

        return Result.err("provider_stub", "mistral provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            "mistral-large-latest",
            "mistral-small-latest",
            "codestral-latest",
            "pixtral-large-latest",
        ]


mistral_provider = MistralProvider()
entry = mistral_provider
