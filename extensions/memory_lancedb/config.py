"""config — MemoryConfig schema + parsing + defaults.

OpenClaw parity: mirrors ``extensions/memory-lancedb/config.ts``.

Defines the operator-facing config schema (a subset of
OpenClaw's `memoryConfigSchema`) plus the embedding model
dimension table. Phase 4.1 ships the same surface as
OpenClaw so the operator can drop in a known-good config
without translation.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Defaults (mirror OpenClaw) ───────────────────────────────────

DEFAULT_MODEL = "text-embedding-3-small"

# Mirrors ``DEFAULT_CAPTURE_MAX_CHARS``.
DEFAULT_CAPTURE_MAX_CHARS = 500

# Mirrors ``DEFAULT_RECALL_MAX_CHARS``.
DEFAULT_RECALL_MAX_CHARS = 1000

# Allowed memory categories. Mirrors ``MEMORY_CATEGORIES``.
MEMORY_CATEGORIES: tuple[str, ...] = (
    "preference",
    "fact",
    "decision",
    "entity",
    "other",
)

# Default embedding dimensions for known models. Mirrors
# ``EMBEDDING_DIMENSIONS`` in OpenClaw.
EMBEDDING_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

ALLOWED_EMBEDDING_KEYS: tuple[str, ...] = (
    "provider",
    "apiKey",
    "model",
    "baseUrl",
    "dimensions",
)

ALLOWED_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "embedding",
    "dreaming",
    "dbPath",
    "autoCapture",
    "autoRecall",
    "captureMaxChars",
    "customTriggers",
    "recallMaxChars",
    "storageOptions",
)


# ── Dataclass ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MemoryConfig:
    """Resolved memory config.

    Mirrors OpenClaw's ``MemoryConfig``. All optional fields
    default to OpenClaw's defaults so the host can hand a
    minimal config to the plugin and the rest is filled in.
    """

    embedding_provider: str = "openai"
    embedding_model: str = DEFAULT_MODEL
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    embedding_dimensions: int | None = None
    db_path: str = ""
    auto_capture: bool = False
    auto_recall: bool = True
    capture_max_chars: int = DEFAULT_CAPTURE_MAX_CHARS
    recall_max_chars: int = DEFAULT_RECALL_MAX_CHARS
    custom_triggers: tuple[str, ...] = ()
    dreaming: Mapping[str, Any] | None = None
    storage_options: Mapping[str, str] = field(default_factory=dict)

    @property
    def embedding(self) -> dict[str, Any]:
        """Return the embedding sub-config in OpenClaw's shape."""
        out: dict[str, Any] = {
            "provider": self.embedding_provider,
            "model": self.embedding_model,
        }
        if self.embedding_api_key is not None:
            out["apiKey"] = self.embedding_api_key
        if self.embedding_base_url is not None:
            out["baseUrl"] = self.embedding_base_url
        if self.embedding_dimensions is not None:
            out["dimensions"] = self.embedding_dimensions
        return out


# ── Parsing ──────────────────────────────────────────────────────


def vector_dims_for_model(model: str) -> int:
    """Return the known embedding dimension for ``model``.

    Mirrors OpenClaw's ``vectorDimsForModel``.
    """
    if model not in EMBEDDING_DIMENSIONS:
        raise ValueError(f"Unsupported embedding model: {model}")
    return EMBEDDING_DIMENSIONS[model]


def _resolve_env_vars(value: str) -> str:
    """Expand ``${VAR}`` references in ``value``.

    Mirrors OpenClaw's ``resolveEnvVars`` — used for
    ``apiKey``, ``baseUrl``, and ``storageOptions`` values.
    """
    out = value
    for var in _env_var_names(value):
        env_value = os.environ.get(var)
        if not env_value:
            raise ValueError(f"Environment variable {var} is not set")
        out = out.replace("${" + var + "}", env_value)
    return out


