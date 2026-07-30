"""jarvis.agents.sessions.http_dispatcher — HTTP session dispatcher config.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/http-dispatcher.ts``.

Parses idle-timeout values shared by the server
and config surfaces.

Parity
======
- ``DEFAULT_HTTP_IDLE_TIMEOUT_MS = 300_000``
  (``http-dispatcher.ts:8``) — five minutes; the
  canonical default for HTTP transport idle timeouts.
- ``parse_http_idle_timeout_ms(value) -> int | None``
  (``http-dispatcher.ts:11-26``):
  - ``str`` input:
    - ``"disabled"`` (any case, trimmed) → ``0``
      (the explicit disabled sentinel)
    - empty string → ``None`` (no value)
    - other → :func:`_parse_strict_non_negative_integer`
  - ``number`` input:
    - non-finite or negative → ``None``
    - other → ``math.floor(value)``
  - other types → ``None``

Phase 6.1 — storage primitives.

Adaptations
-----------
- The OpenClaw source uses
  ``parseStrictNonNegativeInteger`` from
  ``../../infra/parse-finite-number.js``. The
  Python port re-implements the helper locally
  with the same contract.
"""
from __future__ import annotations

import math
from typing import Union


#: Default HTTP idle timeout, in milliseconds.
#: Mirrors ``DEFAULT_HTTP_IDLE_TIMEOUT_MS``
#: (``http-dispatcher.ts:8``). Five minutes.
DEFAULT_HTTP_IDLE_TIMEOUT_MS = 300_000


def _parse_strict_non_negative_integer(value: str) -> int | None:
    """Parse a string as a strict non-negative
    integer. Mirrors ``parseStrictNonNegativeInteger``
    (imported by ``http-dispatcher.ts``).

    The contract: ``value`` must be a non-empty
    string of decimal digits (``"0"``, ``"42"``,
    ``"1000"``). Whitespace, signs, decimals, and
    exponents all return ``None`` — the parser is
    strict on purpose so a config error surfaces at
    load time rather than producing a silent default.
    """
    if not value:
        return None
    if not value.isdigit():
        return None
    result = int(value)
    if result < 0:
        return None
    return result


def parse_http_idle_timeout_ms(value: object) -> Union[int, None]:
    """Parse an idle-timeout value, returning ``0``
    for the explicit ``"disabled"`` sentinel.

    Mirrors ``parseHttpIdleTimeoutMs``
    (``http-dispatcher.ts:11-26``).

    Parameters
    ----------
    value : object
        Either a string (config-file form) or a
        number (programmatic form). ``None`` and other
        types return ``None`` (no value).

    Returns
    -------
    int | None
        The parsed timeout in milliseconds.
        ``0`` means "disabled" (the canonical OpenClaw
        sentinel). ``None`` means the input was
        invalid or empty.
    """
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed.lower() == "disabled":
            return 0
        if not trimmed:
            return None
        return _parse_strict_non_negative_integer(trimmed)

    if isinstance(value, bool):
        # Booleans are a subtype of ``int`` in Python;
        # the OpenClaw source's ``typeof value !==
        # "number"`` excludes booleans (which are
        # ``typeof "boolean"`` in TS). Match by
        # short-circuiting here.
        return None

    if isinstance(value, (int, float)):
        if not math.isfinite(value) or value < 0:
            return None
        return math.floor(value)

    return None


__all__ = [
    "DEFAULT_HTTP_IDLE_TIMEOUT_MS",
    "parse_http_idle_timeout_ms",
]
