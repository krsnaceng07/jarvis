"""jarvis_llm.diagnostics — redacted provider/runtime diagnostics.

OpenClaw parity: ``packages/llm-core/src/utils/diagnostics.ts``.

Mirrors ``DiagnosticErrorInfo``, ``AssistantMessageDiagnostic``,
``formatThrownValue``, ``extractDiagnosticError``,
``createAssistantMessageDiagnostic`` and
``appendAssistantMessageDiagnostic``.

Why this module exists
======================
The agent loop never lets a provider failure escape as an exception
(see ``stream.py`` for the ``StreamFn`` contract). Failures are
recorded as *data* on the assistant message. These helpers are how a
raised Python exception becomes that data without losing the
name/message/traceback/code that operators need.

Parity deviations
=================
- TS reads ``error.stack``; Python has no equivalent attribute, so
  ``stack`` is filled from ``traceback.format_exception`` when a
  traceback is attached, else ``None``.
- TS checks ``typeof code === "string" | "number"``. Python mirrors
  this with ``isinstance(code, (str, int))``, but explicitly excludes
  ``bool`` because ``bool`` is a subclass of ``int`` in Python and
  ``code=True`` is never a meaningful error code.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any


def now_ms() -> int:
    """Unix timestamp in milliseconds — the OpenClaw ``Date.now()`` equivalent.

    Every timestamp in the LLM/agent contracts is milliseconds since the
    epoch, matching OpenClaw. Centralized here so the whole port shares
    one clock and tests can monkeypatch a single symbol.
    """
    return int(time.time() * 1000)


@dataclass(frozen=True)
class DiagnosticErrorInfo:
    """Serializable error fields extracted from a thrown value.

    Parity: ``DiagnosticErrorInfo`` in ``diagnostics.ts``.
    """

    message: str
    name: str | None = None
    stack: str | None = None
    code: str | int | None = None


@dataclass(frozen=True)
class AssistantMessageDiagnostic:
    """One timestamped diagnostic entry attached to an assistant message.

    Parity: ``AssistantMessageDiagnostic`` in ``diagnostics.ts``.
    """

    type: str
    timestamp: int
    error: DiagnosticErrorInfo | None = None
    details: dict[str, Any] | None = None


def format_thrown_value(value: object) -> str:
    """Format an arbitrary thrown value into diagnostic-safe text.

    Parity: ``formatThrownValue``. TS prefers ``value.message`` and falls
    back to ``value.name``; Python prefers ``str(exc)`` and falls back to
    the exception class name, which is the closest equivalent.
    """
    if isinstance(value, BaseException):
        return str(value) or type(value).__name__
    if isinstance(value, str):
        return value
    return str(value)


def extract_diagnostic_error(error: object) -> DiagnosticErrorInfo:
    """Extract serializable diagnostic fields from any thrown value.

    Parity: ``extractDiagnosticError``. Non-exception values get
    ``name="ThrownValue"``, matching OpenClaw's non-``Error`` branch.
    """
    if not isinstance(error, BaseException):
        return DiagnosticErrorInfo(name="ThrownValue", message=format_thrown_value(error))

    raw_code = getattr(error, "code", None)
    # bool is a subclass of int in Python; a boolean is never a real code.
    code = raw_code if isinstance(raw_code, (str, int)) and not isinstance(raw_code, bool) else None

    stack: str | None = None
    if error.__traceback__ is not None:
        stack = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        ).rstrip("\n")

    name = type(error).__name__
    return DiagnosticErrorInfo(
        name=name or None,
        message=str(error) or name,
        stack=stack,
        code=code,
    )


def create_assistant_message_diagnostic(
    diagnostic_type: str,
    error: object,
    details: dict[str, Any] | None = None,
) -> AssistantMessageDiagnostic:
    """Create a timestamped diagnostic entry.

    Parity: ``createAssistantMessageDiagnostic``.
    """
    return AssistantMessageDiagnostic(
        type=diagnostic_type,
        timestamp=now_ms(),
        error=extract_diagnostic_error(error),
        details=details,
    )


def append_assistant_message_diagnostic(
    diagnostics: list[AssistantMessageDiagnostic] | None,
    diagnostic: AssistantMessageDiagnostic,
) -> list[AssistantMessageDiagnostic]:
    """Append a diagnostic while preserving existing entries.

    Parity deviation, deliberate: OpenClaw's
    ``appendAssistantMessageDiagnostic(message, diagnostic)`` mutates
    ``message.diagnostics`` in place. JARVIS's assistant messages are
    frozen dataclasses (per the SDK value-type convention), so this
    returns a **new list** and the caller rebuilds the message with
    ``dataclasses.replace``. The copy-then-append semantics are
    identical; only the mutation site moves.
    """
    return [*(diagnostics or []), diagnostic]


__all__ = [
    "AssistantMessageDiagnostic",
    "DiagnosticErrorInfo",
    "append_assistant_message_diagnostic",
    "create_assistant_message_diagnostic",
    "extract_diagnostic_error",
    "format_thrown_value",
    "now_ms",
]
