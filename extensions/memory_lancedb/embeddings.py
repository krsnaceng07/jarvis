"""embeddings — OpenAI + OpenAI-compatible embeddings + provider adapter.

OpenClaw parity: mirrors the ``OpenAiCompatibleEmbeddings`` and
``ProviderAdapterEmbeddings`` classes from
``extensions/memory-lancedb/index.ts``.

Two strategies are supported, picked at runtime by the
``create_embeddings`` factory:

1. **Direct OpenAI-compatible HTTP** (used when
   ``embedding.provider == "openai"`` AND an ``apiKey`` is
   present). Hits ``POST /embeddings`` directly so we work with
   any OpenAI-compatible endpoint and avoid the SDK's
   ``encoding_format=base64`` auto-injection (some providers
   reject it).
2. **Provider adapter** (used otherwise). Delegates to the
   SDK's ``MemoryEmbeddingProvider`` registry (Phase 4.0 SDK).

Both strategies return a callable ``embed(text, *,
timeout_ms=None)`` matching OpenClaw's ``Embeddings`` shape.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import struct
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from jarvis_sdk import (
    MemoryEmbeddingProvider,
    as_optional_record,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from .config import MemoryConfig

_log = logging.getLogger("extensions.memory_lancedb.embeddings")


class Embeddings(ABC):
    """Abstract embeddings client. Mirrors OpenClaw's ``Embeddings``."""

    @abstractmethod
    async def embed(self, text: str, *, timeout_ms: int | None = None) -> list[float]: ...


# ── Helpers ─────────────────────────────────────────────────────


def normalize_embedding_vector(value: Any) -> list[float]:
    """Normalize a raw embedding response field.

    Mirrors OpenClaw's ``normalizeEmbeddingVector``. Accepts
    either a JSON list of floats or a base64-encoded float32
    array (the format the OpenAI SDK returns when
    ``encoding_format=base64``).
    """
    if isinstance(value, list):
        if not all(isinstance(v, int | float) and math.isfinite(v) for v in value):
            raise ValueError("Embedding response contains non-numeric values")
        return [float(v) for v in value]

    if isinstance(value, str):
        raw = base64.b64decode(value)
        if len(raw) % 4 != 0:
            raise ValueError("Base64 embedding response has invalid byte length")
        floats: list[float] = []
        for offset in range(0, len(raw), 4):
            floats.append(struct.unpack_from("<f", raw, offset)[0])
        return floats

    raise ValueError("Embedding response is missing a vector")


def truncate_embedding_vector(embedding: list[float], dimensions: int, model: str) -> list[float]:
    """Truncate a returned embedding to ``dimensions`` dims.

    Mirrors OpenClaw's ``truncateEmbeddingVector``. The
    returned vector is L2-re-normalized so distance ranking
    compares fallback and stored vectors on the same scale.
    """
    if len(embedding) < dimensions:
        raise RuntimeError(
            f"Embedding model {model} returned {len(embedding)} dimensions, "
            f"need at least {dimensions} for local truncation"
        )
    truncated = embedding[:dimensions]
    magnitude = math.sqrt(sum(v * v for v in truncated))
    if magnitude > 0:
        return [v / magnitude for v in truncated]
    return truncated


def _is_embedding_dimensions_rejected_error(
    error: BaseException,
) -> bool:
    """Return True if ``error`` indicates the provider rejected the
    ``dimensions`` request field.

    Mirrors OpenClaw's ``isEmbeddingDimensionsRejectedError``.
    """
    record = as_optional_record(getattr(error, "__dict__", None))
    status = record.get("status") if record else None
    if status not in (400, 422):
        return False
    details = _stringify_embedding_api_error(error).lower()
    if "dimensions" not in details:
        return False
    return _is_unsupported_embedding_field_error(details)


