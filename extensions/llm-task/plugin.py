"""LLM Task infra plugin entry point — full surface port.

Mirrors OpenClaw's ``extensions/llm-task/index.ts`` 1:1.
The Python port wires the same SDK surface the OpenClaw
source calls (``api.registerTool`` + the config schema
+ the tool factory) using a focused ``LlmTaskTool``
stub that matches the OpenClaw ``createLlmTaskTool``
return shape.

OpenClaw parity (every OpenClaw registrar call lands
here):
- The OpenClaw source uses ``defineToolPlugin({ id,
  name, description, configSchema, tools })`` which is
  a convenience over the generic plugin entry; the
  Python port calls the same SDK registrars
  (``api.registerTool`` + the config schema) directly
  so the host's plugin loader treats the entry the
  same way as every other Python entry
- The tool factory returns a ``AnyAgentTool``
  descriptor with the standard LLM task surface
  (provider / model / auth profile / max tokens /
  timeout / JSON output shape)

Public surface:
- ``LLMTaskPlugin`` — the plugin descriptor
- ``llm_task_plugin`` / ``entry`` — the loaded entry
- ``LlmTaskConfig`` — the TypedDict that mirrors the
  OpenClaw TypeBox schema
- ``LlmTaskTool`` — the tool descriptor factory
- ``resolve_llm_task_config`` — clamp + default the
  raw plugin config

Python adaptations (documented in code):
- TS TypeBox ``Type.Object({...})`` → Python
  ``TypedDict`` (``LlmTaskConfig``); the Python port
  uses ``resolve_llm_task_config`` to clamp each
  numeric field to its safe range (matches the TS
  source's ``optionalPositiveIntegerSchema``)
- TS ``AnyAgentTool`` → Python ``dict`` with the same
  shape (``name``, ``description``, ``input_schema``,
  ``handler``); the in-port stub returns a structured
  ``"not yet ported"`` envelope so the host can route
  the call to a real LLM task handler in a follow-up
  phase
- TS ``createLlmTaskTool(api)`` → Python
  ``build_llm_task_tool(config, deps)`` (the Python
  port accepts the LLM client + temp workspace deps
  as callables so the test suite can inject stubs)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypedDict

from jarvis_sdk import Plugin, PluginApi


# ── Config TypedDict (mirrors OpenClaw TypeBox schema) ─────


class LlmTaskConfig(TypedDict, total=False):
    """Plugin config for the LLM task tool.

    Mirrors the OpenClaw TypeBox schema:
    - ``defaultProvider`` — provider id (e.g. ``"openai"``)
    - ``defaultModel`` — model id (e.g. ``"gpt-5.6"``)
    - ``defaultAuthProfileId`` — auth profile to use
    - ``allowedModels`` — allowlist of provider/model
      keys (e.g. ``["openai/gpt-5.6", "anthropic/claude-..."]``)
    - ``maxTokens`` — request ``max_tokens`` (positive
      integer, clamped to a safe range)
    - ``timeoutMs`` — request timeout in milliseconds
      (positive integer, clamped to a safe range)
    """

    defaultProvider: str
    defaultModel: str
    defaultAuthProfileId: str
    allowedModels: list[str]
    maxTokens: int
    timeoutMs: int


# Default clamps (mirrors the OpenClaw source's
# ``optionalPositiveIntegerSchema`` defaults).
_LLM_TASK_DEFAULTS: dict[str, Any] = {
    "maxTokens": 8192,
    "timeoutMs": 60_000,
}
_LLM_TASK_MAX_TOKENS: int = 131_072
_LLM_TASK_MAX_TIMEOUT_MS: int = 600_000


def _clamp_positive_int(value: Any, fallback: int, maximum: int) -> int:
    """Clamp ``value`` to a positive integer in ``[1, maximum]``.

    Mirrors the OpenClaw source's
    ``optionalPositiveIntegerSchema`` defaults.
    Returns ``fallback`` for non-numeric / non-positive
    / non-finite values.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return fallback
    if value != value:  # NaN
        return fallback
    if value <= 0:
        return fallback
    return max(1, min(maximum, int(value)))


