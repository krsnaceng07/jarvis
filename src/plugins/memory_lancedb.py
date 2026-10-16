"""jarvis.plugins.memory_lancedb — Memory LanceDB plugin & vector database configuration.

OpenClaw parity: mirrors
``openclaw-main/extensions/memory-lancedb/config.ts`` and
``openclaw-main/extensions/memory-lancedb/index.ts``.

Features:
- `MEMORY_LANCEDB_PLUGIN_ID`: `"memory-lancedb"`
- `MEMORY_CATEGORIES`: `"preference"`, `"fact"`, `"decision"`, `"entity"`, `"other"`
- `EMBEDDING_DIMENSIONS`: Built-in dimensions lookup (`text-embedding-3-small`: 1536, `text-embedding-3-large`: 3072).
- `DEFAULT_CAPTURE_MAX_CHARS`: `500`
- `DEFAULT_RECALL_MAX_CHARS`: `1000`
- `MEMORY_LANCEDB_AGENT_TOOLS`: List of 3 agent tools (`memory_recall`, `memory_store`, `memory_forget`).
- `MEMORY_LANCEDB_CLI_COMMANDS`: List of 4 CLI commands (`list`, `search`, `stats`, `query`).
- `ResolvedMemoryLanceDbConfig`: Dataclass containing resolved configuration options.
- `resolve_memory_lancedb_config()`: Resolves and validates Memory LanceDB plugin options.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

MEMORY_LANCEDB_PLUGIN_ID: str = "memory-lancedb"

MemoryCategory = Literal["preference", "fact", "decision", "entity", "other"]
MEMORY_CATEGORIES: list[MemoryCategory] = ["preference", "fact", "decision", "entity", "other"]

EMBEDDING_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

DEFAULT_CAPTURE_MAX_CHARS: int = 500
DEFAULT_RECALL_MAX_CHARS: int = 1000

MEMORY_LANCEDB_AGENT_TOOLS: list[str] = [
    "memory_recall",
    "memory_store",
    "memory_forget",
]

MEMORY_LANCEDB_CLI_COMMANDS: list[str] = [
    "list",
    "search",
    "stats",
    "query",
]


@dataclass
class EmbeddingConfig:
    provider: str = "openai"
    model: str = "text-embedding-3-small"
    apiKey: str | None = None
    baseUrl: str | None = None
    dimensions: int | None = 1536


@dataclass
class ResolvedMemoryLanceDbConfig:
    embedding: EmbeddingConfig
    dbPath: str
    autoCapture: bool = False
    autoRecall: bool = True
    captureMaxChars: int = 500
    recallMaxChars: int = 1000
    customTriggers: list[str] = field(default_factory=list)
    storageOptions: dict[str, str] = field(default_factory=dict)


def resolve_memory_lancedb_config(plugin_cfg: dict[str, Any] | None) -> ResolvedMemoryLanceDbConfig:
    """Resolve and validate Memory LanceDB plugin configuration."""
    val = plugin_cfg if isinstance(plugin_cfg, dict) else {}

    emb_raw = val.get("embedding") if isinstance(val.get("embedding"), dict) else {}
    provider = str(emb_raw.get("provider") or "openai").strip()
    model = str(emb_raw.get("model") or "text-embedding-3-small").strip()
    api_key = str(emb_raw.get("apiKey")).strip() if emb_raw.get("apiKey") else None
    base_url = str(emb_raw.get("baseUrl")).strip() if emb_raw.get("baseUrl") else None

    raw_dims = emb_raw.get("dimensions")
    if raw_dims is not None:
        dims = int(raw_dims)
        if dims < 1:
            raise ValueError("embedding.dimensions must be an integer >= 1")
    else:
        dims = EMBEDDING_DIMENSIONS.get(model)

    raw_db = str(val.get("dbPath") or "").strip()
    if not raw_db:
        db_path = str(Path(os.path.expanduser("~/.jarvis/memory/lancedb")).resolve())
    else:
        db_path = str(Path(os.path.expanduser(raw_db)).resolve())

    cap_max = int(val.get("captureMaxChars", DEFAULT_CAPTURE_MAX_CHARS))
    cap_max = max(100, min(10000, cap_max))

    rec_max = int(val.get("recallMaxChars", DEFAULT_RECALL_MAX_CHARS))
    rec_max = max(100, min(10000, rec_max))

    triggers_raw = val.get("customTriggers")
    clean_triggers = (
        [str(t).strip()[:100] for t in triggers_raw if isinstance(t, str) and str(t).strip()][:50]
        if isinstance(triggers_raw, list)
        else []
    )

    storage_opts = val.get("storageOptions")
    clean_storage = (
        {str(k): str(v) for k, v in storage_opts.items()}
        if isinstance(storage_opts, dict)
        else {}
    )

    return ResolvedMemoryLanceDbConfig(
        embedding=EmbeddingConfig(
            provider=provider,
            model=model,
            apiKey=api_key,
            baseUrl=base_url,
            dimensions=dims,
        ),
        dbPath=db_path,
        autoCapture=bool(val.get("autoCapture", False)),
        autoRecall=bool(val.get("autoRecall", True)),
        captureMaxChars=cap_max,
        recallMaxChars=rec_max,
        customTriggers=clean_triggers,
        storageOptions=clean_storage,
    )


__all__ = [
    "DEFAULT_CAPTURE_MAX_CHARS",
    "DEFAULT_RECALL_MAX_CHARS",
    "EMBEDDING_DIMENSIONS",
    "MEMORY_CATEGORIES",
    "MEMORY_LANCEDB_AGENT_TOOLS",
    "MEMORY_LANCEDB_CLI_COMMANDS",
    "MEMORY_LANCEDB_PLUGIN_ID",
    "EmbeddingConfig",
    "MemoryCategory",
    "ResolvedMemoryLanceDbConfig",
    "resolve_memory_lancedb_config",
]
