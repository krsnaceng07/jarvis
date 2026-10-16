"""jarvis.agents.decision.provider_decision_adapter — Provider-independent tool invocation abstractions.

OpenClaw parity: Normalizes tool calls and tool responses across Gemini Live,
Groq, and OpenAI/Anthropic formatted providers to ensure unified decision semantics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NormalizedFunctionCall:
    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedFunctionResponse:
    call_id: str
    name: str
    result_text: str
    is_error: bool = False
    details: dict[str, Any] = field(default_factory=dict)


class ProviderDecisionAdapter:
    """Adapts tool calls and function responses across differing LLM providers."""

    @classmethod
    def adapt_gemini_call(cls, fc: Any) -> NormalizedFunctionCall:
        """Adapts a Google GenAI FunctionCall instance."""
        cid = getattr(fc, "id", "") or ""
        name = getattr(fc, "name", "")
        raw_args = getattr(fc, "args", {}) or {}
        args = dict(raw_args) if isinstance(raw_args, dict) else {}
        return NormalizedFunctionCall(call_id=str(cid), name=name, arguments=args)

    @classmethod
    def adapt_openai_call(cls, tool_call: Any) -> NormalizedFunctionCall:
        """Adapts an OpenAI / Groq tool_call dictionary or object."""
        if isinstance(tool_call, dict):
            cid = tool_call.get("id", "")
            fn = tool_call.get("function", {})
            name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
        else:
            cid = getattr(tool_call, "id", "")
            fn = getattr(tool_call, "function", None)
            name = getattr(fn, "name", "") if fn else ""
            raw_args = getattr(fn, "arguments", "{}") if fn else "{}"

        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except Exception:
                args = {"raw": raw_args}
        elif isinstance(raw_args, dict):
            args = dict(raw_args)
        else:
            args = {}

        return NormalizedFunctionCall(call_id=str(cid), name=name, arguments=args)

    @classmethod
    def create_gemini_response(cls, nfr: NormalizedFunctionResponse) -> Any:
        """Constructs a Google GenAI types.FunctionResponse."""
        from google.genai import types

        resp_body: dict[str, Any] = {"result": nfr.result_text}
        if nfr.is_error:
            resp_body["error"] = True
        return types.FunctionResponse(
            id=nfr.call_id or None,
            name=nfr.name,
            response=resp_body,
        )

    @classmethod
    def create_openai_response(cls, nfr: NormalizedFunctionResponse) -> dict[str, Any]:
        """Constructs an OpenAI tool message dictionary."""
        return {
            "role": "tool",
            "tool_call_id": nfr.call_id,
            "name": nfr.name,
            "content": nfr.result_text,
        }
