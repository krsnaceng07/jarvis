"""jarvis_sdk.memory_host_secret_input — memory-specific secret facade.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/secret-input.ts`` (32 LOC).
The memory-specific facade for resolving provider secret input from
config. Re-exports the canonical coercion / normalization helpers
from ``memory_host_secret_input_utils`` and adds the
``has_configured_memory_secret_input`` + ``resolve_memory_secret_input_string``
public API.

Key port decisions:
- The facade reads from ``os.environ`` directly (the OpenClaw
  source reads from ``process.env``). Env-var refs are resolved
  inline.
- ``resolve_memory_secret_input_string`` follows the same
  precedence as the TS source: literal string first, then env-var
  ref resolution, then gateway-resolved ref.
"""
from __future__ import annotations

import os
from typing import Any

# Re-export the utility module so callers can import the lower-level
# helpers from the same path. Mirrors the TS source's
# ``import { ... } from "./secret-input-utils.js"`` pattern.
from .memory_host_secret_input_utils import (
    ENV_SECRET_REF_ID_RE,
    ENV_SECRET_TEMPLATE_RE,
    LEGACY_SECRETREF_ENV_MARKER_PREFIX,
    SECRET_REF_SOURCES,
    SecretRef,
    SecretRefSource,
    coerce_secret_ref,
    has_configured_memory_secret_input_value,
    normalize_env_secret_input_string,
    normalize_resolved_memory_secret_input_string,
    parse_env_template_secret_ref,
    parse_legacy_secret_ref_env_marker,
    resolve_memory_secret_input_ref,
)


def has_configured_memory_secret_input(value: Any) -> bool:
    """Return True when a configured memory secret contains a literal value or reference.

    Mirrors OpenClaw's ``hasConfiguredMemorySecretInput``.
    """
    return has_configured_memory_secret_input_value(value)


def resolve_memory_secret_input_string(
    *, value: Any, path: str
) -> str | None:
    """Resolve memory secret input, reading env refs directly when available.

    Mirrors OpenClaw's ``resolveMemorySecretInputString``. Precedence:
    1. If the value is a ref with ``source: "env"``, read the env
       var directly (the OpenClaw source calls
       ``process.env[ref.id]``).
    2. Otherwise normalize the value (literal string or
       already-resolved ref via the gateway).

    Returns the resolved string or ``None`` if no secret is set.
    """
    ref = resolve_memory_secret_input_ref(value)
    if ref is not None and ref.get("source") == "env":
        env_id = ref.get("id")
        if env_id:
            env_value = normalize_env_secret_input_string(os.environ.get(env_id))
            if env_value:
                return env_value
    return normalize_resolved_memory_secret_input_string(value=value, path=path)


__all__ = [
    "SecretRef",
    "SecretRefSource",
    "DEFAULT_SECRET_PROVIDER_ALIAS",
    "ENV_SECRET_REF_ID_RE",
    "LEGACY_SECRETREF_ENV_MARKER_PREFIX",
    "ENV_SECRET_TEMPLATE_RE",
    "SECRET_REF_SOURCES",
    "parse_env_template_secret_ref",
    "parse_legacy_secret_ref_env_marker",
    "coerce_secret_ref",
    "has_configured_memory_secret_input_value",
    "resolve_memory_secret_input_ref",
    "normalize_resolved_memory_secret_input_string",
    "normalize_env_secret_input_string",
    # Public memory-specific facade
    "has_configured_memory_secret_input",
    "resolve_memory_secret_input_string",
]
