"""jarvis.config.types_secrets — secret reference and resolution config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.secrets.ts``.

Focused minimal port: covers the public types, regex constants, narrow
helpers, and ``coerce_secret_ref`` / ``parse_env_template_secret_ref`` /
``parse_legacy_secret_ref_env_marker`` logic that downstream config sites
rely on. The runtime secret-resolution engine itself is delegated to
:mod:`jarvis.config.io` (or, in production, to the gateway runtime).
"""
from __future__ import annotations

import re
from typing import Literal, TypedDict


#: Supported secret reference backends in config.
SecretRefSource = Literal["env", "file", "exec"]


class SecretRef(TypedDict):
    """Stable identifier for a secret in a configured source."""
    source: str  # SecretRefSource
    provider: str
    id: str


#: Secret-bearing config input: either a literal string or a structured SecretRef.
SecretInput = str  # type alias (str | SecretRef); runtime distinguishes


#: Default provider alias for SecretRefs that omit a source-specific provider.
DEFAULT_SECRET_PROVIDER_ALIAS = "default"


#: Strict env-var id shape accepted for env-backed SecretRefs.
ENV_SECRET_REF_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


#: Legacy env SecretRef marker retained for config migration/read compatibility.
LEGACY_SECRETREF_ENV_MARKER_PREFIX = "secretref-env:"


#: Older env SecretRef marker retained for migration/read compatibility.
LEGACY_DOUBLE_UNDERSCORE_ENV_MARKER_PREFIX = "__env__:"

_ENV_SECRET_TEMPLATE_RE = re.compile(r"^\$\{([A-Z][A-Z0-9_]{0,127})\}$")
_ENV_SECRET_SHORTHAND_RE = re.compile(r"^\$([A-Z][A-Z0-9_]{0,127})$")


#: Secret string read mode: throw on unresolved refs or inspect without resolving.
SecretInputStringResolutionMode = Literal["strict", "inspect"]


#: Result of reading a secret input without necessarily materializing the secret value.
#: Discriminated union shape.
SecretInputStringResolution = dict  # status, value, ref


class SecretDefaults(TypedDict, total=False):
    """Default provider aliases for SecretRefs that omit a source-specific provider."""
    env: str
    file: str
    exec: str


#: Return whether an env SecretRef id is a supported uppercase environment variable name.
def is_valid_env_secret_ref_id(value: str) -> bool:
    """Return whether ``value`` is a strict env-var id shape."""
    return bool(ENV_SECRET_REF_ID_RE.match(value))


def _is_record(value) -> bool:
    """Return whether ``value`` is a non-array dict-like mapping."""
    return isinstance(value, dict) and not isinstance(value, (list, tuple, set))


#: Narrow a value to the canonical SecretRef object shape.
def is_secret_ref(value) -> bool:
    """Return whether ``value`` matches the canonical SecretRef shape."""
    if not _is_record(value):
        return False
    if len(value) != 3:
        return False
    return (
        value.get("source") in ("env", "file", "exec")
        and isinstance(value.get("provider"), str)
        and value["provider"].strip() != ""
        and isinstance(value.get("id"), str)
        and value["id"].strip() != ""
    )


def _is_legacy_secret_ref_without_provider(value) -> bool:
    if not _is_record(value):
        return False
    return (
        value.get("source") in ("env", "file", "exec")
        and isinstance(value.get("id"), str)
        and value["id"].strip() != ""
        and value.get("provider") is None
    )


