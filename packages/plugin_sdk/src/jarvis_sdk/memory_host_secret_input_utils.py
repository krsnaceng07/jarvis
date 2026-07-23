"""jarvis_sdk.memory_host_secret_input_utils — secret input parsing helpers.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/secret-input-utils.ts`` (164 LOC).
Helpers for parsing the accepted memory-provider secret input
shapes (literal strings + canonical 3-field refs + legacy
``secretref-env:`` markers + env templates ``"${VAR}"``).

Key port decisions:
- The 3 supported ref sources (``env`` / ``file`` / ``exec``) are
  preserved verbatim.
- The default provider alias is ``"default"`` for legacy refs.
- Env name regex: ``/^[A-Z][A-Z0-9_]{0,127}$/`` (1 + 0-127 chars
  after the first letter, uppercase + digits + underscore).
- All parse functions return ``None`` on malformed input (no
  exceptions). ``normalize_resolved_memory_secret_input_string``
  throws for refs that still require gateway resolution (the
  unmarshaled value is a ref shape, not a literal).
"""
from __future__ import annotations

import re
from typing import Literal, TypedDict

# ── Types ─────────────────────────────────────────────────────────────

#: Supported secret reference backing stores. Mirrors OpenClaw's
#: ``SecretRefSource``.
SecretRefSource = Literal["env", "file", "exec"]


class SecretRef(TypedDict):
    """Canonical 3-field secret reference used after gateway resolution.

    Mirrors OpenClaw's ``SecretRef`` shape.
    """

    source: SecretRefSource
    provider: str
    id: str


# ── Constants (mirrors OpenClaw) ─────────────────────────────────────

#: Provider name used when a legacy ref doesn't carry an explicit
#: provider. Mirrors ``DEFAULT_SECRET_PROVIDER_ALIAS``.
DEFAULT_SECRET_PROVIDER_ALIAS = "default"

#: Regex for env var names referenced by SecretRef. Mirrors the
#: TS ``ENV_SECRET_REF_ID_RE = /^[A-Z][A-Z0-9_]{0,127}$/``.
ENV_SECRET_REF_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")

#: Legacy marker prefix for "secretref-env:" config strings.
#: Mirrors ``LEGACY_SECRETREF_ENV_MARKER_PREFIX``.
LEGACY_SECRETREF_ENV_MARKER_PREFIX = "secretref-env:"

#: Regex for the ``"${VAR}"`` env template shorthand.
#: Mirrors ``ENV_SECRET_TEMPLATE_RE``.
ENV_SECRET_TEMPLATE_RE = re.compile(r"^\$\{([A-Z][A-Z0-9_]{0,127})\}$")

#: The set of accepted ref sources.
SECRET_REF_SOURCES: frozenset = frozenset({"env", "file", "exec"})


# ── Type guards ─────────────────────────────────────────────────────


def _is_record(value: object) -> bool:
    """True when ``value`` is a plain object (not array, not None)."""
    return isinstance(value, dict)


def _normalize_secret_input_string(value: object) -> str | None:
    """Trim a literal secret string; return None when not a non-empty string."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if len(trimmed) > 0 else None


def _has_secret_ref_source(value: object) -> bool:
    """True when ``value`` is one of the supported ``SecretRefSource`` strings."""
    return isinstance(value, str) and value in SECRET_REF_SOURCES


def _has_non_empty_string(value: object) -> bool:
    """True when ``value`` is a non-empty string (after trim)."""
    return isinstance(value, str) and value.strip() != ""


def _is_secret_ref(value: object) -> bool:
    """True when ``value`` is a canonical 3-field SecretRef."""
    if not _is_record(value):
        return False
    keys = list(value.keys())
    if len(keys) != 3:
        return False
    return (
        _has_secret_ref_source(value.get("source"))
        and _has_non_empty_string(value.get("provider"))
        and _has_non_empty_string(value.get("id"))
    )


def _is_legacy_secret_ref_without_provider(value: object) -> bool:
    """True when ``value`` is a legacy 2-field ref (no provider)."""
    if not _is_record(value):
        return False
    return (
        _has_secret_ref_source(value.get("source"))
        and _has_non_empty_string(value.get("id"))
        and "provider" not in value
    )


# ── Parsers ─────────────────────────────────────────────────────────


def parse_env_template_secret_ref(value: object) -> SecretRef | None:
    """Parse the ``"${OPENAI_API_KEY}"`` env template shorthand.

    Mirrors OpenClaw's ``parseEnvTemplateSecretRef``. Returns
    ``SecretRef`` with ``source: "env"`` + the default provider
    alias when the input matches the env template regex; ``None``
    otherwise.
    """
    if not isinstance(value, str):
        return None
    match = ENV_SECRET_TEMPLATE_RE.match(value.strip())
    if not match:
        return None
    return {
        "source": "env",
        "provider": DEFAULT_SECRET_PROVIDER_ALIAS,
        "id": match.group(1) or "",
    }


def parse_legacy_secret_ref_env_marker(value: object) -> SecretRef | None:
    """Parse the legacy ``"secretref-env:OPENAI_API_KEY"`` marker.

    Mirrors OpenClaw's ``parseLegacySecretRefEnvMarker``. Returns
    ``SecretRef`` when the prefix matches and the id is a valid
    env var name; ``None`` otherwise.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed.startswith(LEGACY_SECRETREF_ENV_MARKER_PREFIX):
        return None
    id_ = trimmed[len(LEGACY_SECRETREF_ENV_MARKER_PREFIX):]
    if not ENV_SECRET_REF_ID_RE.match(id_):
        return None
    return {
        "source": "env",
        "provider": DEFAULT_SECRET_PROVIDER_ALIAS,
        "id": id_,
    }


