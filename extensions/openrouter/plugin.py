"""OpenRouter provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``openrouter`` provider
extension (36 files in the OpenClaw source).
The Python port ships a focused ``ProviderPlugin`` stub so
the extension is loadable + discoverable; the full streaming
+ tool-use surface lands in Phase 5.16+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin


@dataclass(frozen=True, slots=True)
class OpenRouterProvider(ProviderPlugin):
    """OpenRouter provider descriptor."""

    id: str = "openrouter"
    name: str = "OpenRouter"
    kind: str = "provider"
    default_model: str = "openrouter/auto"
    max_output_tokens: int = 8192
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Provider init hook (auth + config).

        Resolve credentials from the model registry and attach them to
        `self.metadata['credentials']` for clients to use.
        """
        try:
            from src.sessions.credentials import resolve_credentials

            cred = resolve_credentials(provider="openrouter", model=self.default_model)
            self.metadata["credentials"] = cred
        except Exception as e:
            self.metadata["credentials_error"] = str(e)
            raise

    async def complete(self, messages, **kwargs):  # type: ignore[override]
        """Streaming completion hook. Stub in Phase 5.15."""
        from jarvis_sdk import Result

        return Result.err("provider_stub", "openrouter provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            "openrouter/auto",
            "anthropic/claude-3.5-sonnet",
        ]


openrouter_provider = OpenRouterProvider()
entry = openrouter_provider
