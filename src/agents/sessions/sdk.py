"""jarvis.agents.sessions.sdk — the agent-session factory.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/sdk.ts``.

The single funnel into the brain.
Selects models, wires built-in +
custom tools, loads resources, +
creates :class:`AgentSession`
instances.

Public surface (mirrors the OpenClaw
source):

- :class:`CreateAgentSessionOptions` —
  factory options. Mirrors
  :class:`CreateAgentSessionOptions`
  (``sdk.ts:70-121``).
- :class:`CreateAgentSessionResult` —
  factory result. Mirrors
  :class:`CreateAgentSessionResult`
  (``sdk.ts:124-131``).
- :func:`create_agent_session` —
  the main factory. Mirrors
  :func:`createAgentSession`
  (``sdk.ts:277-553``).
- :func:`get_default_agent_dir` —
  resolve the default agent
  directory. Mirrors
  :func:`getDefaultAgentDir`
  (``sdk.ts:146-148``).
- :func:`create_session_prepare_next_turn_with_context` —
  build the
  ``prepare_next_turn_with_context``
  hook. Mirrors
  :func:`createSessionPrepareNextTurnWithContext`
  (``sdk.ts:150-208``).
- :func:`get_attribution_headers` —
  build the attribution headers for
  known providers. Mirrors
  :func:`getAttributionHeaders`
  (``sdk.ts:210-240``).
- :func:`project_thinking_catalog_compat` —
  project a model's
  ``compat`` block into a
  thinking-catalog compat block.
  Mirrors
  :func:`projectThinkingCatalogCompat`
  (``sdk.ts:50-68``).

Re-exports (mirrors the OpenClaw
source's re-exports at
``sdk.ts:135-142``):

- :class:`ExtensionAPI` /
  :class:`ExtensionContext` /
  :class:`ExtensionFactory` /
  :class:`ToolDefinition` from
  :mod:`jarvis.agents.sessions.extensions.types`
- :func:`create_coding_tools` /
  :func:`create_read_tool` /
  :func:`create_edit_tool` /
  :func:`create_write_tool` from
  :mod:`jarvis.agents.sessions.tools`

Phase 6.14 — terminal Layer 2 phase.

Adaptations
-----------
- All OpenClaw camelCase names
  become snake_case in the Python
  port (``getApiKeyAndHeaders`` →
  :func:`get_api_key_and_headers`,
  ``findInitialModel`` →
  :func:`find_initial_model`,
  ``clampThinkingLevel`` →
  :func:`clamp_thinking_level`,
  ``new AgentSession(...)`` →
  :class:`AgentSession`, etc.).
- The OpenClaw source's
  :class:`Agent` lives in
  ``src/agents/runtime/index.js``.
  The Python port's :class:`Agent`
  lives in
  ``packages.agent_runtime.jarvis_agent.agent``.
- The OpenClaw source's
  :func:`bindStreamLlmRuntime`
  (the LLM-runtime ↔ agent-stream
  binding) comes from
  ``src/llm/model-runtime-binding.js``.
  The Python port's
  :func:`bind_stream_llm_runtime`
  is a STUB — the real binding
  lives in 6.14+ (LLM client
  integration).
- The OpenClaw source's
  :func:`isInstallTelemetryEnabled`
  + :func:`getAttributionHeaders`
  are the source of the
  ``HTTP-Referer`` /
  ``X-OpenRouter-Title`` /
  ``User-Agent`` headers. The
  Python port mirrors the same
  surface (returns ``None`` when
  telemetry is disabled).
- The OpenClaw source's
  :class:`SessionStartEvent` is
  defined in
  ``extensions/types.ts``. The
  Python port's :class:`SessionStartEvent`
  is a TypedDict in
  :mod:`jarvis.agents.sessions.extensions.types`
  (Phase 6.9c).
"""
from __future__ import annotations

import logging
import os
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Optional,
    TypedDict,
    Union,
)

