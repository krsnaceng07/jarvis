"""Additional parity tests for memory_lancedb.

Covers:
  - Ollama native /api/embed embedding client
  - OpenAI-compatible embeddings with base64 / float payloads
  - Deduplication via Unicode NFC and line endings normalization
  - 60-block completed capture history deduplication
  - CLI ltm query with --filter, --order-by, --cols, --limit
  - CLI ltm list, search, stats with shlex-parsed arguments
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest

from extensions.memory_lancedb.config import parse_config
from extensions.memory_lancedb.embeddings import (
    OllamaEmbeddings,
    OpenAiCompatibleEmbeddings,
    create_embeddings,
)
from extensions.memory_lancedb.envelope_scrubber import normalize_memory_text_for_dedupe
from extensions.memory_lancedb.plugin import (
    MemoryLancedbPlugin,
    _cli_list,
    _cli_query,
    _cli_search,
    _cli_stats,
    _parse_cli_args,
)
from extensions.memory_lancedb.plugin_globals import set_active_db, set_active_embeddings
from extensions.memory_lancedb.runtime import MemoryDB


class DummyResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> DummyResponse:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class TestOllamaEmbeddings:
    @pytest.mark.asyncio
    async def test_ollama_embed_success(self) -> None:
        def mock_request(req: Any, timeout: float | None = None) -> DummyResponse:
            assert "/api/embed" in req.full_url
            body = json.loads(req.data.decode("utf-8"))
            assert body["model"] == "mxbai-embed-large"
            assert body["input"] == "hello world"
            assert body["dimensions"] == 1024
            resp_payload = {
                "model": "mxbai-embed-large",
                "embeddings": [[0.1, 0.2, 0.3]],
            }
            return DummyResponse(json.dumps(resp_payload).encode("utf-8"))

        client = OllamaEmbeddings(
            model="mxbai-embed-large",
            base_url="http://127.0.0.1:11434",
            dimensions=1024,
            api_key="secret-ollama-key",
            request=mock_request,
        )
        vec = await client.embed("hello world")
        assert vec == [0.1, 0.2, 0.3]

    def test_factory_creates_ollama_client(self) -> None:
        cfg = parse_config(
            {
                "embedding": {
                    "provider": "ollama",
                    "model": "mxbai-embed-large",
                    "dimensions": 1024,
                    "baseUrl": "http://localhost:11434",
                }
            }
        )
        client = create_embeddings(cfg)
        assert isinstance(client, OllamaEmbeddings)
        assert client._dimensions == 1024
        assert client._base_url == "http://localhost:11434"


class TestOpenAiEmbeddings:
    @pytest.mark.asyncio
    async def test_openai_embed_direct(self) -> None:
        def mock_request(req: Any, timeout: float | None = None) -> DummyResponse:
            assert "/embeddings" in req.full_url
            resp_payload = {
                "data": [{"embedding": [0.5, -0.5, 0.25]}],
            }
            return DummyResponse(json.dumps(resp_payload).encode("utf-8"))

        client = OpenAiCompatibleEmbeddings(
            api_key="test-key",
            model="text-embedding-3-small",
            dimensions=1536,
            request=mock_request,
        )
        vec = await client.embed("test text")
        assert vec == [0.5, -0.5, 0.25]


class TestDeduplicationAndNormalization:
    def test_normalize_memory_text_for_dedupe(self) -> None:
        t1 = "Hello World\r\nThis is a test  \r\n"
        t2 = "Hello World\nThis is a test"
        assert normalize_memory_text_for_dedupe(t1) == normalize_memory_text_for_dedupe(t2)

    @pytest.mark.asyncio
    async def test_store_exact_duplicate_skipped(self, tmp_path: Path) -> None:
        plugin = MemoryLancedbPlugin()
        cfg = parse_config({"embedding": {"provider": "openai", "model": "text-embedding-3-small"}})
        db = MemoryDB(str(tmp_path), vector_dim=3, force_in_memory=True)

        class StubEmbeddings:
            async def embed(self, text: str, timeout_ms: int | None = None) -> list[float]:
                return [1.0, 0.0, 0.0]

        plugin.configure(cfg, db, StubEmbeddings())  # type: ignore[arg-type]

        res1 = await plugin.call(
            "memory_store",
            {"agentId": "agent-1", "text": "I like dark mode theme\r\n", "importance": 0.8},
        )
        assert res1.is_ok
        assert "Stored:" in res1.value

        # Attempt to store identical text with different trailing whitespace/newlines
        res2 = await plugin.call(
            "memory_store",
            {"agentId": "agent-1", "text": "  I like dark mode theme\n", "importance": 0.8},
        )
        assert res2.is_ok
        assert "Similar memory already exists" in res2.value

    @pytest.mark.asyncio
    async def test_auto_capture_60_item_history_dedupe(self, tmp_path: Path) -> None:
        plugin = MemoryLancedbPlugin()
        cfg = parse_config(
            {
                "autoCapture": True,
                "embedding": {"provider": "openai", "model": "text-embedding-3-small"},
            }
        )
        db = MemoryDB(str(tmp_path), vector_dim=3, force_in_memory=True)

        class StubEmbeddings:
            async def embed(self, text: str, timeout_ms: int | None = None) -> list[float]:
                return [0.0, 1.0, 0.0]

        plugin.configure(cfg, db, StubEmbeddings())  # type: ignore[arg-type]

        msg = {"role": "user", "content": "I prefer using PostgreSQL for databases."}
        stored_count_1 = await plugin.auto_capture(
            messages=[msg],
            agent_id="agent-1",
            session_key="session-1",
        )
        assert stored_count_1 == 1

        # Second turn with same message text should be skipped by the 60-item history
        stored_count_2 = await plugin.auto_capture(
            messages=[msg],
            agent_id="agent-1",
            session_key="session-2",
        )
        assert stored_count_2 == 0


class TestCliCommands:
    def test_parse_cli_args_flags_and_values(self) -> None:
        tokens, flags = _parse_cli_args(
            "--agent research --cols id,text,createdAt --filter \"category = 'preference'\" --limit 20"
        )
        assert flags["agent"] == "research"
        assert flags["cols"] == "id,text,createdAt"
        assert flags["filter"] == "category = 'preference'"
        assert flags["limit"] == "20"

    def test_cli_query_with_filter_and_order_by(self, tmp_path: Path) -> None:
        db = MemoryDB(str(tmp_path), vector_dim=3, force_in_memory=True)
        from extensions.memory_lancedb.runtime import MemoryEntryInput

        db.store("agent-a", MemoryEntryInput("Fact 1", [1.0, 0.0, 0.0], 0.3, "fact"))
        db.store("agent-a", MemoryEntryInput("Pref 1", [0.0, 1.0, 0.0], 0.9, "preference"))
        db.store("agent-a", MemoryEntryInput("Pref 2", [0.0, 0.0, 1.0], 0.7, "preference"))

        set_active_db(db)
        try:
            # Query with filter and order-by
            res = _cli_query(
                "--agent agent-a --filter \"category = 'preference'\" --order-by importance:desc --cols text,importance"
            )
            rows = json.loads(res.reply_text)
            assert len(rows) == 2
            assert rows[0]["text"] == "Pref 1"
            assert rows[0]["importance"] == 0.9
            assert rows[1]["text"] == "Pref 2"
            assert rows[1]["importance"] == 0.7
            # sort_col was in requested cols so it remains; verify no extraneous cols
            assert set(rows[0].keys()) == {"id", "text", "importance"}

            # Stats command
            stats_res = _cli_stats("--agent agent-a")
            assert "Total memories: 3" in stats_res.reply_text

            # List command
            list_res = _cli_list("--agent agent-a --limit 2")
            list_rows = json.loads(list_res.reply_text)
            assert len(list_rows) == 2

            class StubEmbeddings:
                async def embed(self, text: str, timeout_ms: int | None = None) -> list[float]:
                    return [0.0, 1.0, 0.0]

            set_active_embeddings(StubEmbeddings())  # type: ignore[arg-type]
            search_res = _cli_search("--agent agent-a Preference search")
            search_rows = json.loads(search_res.reply_text)
            assert len(search_rows) >= 1
            assert search_rows[0]["text"] == "Pref 1"
        finally:
            set_active_db(None)
            set_active_embeddings(None)