#: Parse ``$NAME`` and ``${NAME}`` env-secret shorthand strings into env SecretRefs.
def parse_env_template_secret_ref(value, provider: str = DEFAULT_SECRET_PROVIDER_ALIAS):
    """Parse ``$NAME`` / ``${NAME}`` shorthand into a canonical env SecretRef."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    match = _ENV_SECRET_TEMPLATE_RE.match(trimmed) or _ENV_SECRET_SHORTHAND_RE.match(trimmed)
    if not match:
        return None
    return {
        "source": "env",
        "provider": (provider.strip() or DEFAULT_SECRET_PROVIDER_ALIAS),
        "id": match.group(1),
    }


#: Parse legacy env SecretRef marker strings kept for config migration/read compatibility.
def parse_legacy_secret_ref_env_marker(value, provider: str = DEFAULT_SECRET_PROVIDER_ALIAS):
    """Parse legacy ``secretref-env:`` / ``__env__:`` markers into a canonical env SecretRef."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if trimmed.startswith(LEGACY_SECRETREF_ENV_MARKER_PREFIX):
        prefix = LEGACY_SECRETREF_ENV_MARKER_PREFIX
    elif trimmed.startswith(LEGACY_DOUBLE_UNDERSCORE_ENV_MARKER_PREFIX):
        prefix = LEGACY_DOUBLE_UNDERSCORE_ENV_MARKER_PREFIX
    else:
        return None
    ident = trimmed[len(prefix):]
    if not ENV_SECRET_REF_ID_RE.match(ident):
        return None
    return {
        "source": "env",
        "provider": (provider.strip() or DEFAULT_SECRET_PROVIDER_ALIAS),
        "id": ident,
    }


#: Coerce canonical, legacy, and env-shorthand secret inputs into a SecretRef.
def coerce_secret_ref(value, defaults: SecretDefaults = None):
    """Coerce any of the supported secret input shapes into a canonical SecretRef."""
    if is_secret_ref(value):
        return dict(value)
    env_default = (defaults or {}).get("env") or DEFAULT_SECRET_PROVIDER_ALIAS
    legacy = parse_legacy_secret_ref_env_marker(value, env_default)
    if legacy:
        return legacy
    if _is_legacy_secret_ref_without_provider(value):
        source = value["source"]
        if source == "env":
            provider = (defaults or {}).get("env") or DEFAULT_SECRET_PROVIDER_ALIAS
        elif source == "file":
            provider = (defaults or {}).get("file") or DEFAULT_SECRET_PROVIDER_ALIAS
        else:
            provider = (defaults or {}).get("exec") or DEFAULT_SECRET_PROVIDER_ALIAS
        return {"source": source, "provider": provider, "id": value["id"]}
    env_tmpl = parse_env_template_secret_ref(value, env_default)
    if env_tmpl:
        return env_tmpl
    return None


#: Return whether a value contains either a literal secret string or resolvable SecretRef shape.
def has_configured_secret_input(value, defaults: SecretDefaults = None) -> bool:
    """Return whether ``value`` is a non-empty literal or a resolvable SecretRef."""
    if normalize_secret_input_string(value):
        return True
    return coerce_secret_ref(value, defaults) is not None