from .agent_session import AgentSession
from .agent_session_types import (
    AgentSessionConfig,
    ScopedModelEntry,
    SessionStartEvent,
)
from .auth_storage import AuthStorage
from .auth_storage_oauth_registry import (
    OAuthProviderRegistry,
    get_auth_storage_oauth_provider_registry,
)
from .extensions.types import (
    Extension,
    ExtensionAPI,
    ExtensionContext,
    ExtensionFactory,
    LoadExtensionsResult,
    ToolDefinition,
)
from .extensions.runner import ExtensionRunner
from .model_registry import ModelRegistry
from .model_resolver import find_initial_model
from .model_registry_runtime import (
    ModelRegistryRuntime,
    get_model_registry_runtime,
)
from .resource_loader import DefaultResourceLoader
from .session_manager import SessionManager
from .session_manager_file import get_default_session_dir
from .settings_manager import SettingsManager
from .telemetry import is_install_telemetry_enabled
from .tools import (
    create_coding_tools,
    create_edit_tool,
    create_read_tool,
    create_write_tool,
)


if TYPE_CHECKING:
    from packages.agent_runtime.src.jarvis_agent.agent import (  # type: ignore[import-not-found]
        Agent,
    )
    from packages.agent_runtime.src.jarvis_agent.types import (  # type: ignore[import-not-found]
        AgentMessage,
        AgentTool,
        ThinkingLevel,
    )
else:
    Agent = Any
    AgentMessage = Any
    AgentTool = Any
    ThinkingLevel = str


_LOG = logging.getLogger("jarvis.agents.sessions.sdk")


# ============================================================================
# Public types
# ============================================================================


class CreateAgentSessionOptions(TypedDict, total=False):
    """Factory options for
    :func:`create_agent_session`. Mirrors
    :class:`CreateAgentSessionOptions`
    (``sdk.ts:70-121``). All fields
    are optional.
    """

    cwd: Optional[str]
    agentDir: Optional[str]
    authStorage: Optional[AuthStorage]
    modelRegistry: Optional[ModelRegistry]
    model: Optional[Any]
    thinkingLevel: Optional[ThinkingLevel]
    scopedModels: Optional[list[ScopedModelEntry]]
    noTools: Optional[str]  # "all" | "builtin"
    tools: Optional[list[str]]
    customTools: Optional[list[ToolDefinition]]
    resolveDeferredTool: Optional[Callable[..., Any]]
    resourceLoader: Optional[Any]
    sessionManager: Optional[SessionManager]
    settingsManager: Optional[SettingsManager]
    sessionStartEvent: Optional[SessionStartEvent]
    withSessionWriteLock: Optional[Callable[..., Awaitable[Any]]]
    skipBootstrap: Optional[bool]


class CreateAgentSessionResult(TypedDict):
    """Result of
    :func:`create_agent_session`. Mirrors
    :class:`CreateAgentSessionResult`
    (``sdk.ts:124-131``)."""

    session: AgentSession
    extensionsResult: LoadExtensionsResult
    modelFallbackMessage: Optional[str]


# ============================================================================
# Helper functions
# ============================================================================


def get_default_agent_dir() -> str:
    """Resolve the default agent
    directory. Mirrors
    :func:`getDefaultAgentDir`
    (``sdk.ts:146-148``).

    Phase 6.14 — STUB. Returns
    ``~/.jarvis/agents/default``.
    The real path resolution lands
    in 6.14+ (when the
    config-core is integrated)."""
    return os.path.join(
        os.path.expanduser("~"), ".jarvis", "agents", "default"
    )


def project_thinking_catalog_compat(
    compat: Any,
) -> Optional[dict]:
    """Project a model's ``compat``
    block into a thinking-catalog
    compat block. Mirrors
    :func:`projectThinkingCatalogCompat`
    (``sdk.ts:50-68``)."""
    if not compat or not isinstance(compat, dict):
        return None
    projected: dict = {}
    thinking_format = compat.get("thinkingFormat")
    if isinstance(thinking_format, str):
        projected["thinkingFormat"] = thinking_format
    # The OpenClaw source uses
    # ``record.supportedReasoningEfforts === null`` — distinguish
    # "missing" from "explicit null"
    # via the ``in`` operator (the
    # OpenClaw source's ``=== null``
    # is JavaScript's exact-equality
    # check; in Python ``dict.get()``
    # can't tell them apart).
    if "supportedReasoningEfforts" in compat:
        supported = compat["supportedReasoningEfforts"]
        if supported is None:
            projected["supportedReasoningEfforts"] = None
        elif (
            isinstance(supported, list)
            and all(isinstance(e, str) for e in supported)
        ):
            projected["supportedReasoningEfforts"] = list(supported)
    return projected if projected else None


