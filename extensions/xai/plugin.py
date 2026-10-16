"""xAI Grok provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``xai`` provider
extension (83 files in the OpenClaw source).
The Python port ships a focused ``ProviderPlugin`` stub so
the extension is loadable + discoverable; the full streaming
+ tool-use surface lands in Phase 5.16+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin


@dataclass(frozen=True, slots=True)
class xAIGrokProvider(ProviderPlugin):
    """xAI Grok provider descriptor."""

    id: str = "xai"
    name: str = "xAI Grok"
    kind: str = "provider"
    default_model: str = "grok-2"
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

    def register(self, api: Any) -> None:
        """Register the xAI code execution tool."""
        from .code_execution import execute_code_execution

        # Create a wrapper since the tool takes the api_key and config
        async def execute_wrapper(params: dict[str, Any]) -> Any:
            # Re-fetch credentials from metadata which is populated in init()
            cred = self.metadata.get("credentials")
            api_key = cred.api_key if cred and hasattr(cred, "api_key") else None

            # Re-fetch config from context or fallback to empty
            # In Phase 5+, plugins receive config, but for now we'll pass empty dict
            # or extract from metadata if available.
            config = self.metadata.get("config", {})

            return await execute_code_execution(
                task=params.get("task", ""), api_key=api_key, config=config
            )

        api.register_tool(
            {
                "name": "code_execution",
                "description": "Run sandboxed Python analysis with xAI. Use for calculations, tabulation, summaries, and chart-style analysis without local machine access.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "task": {
                            "type": "STRING",
                            "description": "The full analysis task for xAI's remote Python sandbox. Include any data to analyze directly in the task.",
                        }
                    },
                    "required": ["task"],
                },
                "execute": execute_wrapper,
            }
        )

    async def complete(self, messages, **kwargs):  # type: ignore[override]
        """Streaming completion hook. Stub in Phase 5.15."""
        from jarvis_sdk import Result

        return Result.err("provider_stub", "xai provider is a Phase 5.15 stub")

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            "grok-2",
            "grok-2-mini",
        ]


xai_provider = xAIGrokProvider()
entry = xai_provider
