"""GitHub Copilot 2 provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``github-copilot-2`` provider
extension (33 files in the OpenClaw source).
The Python port ships a focused ``ProviderPlugin`` stub so
the extension is loadable + discoverable; the full streaming
+ tool-use surface lands in Phase 5.16+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin


@dataclass(frozen=True, slots=True)
class GitHubCopilot2Provider(ProviderPlugin):
    """GitHub Copilot 2 provider descriptor."""

    id: str = "github-copilot-2"
    name: str = "GitHub Copilot 2"
    kind: str = "provider"
    default_model: str = "gpt-4o"
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

        return Result.err("provider_stub", "github-copilot-2 provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            "gpt-4o",
        ]


github_copilot_2_provider = GitHubCopilot2Provider()
entry = github_copilot_2_provider
