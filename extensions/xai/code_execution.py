import httpx
from typing import Any, Dict, Optional

XAI_RESPONSES_ENDPOINT = "https://api.x.ai/v1/responses"
XAI_DEFAULT_CODE_EXECUTION_MODEL = "grok-4.3"


def build_missing_api_key_payload() -> Dict[str, Any]:
    """Return structured JSON error when API key is missing (xAI specific)."""
    return {
        "error": "missing_xai_api_key",
        "message": (
            "code_execution needs xAI credentials. Run `openclaw onboard --auth-choice xai-oauth` "
            "to sign in with Grok, run `openclaw onboard --auth-choice xai-api-key`, set `XAI_API_KEY` "
            "in the Gateway environment, or configure `plugins.entries.xai.config.webSearch.apiKey`."
        ),
        "docs": "https://docs.openclaw.ai/tools/code-execution",
    }


async def execute_code_execution(
    task: str, api_key: Optional[str] = None, config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Execute code_execution tool on xAI's remote sandbox."""
    if not api_key:
        # Without auth, the tool returns a structured JSON error (not a thrown exception)
        # so the agent can self-correct.
        return build_missing_api_key_payload()

    config = config or {}
    model = config.get("model", XAI_DEFAULT_CODE_EXECUTION_MODEL)
    timeout_seconds = config.get("timeoutSeconds", 30)
    max_turns = config.get("maxTurns")

    payload: Dict[str, Any] = {
        "model": model,
        "inputText": task,
        "tools": [{"type": "code_interpreter"}],
    }

    if max_turns is not None:
        payload["maxTurns"] = max_turns

    if model == XAI_DEFAULT_CODE_EXECUTION_MODEL:
        payload["reasoningEffort"] = "low"

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        try:
            response = await client.post(
                XAI_RESPONSES_ENDPOINT, json=payload, headers={"Authorization": f"Bearer {api_key}"}
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            return {"error": "xai_api_error", "message": f"xAI code execution failed: {str(e)}"}

    content = data.get("text", "")
    citations = data.get("citations", [])
    outputs = data.get("output", [])

    output_types = (
        list(set([out.get("type") for out in outputs if out.get("type")]))
        if isinstance(outputs, list)
        else []
    )

    return {
        "content": [{"type": "text", "text": content}],
        "details": {
            "citations": citations,
            "usedCodeExecution": "code_interpreter_call" in output_types,
            "outputTypes": output_types,
        },
    }
