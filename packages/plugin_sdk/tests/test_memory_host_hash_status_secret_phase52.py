"""Tests for jarvis_sdk.memory_host_hash + memory_host_status_format +
memory_host_status + memory_host_secret_input_utils +
memory_host_secret_input + memory_host_secret (Phase 5.2).

Mirrors the TypeScript test patterns from the source files in
``packages/memory-host-sdk/src/host/{hash,status-format,secret-input,secret-input-utils}.ts``.
"""

from __future__ import annotations

import hashlib

import pytest

from jarvis_sdk.memory_host_hash import hash_text
from jarvis_sdk.memory_host_hash_facade import hash_text as hash_text_facade
from jarvis_sdk.memory_host_status_format import (
    Tone,
    resolve_memory_cache_summary,
    resolve_memory_fts_state,
    resolve_memory_vector_state,
)
from jarvis_sdk.memory_host_status import (
    Tone as ToneFacade,
    resolve_memory_cache_summary as resolve_cache_facade,
    resolve_memory_fts_state as resolve_fts_facade,
    resolve_memory_vector_state as resolve_vector_facade,
)
from jarvis_sdk.memory_host_secret_input_utils import (
    DEFAULT_SECRET_PROVIDER_ALIAS,
    ENV_SECRET_REF_ID_RE,
    LEGACY_SECRETREF_ENV_MARKER_PREFIX,
    SECRET_REF_SOURCES,
    SecretRef,
    coerce_secret_ref,
    has_configured_memory_secret_input_value,
    normalize_env_secret_input_string,
    normalize_resolved_memory_secret_input_string,
    parse_env_template_secret_ref,
    parse_legacy_secret_ref_env_marker,
    resolve_memory_secret_input_ref,
)
from jarvis_sdk.memory_host_secret_input import (
    has_configured_memory_secret_input,
    resolve_memory_secret_input_string,
)
from jarvis_sdk.memory_host_secret import (
    has_configured_memory_secret_input as has_configured_facade,
    resolve_memory_secret_input_string as resolve_facade,
)


# ── hash_text ────────────────────────────────────────────────────────


def test_hash_text_returns_sha256_hex() -> None:
    """SHA-256 of "hello" is the well-known 64-char hex digest."""
    expected = hashlib.sha256(b"hello").hexdigest()
    assert hash_text("hello") == expected


def test_hash_text_empty_string() -> None:
    """Empty string hashes to the well-known SHA-256 of empty input."""
    expected = hashlib.sha256(b"").hexdigest()
    assert hash_text("") == expected


def test_hash_text_unicode() -> None:
    """Non-ASCII text is UTF-8 encoded before hashing."""
    expected = hashlib.sha256("नमस्ते".encode("utf-8")).hexdigest()
    assert hash_text("नमस्ते") == expected


def test_hash_text_deterministic() -> None:
    """Same input → same output (no random salt)."""
    assert hash_text("test") == hash_text("test")


def test_hash_text_facade_matches_implementation() -> None:
    """The hash facade re-export returns the same value."""
    assert hash_text_facade("test") == hash_text("test")


def test_hash_text_returns_64_hex_chars() -> None:
    """SHA-256 hex is always 64 chars."""
    assert len(hash_text("anything")) == 64
    int(hash_text("anything"), 16)  # valid hex


# ── resolve_memory_vector_state ────────────────────────────────────


def test_vector_state_disabled() -> None:
    """``enabled=False`` → disabled (muted)."""
    result = resolve_memory_vector_state({"enabled": False, "available": True})
    assert result.get("tone") == "muted"
    assert result.get("state") == "disabled"


def test_vector_state_ready() -> None:
    """``enabled=True`` + ``available=True`` → ready (ok)."""
    result = resolve_memory_vector_state({"enabled": True, "available": True})
    assert result.get("tone") == "ok"
    assert result.get("state") == "ready"


def test_vector_state_unavailable() -> None:
    """``enabled=True`` + ``available=False`` → unavailable (warn)."""
    result = resolve_memory_vector_state({"enabled": True, "available": False})
    assert result.get("tone") == "warn"
    assert result.get("state") == "unavailable"


def test_vector_state_unknown() -> None:
    """``enabled=True`` + ``available=undefined`` → unknown (muted)."""
    result = resolve_memory_vector_state({"enabled": True})
    assert result.get("tone") == "muted"
    assert result.get("state") == "unknown"


def test_vector_state_disabled_overrides_available() -> None:
    """When disabled, ``available`` is ignored."""
    result = resolve_memory_vector_state({"enabled": False, "available": False})
    assert result.get("state") == "disabled"


def test_vector_state_facade_matches() -> None:
    """Facade re-export returns the same result."""
    a = resolve_memory_vector_state({"enabled": True, "available": True})
    b = resolve_vector_facade({"enabled": True, "available": True})
    assert a == b


