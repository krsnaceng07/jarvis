"""jarvis_llm.types — shared LLM wire contracts.

OpenClaw parity: ``packages/llm-core/src/types.ts`` (683 LOC).

This module is the vocabulary every provider adapter, the agent loop,
and the session layer share. It is deliberately stdlib-only and holds
no behaviour beyond small constructors — logic lives in
``stream.py``, ``validation.py``, and the agent runtime.

Naming convention (repo-wide, per docs/OPENCLAW_BRAIN_PORT_PLAN_V2.md §6)
========================================================================
``snake_case`` at the Python attribute level, ``camelCase`` preserved at
the JSON/data level. Every dataclass here therefore carries explicit
``to_dict()`` / ``from_dict()`` where it crosses a wire or disk boundary,
and those methods emit OpenClaw's exact camelCase keys (``stopReason``,
``toolCallId``, ``cacheWrite1h``, ``thinkingSignature``, ...). Renaming a
JSON key would break parity with OpenClaw transcripts, so the mapping is
asserted in tests.

Structural parity notes
=======================
- TS discriminated unions (``{type: "text"} | {type: "image"} | ...``)
  become separate frozen dataclasses plus a ``Union`` alias. The
  ``type`` discriminant is kept as a real field with a fixed default so
  serialized output matches OpenClaw byte-for-byte.
- TS ``string & {}`` open-enum pattern (``Api``, ``Provider``) becomes a
  plain ``str`` alias: any provider id is legal, the ``KNOWN_*`` tuples
  document the built-ins without constraining values.
- TS optional (``field?: T``) becomes ``T | None = None``. In
  ``to_dict()`` a ``None`` optional is **omitted** rather than emitted as
  ``null``, matching how TS serializes ``undefined``. This distinction
  matters: OpenClaw providers branch on key presence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeAlias, runtime_checkable

from .diagnostics import AssistantMessageDiagnostic, now_ms

# ─────────────────────────────────────────────────────────────────────
# Provider / API identity
# ─────────────────────────────────────────────────────────────────────

#: Provider API families with first-class request/stream adapters in OpenClaw.
#: Parity: ``KnownApi``. Kept as a tuple (not an Enum) because ``Api`` is an
#: open type — custom providers may use ids outside this set.
KNOWN_APIS: tuple[str, ...] = (
    "openai-completions",
    "mistral-conversations",
    "openai-responses",
    "azure-openai-responses",
    "openai-chatgpt-responses",
    "anthropic-messages",
    "bedrock-converse-stream",
    "google-generative-ai",
    "google-vertex",
)

#: Provider API id; custom providers can use ids outside the built-in set.
#: Parity: ``Api = KnownApi | (string & {})``.
Api: TypeAlias = str

#: Image-generation API families with first-class adapters. Parity: ``KnownImagesApi``.
KNOWN_IMAGES_APIS: tuple[str, ...] = ("openrouter-images",)

#: Image API id. Parity: ``ImagesApi``.
ImagesApi: TypeAlias = str

#: Provider id used for routing, diagnostics, and config lookups. Parity: ``Provider``.
Provider: TypeAlias = str

#: Image provider ids with first-class adapters. Parity: ``KnownImagesProvider``.
KNOWN_IMAGES_PROVIDERS: tuple[str, ...] = ("openrouter",)

#: Image provider id. Parity: ``ImagesProvider``.
ImagesProvider: TypeAlias = str

# ─────────────────────────────────────────────────────────────────────
# Thinking / reasoning levels
# ─────────────────────────────────────────────────────────────────────

#: Normalized reasoning-effort levels. Parity: ``ThinkingLevel``.
ThinkingLevel: TypeAlias = Literal["minimal", "low", "medium", "high", "xhigh", "max"]

#: Model thinking setting including explicit disabled state.
#: Parity: ``ModelThinkingLevel = "off" | ThinkingLevel``.
ModelThinkingLevel: TypeAlias = Literal["off", "minimal", "low", "medium", "high", "xhigh", "max"]

#: Ordered thinking levels, weakest to strongest. Not in OpenClaw's types.ts as a
#: value, but the ordering is implied by ``reasoning.ts`` clamping logic and is
#: needed here so the session layer can clamp a requested level to what a model
#: supports without duplicating the order in several modules.
THINKING_LEVEL_ORDER: tuple[ThinkingLevel, ...] = (
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

#: Provider-specific values for normalized thinking levels.
#: Parity: ``ThinkingLevelMap = Partial<Record<ModelThinkingLevel, string | null>>``.
#: A ``None`` value marks a level as *unsupported* (distinct from absent, which
#: means "use the provider default"). That distinction is load-bearing.
ThinkingLevelMap: TypeAlias = dict[str, str | None]


@dataclass(frozen=True)
class ThinkingBudgets:
    """Token budgets per thinking level, for token-based providers.

    Parity: ``ThinkingBudgets``. Note OpenClaw's interface omits ``xhigh``;
    that omission is reproduced here rather than "fixed", because adding a
    field would diverge from the provider adapters that read this shape.
    """

    minimal: int | None = None
    low: int | None = None
    medium: int | None = None
    high: int | None = None
    max: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "minimal": self.minimal,
                "low": self.low,
                "medium": self.medium,
                "high": self.high,
                "max": self.max,
            }
        )


#: Prompt-cache retention preference. Parity: ``CacheRetention``.
CacheRetention: TypeAlias = Literal["none", "short", "long"]

#: Streaming transport preference. Parity: ``Transport``.
Transport: TypeAlias = Literal["sse", "websocket", "websocket-cached", "auto"]


# ─────────────────────────────────────────────────────────────────────
# Content blocks
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TextSignatureV1:
    """Parity: ``TextSignatureV1``."""

    id: str
    v: Literal[1] = 1
    phase: Literal["commentary", "final_answer"] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact({"v": self.v, "id": self.id, "phase": self.phase})


@dataclass(frozen=True)
class TextContent:
    """Plain assistant/user text block. Parity: ``TextContent``."""

    text: str
    #: For OpenAI responses: message metadata (legacy id string or
    #: ``TextSignatureV1`` JSON). Parity: ``textSignature``.
    text_signature: str | None = None
    type: Literal["text"] = "text"

    def to_dict(self) -> dict[str, Any]:
        return _compact({"type": "text", "text": self.text, "textSignature": self.text_signature})


@dataclass(frozen=True)
class ThinkingContent:
    """Provider reasoning block, including opaque replay signatures.

    Parity: ``ThinkingContent``. ``redacted=True`` means safety filters
    removed the text while ``thinking_signature`` still carries the opaque
    encrypted payload, which must be replayed to the API for multi-turn
    continuity — so a redacted block is *not* droppable.
    """

    thinking: str
    thinking_signature: str | None = None
    redacted: bool | None = None
    type: Literal["thinking"] = "thinking"

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "type": "thinking",
                "thinking": self.thinking,
                "thinkingSignature": self.thinking_signature,
                "redacted": self.redacted,
            }
        )


@dataclass(frozen=True)
class ImageContent:
    """Base64 image block with MIME metadata. Parity: ``ImageContent``."""

    data: str
    mime_type: str
    type: Literal["image"] = "image"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "image", "data": self.data, "mimeType": self.mime_type}


@dataclass(frozen=True)
class ToolCall:
    """Normalized assistant tool call. Parity: ``ToolCall``.

    ``execution_mode`` is per-call and overrides the loop-level default;
    ``thought_signature`` is Google-specific opaque thought context.
    """

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    thought_signature: str | None = None
    execution_mode: Literal["sequential", "parallel"] | None = None
    type: Literal["toolCall"] = "toolCall"

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "type": "toolCall",
                "id": self.id,
                "name": self.name,
                "arguments": self.arguments,
                "thoughtSignature": self.thought_signature,
                "executionMode": self.execution_mode,
            }
        )


#: Blocks allowed in an assistant message. Parity: ``AssistantMessage["content"]``.
AssistantContent: TypeAlias = "TextContent | ThinkingContent | ToolCall"
#: Blocks allowed in a user message / tool result. Parity: ``(TextContent | ImageContent)[]``.
UserContent: TypeAlias = "TextContent | ImageContent"


# ─────────────────────────────────────────────────────────────────────
# Usage / cost accounting
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ContextUsageAvailable:
    """Exact context snapshot for the final provider iteration.

    Parity: ``{state: "available"; promptTokens; totalTokens}``.
    """

    prompt_tokens: int
    total_tokens: int
    state: Literal["available"] = "available"

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": "available",
            "promptTokens": self.prompt_tokens,
            "totalTokens": self.total_tokens,
        }


@dataclass(frozen=True)
class ContextUsageUnavailable:
    """Parity: ``{state: "unavailable"}``."""

    state: Literal["unavailable"] = "unavailable"

    def to_dict(self) -> dict[str, Any]:
        return {"state": "unavailable"}


ContextUsage: TypeAlias = "ContextUsageAvailable | ContextUsageUnavailable"


@dataclass(frozen=True)
class Cost:
    """Parity: ``Usage["cost"]``.

    ``total_origin="provider-billed"`` marks the total as authoritative —
    a provider-reported bill outranks any locally computed figure, and
    downstream cost aggregation must not recompute it.
    """

    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0
    total: float = 0.0
    total_origin: Literal["provider-billed"] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "input": self.input,
                "output": self.output,
                "cacheRead": self.cache_read,
                "cacheWrite": self.cache_write,
                "total": self.total,
                "totalOrigin": self.total_origin,
            }
        )


@dataclass(frozen=True)
class Usage:
    """Normalized token and cost accounting. Parity: ``Usage``."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    #: Subset of ``cache_write`` written with 1-hour retention, when reported.
    cache_write_1h: int | None = None
    context_usage: ContextUsage | None = None
    total_tokens: int = 0
    cost: Cost = field(default_factory=Cost)

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "input": self.input,
                "output": self.output,
                "cacheRead": self.cache_read,
                "cacheWrite": self.cache_write,
                "cacheWrite1h": self.cache_write_1h,
                "contextUsage": (
                    self.context_usage.to_dict() if self.context_usage is not None else None
                ),
                "totalTokens": self.total_tokens,
                "cost": self.cost.to_dict(),
            }
        )