def get_attribution_headers(
    model: Any,
    settings_manager: SettingsManager,
) -> Optional[dict]:
    """Build the attribution headers
    for known providers. Mirrors
    :func:`getAttributionHeaders`
    (``sdk.ts:210-240``).

    The OpenClaw source returns
    ``None`` when install telemetry
    is disabled. Returns the
    appropriate ``HTTP-Referer`` /
    ``User-Agent`` headers for
    OpenRouter + Cloudflare
    providers, ``None`` for
    everything else.
    """
    if not is_install_telemetry_enabled(settings_manager):
        return None
    base_url = (
        getattr(model, "base_url", None)
        or (model.get("baseUrl", "") if isinstance(model, dict) else "")
        or ""
    )
    provider = (
        model.get("provider", "")
        if isinstance(model, dict)
        else getattr(model, "provider", "")
    )
    if provider == "openrouter" or "openrouter.ai" in base_url:
        return {
            "HTTP-Referer": "https://jarvis.ai",
            "X-OpenRouter-Title": "JARVIS",
            "X-OpenRouter-Categories": "cli-agent",
        }
    if (
        provider in ("cloudflare-workers-ai", "cloudflare-ai-gateway")
        or "api.cloudflare.com" in base_url
        or "gateway.ai.cloudflare.com" in base_url
    ):
        return {"User-Agent": "jarvis"}
    return None


def create_session_prepare_next_turn_with_context(
    get_agent: Callable[[], Agent],
) -> Callable[..., Awaitable[Optional[dict]]]:
    """Build the
    ``prepare_next_turn_with_context``
    hook. Mirrors
    :func:`createSessionPrepareNextTurnWithContext`
    (``sdk.ts:150-208``).

    The OpenClaw source uses closure
    state to track
    ``activeRunMessages`` +
    ``effectiveModel`` +
    ``effectiveThinkingLevel`` +
    the last session snapshot. The
    Python port follows the same
    shape.
    """

    state: dict = {
        "active_run_messages": None,
        "effective_model": None,
        "effective_thinking_level": None,
        "last_session_model": None,
        "last_session_thinking_level": None,
        "last_session_prompt": None,
        "last_session_tools": [],
    }

    def _same_tools(
        left: list[AgentTool], right: list[AgentTool]
    ) -> bool:
        if len(left) != len(right):
            return False
        for a, b in zip(left, right):
            if a is not b:
                return False
        return True

    async def _prepare_next_turn_with_context(
        turn: dict, signal: Any = None
    ) -> dict:
        agent = get_agent()
        new_messages = turn.get("newMessages")
        first_turn_in_run = state["active_run_messages"] is not new_messages
        if first_turn_in_run:
            state["active_run_messages"] = new_messages
            agent_state = agent.state
            if isinstance(agent_state, dict):
                state["effective_model"] = agent_state.get("model")
                state["effective_thinking_level"] = agent_state.get(
                    "thinkingLevel"
                )
            else:
                state["effective_model"] = getattr(
                    agent_state, "model", None
                )
                state["effective_thinking_level"] = getattr(
                    agent_state, "thinking_level", None
                )

        # Delegate to the agent's
        # `prepare_next_turn` (when
        # present) for the previous
        # snapshot. The Python port's
        # `Agent` class exposes this
        # via the loop config.
        previous_snapshot: Optional[dict] = None
        prepare_fn = getattr(agent, "prepare_next_turn", None)
        if callable(prepare_fn):
            try:
                previous_snapshot = await prepare_fn(signal)
            except Exception:
                previous_snapshot = None
        # The session state (model +
        # thinking + prompt + tools)
        # — read from the agent's state.
        agent_state = agent.state
        if isinstance(agent_state, dict):
            session_prompt = agent_state.get("systemPrompt", "")
            session_tools = list(agent_state.get("tools", []) or [])
            session_model = agent_state.get("model")
            session_thinking_level = agent_state.get("thinkingLevel")
        else:
            session_prompt = getattr(agent_state, "system_prompt", "")
            session_tools = list(
                getattr(agent_state, "tools", []) or []
            )
            session_model = getattr(agent_state, "model", None)
            session_thinking_level = getattr(
                agent_state, "thinking_level", None
            )
        session_model_changed = (
            first_turn_in_run
            or session_model is not state["last_session_model"]
        )
        session_thinking_changed = (
            first_turn_in_run
            or session_thinking_level
            != state["last_session_thinking_level"]
        )
        session_prompt_changed = (
            first_turn_in_run
            or session_prompt != state["last_session_prompt"]
        )
        session_tools_changed = (
            first_turn_in_run
            or not _same_tools(
                session_tools, state["last_session_tools"]
            )
        )

        # Loop-only hook updates
        # persist for the run; fresh
        # session state wins only
        # after it changes.
        if previous_snapshot and previous_snapshot.get("model"):
            state["effective_model"] = previous_snapshot["model"]
        elif session_model_changed:
            state["effective_model"] = session_model
        if previous_snapshot and previous_snapshot.get("thinkingLevel"):
            state["effective_thinking_level"] = previous_snapshot[
                "thinkingLevel"
            ]
        elif session_thinking_changed:
            state["effective_thinking_level"] = session_thinking_level

        state["last_session_model"] = session_model
        state["last_session_thinking_level"] = session_thinking_level
        state["last_session_prompt"] = session_prompt
        state["last_session_tools"] = list(session_tools)

        if previous_snapshot and previous_snapshot.get("context"):
            next_context = dict(previous_snapshot["context"])
        else:
            turn_context = turn.get("context", {})
            next_context = dict(turn_context)
            if session_prompt_changed:
                next_context["systemPrompt"] = session_prompt
            else:
                next_context["systemPrompt"] = turn_context.get(
                    "systemPrompt"
                )
            if session_tools_changed:
                next_context["tools"] = list(session_tools)
            else:
                turn_tools = turn_context.get("tools") or []
                next_context["tools"] = list(turn_tools)

        result: dict = {}
        if previous_snapshot:
            result.update(previous_snapshot)
        result["context"] = next_context
        result["model"] = state["effective_model"]
        result["thinkingLevel"] = state["effective_thinking_level"]
        return result

    return _prepare_next_turn_with_context


