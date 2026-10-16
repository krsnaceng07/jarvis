"""Built-in realtime voice tools: openclaw_end_call and openclaw_agent_consult."""

from __future__ import annotations

from typing import Any, Callable, Coroutine

from ..types import CallSession

SAFE_READ_ONLY_TOOLS = {
    "read",
    "web_search",
    "web_fetch",
    "x_search",
    "memory_search",
    "memory_get",
}


def get_realtime_tools_definitions(
    *,
    tool_policy: str = "safe-read-only",
    custom_tools: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Declare realtime tool definitions exposed to Gemini Live / OpenAI Realtime."""
    tools: list[dict[str, Any]] = [
        {
            "name": "openclaw_end_call",
            "description": (
                "End the live telephone call immediately. Call this tool when the user asks to hang up "
                "or says goodbye. Speak any final closing words before invoking this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        }
    ]

    if tool_policy != "none":
        tools.append(
            {
                "name": "openclaw_agent_consult",
                "description": (
                    "Consult the full AI agent for deeper reasoning, fact-checking, memory lookups, "
                    "or running workspace tools. Returns the agent's answer to incorporate into your response."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The specific question or task to consult the agent on.",
                        }
                    },
                    "required": ["question"],
                    "additionalProperties": False,
                },
            }
        )

    if custom_tools:
        tools.extend(custom_tools)

    return tools


def get_consult_policy_guidance(consult_policy: str = "auto") -> str:
    """Generate guidance instructions for when the model should call openclaw_agent_consult."""
    pol = consult_policy.lower().strip()
    if pol == "substantive":
        return (
            "Consult Guidance: Handle simple conversational greetings, small talk, and acknowledgment directly. "
            "Call openclaw_agent_consult before answering questions requiring factual information, memory lookups, "
            "computations, or external tools."
        )
    elif pol == "always":
        return "Consult Guidance: Call openclaw_agent_consult before answering every substantive question."
    else:  # "auto"
        return "Consult Guidance: Call openclaw_agent_consult whenever deeper reasoning or external information is needed."


async def execute_realtime_tool(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    session: CallSession,
    tool_policy: str = "safe-read-only",
    on_end_call: Callable[[], Coroutine[Any, Any, None]] | None = None,
    agent_consult_handler: Callable[[str, list[str] | None], Coroutine[Any, Any, str]]
    | None = None,
) -> dict[str, Any]:
    """Execute a tool call invoked by the realtime voice model."""
    name = tool_name.strip()

    if name in ("openclaw_end_call", "jarvis_end_call"):
        if on_end_call:
            await on_end_call()
        session.status = "completed"
        return {"status": "ended", "callId": session.id}

    if name in ("openclaw_agent_consult", "jarvis_agent_consult"):
        if tool_policy == "none":
            return {"error": "Agent consult tool is disabled by toolPolicy: none"}

        question = str(arguments.get("question") or "")
        allowed_tools = list(SAFE_READ_ONLY_TOOLS) if tool_policy == "safe-read-only" else None

        if agent_consult_handler:
            answer = await agent_consult_handler(question, allowed_tools)
            return {"answer": answer, "question": question}

        return {"answer": f"Consult result for: {question}", "question": question}

    return {"error": f"Unknown realtime tool: {name}"}
