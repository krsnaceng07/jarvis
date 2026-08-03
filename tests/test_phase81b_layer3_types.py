"""Phase 8.1b tests — src/types/ (5 stub modules)."""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.types.agent_sessions import (  # noqa: E402
    AgentSessionCountResponse,
    AgentSessionListResponse,
    AgentSessionRecord,
)
from src.types.create_markdown_preview import (  # noqa: E402
    CreateMarkdownPreviewOptions,
    CreateMarkdownPreviewResult,
)
from src.types.microsoft_teams_sdk import (  # noqa: E402
    TeamsActivity,
    TeamsBotClient,
    TeamsConversationReference,
    TeamsTurnContext,
)
from src.types.node_runtime_globals import (  # noqa: E402
    AbortSignalLike,
    BufferBytes,
    NodeProcessEnv,
    NodeTimeout,
    ProcessEnvKey,
)
from src.types.qrcode import (  # noqa: E402
    QrErrorCorrectionLevel,
    QrToBufferResult,
    QrToCanvasOptions,
    QrToDataUrlOptions,
    QrToStringOptions,
)


class TestTypes:
    def test_agent_sessions(self) -> None:
        rec: AgentSessionRecord = {"id": "s1", "name": "test"}
        assert rec["id"] == "s1"
        lst: AgentSessionListResponse = [rec]
        assert len(lst) == 1
        count: AgentSessionCountResponse = {"total": 5}
        assert count["total"] == 5

    def test_create_markdown_preview(self) -> None:
        opts: CreateMarkdownPreviewOptions = {"source": "x.md"}
        assert opts["source"] == "x.md"
        result: CreateMarkdownPreviewResult = {"html": "<p>hi</p>"}
        assert "<p>" in result["html"]

    def test_microsoft_teams_sdk(self) -> None:
        activity: TeamsActivity = {"type": "message", "text": "hi"}
        assert activity["type"] == "message"
        ref: TeamsConversationReference = {"activityId": "a1"}
        assert ref["activityId"] == "a1"
        # TeamsBotClient/TeamsTurnContext are placeholders
        assert TeamsBotClient is not None
        assert TeamsTurnContext is not None

    def test_node_runtime_globals(self) -> None:
        assert isinstance(ProcessEnvKey("PATH"), str)
        assert isinstance(BufferBytes(b"hello"), bytes)
        assert AbortSignalLike is not None
        assert NodeProcessEnv is not None
        assert NodeTimeout is not None

    def test_qrcode(self) -> None:
        opts: QrToCanvasOptions = {"width": 200}
        result: QrToBufferResult = b"\x00\x01"
        assert result == b"\x00\x01"
        assert QrErrorCorrectionLevel is str  # placeholder alias