def bind_stream_llm_runtime(
    stream_fn: Callable[..., Any],
    llm_runtime: Any,
) -> None:
    """Bind the agent's ``stream_fn``
    to the LLM runtime. Mirrors
    :func:`bindStreamLlmRuntime`
    (``llm/model-runtime-binding.js``).

    Phase 6.14 — STUB. The full
    LLM-runtime binding (where
    ``streamFn`` is wired to a
    provider dispatcher) lands in
    6.14+ when the LLM client is
    integrated. The Python port's
    :class:`Agent` already routes
    through ``stream_fn`` directly,
    so the binding is a no-op.
    """
    _ = (stream_fn, llm_runtime)


# ============================================================================
# Main factory
# ============================================================================


def _convert_to_llm_with_block_images(
    messages: list,
    settings_manager: SettingsManager,
    convert_to_llm_fn: Callable[..., Any],
) -> list:
    """Wrap the ``convertToLlm`` to
    filter image content when the
    ``getBlockImages`` setting is
    enabled. Mirrors the OpenClaw
    source's ``convertToLlmWithBlockImages``
    closure inside
    :func:`createAgentSession`
    (``sdk.ts:401-437``)."""
    converted = convert_to_llm_fn(messages)
    if not settings_manager.get_block_images():
        return converted
    filtered: list = []
    for msg in converted:
        if not isinstance(msg, dict):
            filtered.append(msg)
            continue
        role = msg.get("role")
        if role not in ("user", "toolResult"):
            filtered.append(msg)
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            filtered.append(msg)
            continue
        if not any(
            isinstance(c, dict) and c.get("type") == "image"
            for c in content
        ):
            filtered.append(msg)
            continue
        mapped: list = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "image":
                mapped.append(
                    {"type": "text", "text": "Image reading is disabled."}
                )
            else:
                mapped.append(c)
        # Dedupe consecutive placeholder
        # texts.
        deduped: list = []
        for i, c in enumerate(mapped):
            if (
                isinstance(c, dict)
                and c.get("type") == "text"
                and c.get("text") == "Image reading is disabled."
                and i > 0
            ):
                prev = mapped[i - 1]
                if (
                    isinstance(prev, dict)
                    and prev.get("type") == "text"
                    and prev.get("text")
                    == "Image reading is disabled."
                ):
                    continue
            deduped.append(c)
        new_msg = dict(msg)
        new_msg["content"] = deduped
        filtered.append(new_msg)
    return filtered


