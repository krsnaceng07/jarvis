"""extensions.google.memory_embedding_adapter — Gemini memory embedding adapter.

OpenClaw parity: mirrors extensions/google/memory-embedding-adapter.ts and
extensions/google/embedding-provider.ts. Provides GeminiMemoryEmbeddingAdapter
conforming to jarvis_sdk.MemoryEmbeddingProviderAdapter.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jarvis_sdk import (
    MemoryEmbeddingProvider,
    MemoryEmbeddingProviderAdapter,
)

_log = logging.getLogger("extensions.google.embeddings")

DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"


def _resolve_api_key(config: dict[str, Any] | None = None, **options: Any) -> str | None:
    """Resolve Gemini API key from explicit options, config, credentials helper, or env."""
    # 1. Explicit options
    key = options.get("apiKey") or options.get("api_key")
    if key and isinstance(key, str):
        return key

    remote = options.get("remote")
    if isinstance(remote, dict):
        key = remote.get("apiKey") or remote.get("api_key")
        if key and isinstance(key, str):
            return key

    # 2. Config options
    if isinstance(config, dict):
        embedding_cfg = config.get("embedding")
        if isinstance(embedding_cfg, dict):
            key = embedding_cfg.get("apiKey") or embedding_cfg.get("api_key")
            if key and isinstance(key, str):
                return key

    # 3. Environment variables
    for env_var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "JARVIS_GEMINI_API_KEY", "JARVIS_GOOGLE_API_KEY"):
        val = os.environ.get(env_var)
        if val and val.strip():
            return val.strip()

    # 4. Central credential resolver
    try:
        from src.sessions.credentials import resolve_credentials

        cred = resolve_credentials(provider="google") or resolve_credentials(provider="gemini")
        if cred and isinstance(cred, str):
            return cred
    except Exception:
        pass

    # 5. Fallback: repository api_keys.json
    try:
        api_keys_path = Path(__file__).resolve().parents[2] / "config" / "api_keys.json"
        if api_keys_path.exists():
            data = json.loads(api_keys_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                key = data.get("gemini_api_key") or data.get("google_api_key")
                if key and isinstance(key, str):
                    return key
    except Exception:
        pass

    return None


class GeminiMemoryEmbeddingProvider(MemoryEmbeddingProvider):
    """Embeddings provider using Google Gemini API."""

    def __init__(
        self,
        client: Any,
        model: str = DEFAULT_GEMINI_EMBEDDING_MODEL,
        dimensions: int | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._dimensions = dimensions

    async def embed_query(
        self,
        text: str,
        options: dict[str, Any] | None = None,
    ) -> list[float]:
        """Embed a single query or document text."""
        config_dict: dict[str, Any] = {}
        dims = (options.get("outputDimensionality") if options else None) or self._dimensions
        if dims and isinstance(dims, int):
            config_dict["output_dimensionality"] = dims

        def _do_call() -> list[float]:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "contents": text,
            }
            if config_dict:
                kwargs["config"] = config_dict

            res = self._client.models.embed_content(**kwargs)
            if hasattr(res, "embeddings") and res.embeddings:
                return [float(v) for v in res.embeddings[0].values]
            if hasattr(res, "embedding") and getattr(res.embedding, "values", None):
                return [float(v) for v in res.embedding.values]
            raise ValueError(f"Gemini embedding response missing values: {res}")

        return await asyncio.to_thread(_do_call)

    async def embed_batch(
        self,
        chunks: list[str],
        options: dict[str, Any] | None = None,
    ) -> list[list[float]]:
        """Embed a batch of text chunks."""
        results: list[list[float]] = []
        for chunk in chunks:
            vec = await self.embed_query(chunk, options=options)
            results.append(vec)
        return results


@dataclass(frozen=True, slots=True)
class EmbeddingCreateResult:
    """Wrapper matching OpenClaw's MemoryEmbeddingProviderCreateResult."""

    provider: MemoryEmbeddingProvider


def normalize_gemini_model(model: str | None) -> str:
    """Normalize Gemini embedding model name (mirrors OpenClaw's normalizeGeminiModel)."""
    if not model or not isinstance(model, str):
        return DEFAULT_GEMINI_EMBEDDING_MODEL
    trimmed = model.strip()
    if not trimmed:
        return DEFAULT_GEMINI_EMBEDDING_MODEL
    without_prefix = trimmed.removeprefix("models/").removeprefix("gemini/").removeprefix("google/")
    if not without_prefix.startswith("gemini") and not without_prefix.startswith("embedding"):
        return DEFAULT_GEMINI_EMBEDDING_MODEL
    return without_prefix


class GeminiMemoryEmbeddingAdapter(MemoryEmbeddingProviderAdapter):
    """Adapter producing a Gemini embedding provider instance for memory."""

    id: str = "google"
    default_model: str = DEFAULT_GEMINI_EMBEDDING_MODEL
    defaultModel: str = DEFAULT_GEMINI_EMBEDDING_MODEL

    async def create(
        self,
        config: dict[str, Any] | None = None,
        *,
        agent_dir: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        **options: Any,
    ) -> EmbeddingCreateResult | None:
        api_key = _resolve_api_key(config, **options)
        if not api_key:
            _log.warning("Gemini embedding adapter: no API key found")
            return None

        try:
            from google import genai

            client = genai.Client(api_key=api_key)
        except Exception as exc:
            _log.warning("Gemini embedding adapter: failed to initialize client: %s", exc)
            return None

        selected_model = normalize_gemini_model(model)

        dims = options.get("outputDimensionality") or options.get("dimensions")
        if not isinstance(dims, int):
            dims = None

        prov = GeminiMemoryEmbeddingProvider(
            client=client,
            model=selected_model,
            dimensions=dims,
        )
        return EmbeddingCreateResult(provider=prov)


gemini_memory_embedding_adapter = GeminiMemoryEmbeddingAdapter()

__all__ = [
    "DEFAULT_GEMINI_EMBEDDING_MODEL",
    "GeminiMemoryEmbeddingAdapter",
    "GeminiMemoryEmbeddingProvider",
    "gemini_memory_embedding_adapter",
]
