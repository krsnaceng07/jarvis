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
- ``resolve_integer_option(value, fallback, range)``
  (``packages/normalization-core/src/number-coercion.ts:228-240``):
  - Non-finite ``number`` input → ``fallback``
  - Otherwise ``floor(value)``
  - Optional inclusive ``min`` / ``max`` bounds
    clamp the floored result.

Phase 6.1 — storage primitives.
Phase 6.8b — added ``resolve_integer_option``.

Adaptations
-----------
- The OpenClaw source uses
  ``parseStrictNonNegativeInteger`` from
  ``../../infra/parse-finite-number.js``. The
  Python port re-implements the helper locally
  with the same contract.
- The OpenClaw source's ``resolveIntegerOption``
  lives in ``@openclaw/normalization-core``.
  The Python port exposes the same shape from
  this module (it is the canonical place for
  bounded-integer coercion shared by HTTP
  dispatcher + settings manager).
"""
from __future__ import annotations

import math
from typing import Optional, Union


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
    "resolve_integer_option",
]


def resolve_integer_option(
    value: object,
    fallback: int,
    range: Optional[dict] = None,
) -> int:
    """Resolve an integer option, falling back
    when the input is non-finite, and
    optionally clamping to inclusive
    ``min`` / ``max`` bounds. Mirrors the
    OpenClaw source's ``resolveIntegerOption``
    (``packages/normalization-core/src/number-coercion.ts:228-240``)
    which ``SettingsManager`` uses for
    bounded integer config options
    (e.g. ``imageWidthCells``).

    Parameters
    ----------
    value : object
        Candidate value. Finite ``int`` /
        ``float`` inputs are floored; booleans
        are treated as their ``int`` form
        (OpenClaw's ``typeof value === "number"``
        excludes booleans — the Python port
        mirrors that by short-circuiting on
        ``isinstance(value, bool)`` in
        :func:`parse_http_idle_timeout_ms`).
        All other types fall back to
        ``fallback``.
    fallback : int
        Default when ``value`` is not a finite
        number.
    range : dict, optional
        Inclusive bound dict
        ``{"min": int, "max": int}`` (both
        keys optional). The floored candidate
        is clamped to ``range["min"]`` (lower
        bound) and ``range["max"]`` (upper
        bound) when present.

    Returns
    -------
    int
        The floored + clamped integer.
    """
    range = range or {}
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        candidate: float = float(fallback)
    elif not math.isfinite(float(value)):
        candidate = float(fallback)
    else:
        candidate = float(value)
    floored = math.floor(candidate)
    min_bounded = (
        floored
        if range.get("min") is None
        else max(int(range["min"]), floored)
    )
    return (
        min_bounded
        if range.get("max") is None
        else min(int(range["max"]), min_bounded)
    )