def empty_usage() -> Usage:
    """Zeroed usage, for synthesized messages that never hit a provider.

    Not a named export in OpenClaw (it inlines the literal), but the agent
    loop synthesizes failure/abort messages in several places and each one
    needs this exact zero value. One factory keeps them identical.
    """
    return Usage()


# ─────────────────────────────────────────────────────────────────────
# Messages
# ─────────────────────────────────────────────────────────────────────

#: Normalized assistant stop reasons. Parity: ``StopReason``.
StopReason: TypeAlias = Literal["stop", "length", "toolUse", "error", "aborted"]

#: The two stop reasons that denote failure. The ``StreamFn`` contract requires
#: a terminal message carrying one of these when anything goes wrong.
FAILURE_STOP_REASONS: tuple[str, ...] = ("error", "aborted")


@dataclass(frozen=True)
class UserMessage:
    """User turn. Parity: ``UserMessage``.

    ``runtime_context_carrier=True`` marks a *volatile* message holding
    current-turn runtime context. It is stripped on replay, so providers
    must NOT anchor a prompt-cache breakpoint on it — the breakpoint has
    to stay on the last stable (non-carrier) user message, or it would
    land on bytes that change every turn and destroy the cache hit rate.
    """

    content: "str | list[TextContent | ImageContent]"
    timestamp: int = field(default_factory=now_ms)
    runtime_context_carrier: bool | None = None
    role: Literal["user"] = "user"

    def to_dict(self) -> dict[str, Any]:
        content: Any
        if isinstance(self.content, str):
            content = self.content
        else:
            content = [block.to_dict() for block in self.content]
        return _compact(
            {
                "role": "user",
                "content": content,
                "timestamp": self.timestamp,
                "runtimeContextCarrier": self.runtime_context_carrier,
            }
        )


