"""Remote model-catalog bundle validation and sanitization.

OpenClaw parity:
``packages/model-catalog-core/src/remote-catalog-bundle.ts``.
Strict shape validation (unknown keys rejected, duplicate model ids
rejected, ``contextWindowDefault`` must reference a declared option,
``generatedAt`` bounded against future skew), then transport
sanitization: every ``baseUrl``/``headers`` override is stripped
before remote data reaches persistence — remote bundles never set
where requests go.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .model_catalog_types import (
    MODEL_CATALOG_APIS,
    MODEL_CATALOG_MAX_CONTEXT_WINDOWS,
    MODEL_CATALOG_THINKING_LEVELS,
)

#: Remote ``generatedAt`` values beyond this future skew are rejected.
REMOTE_CATALOG_MAX_FUTURE_SKEW_MS = 24 * 60 * 60_000

_STATUSES = ("available", "preview", "deprecated", "disabled")
_INPUTS = ("text", "image", "document")


class RemoteCatalogError(ValueError):
    """Raised when a remote catalog bundle fails strict validation."""


@dataclass(frozen=True, slots=True)
class RemoteModelCatalogPricing:
    """Hosted pricing row for one model."""

    input: float = 0.0
    output: float = 0.0
    cache_read: float | None = None
    cache_write: float | None = None


@dataclass(frozen=True, slots=True)
class RemoteModelCatalogBundle:
    """Validated, transport-sanitized remote catalog bundle."""

    schema_version: int = 1
    generated_at: int = 0
    source_commit: str = ""
    providers: dict[str, Any] = field(default_factory=dict)
    min_version: str | None = None
    pricing: dict[str, RemoteModelCatalogPricing] = field(default_factory=dict)


def _fail(path: str, message: str) -> RemoteCatalogError:
    return RemoteCatalogError(f"{path}: {message}")


def _require_record(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail(path, "must be an object")
    return value


def _as_list(value: Any) -> list[Any] | None:
    """Narrow ``unknown`` JSON to a list (``None`` when not one).

    Centralizes the ``isinstance`` narrowing so element types stay
    explicit ``Any`` instead of degrading to ``Unknown`` at every
    validation call site.
    """
    if not isinstance(value, list):
        return None
    narrowed: list[Any] = value
    return narrowed


def _check_finite_nonnegative(value: object, path: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value != value
        or value in (float("inf"), float("-inf"))
        or value < 0
    ):
        raise _fail(path, "must be a finite non-negative number")
    return float(value)


def _check_positive_int(value: object, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _fail(path, "must be a positive integer")
    return value


def _check_trimmed_string(value: object, path: str, *, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise _fail(path, "must be a non-empty string")
    assert isinstance(value, str)
    return value


def _check_string_map(value: object, path: str) -> dict[str, str]:
    record = _require_record(value, path)
    checked: dict[str, str] = {}
    for key, item in record.items():
        if not isinstance(item, str):
            raise _fail(f"{path}.{key}", "must be a string")
        checked[key] = item
    return checked


def _validate_pricing(value: object, path: str, *, hosted: bool) -> RemoteModelCatalogPricing:
    record = _require_record(value, path)
    allowed = {"input", "output", "cacheRead", "cacheWrite", "tieredPricing"}
    unknown = set(record) - allowed
    if unknown:
        raise _fail(path, f"unknown keys: {sorted(unknown)}")
    get = record.get
    if hosted or "input" in record:
        cost_input = _check_finite_nonnegative(get("input"), f"{path}.input")
    else:
        cost_input = 0.0
    if hosted or "output" in record:
        cost_output = _check_finite_nonnegative(get("output"), f"{path}.output")
    else:
        cost_output = 0.0
    cache_read = (
        _check_finite_nonnegative(get("cacheRead"), f"{path}.cacheRead")
        if "cacheRead" in record
        else None
    )
    cache_write = (
        _check_finite_nonnegative(get("cacheWrite"), f"{path}.cacheWrite")
        if "cacheWrite" in record
        else None
    )
    return RemoteModelCatalogPricing(
        input=cost_input, output=cost_output, cache_read=cache_read, cache_write=cache_write
    )


def _validate_model(value: object, path: str) -> dict[str, Any]:
    record = _require_record(value, path)
    allowed = {
        "id",
        "name",
        "api",
        "baseUrl",
        "headers",
        "input",
        "reasoning",
        "contextWindow",
        "contextWindows",
        "contextWindowDefault",
        "contextTokens",
        "maxTokens",
        "thinkingLevelMap",
        "cost",
        "compat",
        "mediaInput",
        "status",
        "statusReason",
        "replaces",
        "replacedBy",
        "tags",
    }
    unknown = set(record) - allowed
    if unknown:
        raise _fail(path, f"unknown keys: {sorted(unknown)}")
    model_id = _check_trimmed_string(record.get("id"), f"{path}.id")
    if "api" in record and record.get("api") not in MODEL_CATALOG_APIS:
        raise _fail(f"{path}.api", f"must be one of {list(MODEL_CATALOG_APIS)}")
    if "input" in record:
        inputs = _as_list(record.get("input"))
        if inputs is None or any(item not in _INPUTS for item in inputs):
            raise _fail(f"{path}.input", f"must be a list of {list(_INPUTS)}")
    if "contextWindows" in record:
        windows = _as_list(record.get("contextWindows"))
        if windows is None or len(windows) > MODEL_CATALOG_MAX_CONTEXT_WINDOWS:
            raise _fail(f"{path}.contextWindows", "must be a bounded option list")
        seen: set[str] = set()
        for index, entry in enumerate(windows):
            option = _require_record(entry, f"{path}.contextWindows.{index}")
            option_unknown = set(option) - {"id", "label", "contextWindow"}
            if option_unknown:
                raise _fail(
                    f"{path}.contextWindows.{index}",
                    f"unknown keys: {sorted(option_unknown)}",
                )
            option_id = _check_trimmed_string(option.get("id"), f"{path}.contextWindows.{index}.id")
            _check_trimmed_string(option.get("label"), f"{path}.contextWindows.{index}.label")
            _check_positive_int(
                option.get("contextWindow"),
                f"{path}.contextWindows.{index}.contextWindow",
            )
            if option_id in seen:
                raise _fail(f"{path}.contextWindows.{index}.id", "duplicate option id")
            seen.add(option_id)
        default = record.get("contextWindowDefault")
        if default is not None:
            _check_trimmed_string(default, f"{path}.contextWindowDefault")
            if default.strip() not in seen:
                raise _fail(
                    f"{path}.contextWindowDefault",
                    "must reference a declared contextWindows option",
                )
    thinking_map = record.get("thinkingLevelMap")
    if thinking_map is not None:
        thinking_record = _require_record(thinking_map, f"{path}.thinkingLevelMap")
        for level, mapped in thinking_record.items():
            if level not in MODEL_CATALOG_THINKING_LEVELS:
                raise _fail(f"{path}.thinkingLevelMap.{level}", "unknown thinking level")
            if mapped is not None and not isinstance(mapped, str):
                raise _fail(f"{path}.thinkingLevelMap.{level}", "must be a string or null")
    if "cost" in record:
        _validate_pricing(record.get("cost"), f"{path}.cost", hosted=False)
    return {"id": model_id, **{k: v for k, v in record.items() if k != "id"}}


def _validate_provider(value: object, path: str) -> dict[str, Any]:
    record = _require_record(value, path)
    allowed = {"baseUrl", "api", "headers", "defaultModel", "defaultUtilityModel", "models"}
    unknown = set(record) - allowed
    if unknown:
        raise _fail(path, f"unknown keys: {sorted(unknown)}")
    if "api" in record and record.get("api") not in MODEL_CATALOG_APIS:
        raise _fail(f"{path}.api", f"must be one of {list(MODEL_CATALOG_APIS)}")
    models = _as_list(record.get("models"))
    if not models:
        raise _fail(f"{path}.models", "must be a non-empty list")
    seen: set[str] = set()
    for index, model in enumerate(models):
        validated = _validate_model(model, f"{path}.models.{index}")
        if validated["id"] in seen:
            raise _fail(f"{path}.models.{index}.id", f"duplicate model id: {validated['id']}")
        seen.add(validated["id"])
    return record


def parse_remote_model_catalog_bundle(value: object) -> RemoteModelCatalogBundle:
    """Strictly validate a remote catalog bundle (raises :class:`RemoteCatalogError`)."""
    record = _require_record(value, "bundle")
    allowed = {"schemaVersion", "generatedAt", "minVersion", "sourceCommit", "providers", "pricing"}
    unknown = set(record) - allowed
    if unknown:
        raise _fail("bundle", f"unknown keys: {sorted(unknown)}")
    if record.get("schemaVersion") != 1:
        raise _fail("bundle.schemaVersion", "must be 1")
    generated_at = record.get("generatedAt")
    if not isinstance(generated_at, int) or isinstance(generated_at, bool) or generated_at <= 0:
        raise _fail("bundle.generatedAt", "must be a positive integer")
    now_ms = int(time.time() * 1000)
    if generated_at > now_ms + REMOTE_CATALOG_MAX_FUTURE_SKEW_MS:
        raise _fail("bundle.generatedAt", "is implausibly far in the future")
    source_commit = _check_trimmed_string(record.get("sourceCommit"), "bundle.sourceCommit")
    providers = _require_record(record.get("providers"), "bundle.providers")
    validated_providers: dict[str, Any] = {}
    for provider_id, provider in providers.items():
        if not provider_id.strip():
            raise _fail("bundle.providers", "provider ids must be non-empty")
        validated_providers[provider_id] = _validate_provider(
            provider, f"bundle.providers.{provider_id}"
        )
    pricing: dict[str, RemoteModelCatalogPricing] = {}
    if "pricing" in record:
        pricing_record = _require_record(record.get("pricing"), "bundle.pricing")
        for key, entry in pricing_record.items():
            if not key.strip():
                raise _fail("bundle.pricing", "pricing keys must be non-empty")
            pricing[key] = _validate_pricing(entry, f"bundle.pricing.{key}", hosted=True)
    min_version = record.get("minVersion")
    if min_version is not None:
        _check_trimmed_string(min_version, "bundle.minVersion")
    return RemoteModelCatalogBundle(
        schema_version=1,
        generated_at=generated_at,
        source_commit=source_commit,
        providers=validated_providers,
        min_version=min_version if isinstance(min_version, str) else None,
        pricing=pricing,
    )


def _strip_remote_transport_overrides(value: object) -> object:
    items = _as_list(value)
    if items is not None:
        return [_strip_remote_transport_overrides(item) for item in items]
    if not isinstance(value, dict):
        return value
    stripped: Any = value
    return {
        key: _strip_remote_transport_overrides(item)
        for key, item in stripped.items()
        if key not in ("baseUrl", "headers")
    }


def sanitize_remote_model_catalog_bundle(
    bundle: RemoteModelCatalogBundle,
) -> RemoteModelCatalogBundle:
    """Remove every transport endpoint/header override before persistence."""
    return RemoteModelCatalogBundle(
        schema_version=bundle.schema_version,
        generated_at=bundle.generated_at,
        source_commit=bundle.source_commit,
        providers={
            provider_id: _strip_remote_transport_overrides(provider)
            for provider_id, provider in bundle.providers.items()
        },
        min_version=bundle.min_version,
        pricing=dict(bundle.pricing),
    )


def validate_and_sanitize_remote_model_catalog_bundle(
    value: object,
) -> RemoteModelCatalogBundle:
    """Validate then sanitize a remote catalog bundle in one step."""
    return sanitize_remote_model_catalog_bundle(parse_remote_model_catalog_bundle(value))


__all__ = [
    "REMOTE_CATALOG_MAX_FUTURE_SKEW_MS",
    "RemoteCatalogError",
    "RemoteModelCatalogBundle",
    "RemoteModelCatalogPricing",
    "parse_remote_model_catalog_bundle",
    "sanitize_remote_model_catalog_bundle",
    "validate_and_sanitize_remote_model_catalog_bundle",
]
