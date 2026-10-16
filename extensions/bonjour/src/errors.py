"""Bonjour error formatting helper.

Mirrors OpenClaw's ``extensions/bonjour/src/errors.ts``:
normalizes ``Error`` and non-``Error`` values into concise
messages for gateway discovery logs.

The output contract is:
- ``Error`` instance with a non-blank message → message text
  (optionally prefixed with the error's ``name`` when it
  isn't the generic ``"Error"``)
- ``Error`` instance with a blank message → either the
  ``name`` (when it isn't ``"Error"``) or ``"Error"``
- Non-``Error`` value → ``str(value)``
"""

from __future__ import annotations

from typing import Any


def format_bonjour_error(err: Any) -> str:
    """Format an unknown Bonjour/ciao error value for logs.

    Mirrors ``formatBonjourError`` in OpenClaw's
    ``extensions/bonjour/src/errors.ts``. The Python port
    uses ``str(err).strip()`` instead of ``err.message.trim()``
    for blank detection, and falls back to ``type(err).__name__``
    when the name attribute is absent.
    """
    if isinstance(err, BaseException):
        raw_message = str(err) if str(err) else ""
        trimmed_message = raw_message.strip()
        name = getattr(err, "name", None) or type(err).__name__
        msg = trimmed_message or name or str(err).strip()
        if name and name != "Error":
            if msg == name:
                return name
            return f"{name}: {msg}"
        return msg
    return str(err)