@dataclass(frozen=True)
class AssistantMessage:
    """Assistant turn, including provider identity and final stop state.

    Parity: ``AssistantMessage``.
    """

    api: Api
    provider: Provider
    model: str
    content: "list[TextContent | ThinkingContent | ToolCall]" = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    stop_reason: StopReason = "stop"
    #: Concrete ``chunk.model`` when it differs from the requested model
    #: (e.g. OpenRouter ``auto`` resolving to ``anthropic/...``).
    response_model: str | None = None
    response_id: str | None = None
    diagnostics: list[AssistantMessageDiagnostic] | None = None
    error_message: str | None = None
    error_code: str | None = None
    error_type: str | None = None
    error_body: str | None = None
    timestamp: int = field(default_factory=now_ms)
    role: Literal["assistant"] = "assistant"

    @property
    def is_failure(self) -> bool:
        """True when this message terminates a run in failure.

        Convenience over ``stop_reason in FAILURE_STOP_REASONS``; the loop
        and the session layer both branch on this repeatedly.
        """
        return self.stop_reason in FAILURE_STOP_REASONS

    def tool_calls(self) -> list[ToolCall]:
        """Tool calls in assistant source order.

        Source order matters: the loop emits tool-*result* message artifacts
        in this order even when execution finished out of order.
        """
        return [block for block in self.content if isinstance(block, ToolCall)]

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "role": "assistant",
                "content": [block.to_dict() for block in self.content],
                "api": self.api,
                "provider": self.provider,
                "model": self.model,
                "responseModel": self.response_model,
                "responseId": self.response_id,
                "diagnostics": (
                    [_diagnostic_to_dict(d) for d in self.diagnostics]
                    if self.diagnostics is not None
                    else None
                ),
                "usage": self.usage.to_dict(),
                "stopReason": self.stop_reason,
                "errorMessage": self.error_message,
                "errorCode": self.error_code,
                "errorType": self.error_type,
                "errorBody": self.error_body,
                "timestamp": self.timestamp,
            }
        )


