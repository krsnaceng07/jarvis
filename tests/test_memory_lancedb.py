"""Tests for src/plugins/memory_lancedb.py.

Mirrors tests of extensions/memory-lancedb/config.ts in OpenClaw.
"""

from __future__ import annotations

import pytest

from src.plugins.memory_lancedb import (
    DEFAULT_CAPTURE_MAX_CHARS,
    DEFAULT_RECALL_MAX_CHARS,
    EMBEDDING_DIMENSIONS,
    MEMORY_CATEGORIES,
    MEMORY_LANCEDB_AGENT_TOOLS,
    MEMORY_LANCEDB_CLI_COMMANDS,
    MEMORY_LANCEDB_PLUGIN_ID,
    resolve_memory_lancedb_config,
)


def test_memory_lancedb_constants():
    assert MEMORY_LANCEDB_PLUGIN_ID == "memory-lancedb"
    assert "preference" in MEMORY_CATEGORIES
    assert "fact" in MEMORY_CATEGORIES
    assert EMBEDDING_DIMENSIONS["text-embedding-3-small"] == 1536
    assert EMBEDDING_DIMENSIONS["text-embedding-3-large"] == 3072
    assert DEFAULT_CAPTURE_MAX_CHARS == 500
    assert DEFAULT_RECALL_MAX_CHARS == 1000
    assert len(MEMORY_LANCEDB_AGENT_TOOLS) == 3
    assert len(MEMORY_LANCEDB_CLI_COMMANDS) == 4


def test_resolve_memory_lancedb_config_defaults():
    cfg = resolve_memory_lancedb_config(None)
    assert cfg.embedding.provider == "openai"
    assert cfg.embedding.model == "text-embedding-3-small"
    assert cfg.embedding.dimensions == 1536
    assert cfg.autoCapture is False
    assert cfg.autoRecall is True
    assert cfg.captureMaxChars == 500
    assert cfg.recallMaxChars == 1000


def test_resolve_memory_lancedb_config_custom():
    custom = {
        "embedding": {
            "provider": "ollama",
            "model": "mxbai-embed-large",
            "dimensions": 1024,
        },
        "autoCapture": True,
        "captureMaxChars": 600,
        "recallMaxChars": 800,
        "customTriggers": ["remember this preference", "note that"],
    }
    cfg = resolve_memory_lancedb_config(custom)
    assert cfg.embedding.provider == "ollama"
    assert cfg.embedding.model == "mxbai-embed-large"
    assert cfg.embedding.dimensions == 1024
    assert cfg.autoCapture is True
    assert cfg.captureMaxChars == 600
    assert cfg.recallMaxChars == 800
    assert cfg.customTriggers == ["remember this preference", "note that"]


def test_resolve_memory_lancedb_config_invalid_dims():
    custom = {
        "embedding": {
            "model": "custom-model",
            "dimensions": 0,
        }
    }
    with pytest.raises(ValueError, match="embedding.dimensions must be an integer >= 1"):
        resolve_memory_lancedb_config(custom)
