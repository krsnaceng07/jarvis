"""Stable model-catalog ref and merge-key builders.

OpenClaw parity: ``packages/model-catalog-core/src/model-catalog-refs.ts``.
Refs (``provider/model``) are the canonical cross-package model identity;
merge keys (``provider::model``) are the case-insensitive join key for
catalog rows. Parsing is strict and never normalizes either segment —
normalization is an explicit separate step.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis_normalization_core.string_coerce import normalize_lowercase_string_or_empty

from .provider_id import normalize_provider_id
from .provider_id import normalize_provider_id as normalize_model_catalog_provider_id


@dataclass(frozen=True, slots=True)
class ModelCatalogRef:
    """A parsed catalog reference with a normalized provider segment."""

    provider: str
    model_id: str


@dataclass(frozen=True, slots=True)
class ProviderModelRef:
    """A strict provider/model split with both segments verbatim."""

    provider: str
    model: str


def _parse_model_source_suffix(model_ref: str) -> tuple[str, str] | None:
    """Split one ``:cloud``/``:local``/``-cloud`` hosted-source suffix."""
    separator = model_ref.rfind(":")
    if separator < 0:
        return None
    source = model_ref[separator + 1 :]
    if source in ("cloud", "local"):
        return (model_ref[:separator], source)
    if "/" not in source and source.endswith("-cloud"):
        return (model_ref[:separator], "cloud")
    return None


def is_cloud_model_ref(model_ref: object) -> bool:
    """Recognize one unambiguous hosted ``:cloud`` suffix on a model ref.

    Double-suffixed refs (``x:cloud:cloud``) are not cloud refs — the
    ambiguity means the suffix is part of the id, not a source marker.
    """
    if not isinstance(model_ref, str):
        return False
    normalized = model_ref.strip().lower()
    if not normalized:
        return False
    parsed = _parse_model_source_suffix(normalized)
    return (
        parsed is not None
        and parsed[1] == "cloud"
        and _parse_model_source_suffix(parsed[0]) is None
    )


def build_model_catalog_ref(provider: str, model_id: str) -> str:
    """Build a ``provider/model`` catalog reference (provider normalized)."""
    return f"{normalize_provider_id(provider)}/{model_id}"


def parse_provider_model_ref(value: str) -> ProviderModelRef | None:
    """Parse a strict ``provider/model`` reference without normalizing.

    Returns ``None`` when there is no interior ``/`` or either segment
    is empty after trimming.
    """
    trimmed = value.strip()
    slash = trimmed.find("/")
    if slash <= 0 or slash >= len(trimmed) - 1:
        return None
    provider = trimmed[:slash].strip()
    model = trimmed[slash + 1 :].strip()
    return ProviderModelRef(provider=provider, model=model) if provider and model else None


def parse_model_catalog_ref(value: str) -> ModelCatalogRef | None:
    """Parse a catalog reference; the provider segment is normalized."""
    parsed = parse_provider_model_ref(value)
    if parsed is None:
        return None
    return ModelCatalogRef(
        provider=normalize_provider_id(parsed.provider),
        model_id=parsed.model,
    )


def build_model_catalog_merge_key(provider: str, model_id: str) -> str:
    """Build a case-insensitive ``provider::model`` merge key for catalog rows."""
    return f"{normalize_provider_id(provider)}::{normalize_lowercase_string_or_empty(model_id)}"


__all__ = [
    "ModelCatalogRef",
    "ProviderModelRef",
    "build_model_catalog_merge_key",
    "build_model_catalog_ref",
    "is_cloud_model_ref",
    "normalize_model_catalog_provider_id",
    "parse_model_catalog_ref",
    "parse_provider_model_ref",
]