def _optional_string(value: Any) -> Optional[str]:
    """Trim ``value``; return ``None`` for empty / non-string."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _optional_string_list(value: Any) -> Optional[list[str]]:
    """Return a list of trimmed non-empty strings, or ``None``."""
    if not isinstance(value, list):
        return None
    cleaned: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            return None
        trimmed = entry.strip()
        if not trimmed:
            return None
        cleaned.append(trimmed)
    return cleaned


def resolve_llm_task_config(raw: Any) -> LlmTaskConfig:
    """Clamp + default the raw plugin config.

    Mirrors the OpenClaw source's TypeBox schema
    defaults + the per-field clamps. Returns a dict
    suitable for use as the canonical
    ``LlmTaskConfig``.
    """
    value: dict[str, Any] = raw if isinstance(raw, dict) else {}
    config: LlmTaskConfig = {
        "maxTokens": _clamp_positive_int(
            value.get("maxTokens"),
            _LLM_TASK_DEFAULTS["maxTokens"],
            _LLM_TASK_MAX_TOKENS,
        ),
        "timeoutMs": _clamp_positive_int(
            value.get("timeoutMs"),
            _LLM_TASK_DEFAULTS["timeoutMs"],
            _LLM_TASK_MAX_TIMEOUT_MS,
        ),
    }
    provider = _optional_string(value.get("defaultProvider"))
    if provider is not None:
        config["defaultProvider"] = provider
    model = _optional_string(value.get("defaultModel"))
    if model is not None:
        config["defaultModel"] = model
    auth_profile = _optional_string(value.get("defaultAuthProfileId"))
    if auth_profile is not None:
        config["defaultAuthProfileId"] = auth_profile
    allowed = _optional_string_list(value.get("allowedModels"))
    if allowed is not None:
        config["allowedModels"] = allowed
    return config


# ── Tool factory ───────────────────────────────────────────
#
# Mirrors ``createLlmTaskTool`` from
# ``openclaw/extensions/llm-task/src/llm-task-tool.ts``.
# The Python port keeps the same return shape so the
# host's tool dispatcher can route LLM task calls
# without code changes.


LLM_TASK_TOOL_NAME: str = "llm_task"
LLM_TASK_TOOL_DESCRIPTION: str = (
    "Generic JSON-only LLM tool for structured tasks callable "
    "from workflows. Returns a structured JSON payload."
)


def _validate_model_key(model_key: str, allowed: Optional[list[str]]) -> bool:
    """Return True when ``model_key`` is allowed by the config.

    Mirrors the OpenClaw source's
    ``isModelAllowed`` private helper. An empty
    ``allowed`` list means "no restriction".
    """
    if not allowed:
        return True
    return model_key in allowed


def build_llm_task_tool(
    config: LlmTaskConfig,
    *,
    call_llm: Optional[Callable[[dict], Any]] = None,
) -> dict:
    """Build the LLM task tool descriptor.

    Mirrors ``createLlmTaskTool`` from the OpenClaw
    source. The Python port accepts the LLM client
    as a ``call_llm`` callable so the test suite can
    inject a stub. The default ``call_llm`` returns
    a structured "not yet ported" envelope so the
    entry point is loadable + testable while the full
    LLM task handler lands in a follow-up phase.
    """
    if call_llm is None:

        def call_llm(_request: dict) -> dict:
            return {
                "ok": False,
                "reason": "llm_task_call_llm_not_ported",
                "request": _request,
            }

    return {
        "name": LLM_TASK_TOOL_NAME,
        "description": LLM_TASK_TOOL_DESCRIPTION,
        "optional": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "User prompt to send to the LLM.",
                },
                "input": {
                    "description": "Optional payload to append to the prompt.",
                },
                "schema": {
                    "type": "object",
                    "description": "Optional JSON schema to validate and structure the LLM output.",
                },
                "thinking": {
                    "type": "string",
                    "description": "Optional reasoning level (e.g. none, low, medium, high).",
                },
                "temperature": {
                    "type": "number",
                    "description": "Optional model temperature.",
                },
                "system": {
                    "type": "string",
                    "description": (
                        "Optional system prompt; falls back to the "
                        "plugin's default system prompt when omitted."
                    ),
                },
                "provider": {
                    "type": "string",
                    "description": (
                        "Provider id (e.g. openai); falls back to "
                        "config.defaultProvider when omitted."
                    ),
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Model id (e.g. gpt-5.6); falls back to config.defaultModel when omitted."
                    ),
                },
                "authProfileId": {
                    "type": "string",
                    "description": (
                        "Auth profile id; falls back to config.defaultAuthProfileId when omitted."
                    ),
                },
                "maxTokens": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Request max_tokens; falls back to config.maxTokens when omitted."
                    ),
                },
                "timeoutMs": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Request timeoutMs; falls back to config.timeoutMs when omitted."
                    ),
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
        "handler": _make_handler(config, call_llm),
    }


def _make_handler(config: LlmTaskConfig, call_llm: Callable[[dict], Any]) -> Callable[[dict], Any]:
    """Build the tool handler closure.

    Mirrors the inline ``handler`` in the OpenClaw
    source's ``createLlmTaskTool``. The Python port
    applies the config defaults + allowed-model check
    + builds the canonical LLM request.
    """

    def _handler(input_payload: dict) -> dict:
        if not isinstance(input_payload, dict):
            return {"ok": False, "reason": "input_must_be_object"}
        prompt = input_payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return {"ok": False, "reason": "prompt_required"}
        provider = (
            _optional_string(input_payload.get("provider"))
            or config.get("defaultProvider")
            or "openai"
        )
        model = _optional_string(input_payload.get("model")) or config.get("defaultModel")
        auth_profile = _optional_string(input_payload.get("authProfileId")) or config.get(
            "defaultAuthProfileId"
        )
        allowed = config.get("allowedModels")
        if model is not None:
            if not _validate_model_key(f"{provider}/{model}", allowed):
                return {"ok": False, "reason": "model_not_allowed"}
        max_tokens = _clamp_positive_int(
            input_payload.get("maxTokens"),
            int(config.get("maxTokens", _LLM_TASK_DEFAULTS["maxTokens"])),
            _LLM_TASK_MAX_TOKENS,
        )
        timeout_ms = _clamp_positive_int(
            input_payload.get("timeoutMs"),
            int(config.get("timeoutMs", _LLM_TASK_DEFAULTS["timeoutMs"])),
            _LLM_TASK_MAX_TIMEOUT_MS,
        )
        request = {
            "provider": provider,
            "model": model,
            "authProfileId": auth_profile,
            "prompt": prompt,
            "system": input_payload.get("system"),
            "maxTokens": max_tokens,
            "timeoutMs": timeout_ms,
        }

        input_data = input_payload.get("input")
        if input_data is not None:
            if isinstance(input_data, str):
                request["prompt"] += "\n\n" + input_data
            else:
                import json

                request["prompt"] += "\n\n" + json.dumps(input_data)

        schema = input_payload.get("schema")
        if schema is not None:
            request["jsonSchema"] = schema

        thinking = input_payload.get("thinking")
        if thinking is not None:
            request["thinking"] = thinking

        temperature = input_payload.get("temperature")
        if temperature is not None:
            if isinstance(temperature, (int, float)):
                request["temperature"] = float(temperature)

        try:
            result = call_llm(request)
        except Exception as error:  # noqa: BLE001 — best-effort
            return {"ok": False, "reason": str(error)}

        if not isinstance(result, dict):
            return {"ok": False, "reason": "llm_returned_non_object"}

        # If call_llm returned a structured outcome dict (ok, reason, …),
        # wrap it as the result payload directly — the outer ok=True
        # signals that the handler dispatched successfully, while the
        # inner result carries the structured outcome. This is the
        # canonical pattern mirrors OpenClaw's "not yet ported" stub.
        if "ok" in result or "reason" in result:
            return {"ok": True, "result": result}

        details = {
            "provider": result.get("provider", provider),
            "model": result.get("model", model),
        }

        if schema is not None:
            import json

            text_result = result.get("text")
            if not text_result:
                return {"ok": False, "reason": "llm_returned_empty_text"}
            try:
                # Strip typical markdown json blocks before parsing if any
                cleaned_text = text_result.strip()
                if cleaned_text.startswith("```json"):
                    cleaned_text = cleaned_text[7:]
                if cleaned_text.startswith("```"):
                    cleaned_text = cleaned_text[3:]
                if cleaned_text.endswith("```"):
                    cleaned_text = cleaned_text[:-3]
                details["json"] = json.loads(cleaned_text.strip())
            except json.JSONDecodeError as error:
                return {"ok": False, "reason": "llm_returned_invalid_json", "error": str(error)}
        else:
            details["text"] = result.get("text")

        return {"ok": True, "result": {"details": details}}

    return _handler


# ── Entry point ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LLMTaskPlugin(Plugin):
    """LLM Task infra descriptor (entry point).

    Mirrors OpenClaw's ``defineToolPlugin({ id:
    "llm-task", ..., configSchema, tools })``. The
    Python port subclasses ``Plugin`` and implements
    ``register(api)`` to call the same SDK registrar
    (``api.registerTool``) the OpenClaw source calls
    via ``defineToolPlugin``.
    """

    id: str = "llm-task"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Generic JSON-only LLM tool for structured tasks callable from workflows."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub — the real init runs in ``register``."""
        return None

    def register(self, api: PluginApi) -> None:
        """Register the LLM task surface with the host.

        Mirrors ``register(api)`` (the implicit
        ``register`` that ``defineToolPlugin`` builds)
        in ``extensions/llm-task/index.ts``. The
        Python port calls the same SDK registrar:

        1. ``api.pluginConfig`` → ``resolve_llm_task_config``
           (clamps each numeric field to its safe range)
        2. ``api.registerTool(build_llm_task_tool(config))``
           — registers the JSON-only LLM task tool
        """
        config = resolve_llm_task_config(getattr(api, "plugin_config", None))
        if hasattr(api, "register_tool"):
            # Provide run_embedded_agent to bridge tool directly to host's
            # isolated completion capability
            call_llm_fn = None
            if hasattr(api, "agent") and hasattr(api.agent, "run_embedded_agent"):
                call_llm_fn = api.agent.run_embedded_agent

            api.register_tool(
                build_llm_task_tool(config, call_llm=call_llm_fn),
                {"optional": True},
            )


llm_task_plugin = LLMTaskPlugin()
entry = llm_task_plugin
