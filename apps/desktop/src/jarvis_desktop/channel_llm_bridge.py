"""Channel LLM bridge — creates a sync LlmCallFn for the ChannelSessionRunner.

Mirrors OpenClaw's ``src/channels/llm-bridge.ts``.

The ``ChannelSessionRunner`` expects a sync
``(messages, tool_schemas, system) -> (reply_text, tool_calls)``
function. This module provides ``make_gemini_llm_fn()`` which wraps
the Google GenAI ``generate_content`` (non-streaming, non-live)
API into that shape.

The channel runner uses the *non-live* text API (not the Live WebSocket)
because:
  - Channel messages are async / user-paced, not real-time audio.
  - Tool calls need synchronous round-trip handling.
  - The Live WebSocket is for the HUD voice session only.

Phase W2: uses ``google-genai`` synchronous client. Wave 3 will add
streaming so partial replies can be sent as they arrive.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger("jarvis.channels.llm_bridge")

# Default model for channel (text) inference — lighter than the Live model.
CHANNEL_TEXT_MODEL = "gemini-2.0-flash"


def make_gemini_llm_fn(
    api_key: str,
    *,
    model: str = CHANNEL_TEXT_MODEL,
) -> "Any":
    """Return a sync ``LlmCallFn`` backed by the Gemini text API.

    The returned function has signature:
      ``(messages, tool_schemas, system) -> (reply_text | None, tool_calls)``

    Parameters
    ----------
    api_key : str
        Gemini API key.
    model : str
        Model name for channel inference (default: ``gemini-2.0-flash``).
    """
    try:
        from google import genai as _genai
        from google.genai import types as _types
    except ImportError as e:
        raise ImportError(
            "google-genai is required for the channel LLM bridge. "
            "Install it with: uv add google-genai"
        ) from e

    client = _genai.Client(api_key=api_key)

    def _llm_fn(
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
        system: str,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Call Gemini text API and return (reply_text, tool_calls)."""
        # Build contents list (Gemini format).
        contents: list[Any] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "tool":
                # Tool result — wrap as function response.
                contents.append(
                    _types.Content(
                        role="user",
                        parts=[
                            _types.Part.from_function_response(
                                name=msg.get("tool_name", "tool"),
                                response={"result": content},
                            )
                        ],
                    )
                )
            elif role == "assistant":
                contents.append(
                    _types.Content(
                        role="model",
                        parts=[_types.Part.from_text(text=content)],
                    )
                )
            else:
                contents.append(
                    _types.Content(
                        role="user",
                        parts=[_types.Part.from_text(text=content)],
                    )
                )

        # Build tools list from schemas.
        tools_arg = None
        if tool_schemas:
            try:
                fn_decls = []
                for schema in tool_schemas:
                    fn_decls.append(
                        _types.FunctionDeclaration(
                            name=schema.get("name", ""),
                            description=schema.get("description", ""),
                            parameters=schema.get("parameters"),
                        )
                    )
                tools_arg = [_types.Tool(function_declarations=fn_decls)]
            except Exception as e:  # noqa: BLE001
                _log.warning("llm_bridge: failed to build tools list: %s", e)

        # Build config.
        config = _types.GenerateContentConfig(
            system_instruction=system or None,
            tools=tools_arg,
        )

        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            _log.warning("llm_bridge: generate_content failed: %s", e)
            raise

        # Extract reply text and tool_calls.
        reply_text: str | None = None
        tool_calls: list[dict[str, Any]] = []

        candidate = response.candidates[0] if response.candidates else None
        if candidate and candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    reply_text = (reply_text or "") + part.text
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls.append(
                        {
                            "name": fc.name,
                            "args": dict(fc.args) if fc.args else {},
                            "id": getattr(fc, "id", fc.name),
                        }
                    )

        return reply_text, tool_calls

    return _llm_fn


__all__ = ["CHANNEL_TEXT_MODEL", "make_gemini_llm_fn"]
