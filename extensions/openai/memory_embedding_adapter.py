"""extensions.openai.memory_embedding_adapter — OpenAI memory embedding adapter.

OpenClaw parity: mirrors extensions/openai/memory-embedding-adapter.ts.
Provides OpenAiMemoryEmbeddingAdapter conforming to
jarvis_sdk.MemoryEmbeddingProviderAdapter.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import urllib.request

from jarvis_sdk import (
    MemoryEmbeddingProvider,
    MemoryEmbeddingProviderAdapter,
)

_log = logging.getLogger("extensions.openai.embeddings")

DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"


def _resolve_api_key(config: dict[str, Any] | None = None, **options: Any) -> str | None:
    """Resolve OpenAI API key from options, config, credentials, or env."""
    key = options.get("apiKey") or options.get("api_key")
    if key and isinstance(key, str):
        return key

    remote = options.get("remote")
    if isinstance(remote, dict):
        key = remote.get("apiKey") or remote.get("api_key")
        if key and isinstance(key, str):
            return key

    if isinstance(config, dict):
        embedding_cfg = config.get("embedding")
        if isinstance(embedding_cfg, dict):
            key = embedding_cfg.get("apiKey") or embedding_cfg.get("api_key")
            if key and isinstance(key, str):
                return key

    for env_var in ("OPENAI_API_KEY", "JARVIS_OPENAI_API_KEY"):
        val = os.environ.get(env_var)
        if val and val.strip():
            return val.strip()

    try:
        from src.sessions.credentials import resolve_credentials

        cred = resolve_credentials(provider="openai")
        if cred and isinstance(cred, str):
            return cred
    except Exception:
        pass

    try:
        api_keys_path = Path(__file__).resolve().parents[2] / "config" / "api_keys.json"
        if api_keys_path.exists():
            data = json.loads(api_keys_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                key = data.get("openai_api_key")
                if key and isinstance(key, str):
                    return key
    except Exception:
        pass

    return None


class OpenAiMemoryEmbeddingProvider(MemoryEmbeddingProvider):
    """Embeddings provider using OpenAI-compatible HTTP endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_OPENAI_EMBEDDING_MODEL,
        base_url: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._dimensions = dimensions

    async def embed_query(
        self,
        text: str,
        options: dict[str, Any] | None = None,
    ) -> list[float]:
        payload: dict[str, Any] = {
            "model": self._model,
            "input": text,
        }
        dims = (options.get("outputDimensionality") if options else None) or self._dimensions
        if dims and isinstance(dims, int):
            payload["dimensions"] = dims

        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")  # noqa: S310

        def _do_call() -> list[float]:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                raw = resp.read()
            body = json.loads(raw.decode("utf-8"))
            data_list = body.get("data")
            if data_list and isinstance(data_list, list) and len(data_list) > 0:
                vec = data_list[0].get("embedding")
                if vec and isinstance(vec, list):
                    return [float(v) for v in vec]
            raise ValueError(f"OpenAI embedding response missing vector: {body}")

        return await asyncio.to_thread(_do_call)

    async def embed_batch(
        self,
        chunks: list[str],
        options: dict[str, Any] | None = None,
    ) -> list[list[float]]:
        results: list[list[float]] = []
        for chunk in chunks:
            results.append(await self.embed_query(chunk, options=options))
        return results


@dataclass(frozen=True, slots=True)
class OpenAiEmbeddingCreateResult:
    """Wrapper matching OpenClaw's MemoryEmbeddingProviderCreateResult."""

    provider: MemoryEmbeddingProvider


class OpenAiMemoryEmbeddingAdapter(MemoryEmbeddingProviderAdapter):
    """Adapter producing an OpenAI embedding provider instance for memory."""

    id: str = "openai"

    async def create(
        self,
        config: dict[str, Any] | None = None,
        *,
        agent_dir: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        **options: Any,
    ) -> OpenAiEmbeddingCreateResult | None:
        api_key = _resolve_api_key(config, **options)
        if not api_key:
            _log.debug("OpenAI embedding adapter: no API key found")
            return None

        selected_model = model or DEFAULT_OPENAI_EMBEDDING_MODEL
        base_url = options.get("baseUrl") or options.get("base_url")
        dims = options.get("outputDimensionality") or options.get("dimensions")
        if not isinstance(dims, int):
            dims = None

        prov = OpenAiMemoryEmbeddingProvider(
            api_key=api_key,
            model=selected_model,
            base_url=base_url,
            dimensions=dims,
        )
        return OpenAiEmbeddingCreateResult(provider=prov)


openai_memory_embedding_adapter = OpenAiMemoryEmbeddingAdapter()

__all__ = [
    "DEFAULT_OPENAI_EMBEDDING_MODEL",
    "OpenAiMemoryEmbeddingAdapter",
    "OpenAiMemoryEmbeddingProvider",
    "openai_memory_embedding_adapter",
]
