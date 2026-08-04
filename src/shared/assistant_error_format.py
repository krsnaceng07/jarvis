"""jarvis.shared.assistant_error_format — assistant error formatter.

OpenClaw parity: mirrors
``openclaw-main/src/shared/assistant-error-format.ts``.

Focused minimal port: detects JSON API error payloads and HTTP status
prefixes, with HTML/Cloudflare detection and a generic-provider-internal
fallback. The OpenClaw source uses long internal regex helpers; this port
exposes the same public surface with the same classification rules.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional, TypedDict


MALFORMED_STREAMING_FRAGMENT_ERROR_MESSAGE = (
    "OpenClaw transport error: malformed_streaming_fragment"
)
MALFORMED_STREAMING_FRAGMENT_USER_MESSAGE = (
    "LLM streaming response contained a malformed fragment. Please try again."
)

GENERIC_PROVIDER_INTERNAL_ERROR_USER_MESSAGE = (
    "The AI service returned an internal error. Please try again in a moment."
)


class ApiErrorInfo(TypedDict, total=False):
    httpCode: str
    type: str
    message: str
    requestId: str


_ERROR_PAYLOAD_PREFIX_RE = re.compile(
    r"^(?:error|(?:[a-z][\w-]*\s+)?api\s*error|apierror|openai\s*error|anthropic\s*error|gateway\s*error|codex\s*error)"
    r"(?:\s+\d{3})?[:\s-]+",
    re.IGNORECASE,
)
_HTTP_STATUS_DELIMITER_RE = r"(?:\s*:\s*|\s+)"
_HTTP_STATUS_PREFIX_RE = re.compile(
    r"^(?:http\s*)?(\d{3})(?:\s*:\s*|\s+)(.+)$",
    re.IGNORECASE,
)
_HTTP_STATUS_CODE_PREFIX_RE = re.compile(
    r"^(?:http\s*)?(\d{3})(?:\s*:\s*|\s+)([\s\S]+)$",
    re.IGNORECASE,
)
_PROVIDER_WRAPPED_HTTP_STATUS_RE = re.compile(
    r"^(?:[a-z][\w-]*(?:\s+[a-z][\w-]*){0,3}\s+)?api\s*error\s*\((\d{3})\)(?:\s*:\s*([\s\S]*))?$",
    re.IGNORECASE,
)
_HTML_ERROR_PREFIX_RE = re.compile(r"^\s*(?:<!doctype\s+html\b|<html\b)", re.IGNORECASE)
_HTML_CLOSE_RE = re.compile(r"</html>", re.IGNORECASE)
_STANDALONE_HTML_ERROR_HINT_RE = re.compile(
    r"\bcloudflare\b|cdn-cgi/challenge-platform|challenge-error-text|"
    r"enable javascript and cookies to continue|access denied|forbidden|"
    r"service unavailable|bad gateway|web server is down|captcha|"
    r"attention required",
    re.IGNORECASE,
)
_GENERIC_PROVIDER_INTERNAL_ERROR_RE = re.compile(
    r"an error occurred while processing your request",
    re.IGNORECASE,
)
_SUPPORT_REQUEST_ID_RE = re.compile(
    r"(?:request[\s_-]*id)\s*[:#]?\s*([a-z0-9][a-z0-9_-]{6,}[a-z0-9])",
    re.IGNORECASE,
)
_CLOUDFLARE_HTML_ERROR_CODES = frozenset({521, 522, 523, 524, 525, 526, 530})


def _is_error_payload_object(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("type") == "error":
        return True
    if isinstance(payload.get("request_id"), str) or isinstance(payload.get("requestId"), str):
        return True
    err = payload.get("error")
    if isinstance(err, dict):
        return any(
            isinstance(err.get(k), str)
            for k in ("message", "type", "code")
        )
    if isinstance(err, str) and isinstance(payload.get("message"), str):
        return True
    return False


def parse_api_error_payload(raw: Optional[str]) -> Optional[dict]:
    """Parse a JSON error payload after stripping common error prefixes.

    Mirrors :func:`parseApiErrorPayload`
    (``shared/assistant-error-format.ts``).
    """
    if not raw:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    candidates = [trimmed]
    if _ERROR_PAYLOAD_PREFIX_RE.match(trimmed):
        candidates.append(_ERROR_PAYLOAD_PREFIX_RE.sub("", trimmed, count=1).strip())
    for candidate in candidates:
        if not candidate.startswith("{") or not candidate.endswith("}"):
            continue
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if _is_error_payload_object(parsed):
            return parsed
    return None


def _extract_http_status_match(match: Optional["re.Match[str]"]) -> Optional[dict]:
    if not match:
        return None
    try:
        code = int(match.group(1))
    except (ValueError, TypeError):
        return None
    if code < 100 or code > 599:
        return None
    rest = (match.group(2) or "").strip()
    return {"code": code, "rest": rest}


def extract_leading_http_status(raw: str) -> Optional[dict]:
    """Extract a leading HTTP status code from ``raw``.

    Mirrors :func:`extractLeadingHttpStatus`
    (``shared/assistant-error-format.ts``).
    """
    return _extract_http_status_match(_HTTP_STATUS_CODE_PREFIX_RE.match(raw))


def extract_provider_wrapped_http_status(raw: str) -> Optional[dict]:
    """Extract HTTP status from provider-wrapped ``api error (NNN)`` text.

    Mirrors :func:`extractProviderWrappedHttpStatus`
    (``shared/assistant-error-format.ts``).
    """
    return _extract_http_status_match(_PROVIDER_WRAPPED_HTTP_STATUS_RE.match(raw))


def is_cloudflare_or_html_error_page(raw: str) -> bool:
    """Return whether ``raw`` looks like a Cloudflare/HTML error page.

    Mirrors :func:`isCloudflareOrHtmlErrorPage`
    (``shared/assistant-error-format.ts``).
    """
    if not isinstance(raw, str):
        return False
    trimmed = raw.strip()
    if not trimmed:
        return False
    if (
        _HTML_ERROR_PREFIX_RE.match(trimmed)
        and _HTML_CLOSE_RE.search(trimmed)
        and _STANDALONE_HTML_ERROR_HINT_RE.search(trimmed)
    ):
        return True
    status = extract_leading_http_status(trimmed)
    if not status or status["code"] < 500:
        return False
    if status["code"] in _CLOUDFLARE_HTML_ERROR_CODES:
        return True
    return (
        status["code"] < 600
        and bool(_HTML_ERROR_PREFIX_RE.match(status["rest"]))
        and bool(_HTML_CLOSE_RE.search(status["rest"]))
    )


def is_generic_provider_internal_error(raw: str) -> bool:
    """Return whether ``raw`` looks like a generic provider-internal error.

    Mirrors :func:`isGenericProviderInternalError`
    (``shared/assistant-error-format.ts``).
    """
    if not isinstance(raw, str):
        return False
    trimmed = raw.strip()
    if not trimmed:
        return False
    return bool(_GENERIC_PROVIDER_INTERNAL_ERROR_RE.search(trimmed)) and (
        "help.openai.com" in trimmed.lower() or bool(_SUPPORT_REQUEST_ID_RE.search(trimmed))
    )


def parse_api_error_info(raw: Optional[str]) -> Optional[ApiErrorInfo]:
    """Parse a free-form raw error text into structured API error info.

    Mirrors :func:`parseApiErrorInfo`
    (``shared/assistant-error-format.ts``).
    """
    if not raw:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None

    http_code: Optional[str] = None
    candidate = trimmed
    m = re.match(r"^(\d{3})\s+(.+)$", candidate, re.DOTALL)
    parsed_status = _extract_http_status_match(m)
    if parsed_status:
        http_code = str(parsed_status["code"])
        candidate = parsed_status["rest"]

    payload = parse_api_error_payload(candidate)
    if not payload:
        return None

    request_id: Optional[str] = None
    if isinstance(payload.get("request_id"), str):
        request_id = payload["request_id"]
    elif isinstance(payload.get("requestId"), str):
        request_id = payload["requestId"]

    top_type = payload["type"] if isinstance(payload.get("type"), str) else None
    top_message = payload["message"] if isinstance(payload.get("message"), str) else None

    err_type: Optional[str] = None
    err_message: Optional[str] = None
    err = payload.get("error")
    if isinstance(err, dict):
        if isinstance(err.get("type"), str):
            err_type = err["type"]
        if not err_type and isinstance(err.get("code"), str):
            err_type = err["code"]
        if isinstance(err.get("message"), str):
            err_message = err["message"]
    elif isinstance(err, str):
        err_type = err
    return {
        "httpCode": http_code,
        "type": err_type if err_type is not None else top_type,
        "message": err_message if err_message is not None else top_message,
        "requestId": request_id,
    }


def _truncate(text: str, max_length: int) -> str:
    if max_length <= 0 or len(text) <= max_length:
        return text
    return text[:max_length]


def format_raw_assistant_error_for_ui(raw: Optional[str]) -> str:
    """Format a raw assistant error string for the user-facing UI.

    Mirrors :func:`formatRawAssistantErrorForUi`
    (``shared/assistant-error-format.ts``).
    """
    if not isinstance(raw, str):
        return "LLM request failed with an unknown error."
    trimmed = raw.strip()
    if not trimmed:
        return "LLM request failed with an unknown error."
    if trimmed == MALFORMED_STREAMING_FRAGMENT_ERROR_MESSAGE:
        return MALFORMED_STREAMING_FRAGMENT_USER_MESSAGE
    if is_generic_provider_internal_error(trimmed):
        return GENERIC_PROVIDER_INTERNAL_ERROR_USER_MESSAGE
    leading = extract_leading_http_status(trimmed)
    is_html = is_cloudflare_or_html_error_page(trimmed)
    if leading and is_html:
        return (
            f"The AI service is temporarily unavailable (HTTP {leading['code']}). "
            "Please try again in a moment."
        )
    if is_html:
        return (
            "The provider returned an HTML error page instead of an API response. "
            "This usually means a CDN or gateway (e.g. Cloudflare) blocked the request. "
            "Retry in a moment or check provider status."
        )
    http_match = _extract_http_status_match(_HTTP_STATUS_PREFIX_RE.match(trimmed))
    if http_match and not http_match["rest"].startswith("{"):
        return f"HTTP {http_match['code']}: {http_match['rest']}"
    info = parse_api_error_info(trimmed)
    if info and info.get("message"):
        prefix = f"HTTP {info['httpCode']}" if info.get("httpCode") else "LLM error"
        type_part = f" {info['type']}" if info.get("type") else ""
        return f"{prefix}{type_part}: {info['message']}"
    return _truncate(trimmed, 600) + ("…" if len(trimmed) > 600 else "")


__all__ = [
    "MALFORMED_STREAMING_FRAGMENT_ERROR_MESSAGE",
    "MALFORMED_STREAMING_FRAGMENT_USER_MESSAGE",
    "GENERIC_PROVIDER_INTERNAL_ERROR_USER_MESSAGE",
    "ApiErrorInfo",
    "parse_api_error_payload",
    "extract_leading_http_status",
    "extract_provider_wrapped_http_status",
    "is_cloudflare_or_html_error_page",
    "is_generic_provider_internal_error",
    "parse_api_error_info",
    "format_raw_assistant_error_for_ui",
]
