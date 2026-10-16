"""jarvis.agents.codex_harness — OpenAI Codex app-server agent harness registration & contract facade.

OpenClaw parity: ``extensions/codex/harness.ts`` facade.
"""

from __future__ import annotations


from extensions.codex.harness import (
    CODEX_CONTEXT_ENGINE_HOST_CAPABILITIES,
    CODEX_HARNESS_ID,
    CODEX_HARNESS_LABEL,
    DEFAULT_CODEX_HARNESS_PROVIDER_IDS,
    CodexAgentHarness,
    create_codex_app_server_agent_harness,
)
from extensions.codex.src.app_server.config import CodexAppServerConfig

CODEX_HARNESS_PROVIDER_IDS: list[str] = list(DEFAULT_CODEX_HARNESS_PROVIDER_IDS)

__all__ = [
    "CODEX_CONTEXT_ENGINE_HOST_CAPABILITIES",
    "CODEX_HARNESS_ID",
    "CODEX_HARNESS_LABEL",
    "CODEX_HARNESS_PROVIDER_IDS",
    "CodexAgentHarness",
    "CodexAppServerConfig",
    "create_codex_app_server_agent_harness",
]
