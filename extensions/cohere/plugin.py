"""cohere provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``cohere`` provider
extension (11 files in the OpenClaw source).
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
class CohereProvider(ProviderPlugin):
    """cohere provider descriptor.

    Mirrors the OpenClaw ``cohereProvider`` export: the
    LLM client reads this descriptor to discover the
    available models + the streaming contract.
    """

    id: str = "cohere"
    name: str = "Cohere"
    kind: str = "provider"
    default_model: str = "command-a-plus-05-2026"
    max_output_tokens: int = 64000
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Provider init hook (auth + config).

        Best-effort: resolve workspace credentials via the registry/auth
        helper and attach to `self.metadata['credentials']`.
        """
        try:
            from src.sessions.credentials import resolve_credentials

            cred = resolve_credentials(provider=self.id, model=self.default_model)
            self.metadata["credentials"] = cred
        except Exception as e:
            self.metadata["credentials_error"] = str(e)
            return None

    async def complete(self, messages, **kwargs):  # type: ignore[override]
        """Streaming completion hook. Stub in Phase 5.15."""
        from jarvis_sdk import Result

        return Result.err("provider_stub", "cohere provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            "command-a-plus-05-2026",
            "command-r-plus-08-2026",
            "command-r-08-2026",
            "embed-english-v3.0",
        ]


cohere_provider = CohereProvider()
entry = cohere_provider
