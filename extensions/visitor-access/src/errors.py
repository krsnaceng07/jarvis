"""Errors and redaction helpers for visitor access."""

from __future__ import annotations


class VisitorAccessError(Exception):
    pass


def visitor_error_text(error: Exception | str, api_token: str | None = None) -> str:
    text = str(error)
    if api_token and api_token in text:
        text = text.replace(api_token, "[REDACTED]")
    return text
