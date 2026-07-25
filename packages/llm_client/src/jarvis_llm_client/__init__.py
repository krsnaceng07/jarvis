"""jarvis_llm_client — LLM client + agent-runtime helpers.

OpenClaw parity: mirrors
``packages/llm-core/`` + ``src/llm/`` + the agent-runtime
piece of ``src/plugin-sdk/``.

This package re-exports the agent-runtime + LLM facade
modules originally ported into
``packages/plugin_sdk/src/jarvis_sdk/``.

The re-export shim is temporary: a follow-up phase will
physically move the modules here and update all
``jarvis_sdk.{agent_runtime,expect_runtime,...}`` import
sites to ``jarvis_llm_client.*``.
"""
from __future__ import annotations

# Agent runtime (mirrors `src/plugin-sdk/agent-runtime.ts`).
from jarvis_sdk.agent_runtime import (  # noqa: F401
    DEFAULT_AGENT_ID,
    DEFAULT_PROVIDER,
    parse_model_ref,
    resolve_agent_dir,
    resolve_agent_effective_model_primary,
    resolve_agent_workspace_dir,
    resolve_default_agent_id,
    resolve_default_model_for_agent,
    resolve_remember_across_conversations,
    resolve_session_agent_id,
)

# Runtime helpers (mirrors `src/plugin-sdk/runtime-*` pieces).
from jarvis_sdk.expect_runtime import (  # noqa: F401
    expect_defined,
    expect_truthy,
)
from jarvis_sdk.lazy_runtime import create_lazy_runtime_module  # noqa: F401
from jarvis_sdk.number_runtime import (  # noqa: F401
    as_date_timestamp_ms,
    parse_strict_positive_integer,
    resolve_expires_at_ms_from_duration_ms,
    resolve_timer_timeout_ms,
    timestamp_ms_to_iso_string,
)
from jarvis_sdk.runtime_env import ensure_global_undici_env_proxy_dispatcher  # noqa: F401

# Memory embeddings (lives with the LLM facade in OpenClaw).
from jarvis_sdk.memory_embeddings import (  # noqa: F401
    MemoryEmbeddingProvider,
    MemoryEmbeddingProviderAdapter,
    get_memory_embedding_provider,
    list_registered_memory_embedding_providers,
    register_memory_embedding_provider,
)