@dataclass(frozen=True)
class ToolResultMessage:
    """Tool result answering a prior assistant tool call.

    Parity: ``ToolResultMessage<TDetails>``. ``details`` is the typed
    payload consumers may inspect; ``content`` is what goes back to the
    model. ``after_tool_call`` replaces either wholesale — never merges.
    """

    tool_call_id: str
    tool_name: str
    content: "list[TextContent | ImageContent]" = field(default_factory=list)
    details: Any | None = None
    is_error: bool = False
    timestamp: int = field(default_factory=now_ms)
    role: Literal["toolResult"] = "toolResult"

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "role": "toolResult",
                "toolCallId": self.tool_call_id,
                "toolName": self.tool_name,
                "content": [block.to_dict() for block in self.content],
                "details": self.details,
                "isError": self.is_error,
                "timestamp": self.timestamp,
            }
        )


#: Any text-model conversation message. Parity: ``Message``.
Message: TypeAlias = "UserMessage | AssistantMessage | ToolResultMessage"


# ─────────────────────────────────────────────────────────────────────
# Tools and request context
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tool:
    """Provider tool declaration with a JSON-schema parameter object.

    Parity: ``Tool<TParameters extends TSchema>``. OpenClaw types
    ``parameters`` as a TypeBox ``TSchema``; JARVIS carries the plain
    JSON-schema dict. Pydantic-backed schema construction is deferred to
    a later phase (plan §7) — the wire shape is a JSON schema either way.
    """

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


@dataclass(frozen=True)
class Context:
    """Text-model request context shared by provider adapters.

    Parity: ``Context``.
    """

    messages: list[Message] = field(default_factory=list)
    system_prompt: str | None = None
    tools: list[Tool] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "systemPrompt": self.system_prompt,
                "messages": [m.to_dict() for m in self.messages],
                "tools": ([t.to_dict() for t in self.tools] if self.tools is not None else None),
            }
        )


# ─────────────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelCost:
    """Per-million-token pricing. Parity: ``Model["cost"]``."""

    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": self.input,
            "output": self.output,
            "cacheRead": self.cache_read,
            "cacheWrite": self.cache_write,
        }


