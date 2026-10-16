"""Google Gemini provider plugin definition.

OpenClaw parity: mirrors the OpenClaw ``google`` provider
extension (89 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ProviderPlugin


@dataclass(frozen=True, slots=True)
class GoogleGeminiProvider(ProviderPlugin):
    """Google Gemini provider descriptor."""

    id: str = "google"
    name: str = "Google Gemini"
    kind: str = "provider"
    default_model: str = "gemini-2.0-flash"
    max_output_tokens: int = 8192
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Provider init hook (auth + config).

        Resolve credentials via the model registry and attach them to
        `self.metadata['credentials']` for consumer clients.
        """
        try:
            from src.sessions.credentials import resolve_credentials

            cred = resolve_credentials(provider="google", model=self.default_model)
            self.metadata["credentials"] = cred
        except Exception as e:
            self.metadata["credentials_error"] = str(e)
            raise

    async def complete(self, messages, **kwargs):  # type: ignore[override]
        """Streaming completion hook. Kept for legacy callers."""
        from jarvis_sdk import Result

        return Result.err("provider_stub", "use stream_simple instead")

    async def stream_simple(self, model: Any, context: Any, options: Any = None):
        """Yields AssistantMessageEvent stream compatible with jarvis_agent."""
        try:
            from google import genai as _genai
            from google.genai import types as _types
        except ImportError as e:
            raise ImportError(
                "google-genai is required for the google provider. "
                "Install it with: uv add google-genai"
            ) from e

        model_id = model.id if hasattr(model, "id") else self.default_model
        system = context.system if hasattr(context, "system") else ""
        messages = context.messages if hasattr(context, "messages") else []
        tools = context.tools if hasattr(context, "tools") else []

        api_key = self.metadata.get("credentials")
        if not api_key:
            raise RuntimeError("Missing Google Gemini credentials.")

        client = _genai.Client(api_key=api_key)

        contents: list[Any] = []
        for msg in messages:
            role = msg.role
            content = msg.content if hasattr(msg, "content") and msg.content else ""

            if role == "toolResult":
                tool_call_id = getattr(msg, "toolCallId", "tool")
                contents.append(
                    _types.Content(
                        role="user",
                        parts=[
                            _types.Part.from_function_response(
                                name=getattr(msg, "toolName", tool_call_id),
                                response={"result": content},
                            )
                        ],
                    )
                )
            elif role == "assistant":
                tool_calls = getattr(msg, "toolCalls", [])
                if tool_calls:
                    parts = []
                    if content:
                        parts.append(_types.Part.from_text(text=content))
                    for tc in tool_calls:
                        parts.append(
                            _types.Part.from_function_call(
                                name=tc.name,
                                args=tc.args,
                            )
                        )
                    contents.append(_types.Content(role="model", parts=parts))
                else:
                    contents.append(
                        _types.Content(
                            role="model",
                            parts=[_types.Part.from_text(text=content)],
                        )
                    )
            else:
                if content:
                    contents.append(
                        _types.Content(
                            role="user",
                            parts=[_types.Part.from_text(text=content)],
                        )
                    )

        gemini_tools = None
        if tools:
            func_decls = []
            for schema in tools:
                func_decls.append(
                    _types.FunctionDeclaration(
                        name=schema.name,
                        description=schema.description or "",
                        parameters=schema.parameters or {},
                    )
                )
            gemini_tools = [_types.Tool(function_declarations=func_decls)]

        config = _types.GenerateContentConfig(
            system_instruction=system if system else None,
            tools=gemini_tools,
        )

        response_stream = await client.aio.models.generate_content_stream(
            model=model_id,
            contents=contents,
            config=config,
        )

        async for chunk in response_stream:
            if chunk.text:
                yield {
                    "type": "text-chunk",
                    "text": chunk.text,
                }
            if chunk.function_calls:
                for fc in chunk.function_calls:
                    yield {
                        "type": "tool-call",
                        "toolCall": {
                            "id": fc.name,
                            "name": fc.name,
                            "args": fc.args,
                        },
                    }

        yield {
            "type": "done",
            "finishReason": "stop",
        }

    def list_models(self) -> list[str]:  # type: ignore[override]
        """Catalog of available models. Stub in Phase 5.15."""
        return [
            "gemini-2.0-flash",
            "gemini-1.5-pro",
        ]

    def register(self, api: Any) -> None:
        """Register Google provider and embedding adapter with host."""
        from .memory_embedding_adapter import gemini_memory_embedding_adapter

        api.register_embedding_provider(gemini_memory_embedding_adapter)


google_provider = GoogleGeminiProvider()
entry = google_provider

