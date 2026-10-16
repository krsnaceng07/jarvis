"""deepseek provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``deepseek`` provider
extension (14 files in the OpenClaw source).
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
class DeepseekProvider(ProviderPlugin):
    """deepseek provider descriptor.

    Mirrors the OpenClaw ``deepseekProvider`` export: the
    LLM client reads this descriptor to discover the
    available models + the streaming contract.
    """

    id: str = "deepseek"
    name: str = "Deepseek"
    kind: str = "provider"
    default_model: str = "deepseek-chat"
    max_output_tokens: int = 8192
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

        return Result.err("provider_stub", "deepseek provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            "deepseek-chat",
            "deepseek-reasoner",
        ]


deepseek_provider = DeepseekProvider()
entry = deepseek_provider
