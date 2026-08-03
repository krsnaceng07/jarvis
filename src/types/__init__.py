"""jarvis.types — type stubs for external SDKs.

OpenClaw parity: mirrors ``openclaw-main/src/types/`` directory.
"""
from __future__ import annotations

from .agent_sessions import (  # noqa: F401
    AgentSessionCountResponse,
    AgentSessionListResponse,
    AgentSessionRecord,
)
from .create_markdown_preview import (  # noqa: F401
    CreateMarkdownPreviewOptions,
    CreateMarkdownPreviewResult,
)
from .microsoft_teams_sdk import (  # noqa: F401
    TeamsActivity,
    TeamsBotClient,
    TeamsConversationReference,
    TeamsTurnContext,
)
from .node_runtime_globals import (  # noqa: F401
    AbortSignalLike,
    BufferBytes,
    NodeProcessEnv,
    NodeTimeout,
    ProcessEnvKey,
)
from .qrcode import (  # noqa: F401
    QrErrorCorrectionLevel,
    QrToBufferResult,
    QrToCanvasOptions,
    QrToDataUrlOptions,
    QrToStringOptions,
)