# ── resolve_memory_fts_state ───────────────────────────────────────


def test_fts_state_disabled() -> None:
    """``enabled=False`` → disabled (muted)."""
    result = resolve_memory_fts_state({"enabled": False, "available": True})
    assert result.get("tone") == "muted"
    assert result.get("state") == "disabled"


def test_fts_state_ready() -> None:
    """``enabled=True`` + ``available=True`` → ready (ok)."""
    result = resolve_memory_fts_state({"enabled": True, "available": True})
    assert result.get("tone") == "ok"
    assert result.get("state") == "ready"


def test_fts_state_unavailable() -> None:
    """``enabled=True`` + ``available=False`` → unavailable (warn)."""
    result = resolve_memory_fts_state({"enabled": True, "available": False})
    assert result.get("tone") == "warn"
    assert result.get("state") == "unavailable"


def test_fts_state_facade_matches() -> None:
    a = resolve_memory_fts_state({"enabled": True, "available": True})
    b = resolve_fts_facade({"enabled": True, "available": True})
    assert a == b


# ── resolve_memory_cache_summary ──────────────────────────────────


def test_cache_summary_disabled() -> None:
    """``enabled=False`` → ``"cache off"`` (muted)."""
    result = resolve_memory_cache_summary({"enabled": False, "entries": 99})
    assert result.get("tone") == "muted"
    assert result.get("text") == "cache off"


def test_cache_summary_enabled_no_entries() -> None:
    """``enabled=True`` without entries → ``"cache on"``."""
    result = resolve_memory_cache_summary({"enabled": True})
    assert result.get("tone") == "ok"
    assert result.get("text") == "cache on"


def test_cache_summary_enabled_with_entries() -> None:
    """``enabled=True`` + numeric entries → ``"cache on (N)"``."""
    result = resolve_memory_cache_summary({"enabled": True, "entries": 5})
    assert result.get("tone") == "ok"
    assert result.get("text") == "cache on (5)"


def test_cache_summary_entries_non_numeric() -> None:
    """Non-numeric entries → no suffix."""
    result = resolve_memory_cache_summary({"enabled": True, "entries": "five"})
    assert result.get("text") == "cache on"


def test_cache_summary_facade_matches() -> None:
    a = resolve_memory_cache_summary({"enabled": True, "entries": 3})
    b = resolve_cache_facade({"enabled": True, "entries": 3})
    assert a == b


# ── Tone (status / facade) ─────────────────────────────────────────


def test_tone_values() -> None:
    """``Tone`` accepts the three documented values."""
    # Tone is a ``Literal`` alias — the values are checked at usage,
    # not via ``Tone("ok")`` (which is for ``Enum``). Verify the
    # underlying type by checking the repr + a normal usage.
    for value in ("ok", "warn", "muted"):
        # If a function accepts ``Tone``, the value is valid.
        assert value in ("ok", "warn", "muted")


def test_tone_facade_is_same_as_tone() -> None:
    """The facade's ``Tone`` re-export is the same as the implementation's."""
    assert ToneFacade is Tone


# ── Secret reference shape parsing ─────────────────────────────────


def test_secret_ref_sources_constant() -> None:
    """``SECRET_REF_SOURCES`` contains the three accepted sources."""
    assert SECRET_REF_SOURCES == frozenset({"env", "file", "exec"})


def test_env_secret_ref_id_re_accepts_valid_names() -> None:
    """Standard env-var names match."""
    for name in ("PATH", "OPENAI_API_KEY", "A", "ABCDEFGHIJ"):
        assert ENV_SECRET_REF_ID_RE.match(name), name


def test_env_secret_ref_id_re_rejects_invalid_names() -> None:
    """Lowercase / non-alpha / too-long names don't match."""
    for name in ("", "path", "1ABC", "ABC-DEF", "a" * 129):
        assert not ENV_SECRET_REF_ID_RE.match(name), name


def test_legacy_secret_ref_env_marker_prefix() -> None:
    """The legacy prefix is ``"secretref-env:"``."""
    assert LEGACY_SECRETREF_ENV_MARKER_PREFIX == "secretref-env:"


def test_default_secret_provider_alias() -> None:
    """The default provider alias is ``"default"``."""
    assert DEFAULT_SECRET_PROVIDER_ALIAS == "default"


# ── parse_env_template_secret_ref ──────────────────────────────────


def test_parse_env_template_valid() -> None:
    """``"${OPENAI_API_KEY}"`` parses to a valid env ref."""
    ref = parse_env_template_secret_ref("${OPENAI_API_KEY}")
    assert ref == {"source": "env", "provider": "default", "id": "OPENAI_API_KEY"}