@dataclass(frozen=True)
class Model:
    """Unified model descriptor. Parity: ``Model<TApi>``.

    ``context_window`` is the provider/native metadata and stays intact;
    ``context_tokens`` is an optional smaller *effective* runtime cap used
    for compaction and session budgeting. Compaction must read
    ``effective_context_tokens``, not ``context_window``, or it will
    overfill a deliberately narrowed window.
    """

    id: str
    name: str
    api: Api
    provider: Provider
    base_url: str = ""
    reasoning: bool = False
    thinking_level_map: ThinkingLevelMap | None = None
    input: tuple[Literal["text", "image"], ...] = ("text",)
    cost: ModelCost = field(default_factory=ModelCost)
    context_window: int = 0
    context_tokens: int | None = None
    max_tokens: int = 0
    params: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    #: Sends credentials as ``Authorization: Bearer`` instead of
    #: provider-specific key headers. Parity: ``authHeader``.
    auth_header: bool | None = None
    #: Compatibility overrides for OpenAI/Anthropic-compatible APIs.
    #: OpenClaw types this per-``TApi`` via conditional types, which Python
    #: cannot express; carried as a dict and validated by the adapter that
    #: consumes it.
    compat: dict[str, Any] | None = None
    #: Provider-documented media input limits. Parity: ``mediaInput``.
    media_input: dict[str, Any] | None = None

    @property
    def effective_context_tokens(self) -> int:
        """The window compaction/budgeting must use.

        ``context_tokens`` when set, else ``context_window``. Mirrors how
        OpenClaw's compaction reads ``model.contextTokens ?? model.contextWindow``.
        """
        return self.context_tokens if self.context_tokens is not None else self.context_window

    def supports_thinking_level(self, level: ModelThinkingLevel) -> bool:
        """Whether a thinking level is usable on this model.

        Absent key -> supported via provider default. Explicit ``None`` ->
        unsupported. That two-state distinction is why
        ``thinking_level_map`` cannot be a plain ``dict[str, str]``.
        """
        if not self.reasoning:
            return level == "off"
        if self.thinking_level_map is None:
            return True
        if level not in self.thinking_level_map:
            return True
        return self.thinking_level_map[level] is not None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "id": self.id,
                "name": self.name,
                "api": self.api,
                "provider": self.provider,
                "baseUrl": self.base_url,
                "reasoning": self.reasoning,
                "thinkingLevelMap": self.thinking_level_map,
                "input": list(self.input),
                "cost": self.cost.to_dict(),
                "contextWindow": self.context_window,
                "contextTokens": self.context_tokens,
                "maxTokens": self.max_tokens,
                "params": self.params,
                "headers": self.headers,
                "authHeader": self.auth_header,
                "compat": self.compat,
                "mediaInput": self.media_input,
            }
        )


# ─────────────────────────────────────────────────────────────────────
# Request options
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProviderResponse:
    """Minimal HTTP response metadata surfaced through provider hooks.

    Parity: ``ProviderResponse``.
    """

    status: int
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StreamOptions:
    """Request options shared by text streaming providers.

    Parity: ``StreamOptions``. ``signal`` is an ``AbortSignal`` in
    OpenClaw; JARVIS uses an explicit :class:`~jarvis_llm.abort.AbortSignal`
    object rather than relying on ``asyncio`` task cancellation, because
    cancellation does not survive the sync/async wrapper boundary the way
    a checkable flag does (plan §7 risk note).
    """

    temperature: float | None = None
    max_tokens: int | None = None
    #: Stop sequences; providers map to their native field
    #: (OpenAI ``stop`` / Anthropic ``stop_sequences``).
    stop: list[str] | None = None
    signal: Any | None = None
    api_key: str | None = None
    transport: Transport | None = None
    #: Prompt cache retention preference. Provider default: ``"short"``.
    cache_retention: CacheRetention | None = None
    session_id: str | None = None
    #: Opaque per-model-call id for provider transport correlation.
    request_id: str | None = None
    #: Prompt-cache affinity key, distinct from transcript/session identity.
    prompt_cache_key: str | None = None
    on_payload: Any | None = None
    on_response: Any | None = None
    headers: dict[str, str] | None = None
    timeout_ms: int | None = None
    max_retries: int | None = None
    #: Cap on a server-requested retry delay. When the server asks for
    #: longer, the request fails immediately carrying the requested delay so
    #: higher-level retry logic can surface it to the user.
    #: Default ``60000``; ``0`` disables the cap.
    max_retry_delay_ms: int | None = None
    metadata: dict[str, Any] | None = None