def _env_var_names(value: str) -> list[str]:
    """Return the env-var names referenced in ``${...}`` form."""
    out: list[str] = []
    cursor = 0
    needle = "${"
    while True:
        idx = value.find(needle, cursor)
        if idx == -1:
            break
        end = value.find("}", idx + 2)
        if end == -1:
            break
        out.append(value[idx + 2 : end])
        cursor = end + 1
    return out


def _assert_allowed_keys(value: Mapping[str, Any], allowed: tuple[str, ...], label: str) -> None:
    unknown = [k for k in value if k not in allowed]
    if unknown:
        raise ValueError(f"{label} has unknown keys: {', '.join(unknown)}")


def _resolve_bounded_int(
    *,
    value: Any,
    fallback: int,
    lo: int,
    hi: int,
    label: str,
) -> int:
    raw = value
    if raw is None:
        return fallback
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise ValueError(f"{label} must be a number")
    resolved = int(raw)
    if resolved < lo or resolved > hi:
        raise ValueError(f"{label} must be between {lo} and {hi}")
    return resolved


def _resolve_storage_options(
    raw: Mapping[str, Any] | None,
) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError("storageOptions must be an object")
    out: dict[str, str] = {}
    for key, val in raw.items():
        if not isinstance(val, str):
            raise ValueError(f"storageOptions.{key} must be a string")
        out[key] = _resolve_env_vars(val)
    return out