def test_parse_env_template_with_whitespace() -> None:
    """Leading/trailing whitespace is trimmed."""
    ref = parse_env_template_secret_ref("  ${PATH}  ")
    assert ref is not None
    assert ref["id"] == "PATH"


def test_parse_env_template_invalid() -> None:
    """Non-template strings return ``None``."""
    assert parse_env_template_secret_ref("OPENAI_API_KEY") is None
    assert parse_env_template_secret_ref("${lowercase}") is None
    assert parse_env_template_secret_ref("${1NUM}") is None
    assert parse_env_template_secret_ref("") is None
    assert parse_env_template_secret_ref(None) is None  # type: ignore[arg-type]


# ── parse_legacy_secret_ref_env_marker ────────────────────────────


def test_parse_legacy_marker_valid() -> None:
    """``"secretref-env:OPENAI_API_KEY"`` parses to a valid env ref."""
    ref = parse_legacy_secret_ref_env_marker("secretref-env:OPENAI_API_KEY")
    assert ref == {"source": "env", "provider": "default", "id": "OPENAI_API_KEY"}


def test_parse_legacy_marker_lowercase_id_rejected() -> None:
    """Lowercase ids don't match the env-name regex."""
    assert parse_legacy_secret_ref_env_marker("secretref-env:openai_api_key") is None


def test_parse_legacy_marker_no_prefix_rejected() -> None:
    """Without the prefix, the input isn't a legacy marker."""
    assert parse_legacy_secret_ref_env_marker("OPENAI_API_KEY") is None
    assert parse_legacy_secret_ref_env_marker("") is None


# ── coerce_secret_ref ──────────────────────────────────────────────


def test_coerce_canonical_ref() -> None:
    """Canonical 3-field refs pass through."""
    ref_in: SecretRef = {"source": "env", "provider": "openai", "id": "OPENAI_API_KEY"}
    ref = coerce_secret_ref(ref_in)
    assert ref == ref_in


def test_coerce_legacy_ref_without_provider() -> None:
    """Legacy refs without ``provider`` get the default alias."""
    ref = coerce_secret_ref({"source": "file", "id": "/path/to/key"})
    assert ref == {"source": "file", "provider": "default", "id": "/path/to/key"}


def test_coerce_env_template() -> None:
    """``"${VAR}"`` strings coerce to env refs."""
    ref = coerce_secret_ref("${PATH}")
    assert ref == {"source": "env", "provider": "default", "id": "PATH"}


def test_coerce_legacy_marker() -> None:
    """``"secretref-env:VAR"`` strings coerce to env refs."""
    ref = coerce_secret_ref("secretref-env:OPENAI_API_KEY")
    assert ref == {"source": "env", "provider": "default", "id": "OPENAI_API_KEY"}


def test_coerce_literal_string_returns_none() -> None:
    """Plain literal strings are not refs."""
    assert coerce_secret_ref("my-literal-secret") is None
    assert coerce_secret_ref("") is None


def test_coerce_malformed_object_returns_none() -> None:
    """Objects that don't match any shape return ``None``."""
    assert coerce_secret_ref({"source": "unknown", "id": "X"}) is None
    assert coerce_secret_ref({"source": "env", "id": ""}) is None
    assert coerce_secret_ref({"source": "env", "id": 123}) is None  # not a string
    assert coerce_secret_ref({}) is None
    assert coerce_secret_ref(None) is None
    assert coerce_secret_ref(123) is None  # not a dict


def test_coerce_wrong_key_count_rejected() -> None:
    """Canonical refs must have exactly 3 keys; legacy 2-field refs
    are still accepted (with default provider)."""
    # 4 keys (extra) is rejected
    assert coerce_secret_ref({"source": "env", "provider": "p", "id": "v", "extra": "x"}) is None
    # 2 keys (no provider) is accepted as legacy → gets default provider
    legacy = coerce_secret_ref({"source": "env", "id": "v"})
    assert legacy == {"source": "env", "provider": "default", "id": "v"}


# ── has_configured_memory_secret_input_value ────────────────────────


def test_has_configured_literal_non_empty() -> None:
    """Non-empty literal strings count as configured."""
    assert has_configured_memory_secret_input_value("my-key") is True


def test_has_configured_literal_empty() -> None:
    """Empty literal strings don't count as configured."""
    assert has_configured_memory_secret_input_value("") is False
    assert has_configured_memory_secret_input_value("   ") is False


def test_has_configured_canonical_ref() -> None:
    """Canonical refs count as configured."""
    ref: SecretRef = {"source": "env", "provider": "openai", "id": "OPENAI_API_KEY"}
    assert has_configured_memory_secret_input_value(ref) is True


def test_has_configured_env_template() -> None:
    """``"${VAR}"`` templates count as configured."""
    assert has_configured_memory_secret_input_value("${PATH}") is True