#: Default for ``max_retry_delay_ms`` when unset. Parity: documented default
#: of 60s in ``StreamOptions.maxRetryDelayMs``.
DEFAULT_MAX_RETRY_DELAY_MS = 60_000

#: Default for ``cache_retention`` when unset. Parity: documented ``"short"``.
DEFAULT_CACHE_RETENTION: CacheRetention = "short"


@dataclass(frozen=True)
class SimpleStreamOptions(StreamOptions):
    """Unified text options used by the simple completion helpers.

    Parity: ``SimpleStreamOptions extends StreamOptions``.
    """

    reasoning: ModelThinkingLevel | None = None
    thinking_budgets: ThinkingBudgets | None = None


# ─────────────────────────────────────────────────────────────────────
# Stream event protocol
# ─────────────────────────────────────────────────────────────────────
#
# Parity: ``AssistantMessageEvent``. Streams emit ``start`` before partial
# updates, then terminate with EITHER ``done`` (success) OR ``error``
# (stopReason "error"/"aborted" + errorMessage). Exactly one terminal event.


@dataclass(frozen=True)
class StreamEventStart:
    partial: AssistantMessage
    type: Literal["start"] = "start"


@dataclass(frozen=True)
class StreamEventTextStart:
    content_index: int
    partial: AssistantMessage
    type: Literal["text_start"] = "text_start"


@dataclass(frozen=True)
class StreamEventTextDelta:
    """Plain text delta.

    ``partial`` is intentionally optional here and required on the other
    delta events: retaining a full assistant snapshot per token is the
    dominant memory cost in a long stream. Consumers needing current text
    replay ``delta`` from the latest start/end partial checkpoint.
    """

    content_index: int
    delta: str
    partial: AssistantMessage | None = None
    type: Literal["text_delta"] = "text_delta"


@dataclass(frozen=True)
class StreamEventTextEnd:
    content_index: int
    content: str
    partial: AssistantMessage
    type: Literal["text_end"] = "text_end"


@dataclass(frozen=True)
class StreamEventThinkingStart:
    content_index: int
    partial: AssistantMessage
    type: Literal["thinking_start"] = "thinking_start"


@dataclass(frozen=True)
class StreamEventThinkingDelta:
    content_index: int
    delta: str
    partial: AssistantMessage
    type: Literal["thinking_delta"] = "thinking_delta"


@dataclass(frozen=True)
class StreamEventThinkingEnd:
    content_index: int
    content: str
    partial: AssistantMessage
    type: Literal["thinking_end"] = "thinking_end"


@dataclass(frozen=True)
class StreamEventToolCallStart:
    content_index: int
    partial: AssistantMessage
    type: Literal["toolcall_start"] = "toolcall_start"


@dataclass(frozen=True)
class StreamEventToolCallDelta:
    content_index: int
    delta: str
    partial: AssistantMessage
    type: Literal["toolcall_delta"] = "toolcall_delta"


@dataclass(frozen=True)
class StreamEventToolCallEnd:
    content_index: int
    tool_call: ToolCall
    partial: AssistantMessage
    type: Literal["toolcall_end"] = "toolcall_end"


@dataclass(frozen=True)
class StreamEventDone:
    """Successful terminal event.

    ``reason`` is narrowed to the non-failure stop reasons, matching
    ``Extract<StopReason, "stop" | "length" | "toolUse">``.
    """

    reason: Literal["stop", "length", "toolUse"]
    message: AssistantMessage
    type: Literal["done"] = "done"


@dataclass(frozen=True)
class StreamEventError:
    """Failure terminal event.

    ``reason`` is narrowed to ``Extract<StopReason, "aborted" | "error">``.
    Carrying the full ``AssistantMessage`` (not an exception) is what makes
    the never-throw ``StreamFn`` contract possible.
    """

    reason: Literal["aborted", "error"]
    error: AssistantMessage
    type: Literal["error"] = "error"