async def create_agent_session(
    options: Optional[CreateAgentSessionOptions] = None,
) -> CreateAgentSessionResult:
    """The main factory. Mirrors
    :func:`createAgentSession`
    (``sdk.ts:277-553``).

    See the OpenClaw source for
    the full docstring + examples.
    """
    options = options or CreateAgentSessionOptions()

    # 1. Resolve cwd + agentDir.
    cwd = (
        options.get("cwd")
        or (
            options.get("sessionManager").get_cwd()
            if options.get("sessionManager")
            else None
        )
        or os.getcwd()
    )
    agent_dir = options.get("agentDir") or get_default_agent_dir()

    # 2. Resource loader — use
    #    provided or create
    #    DefaultResourceLoader.
    resource_loader = options.get("resourceLoader")

    # 3. AuthStorage + ModelRegistry.
    auth_path = (
        os.path.join(agent_dir, "auth.json")
        if options.get("agentDir") or options.get("authStorage")
        else None
    )
    models_path = (
        os.path.join(agent_dir, "models.json")
        if options.get("agentDir") or options.get("modelRegistry")
        else None
    )
    auth_storage = options.get("authStorage")
    if auth_storage is None:
        # Phase 6.14 — STUB. The real
        # `AuthStorage.create()` returns
        # the file-backed auth storage.
        # The Python port's
        # `AuthStorage.create()` is the
        # same factory.
        from .auth_storage import (
            FileAuthStorageBackend,
        )
        if auth_path:
            auth_storage = AuthStorage(FileAuthStorageBackend(auth_path))
        else:
            # Use in-memory when no path
            # provided.
            from .auth_storage import (
                InMemoryAuthStorageBackend,
            )
            auth_storage = AuthStorage(InMemoryAuthStorageBackend())
    # Initialize the OAuth provider
    # registry (idempotent).
    try:
        get_auth_storage_oauth_provider_registry()
    except Exception:
        pass
    model_registry = options.get("modelRegistry")
    if model_registry is None:
        # Phase 6.14 — STUB. The real
        # `ModelRegistry.create()` is
        # the factory; here we use the
        # default constructor.
        model_registry = ModelRegistry(auth_storage, models_path)

    # 4. Settings manager.
    settings_manager = options.get("settingsManager")
    if settings_manager is None:
        settings_manager = SettingsManager.create(
            cwd=cwd, agent_dir=agent_dir
        )
    # 5. Session manager.
    session_manager = options.get("sessionManager")
    if session_manager is None:
        default_session_dir = get_default_session_dir(
            cwd, agent_dir
        )
        agent_id = os.path.basename(os.path.normpath(agent_dir)) or "default"
        session_manager = SessionManager.create(
            cwd=cwd,
            session_dir=default_session_dir,
            sqlite_persistence={
                "agent_id": agent_id,
                "store_path": os.path.join(agent_dir, "agent.sqlite"),
            },
        )

    # 6. Create the resource loader
    #    if not provided.
    if resource_loader is None:
        from .resource_loader import (
            DefaultResourceLoaderOptions,
        )
        resource_loader = DefaultResourceLoader(
            DefaultResourceLoaderOptions(
                cwd=cwd,
                agent_dir=agent_dir,
                settings_manager=settings_manager,
                no_context_files=options.get("skipBootstrap", False),
            )
        )
        reload = getattr(resource_loader, "reload", None)
        if callable(reload):
            result = reload()
            if hasattr(result, "__await__"):
                await result
        refresh = getattr(model_registry, "refresh", None)
        if callable(refresh):
            refresh()

    # 7. Check for existing session
    #    data.
    build_ctx = getattr(
        session_manager, "build_session_context", None
    )
    existing_session: dict = {}
    if callable(build_ctx):
        try:
            existing_session = build_ctx() or {}
        except Exception:
            existing_session = {}
    existing_messages = (
        existing_session.get("messages", [])
        if isinstance(existing_session, dict)
        else []
    )
    has_existing_session = len(existing_messages) > 0
    get_branch = getattr(session_manager, "get_branch", None)
    branch_entries = (
        get_branch() if callable(get_branch) else []
    )
    has_thinking_entry = any(
        isinstance(e, dict) and e.get("type") == "thinking_level_change"
        for e in (branch_entries or [])
    )

    # 8. Try to restore the model
    #    from existing session data.
    model = options.get("model")
    model_fallback_message: Optional[str] = None
    if (
        not model
        and has_existing_session
        and isinstance(existing_session, dict)
        and existing_session.get("model")
    ):
        saved = existing_session["model"]
        provider = (
            saved.get("provider")
            if isinstance(saved, dict)
            else getattr(saved, "provider", None)
        )
        model_id = (
            saved.get("modelId")
            if isinstance(saved, dict)
            else getattr(saved, "model_id", None)
        )
        find = getattr(model_registry, "find", None)
        if callable(find):
            try:
                restored = find(provider, model_id)
            except Exception:
                restored = None
            if restored and model_registry.has_configured_auth(
                restored
            ):
                model = restored
        if not model and provider and model_id:
            model_fallback_message = (
                f"Could not restore model {provider}/{model_id}"
            )

    # 9. Otherwise, use findInitialModel.
    if not model:
        try:
            result = await find_initial_model(
                {
                    "scopedModels": [],
                    "isContinuing": has_existing_session,
                    "defaultProvider": settings_manager.get_default_provider(),
                    "defaultModelId": settings_manager.get_default_model(),
                    "defaultThinkingLevel": settings_manager.get_default_thinking_level(),
                    "modelRegistry": model_registry,
                }
            )
            model = result.get("model") if isinstance(result, dict) else None
        except Exception:
            model = None
        if not model:
            from .auth_guidance import (
                format_no_models_available_message,
            )
            model_fallback_message = (
                format_no_models_available_message()
            )
        elif model_fallback_message:
            provider_str = (
                model.get("provider")
                if isinstance(model, dict)
                else getattr(model, "provider", "")
            )
            model_id_str = (
                model.get("id")
                if isinstance(model, dict)
                else getattr(model, "id", "")
            )
            model_fallback_message += (
                f". Using {provider_str}/{model_id_str}"
            )

    # 10. Compute the thinking level.
    thinking_level = options.get("thinkingLevel")
    # Resolve the model-thinking
    # provider default.
    from .agent_session_models import clamp_thinking_level
    from .defaults import DEFAULT_THINKING_LEVEL
    model_thinking_provider: Optional[str] = None
    if model is not None:
        api = (
            model.get("api")
            if isinstance(model, dict)
            else getattr(model, "api", None)
        )
        provider_str = (
            model.get("provider")
            if isinstance(model, dict)
            else getattr(model, "provider", None)
        )
        model_thinking_provider = (
            "ollama" if api == "ollama" else provider_str
        )
    # Phase 6.14 — STUB. The real
    # `resolveThinkingDefaultForModel`
    # comes from the auto-reply
    # thinking catalog (lands in
    # 6.14+). For now, return the
    # default.
    resolved_provider_default: Optional[str] = None
    model_thinking_default: ThinkingLevel = (
        "off"
        if resolved_provider_default == "off"
        else DEFAULT_THINKING_LEVEL
    )
    # Restore from session if it
    # has data.
    if (
        thinking_level is None
        and has_existing_session
        and isinstance(existing_session, dict)
    ):
        if has_thinking_entry:
            thinking_level = existing_session.get(
                "thinkingLevel", model_thinking_default
            )
        else:
            default_tl = settings_manager.get_default_thinking_level()
            thinking_level = default_tl or model_thinking_default
    # Fall back to settings default.
    if thinking_level is None:
        default_tl = settings_manager.get_default_thinking_level()
        thinking_level = default_tl or model_thinking_default

    # Clamp to model capabilities.
    if not model:
        thinking_level = "off"
    else:
        thinking_level = clamp_thinking_level(model, thinking_level)

    # 11. Resolve the default tool
    #     set.
    default_active_tool_names: list[str] = [
        "read",
        "bash",
        "edit",
        "write",
    ]
    custom_tool_names: list[str] = [
        tool.get("name", "")
        for tool in (options.get("customTools") or [])
        if isinstance(tool, dict)
    ]
    no_tools = options.get("noTools")
    explicit_tools = options.get("tools")
    allowed_tool_names: Optional[set[str]] = None
    if explicit_tools is not None:
        allowed_tool_names = set(explicit_tools)
    elif no_tools == "all":
        allowed_tool_names = set()
    disable_built_in_tools = (
        explicit_tools is None and no_tools == "builtin"
    )
    if explicit_tools is not None:
        initial_active_tool_names: list[str] = list(explicit_tools)
    elif no_tools == "all":
        initial_active_tool_names = []
    elif no_tools == "builtin":
        initial_active_tool_names = list(custom_tool_names)
    else:
        initial_active_tool_names = list(default_active_tool_names)

    # 12. convertToLlmWithBlockImages.
    from .messages import convert_to_llm
    convert_to_llm_with_block = _convert_to_llm_with_block_images

    def _convert(messages: list) -> list:
        return convert_to_llm_with_block(
            messages, settings_manager, convert_to_llm
        )

    # 13. extensionRunnerRef.
    extension_runner_ref: dict = {}

    # 14. runWithSessionWriteLock.
    external_lock = options.get("withSessionWriteLock")

    async def _run_with_session_write_lock(
        run: Callable[[], Any],
    ) -> Any:
        if external_lock is not None:
            return await external_lock(run)
        result = run()
        if hasattr(result, "__await__"):
            return await result
        return result

    # 15. Get the model registry
    #     runtime.
    model_registry_runtime = get_model_registry_runtime(model_registry)

    # 16. Create the Agent.
    from packages.agent_runtime.src.jarvis_agent.agent import Agent as _Agent
    initial_state: dict = {
        "systemPrompt": "",
        "model": model,
        "thinkingLevel": thinking_level,
        "tools": [],
    }
    from packages.agent_runtime.src.jarvis_agent.agent import (
        AgentInitialState as _AgentInitialState,
    )
    initial_state_obj = _AgentInitialState(
        system_prompt="",
        model=model,
        thinking_level=thinking_level,
        tools=[],
    )

    async def _stream_fn(
        model_result: Any,
        context: Any,
        stream_options: Optional[dict] = None,
    ) -> Any:
        stream_options = stream_options or {}
        get_key = getattr(
            model_registry, "get_api_key_and_headers", None
        )
        if not callable(get_key):
            raise RuntimeError(
                "model_registry has no get_api_key_and_headers"
            )
        auth = await get_key(model_result)
        if not auth.get("ok"):
            raise RuntimeError(auth.get("error", "auth error"))
        provider_retry = settings_manager.get_provider_retry_settings()
        attribution = get_attribution_headers(
            model_result, settings_manager
        )
        llm_runtime = model_registry_runtime["llmRuntime"]
        merged_headers: Optional[dict] = None
        if (
            attribution
            or (auth.get("headers"))
            or stream_options.get("headers")
        ):
            merged_headers = {
                **(attribution or {}),
                **(auth.get("headers") or {}),
                **(stream_options.get("headers") or {}),
            }
        return await llm_runtime.stream_simple(
            model_result,
            context,
            {
                **stream_options,
                "apiKey": auth.get("apiKey"),
                "timeoutMs": stream_options.get(
                    "timeoutMs", provider_retry.get("timeoutMs")
                ),
                "maxRetries": stream_options.get(
                    "maxRetries", provider_retry.get("maxRetries")
                ),
                "maxRetryDelayMs": stream_options.get(
                    "maxRetryDelayMs",
                    provider_retry.get("maxRetryDelayMs"),
                ),
                "headers": merged_headers,
            },
        )

    async def _on_payload(
        payload: Any, model_value: Any
    ) -> Any:
        _ = model_value
        runner = extension_runner_ref.get("current")
        if runner is None:
            return payload
        if not runner.has_handlers("before_provider_request"):
            return payload
        return await _run_with_session_write_lock(
            lambda: runner.emit_before_provider_request(payload)
        )

    async def _on_response(
        response: Any, model_local: Any
    ) -> None:
        _ = model_local
        runner = extension_runner_ref.get("current")
        if runner is None:
            return
        if not runner.has_handlers("after_provider_response"):
            return
        await _run_with_session_write_lock(
            lambda: runner.emit({
                "type": "after_provider_response",
                "status": response.get("status"),
                "headers": response.get("headers"),
            })
        )

    async def _transform_context(
        messages: list,
    ) -> list:
        runner = extension_runner_ref.get("current")
        if runner is None:
            return messages
        return runner.emit_context(messages)

    agent: Agent = _Agent(
        _AgentOptions(
            initial_state=initial_state_obj,
            convert_to_llm=_convert,
            stream_fn=_stream_fn,
            on_payload=_on_payload,
            on_response=_on_response,
            transform_context=_transform_context,
            resolve_deferred_tool=options.get("resolveDeferredTool"),
            prepare_next_turn_with_context=(
                create_session_prepare_next_turn_with_context(
                    lambda: agent
                )
            ),
            session_id=session_manager.get_session_id(),
            steering_mode=settings_manager.get_steering_mode(),
            follow_up_mode=settings_manager.get_follow_up_mode(),
            transport=settings_manager.get_transport(),
            thinking_budgets=settings_manager.get_thinking_budgets(),
            max_retry_delay_ms=(
                settings_manager.get_provider_retry_settings().get(
                    "maxRetryDelayMs"
                )
            ),
        )
    )

    # 17. Bind the stream function
    #     to the LLM runtime.
    if getattr(agent, "stream_fn", None) is not None:
        bind_stream_llm_runtime(
            agent.stream_fn, model_registry_runtime["llmRuntime"]
        )

    # 18. Restore messages if the
    #     session has data; save
    #     initial model + thinking
    #     level for new sessions.
    if has_existing_session:
        agent.state.messages = list(existing_messages)
        if not has_thinking_entry:
            append_thinking = getattr(
                session_manager, "append_thinking_level_change", None
            )
            if callable(append_thinking):
                try:
                    append_thinking(thinking_level)
                except Exception:
                    pass
    else:
        if model is not None:
            provider_for_change = (
                model.get("provider")
                if isinstance(model, dict)
                else getattr(model, "provider", "")
            )
            model_id_for_change = (
                model.get("id")
                if isinstance(model, dict)
                else getattr(model, "id", "")
            )
            append_model = getattr(
                session_manager, "append_model_change", None
            )
            if callable(append_model):
                try:
                    append_model(
                        provider_for_change, model_id_for_change
                    )
                except Exception:
                    pass
        append_thinking = getattr(
            session_manager, "append_thinking_level_change", None
        )
        if callable(append_thinking):
            try:
                append_thinking(thinking_level)
            except Exception:
                pass

    # 19. Create the AgentSession.
    config: AgentSessionConfig = AgentSessionConfig(
        agent=agent,
        session_manager=session_manager,
        settings_manager=settings_manager,
        cwd=cwd,
        resource_loader=resource_loader,
        model_registry=model_registry,
        scoped_models=options.get("scopedModels"),
        custom_tools=options.get("customTools"),
        initial_active_tool_names=initial_active_tool_names,
        allowed_tool_names=(
            list(allowed_tool_names)
            if allowed_tool_names is not None
            else None
        ),
        disable_built_in_tools=disable_built_in_tools,
        extension_runner_ref=extension_runner_ref,
        session_start_event=options.get("sessionStartEvent"),
        with_session_write_lock=external_lock,
    )
    session = AgentSession(config)

    # 20. Get the extensions result.
    extensions_result: LoadExtensionsResult = (
        resource_loader.get_extensions()
    )

    return {
        "session": session,
        "extensionsResult": extensions_result,
        "modelFallbackMessage": model_fallback_message,
    }


# Local import to avoid circular
# imports with `packages.agent_runtime`.
from packages.agent_runtime.src.jarvis_agent.agent import (  # noqa: E402
    AgentOptions as _AgentOptions,
)


__all__ = [
    "CreateAgentSessionOptions",
    "CreateAgentSessionResult",
    "bind_stream_llm_runtime",
    "create_agent_session",
    "create_coding_tools",
    "create_edit_tool",
    "create_read_tool",
    "create_session_prepare_next_turn_with_context",
    "create_write_tool",
    "get_attribution_headers",
    "get_default_agent_dir",
    "project_thinking_catalog_compat",
    # Re-exports from extensions.types
    "ExtensionAPI",
    "ExtensionContext",
    "ExtensionFactory",
    "ExtensionRunner",
    "LoadExtensionsResult",
    "ToolDefinition",
]