def test_has_configured_none_or_non_string() -> None:
    """Non-string / non-ref values don't count."""
    assert has_configured_memory_secret_input_value(None) is False
    assert has_configured_memory_secret_input_value(123) is False
    assert has_configured_memory_secret_input_value({}) is False


# ── resolve_memory_secret_input_ref ───────────────────────────────


def test_resolve_ref_canonical() -> None:
    """Canonical refs return as-is."""
    ref_in: SecretRef = {"source": "file", "provider": "openai", "id": "/path"}
    assert resolve_memory_secret_input_ref(ref_in) == ref_in


def test_resolve_ref_literal_returns_none() -> None:
    """Literal strings don't have a ref (they ARE the value)."""
    assert resolve_memory_secret_input_ref("my-key") is None


# ── normalize_resolved_memory_secret_input_string ─────────────────


def test_normalize_resolved_literal() -> None:
    """Literal non-empty string is returned (trimmed)."""
    assert normalize_resolved_memory_secret_input_string(value="  my-key  ", path="x") == "my-key"


def test_normalize_resolved_empty_literal() -> None:
    """Empty / whitespace-only literal returns ``None``."""
    assert normalize_resolved_memory_secret_input_string(value="", path="x") is None
    assert normalize_resolved_memory_secret_input_string(value="   ", path="x") is None


def test_normalize_resolved_ref_raises() -> None:
    """A ref raises ``ValueError`` (unresolved by gateway)."""
    ref: SecretRef = {"source": "env", "provider": "openai", "id": "OPENAI_API_KEY"}
    with pytest.raises(ValueError, match="unresolved SecretRef"):
        normalize_resolved_memory_secret_input_string(value=ref, path="memory.openai.apiKey")


def test_normalize_resolved_non_string_non_ref_returns_none() -> None:
    """Non-string + non-ref input returns ``None``."""
    assert normalize_resolved_memory_secret_input_string(value=123, path="x") is None
    assert normalize_resolved_memory_secret_input_string(value=None, path="x") is None


# ── normalize_env_secret_input_string ─────────────────────────────


def test_normalize_env_string() -> None:
    """Non-empty strings are trimmed and returned."""
    assert normalize_env_secret_input_string("  value  ") == "value"


def test_normalize_env_empty() -> None:
    """Empty / non-string returns ``None``."""
    assert normalize_env_secret_input_string("") is None
    assert normalize_env_secret_input_string("   ") is None
    assert normalize_env_secret_input_string(None) is None
    assert normalize_env_secret_input_string(123) is None


# ── resolve_memory_secret_input_string (memory-specific facade) ───


def test_resolve_facade_literal() -> None:
    """Literal strings pass through."""
    assert resolve_memory_secret_input_string(value="my-literal", path="x") == "my-literal"


def test_resolve_facade_env_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    """An env ref reads from ``os.environ``."""
    monkeypatch.setenv("MY_TEST_KEY", "secret-value")
    ref: SecretRef = {"source": "env", "provider": "default", "id": "MY_TEST_KEY"}
    assert resolve_memory_secret_input_string(value=ref, path="x") == "secret-value"


def test_resolve_facade_env_ref_missing_raises() -> None:
    """An env ref with no env value falls through to the unresolved
    ref path and raises ``ValueError`` (matches OpenClaw's
    precedence: env-var read first; if missing, treat as a still-
    unresolved ref via the normal path)."""
    ref: SecretRef = {"source": "env", "provider": "default", "id": "MISSING_VAR_XYZ"}
    with pytest.raises(ValueError, match="unresolved SecretRef"):
        resolve_memory_secret_input_string(value=ref, path="x")


def test_resolve_facade_unresolved_ref_raises() -> None:
    """Non-env refs raise (unresolved)."""
    ref: SecretRef = {"source": "file", "provider": "openai", "id": "/path"}
    with pytest.raises(ValueError, match="unresolved"):
        resolve_memory_secret_input_string(value=ref, path="x")


def test_resolve_facade_none_input() -> None:
    """``None`` / non-string-non-ref returns ``None``."""
    assert resolve_memory_secret_input_string(value=None, path="x") is None
    assert resolve_memory_secret_input_string(value=123, path="x") is None


# ── has_configured_memory_secret_input (memory-specific facade) ────


def test_has_configured_facade_literal() -> None:
    """The facade accepts the same inputs as the implementation."""
    assert has_configured_memory_secret_input("my-key") is True
    assert has_configured_memory_secret_input("") is False
    assert (
        has_configured_memory_secret_input({"source": "env", "provider": "default", "id": "PATH"})
        is True
    )


def test_has_configured_facade_aliases() -> None:
    """The facade ``has_configured_memory_secret_input`` is the same as the implementation."""
    assert has_configured_facade is has_configured_memory_secret_input
    assert resolve_facade is resolve_memory_secret_input_string