AssistantMessageEvent: TypeAlias = (
    "StreamEventStart | StreamEventTextStart | StreamEventTextDelta | StreamEventTextEnd"
    " | StreamEventThinkingStart | StreamEventThinkingDelta | StreamEventThinkingEnd"
    " | StreamEventToolCallStart | StreamEventToolCallDelta | StreamEventToolCallEnd"
    " | StreamEventDone | StreamEventError"
)

#: The two terminal event types. Any stream must end with exactly one.
TERMINAL_EVENT_TYPES: tuple[str, ...] = ("done", "error")


@runtime_checkable
class AssistantMessageEventStreamLike(Protocol):
    """Read-only stream contract for consumers that never push.

    Parity: ``AssistantMessageEventStreamLike``.
    """

    def __aiter__(self) -> Any: ...

    async def result(self) -> AssistantMessage:
        """The final assistant message produced by the stream."""
        ...


@runtime_checkable
class AssistantMessageEventStreamContract(Protocol):
    """Full producer+consumer stream contract.

    Parity: ``AssistantMessageEventStreamContract``.
    """

    def __aiter__(self) -> Any: ...

    def push(self, event: Any) -> None:
        """Queue one stream event for consumers."""
        ...

    def end(self, result: AssistantMessage | None = None) -> None:
        """Complete the stream and optionally resolve the final message."""
        ...

    async def result(self) -> AssistantMessage:
        """The final assistant message produced by the stream."""
        ...


# ─────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` values so JSON matches TS ``undefined`` omission.

    OpenClaw providers branch on *key presence*, not on ``null``. Emitting
    ``"textSignature": null`` where TS emits nothing is a real behavioural
    difference, so every ``to_dict`` routes through here.
    """
    return {key: value for key, value in payload.items() if value is not None}


def _diagnostic_to_dict(diagnostic: AssistantMessageDiagnostic) -> dict[str, Any]:
    """Serialize a diagnostic with OpenClaw's key names."""
    error = diagnostic.error
    return _compact(
        {
            "type": diagnostic.type,
            "timestamp": diagnostic.timestamp,
            "error": (
                _compact(
                    {
                        "name": error.name,
                        "message": error.message,
                        "stack": error.stack,
                        "code": error.code,
                    }
                )
                if error is not None
                else None
            ),
            "details": diagnostic.details,
        }
    )


__all__ = [
    "DEFAULT_CACHE_RETENTION",
    "DEFAULT_MAX_RETRY_DELAY_MS",
    "FAILURE_STOP_REASONS",
    "KNOWN_APIS",
    "KNOWN_IMAGES_APIS",
    "KNOWN_IMAGES_PROVIDERS",
    "TERMINAL_EVENT_TYPES",
    "THINKING_LEVEL_ORDER",
    "Api",
    "AssistantContent",
    "AssistantMessage",
    "AssistantMessageEvent",
    "AssistantMessageEventStreamContract",
    "AssistantMessageEventStreamLike",
    "CacheRetention",
    "Context",
    "ContextUsage",
    "ContextUsageAvailable",
    "ContextUsageUnavailable",
    "Cost",
    "ImageContent",
    "ImagesApi",
    "ImagesProvider",
    "Message",
    "Model",
    "ModelCost",
    "ModelThinkingLevel",
    "Provider",
    "ProviderResponse",
    "SimpleStreamOptions",
    "StopReason",
    "StreamEventDone",
    "StreamEventError",
    "StreamEventStart",
    "StreamEventTextDelta",
    "StreamEventTextEnd",
    "StreamEventTextStart",
    "StreamEventThinkingDelta",
    "StreamEventThinkingEnd",
    "StreamEventThinkingStart",
    "StreamEventToolCallDelta",
    "StreamEventToolCallEnd",
    "StreamEventToolCallStart",
    "StreamOptions",
    "TextContent",
    "TextSignatureV1",
    "ThinkingBudgets",
    "ThinkingContent",
    "ThinkingLevel",
    "ThinkingLevelMap",
    "Tool",
    "ToolCall",
    "ToolResultMessage",
    "Transport",
    "UserContent",
    "UserMessage",
    "Usage",
    "empty_usage",
]
