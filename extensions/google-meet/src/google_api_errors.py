"""Google API error extraction and scope hint formatting."""

from __future__ import annotations

from typing import Any

REAUTH_HINT = "Re-run `jarvis googlemeet auth login` and store the refreshed oauth block."
GOOGLE_API_ERROR_BODY_LIMIT_BYTES = 8 * 1024


class GoogleApiError(Exception):
    """Google API request error with status code and scope hints."""

    def __init__(self, message: str, status_code: int | None = None, response: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response

    def __str__(self) -> str:
        return self.message


def _scope_text(scopes: list[str] | tuple[str, ...]) -> str:
    return ", ".join(f"`{scope}`" for scope in scopes)


def read_google_api_error_detail(response: Any) -> str:
    """Read bounded error text from an HTTP response."""
    if hasattr(response, "text"):
        text = str(response.text)
    elif hasattr(response, "read"):
        content = response.read()
        text = (
            content.decode("utf-8", errors="replace")
            if isinstance(content, bytes)
            else str(content)
        )
    elif isinstance(response, (str, bytes)):
        text = (
            response.decode("utf-8", errors="replace") if isinstance(response, bytes) else response
        )
    else:
        text = str(response)

    if len(text.encode("utf-8")) > GOOGLE_API_ERROR_BODY_LIMIT_BYTES:
        text = text[:GOOGLE_API_ERROR_BODY_LIMIT_BYTES]
    return text.strip()


def google_api_error(
    response: Any,
    prefix: str,
    scopes: list[str] | tuple[str, ...] | None = None,
) -> GoogleApiError:
    """Construct an informative error with HTTP status and OAuth scope hints."""
    raw_status = getattr(response, "status_code", getattr(response, "status", None))
    status = int(raw_status) if raw_status is not None and str(raw_status).isdigit() else 500
    detail = read_google_api_error_detail(response)
    scope_hint = ""
    if scopes:
        scope_hint = f" Required OAuth scope: {_scope_text(scopes)}. {REAUTH_HINT}"
    return GoogleApiError(
        message=f"{prefix} failed ({status}): {detail}{scope_hint}",
        status_code=status,
        response=response,
    )
