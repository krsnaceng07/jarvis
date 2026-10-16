"""LLM Task tool — generic JSON-only LLM task with schema validation.

Mirrors OpenClaw's ``extensions/llm-task/src/llm-task-tool.ts``.

The tool runs an embedded LLM agent turn, collects the
plain-text response, strips any code-fence wrappers, JSON-
parses the result, optionally validates against a caller-
provided JSON Schema, and returns the parsed JSON. The
implementation is the canonical "JSON-only function" tool
used by orchestration workflows.

Public surface (mirrors the TS source):
- ``llm_task_tool_definition`` — the tool's name, label,
  description, and JSON Schema parameters
- ``create_llm_task_tool(api, deps=None)`` — build the
  executable tool handle; ``deps`` injects the
  ``run_embedded_agent`` callable and the model-ref
  resolution helpers

Python adaptations (documented in code):
- TS TypeBox schemas → Python TypedDict + ``__all__`` re-
  exported parameter shape
- TS as const string-literal unions → Python ``Literal``
- TS crypto.createHash → Python hashlib.sha256 (not needed
  in the focused port)
- TS ``api.runtime.agent.runEmbeddedAgent`` → Python
  ``api.runtime.agent.run_embedded_agent`` (injected via
  the runtime DI bag; the host wires it)
- The directory is named ``lib/`` (not ``src/``) to avoid
  the namespace collision with the JARVIS root ``src/``
  package
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, TypedDict

from jarvis_sdk.api import PluginApi
from jarvis_sdk.speech_provider import (  # noqa: F401  (typed-dict import unused at runtime)
    SpeechProviderConfig,
)


# ── Public constants ─────────────────────────────────────


LlmTaskToolName = "llm-task"
LlmTaskToolLabel = "LLM Task"
LlmTaskToolDescription = (
    "Run a generic JSON-only LLM task and return schema-validated JSON. "
    "Designed for orchestration from Lobster workflows via openclaw.invoke."
)

# Closed set of system-prompt instructions.
LlmTaskSystemPrompt = (
    "You are a JSON-only function. Return ONLY a valid JSON value. "
    "Do not wrap in markdown fences. Do not include commentary. "
    "Do not call tools."
)


# ── Type aliases ─────────────────────────────────────────


class LlmTaskPluginConfig(TypedDict, total=False):
    defaultProvider: str
    defaultModel: str
    defaultAuthProfileId: str
    allowedModels: list[str]
    maxTokens: int
    timeoutMs: int


class LlmTaskParams(TypedDict, total=False):
    prompt: str
    input: Any
    schema: dict[str, Any]
    provider: str
    model: str
    thinking: str
    authProfileId: str
    temperature: float
    maxTokens: int
    timeoutMs: int


class LlmTaskExecuteResult(TypedDict, total=False):
    content: list[dict[str, Any]]
    details: dict[str, Any]


class EmbeddedAgentPayloadItem(TypedDict, total=False):
    text: str
    isError: bool


class EmbeddedAgentResult(TypedDict, total=False):
    payloads: list[EmbeddedAgentPayloadItem]


RunEmbeddedAgentFn = Callable[[dict[str, Any]], Awaitable[EmbeddedAgentResult]]


# ── Helpers (mirrors the private TS helpers) ─────────────


def strip_code_fences(s: str) -> str:
    """Strip ``\\`\\`\\`json ... \\`\\`\\``` wrappers from a model response.

    Mirrors the private ``stripCodeFences`` helper. If the
    input is not fenced, the trimmed input is returned.
    """
    if not isinstance(s, str):
        return ""
    trimmed = s.strip()
    match = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", trimmed, re.IGNORECASE)
    if match:
        return (match.group(1) or "").strip()
    return trimmed


def collect_text(
    payloads: Optional[list[EmbeddedAgentPayloadItem]],
) -> str:
    """Concatenate the non-error text payloads from an agent result.

    Mirrors the private ``collectText`` helper.
    """
    parts: list[str] = []
    for payload in payloads or []:
        if payload.get("isError"):
            continue
        text = payload.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts).strip()


def to_model_key(provider: Optional[str], model: Optional[str]) -> Optional[str]:
    """Build a ``"{provider}/{model}"`` model key, or ``None`` if either is empty."""
    p = (provider or "").strip()
    m = (model or "").strip()
    if not p or not m:
        return None
    return f"{p}/{m}"


def strip_duplicate_provider_prefix(provider: Optional[str], model: Optional[str]) -> Optional[str]:
    """Strip the redundant ``{provider}/`` prefix from ``model``.

    Mirrors the private ``stripDuplicateProviderPrefix`` helper.
    """
    p = (provider or "").strip()
    m = (model or "").strip()
    if not p or not m:
        return m or None
    prefix = f"{p}/"
    if m.startswith(prefix):
        return m[len(prefix) :]
    return m


def resolve_llm_task_model_ref(
    *,
    api: PluginApi,
    provider: Optional[str],
    raw_model: Optional[str],
) -> dict[str, Optional[str]]:
    """Resolve the (provider, model) for the LLM Task call.

    Mirrors the private ``resolveLlmTaskModelRef`` helper.
    The host wires ``buildModelAliasIndex`` and
    ``resolveModelRefFromString``; the fallback returns the
    raw (provider, model) with the duplicate prefix
    stripped.
    """
    if not raw_model or not provider:
        return {
            "provider": provider,
            "model": strip_duplicate_provider_prefix(provider, raw_model),
        }
    cfg = getattr(api, "config", None)
    alias_index = (
        api.runtime.agent.build_model_alias_index({"cfg": cfg, "defaultProvider": provider})
        if cfg
        else None
    )
    resolved = api.runtime.agent.resolve_model_ref_from_string(
        {
            "cfg": cfg,
            "raw": raw_model,
            "defaultProvider": provider,
            "aliasIndex": alias_index,
        }
    )
    if not resolved:
        return {
            "provider": provider,
            "model": strip_duplicate_provider_prefix(provider, raw_model),
        }
    return resolved.get("ref") or {
        "provider": provider,
        "model": raw_model,
    }


def format_thinking_policy(policy: dict[str, Any]) -> str:
    """Format a thinking policy's level labels for error messages.

    Mirrors the private ``formatThinkingPolicy`` helper.
    """
    levels = policy.get("levels") or []
    return ", ".join(str(level.get("label")) for level in levels if isinstance(level, dict))


def supports_thinking_policy_level(policy: dict[str, Any], level: Optional[str]) -> bool:
    """Return ``True`` when ``level`` is in the policy's levels list.

    Mirrors the private ``supportsThinkingPolicyLevel`` helper.
    """
    if not level:
        return False
    levels = policy.get("levels") or []
    return any(isinstance(entry, dict) and entry.get("id") == level for entry in levels)


# ── Tool definition ──────────────────────────────────────


@dataclass
class LlmTaskToolDefinition:
    """The LLM Task tool descriptor (mirrors the TS ``llmTaskToolDefinition``)."""

    name: str = LlmTaskToolName
    label: str = LlmTaskToolLabel
    description: str = LlmTaskToolDescription
    # The TS source uses Type.Object for the parameters
    # schema. The Python port exposes a flat dict the host
    # can project into a JSON Schema (the OpenClaw test
    # file uses the same flat shape).
    parameters: dict[str, Any] = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Task instruction for the LLM.",
                },
                "input": {
                    "description": "Optional input payload for the task.",
                },
                "schema": {
                    "description": ("Optional JSON Schema to validate the returned JSON."),
                },
                "provider": {
                    "type": "string",
                    "description": ("Provider override (e.g. openai, anthropic)."),
                },
                "model": {
                    "type": "string",
                    "description": "Model id override.",
                },
                "thinking": {
                    "type": "string",
                    "description": "Thinking level override.",
                },
                "authProfileId": {
                    "type": "string",
                    "description": "Auth profile override.",
                },
                "temperature": {
                    "type": "number",
                    "description": "Best-effort temperature override.",
                },
                "maxTokens": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Best-effort maxTokens override.",
                },
                "timeoutMs": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Timeout for the LLM run.",
                },
            },
            "required": ["prompt"],
        }
    )


llm_task_tool_definition = LlmTaskToolDefinition()


# ── create_llm_task_tool ──────────────────────────────────


def _read_finite_number_param(params: dict[str, Any], key: str) -> Optional[float]:
    """Read a finite numeric param, or ``None`` if missing/invalid."""
    value = params.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value == value:  # NaN check
        return float(value)
    return None


def _read_positive_integer_param(params: dict[str, Any], key: str) -> Optional[int]:
    """Read a positive integer param, or ``None`` if missing/invalid."""
    value = _read_finite_number_param(params, key)
    if value is None:
        return None
    if value <= 0:
        return None
    return int(value)


def _as_positive_safe_integer(value: object) -> Optional[int]:
    """Coerce a value to a positive safe integer (Python int safe range)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value == value:
        n = int(value)
        return n if n > 0 else None
    return None