def _is_unsupported_embedding_field_error(details: str) -> bool:
    if (
        "parameter_value" in details.replace(" ", "_")
        or "field_value" in details.replace(" ", "_")
        or "argument_value" in details.replace(" ", "_")
    ):
        return False
    needles = (
        "extra_forbidden",
        "extra inputs not permitted",
        "extra input not permitted",
        "extra fields not permitted",
        "unknown_request_parameter",
        "unknown_request_field",
        "unknown_request_argument",
        "unrecognized_request_parameter",
        "unrecognized_request_field",
        "unrecognized_request_argument",
        "unexpected_request_parameter",
        "unexpected_request_field",
        "unexpected_request_argument",
        "unsupported_request_parameter",
        "unsupported_request_field",
        "unsupported_request_argument",
        "unknown parameter",
        "unknown field",
        "unknown argument",
        "unrecognized parameter",
        "unrecognized field",
        "unrecognized argument",
        "unexpected parameter",
        "unexpected field",
        "unexpected argument",
        "unsupported parameter",
        "unsupported field",
        "unsupported argument",
    )
    return any(n in details for n in needles)


def _stringify_embedding_api_error(error: BaseException) -> str:
    parts: list[str] = [str(error)]
    record = as_optional_record(getattr(error, "__dict__", None))
    for key in ("code", "type", "param", "error"):
        value = record.get(key) if record else None
        if isinstance(value, str | int | float | bool):
            parts.append(str(value))
        elif value is not None:
            try:
                parts.append(json.dumps(value, default=str))
            except Exception as exc:
                _log.debug("stringify_embedding_api_error: %s", exc)
    return "\n".join(parts)


# ── Direct OpenAI-compatible HTTP client ────────────────────────


