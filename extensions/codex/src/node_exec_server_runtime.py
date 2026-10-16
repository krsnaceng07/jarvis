"""Connection-bound Codex exec-server process runtime on remote nodes.

OpenClaw parity: ``extensions/codex/src/node-exec-server.runtime.ts`` for
session/env handling plus the credential-gate section of
``extensions/codex/src/app-server/sandbox-exec-server-node-relay.ts``
(``rejectCredentialedCodexNodeHttpRequest`` and helpers).

Adaptations: the ``hasSensitiveCodexNodeText`` oracle uses the canonical
``jarvis_sdk.memory_host_error_utils.redact_sensitive_text`` secret-pattern
check (Jarvis has no tool-payload redactor seam yet); the header/field
pattern matching — the primary signal — is ported verbatim.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, unquote, urlparse

from jarvis_sdk.memory_host_error_utils import redact_sensitive_text

MAX_CODEX_EXEC_SERVER_MESSAGE_BYTES: int = 64 * 1024 * 1024  # 64 MiB limit
CODEX_EXEC_SERVER_TERMINATION_GRACE_SECONDS: float = 1.0

#: Sensitive authorization headers and credential keys scrubbed before remote relay
SENSITIVE_AUTH_KEYS: tuple[str, ...] = (
    "authorization",
    "bearer",
    "oauth",
    "cookie",
    "cookies",
    "api_key",
    "apikey",
    "codex_api_key",
    "openai_api_key",
    "github_token",
)

#: Max decoded body bytes inspected for credentials. Mirrors
#: ``CODEX_NODE_HTTP_CREDENTIAL_BODY_MAX_BYTES``.
CODEX_NODE_HTTP_CREDENTIAL_BODY_MAX_BYTES: int = 1024 * 1024
#: Max fields scanned per request before failing closed. Mirrors
#: ``CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_FIELDS``.
CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_FIELDS: int = 256
#: Max nested-encoding depth walked before failing closed. Mirrors
#: ``CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_DEPTH``.
CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_DEPTH: int = 8
#: JSON-RPC error code for rejected credentialed requests. Mirrors the
#: ``-32602`` in ``createCredentialedCodexNodeHttpRejection``.
CODEX_NODE_HTTP_CREDENTIAL_REJECTION_CODE: int = -32602
#: Rejection message. Mirrors ``createCredentialedCodexNodeHttpRejection`` verbatim.
CODEX_NODE_HTTP_CREDENTIAL_REJECTION_MESSAGE: str = (
    "Authenticated remote HTTP is unavailable on execution nodes; "
    "run on Gateway or use an intentionally credential-free endpoint."
)

#: Exact credential-bearing header names. Mirrors
#: ``CODEX_NODE_HTTP_CREDENTIAL_HEADER_NAMES``.
CODEX_NODE_HTTP_CREDENTIAL_HEADER_NAMES: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "apikey",
        "x-auth-token",
        "auth-token",
        "x-access-token",
        "access-token",
        "x-secret-key",
        "secret-key",
        "x-goog-api-key",
        "x-vault-token",
        "x-api-token",
    }
)

#: Credential-like header names. Mirrors
#: ``CODEX_NODE_HTTP_CREDENTIAL_HEADER_NAME_PATTERN``.
CODEX_NODE_HTTP_CREDENTIAL_HEADER_NAME_PATTERN: re.Pattern[str] = re.compile(
    r"(?:^|[-_])(?:auth(?:orization|entication)?|token|secret|api[-_]?key|apikey|key"
    r"|password|passwd|pwd|passphrase|passcode|credentials?|session|jwt|assertion"
    r"|verifier|sig(?:nature)?|hmac|bearer|ticket|challenge|proof|dpop|otp|totp"
    r"|pin|mfa)(?:[-_]|$)",
    re.IGNORECASE,
)

#: Credential-like field-name components. Mirrors
#: ``CODEX_NODE_HTTP_CREDENTIAL_FIELD_NAME_PATTERN``.
CODEX_NODE_HTTP_CREDENTIAL_FIELD_NAME_PATTERN: re.Pattern[str] = re.compile(
    r"^(?:(?:[a-z\d]+_)*(?:token|secret|password|passwd|pwd|passphrase|passcode"
    r"|credentials?|authorization|api_?key|private_key|secret_key|secret_access_key"
    r"|jwt|assertion|verifier|signature|hmac|bearer|ticket|(?:oauth|consumer|auth"
    r"|access)_key|otp|totp|pin)|(?:device|authorization|auth|verification|mfa)_code"
    r"|session(?:_id)?|jsessionid|saml(?:_?response|_?assertion)?|auth|jwt|code|sig"
    r"|signature|hmac|key|pass)$"
)

_PERCENT_ESCAPE_RE: re.Pattern[str] = re.compile(r"%[\da-f]{2}", re.IGNORECASE)
_STRAY_PERCENT_RE: re.Pattern[str] = re.compile(r"%(?![\da-f]{2})", re.IGNORECASE)


def _decode_uri_component(value: str) -> str:
    """Decode percent-escapes with ``decodeURIComponent`` throw conditions.

    A stray ``%`` (not starting a valid escape) or invalid UTF-8 raises,
    matching the fail-closed decode in ``isCodexNodeCredentialField``.
    """
    if _STRAY_PERCENT_RE.search(value):
        raise ValueError("malformed percent-encoding")
    return unquote(value, errors="strict")


_JSON_STRING_TOKEN_RE: re.Pattern[str] = re.compile(r'("(?:\\.|[^"\\])*")(\s*:)?')
_CAMEL_SPLIT_RE: re.Pattern[str] = re.compile(r"([a-z\d])([A-Z])")
_FIELD_SPLIT_RE: re.Pattern[str] = re.compile(r"[.[\]]+")
_QUERY_SPLIT_RE: re.Pattern[str] = re.compile(r"[?#]")
# Mirrors the ``[\p{C}\p{Z}\u115F\u1160\u3164\uFFA0+]`` strip in
# ``isCodexNodeCredentialField`` (the explicit chars are Lo, not C/Z).
# Code points, not literals: invisible chars must never be typed raw.
_FIELD_STRIP_CHARS: frozenset[str] = frozenset(
    [chr(0x115F), chr(0x1160), chr(0x3164), chr(0xFFA0), "+"]
)


@dataclass(frozen=True, slots=True)
class ExecServerMessageValidationResult:
    """Validation outcome for a remote JSON-RPC frame."""

    ok: bool
    payload: dict[str, Any] | None = None
    error: str | None = None


def validate_node_exec_server_message(data: bytes) -> ExecServerMessageValidationResult:
    """Validate remote exec-server message payload size and JSON-RPC structure."""
    if len(data) == 0:
        return ExecServerMessageValidationResult(
            ok=False, error="Codex exec-server received an empty message."
        )

    if len(data) > MAX_CODEX_EXEC_SERVER_MESSAGE_BYTES:
        return ExecServerMessageValidationResult(
            ok=False,
            error=f"Codex exec-server JSON-RPC message exceeds its 64 MiB limit ({len(data)} bytes).",
        )

    if b"\n" in data or b"\r" in data:
        return ExecServerMessageValidationResult(
            ok=False,
            error="Codex exec-server JSON-RPC frames must contain exactly one message without inline newlines.",
        )

    try:
        text = data.decode("utf-8")
        parsed = json.loads(text)
    except Exception as exc:
        return ExecServerMessageValidationResult(
            ok=False, error=f"Codex exec-server received malformed UTF-8 or JSON-RPC: {exc}"
        )

    if not isinstance(parsed, dict):
        return ExecServerMessageValidationResult(
            ok=False, error="Codex exec-server received an invalid JSON-RPC message."
        )

    return ExecServerMessageValidationResult(ok=True, payload=parsed)


def sanitize_remote_exec_environment(env: dict[str, str] | None = None) -> dict[str, str]:
    """Sanitize environment variables for remote node execution.

    OpenClaw parity: strips bearer/OAuth tokens, credentials, and sensitive auth keys.

    NOTE: an explicit empty map stays empty — it must never fall back to
    the ambient environment (node-bound requests would otherwise inherit
    Gateway credentials). Mirrors ``sanitizeEnvVars(values)``, which only
    filters.
    """
    base_env = dict(os.environ) if env is None else dict(env)
    clean_env: dict[str, str] = {}

    for key, val in base_env.items():
        key_lower = key.lower()
        if any(s in key_lower for s in SENSITIVE_AUTH_KEYS):
            continue
        clean_env[key] = val

    return clean_env


# ---------------------------------------------------------------------------
# Remote HTTP credential gate (sandbox-exec-server-node-relay.ts)
# ---------------------------------------------------------------------------


def _is_url_with_userinfo(value: str) -> bool:
    """Return whether *value* parses as a URL carrying username/password."""
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return bool(parsed.username or parsed.password)


def has_sensitive_node_text(value: str) -> bool:
    """Return whether *value* looks credential-bearing, decoding escapes.

    Mirrors ``hasSensitiveCodexNodeText``: the canonical
    ``redact_sensitive_text`` secret-pattern check decides, walking
    percent-encoded layers (bad escapes fail closed).
    """
    decoded = value
    for _depth in range(CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_DEPTH + 1):
        if redact_sensitive_text(decoded) != decoded:
            return True
        if not _PERCENT_ESCAPE_RE.search(decoded):
            return False
        try:
            decoded = unquote(decoded, errors="strict")
        except Exception:
            return True
    return True


def is_node_credential_field(value: str) -> bool:
    """Return whether a field name looks credential-bearing.

    Mirrors ``isCodexNodeCredentialField``: percent-decode walk, then
    control/format strip, camel-to-snake, dash-to-underscore, lowercase,
    split on ``.[]``, and match every component against the field pattern.
    Overlong names fail closed.
    """
    decoded = value
    for _depth in range(CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_DEPTH):
        try:
            nxt = _decode_uri_component(decoded)
        except Exception:
            return True
        if nxt == decoded:
            break
        decoded = nxt
    normalized = "".join(
        ch
        for ch in decoded
        if ch not in _FIELD_STRIP_CHARS and not unicodedata.category(ch).startswith(("C", "Z"))
    )
    normalized = _CAMEL_SPLIT_RE.sub(r"\1_\2", normalized).replace("-", "_").lower()
    if len(normalized) > CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_FIELDS:
        return True
    return any(
        CODEX_NODE_HTTP_CREDENTIAL_FIELD_NAME_PATTERN.match(component)
        for component in _FIELD_SPLIT_RE.split(normalized)
    )


def _has_credentialed_node_http_url(value: str) -> bool:
    """Mirror ``hasCredentialedCodexNodeHttpUrl`` (raises on invalid URL)."""
    try:
        url = urlparse(value)
    except Exception:
        raise ValueError("Codex http/request URL must be valid.")
    if not url.scheme or not url.netloc:
        raise ValueError("Codex http/request URL must be valid.")
    if url.username or url.password or has_sensitive_node_text(value):
        return True

    def _check_param(name: str, param_value: str, fields: list[int]) -> bool:
        fields[0] += 1
        return (
            fields[0] > CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_FIELDS
            or is_node_credential_field(name)
            or has_sensitive_node_text(param_value)
        )

    fields = [0]
    # Query params plus fragment-parsed-as-query (mirrors URLSearchParams(hash)).
    for query in (url.query, url.fragment):
        for name, param_value in parse_qsl(query, keep_blank_values=True):
            if _check_param(name, param_value, fields):
                return True
    # Nested encodings inside path, fragment, and values (bounded depth walk).
    for initial in (
        url.path,
        url.fragment,
        *[v for _, v in parse_qsl(url.query, keep_blank_values=True)],
    ):
        component = initial
        for depth in range(CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_DEPTH + 1):
            for nested_query in _QUERY_SPLIT_RE.split(component)[1:]:
                for name, param_value in parse_qsl(nested_query, keep_blank_values=True):
                    if _check_param(name, param_value, fields):
                        return True
            for segment in component.split("/"):
                for parameter in segment.split(";")[1:]:
                    sep = parameter.find("=")
                    name = parameter if sep < 0 else parameter[:sep]
                    param_value = "" if sep < 0 else parameter[sep + 1 :]
                    if _check_param(name, param_value, fields):
                        return True
            if not _PERCENT_ESCAPE_RE.search(component):
                break
            if depth == CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_DEPTH:
                return True
            try:
                component = unquote(component, errors="strict")
            except Exception:
                return True
    return False


def _iter_json_string_tokens(body: str):  # type: ignore[no-untyped-def]
    r"""Yield ``(value, has_key_colon)`` for every JSON string token in *body*.

    Mirrors the ``/("(?:\\.|[^"\\])*")(\s*:)?/gu`` scan in
    ``hasCredentialedCodexNodeRawJsonStrings``.
    """
    for match in _JSON_STRING_TOKEN_RE.finditer(body):
        try:
            value = json.loads(match.group(1))
        except Exception:
            continue
        yield value, match.group(2) is not None


def _has_credentialed_node_raw_json_strings(body: str) -> bool:
    """Mirror ``hasCredentialedCodexNodeRawJsonStrings``."""
    fields = 0
    for value, has_key_colon in _iter_json_string_tokens(body):
        fields += 1
        if (
            fields > CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_FIELDS
            or not isinstance(value, str)
            or has_sensitive_node_text(value)
            or (has_key_colon and is_node_credential_field(value))
        ):
            return True
    return False


def _has_credentialed_node_json_fields(value: Any) -> bool:
    """Mirror ``hasCredentialedCodexNodeJsonFields`` (bounded field/depth walk)."""
    pending: list[tuple[Any, int]] = [(value, 0)]
    fields = 0
    while pending:
        current, depth = pending.pop()
        if isinstance(current, str) and has_sensitive_node_text(current):
            return True
        if not isinstance(current, (dict, list)):
            continue
        if depth >= CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_DEPTH:
            return True
        entries = list(enumerate(current)) if isinstance(current, list) else list(current.items())
        for name, nested in entries:
            fields += 1
            if fields > CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_FIELDS or (
                isinstance(name, str) and is_node_credential_field(name)
            ):
                return True
            pending.append((nested, depth + 1))
    return False


def _has_credentialed_node_http_body(value: Any, content_type: str | None) -> bool:
    """Mirror ``hasCredentialedCodexNodeHttpBody`` (raises on malformed body)."""
    if not isinstance(value, str):
        raise ValueError("Codex http/request bodyBase64 must be a string.")
    declared_text = content_type == "text/plain"
    if not declared_text and len(value) > -(-CODEX_NODE_HTTP_CREDENTIAL_BODY_MAX_BYTES // 3) * 4:
        # Missing content-type or binary disguise must not bypass inspection.
        return True
    try:
        decoded_bytes = base64.b64decode(value, validate=True)
        if (
            not declared_text and len(decoded_bytes) > CODEX_NODE_HTTP_CREDENTIAL_BODY_MAX_BYTES
        ) or base64.b64encode(decoded_bytes).decode("ascii") != value:
            return True
        body = decoded_bytes.decode("utf-8")
    except Exception:
        return True
    if not body:
        return False
    if has_sensitive_node_text(body):
        return True
    declared_json = content_type == "application/json" or (
        content_type is not None and content_type.endswith("+json")
    )
    declared_form = content_type == "application/x-www-form-urlencoded"
    if content_type and not declared_json and not declared_form and not declared_text:
        return True
    if body.lstrip()[:1] == "<":
        return True
    stripped = body.lstrip()
    if declared_json or stripped[:1] in ("{", "["):
        try:
            if _has_credentialed_node_raw_json_strings(body):
                return True
            return _has_credentialed_node_json_fields(json.loads(body))
        except Exception:
            if not declared_text:
                return True
    if not declared_form and "=" not in body:
        return not declared_text
    fields = 0
    for name, param_value in parse_qsl(body, keep_blank_values=True):
        fields += 1
        if (
            fields > CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_FIELDS
            or is_node_credential_field(name)
            or has_sensitive_node_text(param_value)
        ):
            return True
    return False


def create_credentialed_node_http_rejection(request_id: Any) -> dict[str, Any]:
    """Build the ``-32602`` rejection frame. Mirrors
    ``createCredentialedCodexNodeHttpRejection`` (raises without a
    JSON-RPC request id)."""
    if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
        raise ValueError("Codex http/request must have a JSON-RPC request id.")
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": CODEX_NODE_HTTP_CREDENTIAL_REJECTION_CODE,
            "message": CODEX_NODE_HTTP_CREDENTIAL_REJECTION_MESSAGE,
        },
    }


def reject_credentialed_node_http_request(request: Any) -> dict[str, Any] | None:
    """Reject credential-bearing remote ``http/request`` messages.

    Mirrors ``rejectCredentialedCodexNodeHttpRequest``: non-``http/request``
    methods pass (``None``); malformed shapes raise ``ValueError`` (the
    relay fails the message); credentialed requests get the ``-32602``
    rejection frame. Only credential-free HTTP is forwarded to the node.
    """
    if not isinstance(request, dict) or request.get("method") != "http/request":
        return None
    params = request.get("params")
    if not isinstance(params, dict):
        raise ValueError("Codex http/request params must be an object.")
    headers = params.get("headers", [])
    if not isinstance(headers, list):
        raise ValueError("Codex http/request headers must be an array.")
    if len(headers) > CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_FIELDS:
        return create_credentialed_node_http_rejection(request.get("id"))
    credential_bearing = False
    content_type: str | None = None
    for header in headers:
        if (
            not isinstance(header, dict)
            or not isinstance(header.get("name"), str)
            or not isinstance(header.get("value"), str)
        ):
            raise ValueError("Codex http/request headers must contain string names and values.")
        name = header["name"].strip().lower()
        if (
            name in CODEX_NODE_HTTP_CREDENTIAL_HEADER_NAMES
            or CODEX_NODE_HTTP_CREDENTIAL_HEADER_NAME_PATTERN.search(name)
            or has_sensitive_node_text(header["value"])
        ):
            credential_bearing = True
        if name == "content-type":
            declared = header["value"].split(";", 1)[0].strip().lower()
            credential_bearing = credential_bearing or bool(
                content_type and content_type != declared
            )
            content_type = declared
    if not credential_bearing and isinstance(params.get("url"), str):
        credential_bearing = _has_credentialed_node_http_url(params["url"])
    if not credential_bearing and params.get("bodyBase64") is not None:
        credential_bearing = _has_credentialed_node_http_body(params["bodyBase64"], content_type)
    if credential_bearing:
        return create_credentialed_node_http_rejection(request.get("id"))
    return None


def sanitize_exec_server_request(request: Any) -> Any:
    """Strip credential-capable values from ``process/start`` environments.

    Mirrors ``sanitizeCodexExecServerRequest``: only ``process/start``
    is rewritten (other methods pass through untouched); ``env`` and
    ``envPolicy.set`` must be string maps; URL values carrying userinfo
    are dropped, the rest go through ``sanitize_remote_exec_environment``.
    Malformed shapes raise ``ValueError``.
    """
    if not isinstance(request, dict) or request.get("method") != "process/start":
        return request
    params = request.get("params")
    if not isinstance(params, dict):
        raise ValueError("Codex process/start params must be an object.")
    _sanitize_exec_server_environment_map(params, "env")
    if params.get("envPolicy") is not None:
        if not isinstance(params["envPolicy"], dict):
            raise ValueError("Codex process/start envPolicy must be an object.")
        _sanitize_exec_server_environment_map(params["envPolicy"], "set")
    return request


def _sanitize_exec_server_environment_map(record: dict[str, Any], key: str) -> None:
    """Rewrite one string environment map in place (drop userinfo URLs, scrub keys).

    Mirrors ``sanitizeCodexExecServerEnvironment``; absent maps stay absent.
    """
    environment = record.get(key)
    if environment is None:
        return
    if not isinstance(environment, dict):
        raise ValueError(f"Codex process/start {key} must be an object.")
    values: dict[str, str] = {}
    for name, value in environment.items():
        if not isinstance(value, str):
            raise ValueError(f"Codex process/start {key} values must be strings.")
        if _is_url_with_userinfo(value):
            continue
        values[name] = value
    record[key] = sanitize_remote_exec_environment(values)


@dataclass(slots=True)
class RemoteNodeExecSession:
    """Isolated remote execution session managing temp HOME and CODEX_HOME."""

    workspace_dir: str
    temp_home: str
    temp_codex_home: str
    active: bool = True

    def cleanup(self) -> None:
        """Remove isolated temp paths on attempt termination."""
        if not self.active:
            return
        self.active = False
        for path in (self.temp_home, self.temp_codex_home):
            if os.path.exists(path):
                try:
                    shutil.rmtree(path, ignore_errors=True)
                except Exception:
                    pass


def create_remote_node_exec_session(workspace_dir: str) -> RemoteNodeExecSession:
    """Create isolated remote node execution session with temp HOME and CODEX_HOME."""
    temp_home = tempfile.mkdtemp(prefix="jarvis_node_home_")
    temp_codex_home = tempfile.mkdtemp(prefix="jarvis_node_codex_")

    return RemoteNodeExecSession(
        workspace_dir=workspace_dir,
        temp_home=temp_home,
        temp_codex_home=temp_codex_home,
    )


__all__ = [
    "CODEX_EXEC_SERVER_TERMINATION_GRACE_SECONDS",
    "CODEX_NODE_HTTP_CREDENTIAL_BODY_MAX_BYTES",
    "CODEX_NODE_HTTP_CREDENTIAL_FIELD_NAME_PATTERN",
    "CODEX_NODE_HTTP_CREDENTIAL_HEADER_NAME_PATTERN",
    "CODEX_NODE_HTTP_CREDENTIAL_HEADER_NAMES",
    "CODEX_NODE_HTTP_CREDENTIAL_REJECTION_CODE",
    "CODEX_NODE_HTTP_CREDENTIAL_REJECTION_MESSAGE",
    "CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_DEPTH",
    "CODEX_NODE_HTTP_CREDENTIAL_SCAN_MAX_FIELDS",
    "MAX_CODEX_EXEC_SERVER_MESSAGE_BYTES",
    "ExecServerMessageValidationResult",
    "RemoteNodeExecSession",
    "create_credentialed_node_http_rejection",
    "create_remote_node_exec_session",
    "has_sensitive_node_text",
    "is_node_credential_field",
    "reject_credentialed_node_http_request",
    "sanitize_exec_server_request",
    "sanitize_remote_exec_environment",
    "validate_node_exec_server_message",
]