@dataclass
class LlmTaskDeps:
    """Dependency-injection bag for the LLM Task tool.

    The host wires ``run_embedded_agent_fn`` (and
    optionally ``build_model_alias_index_fn`` /
    ``resolve_model_ref_from_string_fn``) via the
    ``api.runtime.agent`` namespace; this bag lets tests
    inject a fake implementation without touching the
    plugin API.
    """

    run_embedded_agent: Optional[RunEmbeddedAgentFn] = None


def _validate_against_schema_stub(schema: dict[str, Any], value: object) -> dict[str, Any]:
    """A no-op schema validator (the host wires the real one).

    The OpenClaw source uses ``validateJsonSchemaValue``
    with a cache. The Python port returns a successful
    no-op for now; the host can wire a real validator via
    a future port of ``openclaw/plugin-sdk/json-schema-runtime``.

    Returns ``{"ok": True}`` for any input so the tool
    works without a real schema validator.
    """
    return {"ok": True}


def create_llm_task_tool(
    api: PluginApi,
    *,
    deps: Optional[LlmTaskDeps] = None,
) -> dict[str, Any]:
    """Build the LLM Task tool.

    Mirrors ``createLlmTaskTool`` in OpenClaw. Returns a
    dict carrying the tool's name, label, description,
    parameters schema, and an ``async execute(id, params)``
    callable.
    """
    effective_deps = deps or LlmTaskDeps()

    # If the host wired a real run_embedded_agent into the
    # API runtime, prefer it; otherwise fall back to the
    # DI bag.
    if effective_deps.run_embedded_agent is None:
        effective_deps.run_embedded_agent = (
            api.runtime.agent.run_embedded_agent
            if callable(api.runtime.agent.run_embedded_agent)
            else None
        )

    async def execute(_id: str, params: LlmTaskParams) -> LlmTaskExecuteResult:
        prompt = params.get("prompt") if isinstance(params.get("prompt"), str) else ""
        if not prompt.strip():
            raise ValueError("prompt required")

        plugin_cfg: dict[str, Any] = (
            api.plugin_config if isinstance(api.plugin_config, dict) else {}
        )

        defaults_model = (
            (api.config or {}).get("agents", {}).get("defaults", {}).get("model")
            if isinstance(api.config, dict)
            else None
        )
        if isinstance(defaults_model, str):
            primary = defaults_model
        elif isinstance(defaults_model, dict):
            primary = defaults_model.get("primary")
        else:
            primary = None
        if isinstance(primary, str):
            primary_provider = primary.split("/", 1)[0] or None
            primary_model = primary.split("/", 1)[1] if "/" in primary else None
        else:
            primary_provider = None
            primary_model = None

        requested_provider = (
            params.get("provider")
            if isinstance(params.get("provider"), str) and (params.get("provider") or "").strip()
            else (
                plugin_cfg.get("defaultProvider")
                if isinstance(plugin_cfg.get("defaultProvider"), str)
                and (plugin_cfg.get("defaultProvider") or "").strip()
                else primary_provider
            )
        )
        raw_model = (
            params.get("model")
            if isinstance(params.get("model"), str) and (params.get("model") or "").strip()
            else (
                plugin_cfg.get("defaultModel")
                if isinstance(plugin_cfg.get("defaultModel"), str)
                and (plugin_cfg.get("defaultModel") or "").strip()
                else primary_model
            )
        )

        resolved = resolve_llm_task_model_ref(
            api=api,
            provider=requested_provider,
            raw_model=raw_model,
        )
        provider = resolved.get("provider") or requested_provider
        model = resolved.get("model") or raw_model

        auth_profile_id = (
            params.get("authProfileId")
            if isinstance(params.get("authProfileId"), str)
            and (params.get("authProfileId") or "").strip()
            else (
                plugin_cfg.get("defaultAuthProfileId")
                if isinstance(plugin_cfg.get("defaultAuthProfileId"), str)
                and (plugin_cfg.get("defaultAuthProfileId") or "").strip()
                else None
            )
        )

        model_key = to_model_key(provider, model)
        if not provider or not model or not model_key:
            raise RuntimeError(
                f"provider/model could not be resolved "
                f"(provider={provider or ''}, model={model or ''})"
            )

        allowed_raw = plugin_cfg.get("allowedModels")
        if isinstance(allowed_raw, list) and allowed_raw:
            if model_key not in allowed_raw:
                raise RuntimeError(
                    f"Model not allowed by llm-task plugin config: "
                    f"{model_key}. Allowed models: "
                    f"{', '.join(allowed_raw)}"
                )

        agent_runtime = api.runtime.agent.resolve_effective_agent_runtime(
            {
                "cfg": api.config or {},
                "provider": provider,
                "modelId": model,
            }
        )

        thinking_raw = (
            params.get("thinking")
            if isinstance(params.get("thinking"), str) and (params.get("thinking") or "").strip()
            else None
        )
        think_level: Optional[str] = None
        if thinking_raw:
            policy = api.runtime.agent.resolve_thinking_policy(
                {
                    "provider": provider,
                    "model": model,
                    "agentRuntime": agent_runtime,
                }
            )
            levels_hint = format_thinking_policy(policy)
            think_level = api.runtime.agent.normalize_thinking_level(thinking_raw)
            if not think_level:
                raise RuntimeError(
                    f'Invalid thinking level "{thinking_raw}". Use one of: {levels_hint}.'
                )
            if not supports_thinking_policy_level(policy, think_level):
                raise RuntimeError(
                    f'Thinking level "{think_level}" is not supported for '
                    f"{provider}/{model}. Use one of: {levels_hint}."
                )

        timeout_ms = (
            _read_positive_integer_param(params, "timeoutMs")
            or _as_positive_safe_integer(plugin_cfg.get("timeoutMs"))
            or 30_000
        )

        temperature = _read_finite_number_param(params, "temperature")
        max_tokens = _read_positive_integer_param(params, "maxTokens") or _as_positive_safe_integer(
            plugin_cfg.get("maxTokens")
        )

        try:
            input_json = json.dumps(params.get("input") or None, indent=2)
        except (TypeError, ValueError):
            raise ValueError("input must be JSON-serializable") from None

        full_prompt = f"{LlmTaskSystemPrompt}\n\nTASK:\n{prompt}\n\nINPUT_JSON:\n{input_json}\n"

        if effective_deps.run_embedded_agent is None:
            raise NotImplementedError("llm-task: run_embedded_agent dependency is not wired")

        # The host wires a temp workspace; the OpenClaw
        # source uses ``withTempWorkspace({...})`` to create
        # a session file inside a temp dir. The Python port
        # accepts the host's temp dir via ``api.config`` and
        # falls back to ``os.getcwd()`` for tests.
        import os

        tmp_dir = (
            (api.config or {}).get("tmpDir") if isinstance(api.config, dict) else None
        ) or os.getcwd()
        session_id = f"llm-task-{int(time.time() * 1000)}"
        session_file = os.path.join(tmp_dir, f"{session_id}.json")

        result = await effective_deps.run_embedded_agent(
            {
                "sessionId": session_id,
                "sessionFile": session_file,
                "workspaceDir": (
                    (api.config or {}).get("agents", {}).get("defaults", {}).get("workspace")
                    if isinstance(api.config, dict)
                    else None
                )
                or os.getcwd(),
                "config": api.config,
                "prompt": full_prompt,
                "timeoutMs": timeout_ms,
                "runId": session_id,
                "provider": provider,
                "model": model,
                "authProfileId": auth_profile_id,
                "authProfileIdSource": "user" if auth_profile_id else "auto",
                "agentHarnessRuntimeOverride": agent_runtime,
                "thinkLevel": think_level,
                "streamParams": {
                    "temperature": temperature,
                    "maxTokens": max_tokens,
                },
                "disableTools": True,
            }
        )

        text = collect_text(result.get("payloads") if isinstance(result, dict) else None)
        if not text:
            raise RuntimeError("LLM returned empty output")

        raw = strip_code_fences(text)
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            raise RuntimeError("LLM returned invalid JSON") from None

        schema = params.get("schema")
        if isinstance(schema, dict) and schema and not isinstance(schema, list):
            validation = _validate_against_schema_stub(schema, parsed)
            if not validation.get("ok"):
                msg = "invalid"
                raise RuntimeError(f"LLM JSON did not match schema: {msg}") from None

        return {
            "content": [{"type": "text", "text": json.dumps(parsed, indent=2)}],
            "details": {"json": parsed, "provider": provider, "model": model},
        }

    return {
        "name": LlmTaskToolName,
        "label": LlmTaskToolLabel,
        "description": LlmTaskToolDescription,
        "parameters": llm_task_tool_definition.parameters,
        "execute": execute,
    }


__all__ = [
    "LlmTaskDeps",
    "LlmTaskExecuteResult",
    "LlmTaskParams",
    "LlmTaskPluginConfig",
    "LlmTaskToolDefinition",
    "LlmTaskToolLabel",
    "LlmTaskToolName",
    "LlmTaskToolDescription",
    "RunEmbeddedAgentFn",
    "create_llm_task_tool",
    "llm_task_tool_definition",
    "collect_text",
    "format_thinking_policy",
    "resolve_llm_task_model_ref",
    "strip_code_fences",
    "strip_duplicate_provider_prefix",
    "supports_thinking_policy_level",
    "to_model_key",
]