class OpenAiCompatibleEmbeddings(Embeddings):
    """Direct ``POST /embeddings`` client.

    Mirrors OpenClaw's ``OpenAiCompatibleEmbeddings``. We
    use ``urllib.request`` so we don't pull the openai SDK as
    a hard dep (the SDK is heavy and adds ``openai>=6.45``).
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        dimensions: int | None = None,
        *,
        request: Callable[..., Any] | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._dimensions = dimensions
        self._request = request or urllib.request.urlopen

    async def embed(self, text: str, *, timeout_ms: int | None = None) -> list[float]:
        started_at = time.monotonic() if timeout_ms else None
        try:
            payload = await self._post(text, include_dimensions=True, timeout_ms=timeout_ms)
            return normalize_embedding_vector(payload["data"][0]["embedding"])
        except urllib.error.HTTPError as exc:
            if self._dimensions is None or not _is_embedding_dimensions_rejected_error(exc):
                raise
            if started_at is not None and timeout_ms is not None:
                remaining = max(1, int(timeout_ms - (time.monotonic() - started_at) * 1000))
            else:
                remaining = timeout_ms
            payload = await self._post(text, include_dimensions=False, timeout_ms=remaining)
            embedding = normalize_embedding_vector(payload["data"][0]["embedding"])
            return truncate_embedding_vector(embedding, self._dimensions, self._model)

    async def _post(
        self, text: str, *, include_dimensions: bool, timeout_ms: int | None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"model": self._model, "input": text}
        if include_dimensions and isinstance(self._dimensions, int):
            params["dimensions"] = self._dimensions
        body = json.dumps(params).encode("utf-8")
        url = f"{self._base_url}/embeddings"
        # base_url is operator-configured (embedding.baseUrl in
        # the plugin config), so SSRF concerns are bounded to
        # the operator's own network. The S310 warning is
        # therefore acceptable here.
        req = urllib.request.Request(  # noqa: S310
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        timeout_s: float | None = None
        if timeout_ms is not None:
            timeout_s = max(0.001, timeout_ms / 1000.0)
        with self._request(req, timeout=timeout_s) as resp:  # type: ignore[call-arg]
            raw = resp.read()
        return json.loads(raw.decode("utf-8"))


# ── Provider adapter ────────────────────────────────────────────


class ProviderAdapterEmbeddings(Embeddings):
    """Delegates to the SDK's ``MemoryEmbeddingProvider`` registry.

    Mirrors OpenClaw's ``ProviderAdapterEmbeddings``. The
    provider instance is created lazily so auth-profile or
    local-provider repairs while the Gateway is up are picked
    up on the next call.
    """

    def __init__(
        self,
        *,
        provider_id: str,
        embedding_model: str,
        embedding_dimensions: int | None,
        config_provider: Callable[[], Any] | None = None,
        get_provider: Callable[[str, Any], Any] | None = None,
        create_provider: Callable[..., Any] | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._model = embedding_model
        self._dimensions = embedding_dimensions
        self._config_provider = config_provider
        self._get_provider = get_provider
        self._create_provider = create_provider
        self._lock = threading.Lock()
        self._provider: MemoryEmbeddingProvider | None = None
        self._failed: BaseException | None = None

    async def embed(self, text: str, *, timeout_ms: int | None = None) -> list[float]:
        provider = await self._get_or_create_provider()
        if not timeout_ms:
            return await provider.embed_query(text)
        return await _run_embed_with_timeout(provider, text, timeout_ms=timeout_ms)

    async def _get_or_create_provider(self) -> MemoryEmbeddingProvider:
        if self._provider is not None:
            return self._provider
        with self._lock:
            if self._provider is not None:
                return self._provider
            if self._failed is not None:
                # Retry the failure path so transient auth repairs work.
                self._failed = None
            try:
                provider = self._create_provider_fn()
            except BaseException as exc:
                self._failed = exc
                raise
            self._provider = provider
            return provider

    def _create_provider_fn(self) -> MemoryEmbeddingProvider:
        if self._create_provider is not None:
            created = self._create_provider()
        elif self._get_provider is not None and self._config_provider is not None:
            adapter = self._get_provider(self._provider_id, self._config_provider())
            if adapter is None:
                raise RuntimeError(f"Unknown memory embedding provider: {self._provider_id}")
            created = adapter.create(
                config=self._config_provider(),
                provider=self._provider_id,
                fallback="none",
                model=self._model,
                **(
                    {"outputDimensionality": self._dimensions}
                    if isinstance(self._dimensions, int)
                    else {}
                ),
            )
            if not getattr(created, "provider", None):
                raise RuntimeError(f"Memory embedding provider {self._provider_id} is unavailable.")
            created = created.provider
        else:  # pragma: no cover - defensive
            raise RuntimeError("ProviderAdapterEmbeddings not configured")
        return created


async def _run_embed_with_timeout(
    provider: MemoryEmbeddingProvider, text: str, *, timeout_ms: int
) -> list[float]:
    """Run ``provider.embed_query`` with a Python-level timeout.

    Mirrors OpenClaw's ``setTimeout`` + ``AbortController``
    pattern. The provider implementations may or may not
    honor ``signal``; this is a defensive belt-and-braces.
    """
    try:
        return await asyncio.wait_for(
            provider.embed_query(text),  # type: ignore[arg-type]
            timeout=max(0.001, timeout_ms / 1000.0),
        )
    except TimeoutError as exc:
        raise RuntimeError(f"memory-lancedb embedding timed out after {timeout_ms}ms") from exc


# ── Factory ─────────────────────────────────────────────────────


def create_embeddings(
    cfg: MemoryConfig,
    *,
    config_provider: Callable[[], Any] | None = None,
    get_provider: Callable[[str, Any], Any] | None = None,
    create_provider: Callable[..., Any] | None = None,
    request: Callable[..., Any] | None = None,
) -> Embeddings:
    """Pick the right embeddings strategy based on ``cfg``.

    Mirrors OpenClaw's ``createEmbeddings``. Direct OpenAI
    when ``provider == "openai"`` AND an ``apiKey`` is
    present; otherwise fall back to the provider adapter.
    """
    if (
        cfg.embedding_provider == "openai"
        and cfg.embedding_api_key
        and create_provider is None
        and get_provider is None
    ):
        return OpenAiCompatibleEmbeddings(
            api_key=cfg.embedding_api_key,
            model=cfg.embedding_model,
            base_url=cfg.embedding_base_url,
            dimensions=cfg.embedding_dimensions,
            request=request,
        )
    return ProviderAdapterEmbeddings(
        provider_id=cfg.embedding_provider,
        embedding_model=cfg.embedding_model,
        embedding_dimensions=cfg.embedding_dimensions,
        config_provider=config_provider,
        get_provider=get_provider,
        create_provider=create_provider,
    )


__all__ = [
    "Embeddings",
    "OpenAiCompatibleEmbeddings",
    "ProviderAdapterEmbeddings",
    "create_embeddings",
    "normalize_embedding_vector",
    "truncate_embedding_vector",
]
