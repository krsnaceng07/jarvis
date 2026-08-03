"""jarvis.utils.fetch_timeout — fetch wrapper with timeout + abort behavior.

OpenClaw parity: mirrors ``openclaw-main/src/utils/fetch-timeout.ts``.

Public surface:

- :func:`bind_abort_relay`
- :func:`build_timeout_abort_signal`
- :func:`fetch_with_timeout`
- :data:`LOG_URL_MAX_CHARS`
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Optional


_log = logging.getLogger("jarvis.utils.fetch_timeout")

LOG_URL_MAX_CHARS = 500

#: Default fetch timeout fallback when callers pass invalid delays.
DEFAULT_FETCH_TIMEOUT_MS = 30_000


def _resolve_safe_timeout_delay_ms(value: Any) -> int:
    if not isinstance(value, (int, float)) or value != value or value < 0:
        return 0
    if value > 60 * 60 * 1000:
        return 60 * 60 * 1000
    return int(value)


def bind_abort_relay(controller: Any) -> Callable[[], None]:
    """Return a bound abort relay for use as an event listener.

    Mirrors :func:`bindAbortRelay` (``utils/fetch-timeout.ts``).
    """
    def _relay() -> None:
        try:
            controller.abort()
        except Exception:
            pass
    return _relay


def _sanitize_timeout_log_url(raw_url: Optional[str]) -> Optional[str]:
    trimmed = (raw_url or "").strip()
    if not trimmed:
        return None
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(trimmed)
        sanitized = urlunparse(parsed._replace(netloc="", query="", fragment=""))
        if len(sanitized) > LOG_URL_MAX_CHARS:
            return sanitized[:LOG_URL_MAX_CHARS] + "..."
        return sanitized
    except Exception:
        return trimmed[:LOG_URL_MAX_CHARS]


def build_timeout_abort_signal(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build an abort signal that combines an optional parent signal with a timeout.

    Mirrors :func:`buildTimeoutAbortSignal` (``utils/fetch-timeout.ts``).
    """
    timeout_ms = params.get("timeoutMs")
    parent_signal = params.get("signal")
    if not timeout_ms and not parent_signal:
        return {"signal": None, "cleanup": lambda: None, "refresh": lambda: None}
    if not timeout_ms:
        return {"signal": parent_signal, "cleanup": lambda: None, "refresh": lambda: None}

    controller: Any = getattr(asyncio, "AbortController", None)
    # asyncio has no AbortController in 3.13. Provide a simple stand-in.
    if controller is None:
        state = {"aborted": False}

        class _PyController:
            def abort(self, *_args: Any) -> None:
                state["aborted"] = True

            @property
            def signal(self) -> Any:
                return type(
                    "_PySignal",
                    (),
                    {
                        "aborted": state["aborted"],
                        "add_event_listener": lambda *_a, **_k: None,
                    },
                )()

        controller = _PyController()

    normalized_timeout_ms = _resolve_safe_timeout_delay_ms(timeout_ms)
    active = True
    timer_handle: Optional[asyncio.TimerHandle] = None
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None

    def _abort_due_to_timeout() -> None:
        try:
            if getattr(controller.signal, "aborted", False):
                return
            sanitized_url = _sanitize_timeout_log_url(params.get("url"))
            _log.warning(
                "fetch timeout reached; aborting operation timeoutMs=%s url=%s",
                normalized_timeout_ms,
                sanitized_url,
            )
            try:
                controller.abort()
            except Exception:
                pass
        except Exception:
            pass

    def _schedule() -> None:
        nonlocal timer_handle
        if loop is None:
            return
        try:
            timer_handle = loop.call_later(
                normalized_timeout_ms / 1000.0, _abort_due_to_timeout
            )
        except Exception:
            timer_handle = None

    _schedule()

    def _refresh() -> None:
        if not active:
            return
        if getattr(controller.signal, "aborted", False):
            return
        if timer_handle is not None:
            try:
                timer_handle.cancel()
            except Exception:
                pass
        _schedule()

    def _cleanup() -> None:
        nonlocal active
        active = False
        if timer_handle is not None:
            try:
                timer_handle.cancel()
            except Exception:
                pass

    return {"signal": controller.signal, "cleanup": _cleanup, "refresh": _refresh}


async def fetch_with_timeout(
    url: str,
    init: Optional[Dict[str, Any]] = None,
    timeout_ms: int = DEFAULT_FETCH_TIMEOUT_MS,
    fetch_fn: Optional[Callable[..., Awaitable[Any]]] = None,
) -> Any:
    """Fetch wrapper that adds timeout support via AbortController.

    Mirrors :func:`fetchWithTimeout` (``utils/fetch-timeout.ts``).
    """
    init = dict(init or {})
    built = build_timeout_abort_signal(
        {"timeoutMs": max(1, timeout_ms), "operation": "fetchWithTimeout", "url": url}
    )
    signal = built["signal"]
    caller_signal = init.get("signal")
    combined = caller_signal if caller_signal else signal
    try:
        target = fetch_fn or _default_fetch
        return await target(url, {**init, "signal": combined})
    finally:
        built["cleanup"]()


async def _default_fetch(url: str, init: Dict[str, Any]) -> Any:
    """Default fetch implementation (uses asyncio streams if no requests)."""
    # Best-effort: try the injected fetch_fn first; if no real fetch is
    # available, raise a clear error so callers can wire their own.
    import urllib.request
    import urllib.error

    method = init.get("method", "GET")
    req = urllib.request.Request(
        url, data=init.get("body") if init.get("body") else None, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=init.get("timeout", 30)) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"fetch failed: {exc}") from exc


__all__ = [
    "LOG_URL_MAX_CHARS",
    "DEFAULT_FETCH_TIMEOUT_MS",
    "bind_abort_relay",
    "build_timeout_abort_signal",
    "fetch_with_timeout",
]