def coerce_secret_ref(value: object) -> SecretRef | None:
    """Coerce any accepted secret input shape to canonical ``SecretRef``.

    Mirrors OpenClaw's ``coerceSecretRef``. Recognizes:

    - Canonical 3-field refs (passes through)
    - Legacy 2-field refs (no ``provider`` → uses default alias)
    - ``"${VAR}"`` env templates
    - Legacy ``"secretref-env:VAR"`` markers
    """
    if _is_secret_ref(value):
        return value  # type: ignore[return-value]
    if _is_legacy_secret_ref_without_provider(value):
        legacy = value  # type: ignore[assignment]
        return {
            "source": legacy["source"],
            "provider": DEFAULT_SECRET_PROVIDER_ALIAS,
            "id": legacy["id"],
        }
    return parse_env_template_secret_ref(value) or parse_legacy_secret_ref_env_marker(value)


# ── Public helpers ─────────────────────────────────────────────────


def has_configured_memory_secret_input_value(value: object) -> bool:
    """True when a secret input has a literal value or resolvable ref.

    Mirrors OpenClaw's ``hasConfiguredMemorySecretInputValue``.
    """
    if _normalize_secret_input_string(value):
        return True
    return coerce_secret_ref(value) is not None


def _format_secret_ref_label(ref: SecretRef) -> str:
    """Format a ref label without revealing a resolved secret value."""
    return f"{ref['source']}:{ref['provider']}:{ref['id']}"


def _create_unresolved_secret_input_error(*, path: str, ref: SecretRef) -> Exception:
    """Build the unresolved-ref error used when callers bypass gateway."""
    return ValueError(
        f"{path}: unresolved SecretRef \"{_format_secret_ref_label(ref)}\". "
        f"Resolve this command against an active gateway runtime snapshot "
        f"before reading it."
    )


def resolve_memory_secret_input_ref(value: object) -> SecretRef | None:
    """Return a canonical ``SecretRef`` when ``value`` is a supported ref shape.

    Mirrors OpenClaw's ``resolveMemorySecretInputRef``. Returns
    ``None`` when ``value`` is a literal string (not a ref) or when
    it doesn't match any accepted ref shape.
    """
    return coerce_secret_ref(value)


def normalize_resolved_memory_secret_input_string(
    *, value: object, path: str
) -> str | None:
    """Normalize literal secrets; throw for unresolved refs.

    Mirrors OpenClaw's ``normalizeResolvedMemorySecretInputString``.

    Returns:
    - ``str`` when ``value`` is a non-empty literal string.
    - ``None`` when ``value`` is empty / not a string and not a
      resolvable ref.
    - Raises ``ValueError`` when ``value`` is a SecretRef that
      still needs gateway resolution.
    """
    normalized = _normalize_secret_input_string(value)
    if normalized:
        return normalized
    ref = resolve_memory_secret_input_ref(value)
    if ref is None:
        return None
    raise _create_unresolved_secret_input_error(path=path, ref=ref)


def normalize_env_secret_input_string(value: object) -> str | None:
    """Normalize env-provided secret values before use.

    Mirrors OpenClaw's ``normalizeEnvSecretInputString``. Same as
    ``_normalize_secret_input_string`` but exposed as a public
    helper for symmetry with the SDK's name.
    """
    return _normalize_secret_input_string(value)


__all__ = [
    "SecretRefSource",
    "SecretRef",
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
]