# ruff: noqa: PLR0912  # config parser is intentionally branchy (mirrors OpenClaw)
def _resolve_embedding(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    if raw is None or not isinstance(raw, Mapping):
        raise ValueError("embedding config required")
    _assert_allowed_keys(raw, ALLOWED_EMBEDDING_KEYS, "embedding config")
    if not raw:
        raise ValueError("embedding config must include at least one setting")

    provider_raw = raw.get("provider", "openai")
    if not isinstance(provider_raw, str):
        raise ValueError("embedding.provider must be a string")
    provider = provider_raw.strip()
    if not provider:
        raise ValueError("embedding.provider must not be empty")

    model_raw = raw.get("model", DEFAULT_MODEL)
    if not isinstance(model_raw, str):
        raise ValueError("embedding.model must be a string")
    model = model_raw

    api_key_raw = raw.get("apiKey")
    api_key: str | None
    if isinstance(api_key_raw, str):
        api_key = _resolve_env_vars(api_key_raw)
    elif api_key_raw is None:
        api_key = None
    else:
        raise ValueError("embedding.apiKey must be a string")

    base_url_raw = raw.get("baseUrl")
    base_url: str | None
    if isinstance(base_url_raw, str):
        base_url = _resolve_env_vars(base_url_raw)
    elif base_url_raw is None:
        base_url = None
    else:
        raise ValueError("embedding.baseUrl must be a string")

    dimensions_raw = raw.get("dimensions")
    dimensions: int | None
    if dimensions_raw is None:
        dimensions = None
    else:
        if isinstance(dimensions_raw, bool) or not isinstance(dimensions_raw, int | float):
            raise ValueError("embedding.dimensions must be a positive integer")
        d = int(dimensions_raw)
        if d < 1:
            raise ValueError("embedding.dimensions must be a positive integer")
        dimensions = d

    if dimensions is None:
        # Validate the model against the known table.
        vector_dims_for_model(model)

    return {
        "provider": provider,
        "model": model,
        "apiKey": api_key,
        "baseUrl": base_url,
        "dimensions": dimensions,
    }


def default_db_path(home: Path | None = None) -> str:
    """Return the default LanceDB path under the user's home.

    Mirrors OpenClaw's ``resolveDefaultDbPath``. The Phase 4.1
    port only checks the canonical ``~/.jarvis/memory/lancedb``
    location (no legacy fallbacks yet).
    """
    root = home if home is not None else Path.home()
    return str(root / ".jarvis" / "memory" / "lancedb")


# ruff: noqa: PLR0912  # config parser is intentionally branchy (mirrors OpenClaw)
def parse_config(raw: Any) -> MemoryConfig:
    """Parse an OpenClaw-shaped config value into ``MemoryConfig``.

    Mirrors OpenClaw's ``memoryConfigSchema.parse``. Raises
    ``ValueError`` on invalid input.

    An empty dict (``parse_config({})``) is accepted and
    returns the defaults — useful for tests + early boot
    where the operator hasn't filled in any settings yet.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ValueError("memory config required")
    _assert_allowed_keys(raw, ALLOWED_TOP_LEVEL_KEYS, "memory config")

    # Embedding is optional. If absent, use the OpenClaw default
    # (openai + text-embedding-3-small). The host can override
    # later via the SDK provider-adapter path.
    raw_embedding = raw.get("embedding")
    if raw_embedding is None:
        embedding = {
            "provider": "openai",
            "model": DEFAULT_MODEL,
            "apiKey": None,
            "baseUrl": None,
            "dimensions": None,
        }
    else:
        embedding = _resolve_embedding(raw_embedding)

    capture_max = _resolve_bounded_int(
        value=raw.get("captureMaxChars"),
        fallback=DEFAULT_CAPTURE_MAX_CHARS,
        lo=100,
        hi=10_000,
        label="captureMaxChars",
    )
    recall_max = _resolve_bounded_int(
        value=raw.get("recallMaxChars"),
        fallback=DEFAULT_RECALL_MAX_CHARS,
        lo=100,
        hi=10_000,
        label="recallMaxChars",
    )

    custom_triggers_raw = raw.get("customTriggers")
    custom_triggers: tuple[str, ...]
    if custom_triggers_raw is None:
        custom_triggers = ()
    else:
        if not isinstance(custom_triggers_raw, list | tuple):
            raise ValueError("customTriggers must be an array of strings")
        if len(custom_triggers_raw) > 50:
            raise ValueError("customTriggers must include at most 50 entries")
        triggers: list[str] = []
        for i, t in enumerate(custom_triggers_raw):
            if not isinstance(t, str):
                raise ValueError(f"customTriggers.{i} must be a string")
            normalized = t.strip()
            if not normalized:
                raise ValueError(f"customTriggers.{i} must not be empty")
            if len(normalized) > 100:
                raise ValueError(f"customTriggers.{i} must be at most 100 characters")
            triggers.append(normalized)
        custom_triggers = tuple(triggers)

    dreaming_raw = raw.get("dreaming")
    if dreaming_raw is None:
        dreaming: Mapping[str, Any] | None = None
    elif isinstance(dreaming_raw, Mapping):
        dreaming = dict(dreaming_raw)
    else:
        raise ValueError("dreaming config must be an object")

    db_path_raw = raw.get("dbPath")
    if db_path_raw is None or db_path_raw == "":
        db_path = default_db_path()
    elif isinstance(db_path_raw, str):
        db_path = db_path_raw
    else:
        raise ValueError("dbPath must be a string")

    auto_capture = raw.get("autoCapture", False) is True
    auto_recall_raw = raw.get("autoRecall", True)
    auto_recall = auto_recall_raw is not False

    storage_options = _resolve_storage_options(raw.get("storageOptions"))

    return MemoryConfig(
        embedding_provider=embedding["provider"],
        embedding_model=embedding["model"],
        embedding_api_key=embedding["apiKey"],
        embedding_base_url=embedding["baseUrl"],
        embedding_dimensions=embedding["dimensions"],
        db_path=db_path,
        auto_capture=auto_capture,
        auto_recall=auto_recall,
        capture_max_chars=capture_max,
        recall_max_chars=recall_max,
        custom_triggers=custom_triggers,
        dreaming=dreaming,
        storage_options=storage_options,
    )


__all__ = [
    "ALLOWED_EMBEDDING_KEYS",
    "ALLOWED_TOP_LEVEL_KEYS",
    "DEFAULT_CAPTURE_MAX_CHARS",
    "DEFAULT_MODEL",
    "DEFAULT_RECALL_MAX_CHARS",
    "EMBEDDING_DIMENSIONS",
    "MEMORY_CATEGORIES",
    "MemoryConfig",
    "default_db_path",
    "parse_config",
    "vector_dims_for_model",
]