#: Trim a literal secret input string while leaving non-string inputs unresolved.
def normalize_secret_input_string(value):
    """Trim a string and return ``None`` if empty/non-string."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


class UnresolvedSecretInputError(Exception):
    """Error thrown when strict secret reads encounter a configured but unresolved SecretRef."""

    def __init__(self, path: str, ref):
        self.path = path
        self.ref = ref
        label = f"{ref['source']}:{ref['provider']}:{ref['id']}"
        super().__init__(
            f"{path}: unresolved SecretRef \"{label}\". Resolve this command against an active gateway runtime snapshot before reading it."
        )
        self.name = "UnresolvedSecretInputError"


#: Narrow errors from strict secret read sites without parsing user-facing messages.
def is_unresolved_secret_input_error(value) -> bool:
    return isinstance(value, UnresolvedSecretInputError)


#: Throw when a secret field still contains an unresolved SecretRef at a read site.
def assert_secret_input_resolved(*, value, ref_value=None, defaults=None, path: str) -> None:
    """Raise :class:`UnresolvedSecretInputError` if the field is still a SecretRef."""
    resolved = resolve_secret_input_ref(value=value, ref_value=ref_value, defaults=defaults)
    if resolved["ref"]:
        raise UnresolvedSecretInputError(path=path, ref=resolved["ref"])


#: Resolve a secret field to either a literal value, a configured-unavailable ref, or missing.
def resolve_secret_input_string(*, value, ref_value=None, defaults=None, path: str, mode: str = "strict"):
    """Resolve a secret field to one of ``available`` / ``configured_unavailable`` / ``missing``."""
    normalized = normalize_secret_input_string(value)
    if normalized:
        return {"status": "available", "value": normalized, "ref": None}
    resolved = resolve_secret_input_ref(value=value, ref_value=ref_value, defaults=defaults)
    if not resolved["ref"]:
        return {"status": "missing", "value": None, "ref": None}
    if (mode or "strict") == "strict":
        raise UnresolvedSecretInputError(path=path, ref=resolved["ref"])
    return {"status": "configured_unavailable", "value": None, "ref": resolved["ref"]}


#: Return a strict literal secret value, throwing if the field still points at a SecretRef.
def normalize_resolved_secret_input_string(*, value, ref_value=None, defaults=None, path: str):
    """Strict-mode resolve; return the literal value or ``None`` if missing/ref-only."""
    resolved = resolve_secret_input_string(value=value, ref_value=ref_value, defaults=defaults, path=path, mode="strict")
    if resolved["status"] == "available":
        return resolved["value"]
    return None


#: Resolve explicit ``refValue`` before inline secret references embedded in ``value``.
def resolve_secret_input_ref(*, value, ref_value=None, defaults=None):
    """Resolve both the explicit ref and the inline ref from a secret field."""
    explicit = coerce_secret_ref(ref_value, defaults)
    # Explicit ref fields take precedence so a literal fallback can stay beside a configured ref.
    inline = None if explicit else coerce_secret_ref(value, defaults)
    return {
        "explicitRef": explicit,
        "inlineRef": inline,
        "ref": explicit or inline,
    }


class EnvSecretProviderConfig(TypedDict, total=False):
    source: str  # "env"
    allowlist: list  # exact env-var names


FileSecretProviderMode = Literal["singleValue", "json"]


class FileSecretProviderConfig(TypedDict, total=False):
    source: str  # "file"
    path: str
    mode: str  # FileSecretProviderMode
    timeoutMs: int
    maxBytes: int
    allowInsecurePath: bool


class ManualExecSecretProviderConfig(TypedDict, total=False):
    source: str  # "exec"
    command: str
    args: list
    timeoutMs: int
    noOutputTimeoutMs: int
    maxOutputBytes: int
    jsonOnly: bool
    env: dict
    passEnv: list
    trustedDirs: list
    allowInsecurePath: bool
    allowSymlinkCommand: bool


class PluginIntegrationSecretProviderConfig(TypedDict, total=False):
    source: str  # "exec"
    pluginIntegration: dict  # {pluginId, integrationId}


#: Exec secret provider config union.
ExecSecretProviderConfig = dict  # ManualExecSecretProviderConfig | PluginIntegrationSecretProviderConfig


#: Secret provider config union.
SecretProviderConfig = dict  # EnvSecretProviderConfig | FileSecretProviderConfig | ExecSecretProviderConfig


class SecretsConfig(TypedDict, total=False):
    providers: dict
    defaults: dict  # {env?, file?, exec?}
    resolution: dict  # {maxProviderConcurrency?, maxRefsPerProvider?, maxBatchBytes?}


__all__ = [
    "SecretRefSource",
    "SecretRef",
    "SecretInput",
    "DEFAULT_SECRET_PROVIDER_ALIAS",
    "ENV_SECRET_REF_ID_RE",
    "LEGACY_SECRETREF_ENV_MARKER_PREFIX",
    "LEGACY_DOUBLE_UNDERSCORE_ENV_MARKER_PREFIX",
    "SecretInputStringResolutionMode",
    "SecretInputStringResolution",
    "SecretDefaults",
    "is_valid_env_secret_ref_id",
    "is_secret_ref",
    "parse_env_template_secret_ref",
    "parse_legacy_secret_ref_env_marker",
    "coerce_secret_ref",
    "has_configured_secret_input",
    "normalize_secret_input_string",
    "UnresolvedSecretInputError",
    "is_unresolved_secret_input_error",
    "assert_secret_input_resolved",
    "resolve_secret_input_string",
    "normalize_resolved_secret_input_string",
    "resolve_secret_input_ref",
    "EnvSecretProviderConfig",
    "FileSecretProviderMode",
    "FileSecretProviderConfig",
    "ManualExecSecretProviderConfig",
    "PluginIntegrationSecretProviderConfig",
    "ExecSecretProviderConfig",
    "SecretProviderConfig",
    "SecretsConfig",
]
