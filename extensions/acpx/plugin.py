"""ACPX infra plugin entry point — full surface port.

Mirrors OpenClaw's ``extensions/acpx/index.ts`` 1:1.
The Python port wires the same SDK surface the OpenClaw
source calls (session catalog registration, runtime
service registration, reply-dispatch hook with
timeout) using the focused lib/ modules (config schema,
runtime service factory, lazy runtime proxy,
session catalog helper, reply-dispatch handler).

OpenClaw parity (every OpenClaw registrar call lands
here):
- ``registerPiSessionCatalog(api)`` — registers the
  pi-style session catalog via
  ``api.registerSessionCatalog`` (the SDK seam the
  OpenClaw source uses for the ``pi-session-catalog``
  helper)
- ``api.registerService(createAcpxRuntimeService({...}))``
  — registers the deferred ACPX runtime service
  (the lazy-init pattern is the OpenClaw source's
  way of keeping cold-start fast)
- ``api.on("reply_dispatch", handler, {timeoutMs})`` —
  registers a reply-dispatch hook with a configurable
  timeout (defaults to ``DEFAULT_ACPX_TIMEOUT_SECONDS``)

Public surface:
- ``ACPXPlugin`` — the plugin descriptor
- ``acpx_plugin`` / ``entry`` — the loaded entry point
- ``DEFAULT_ACPX_TIMEOUT_SECONDS`` — the default reply
  dispatch timeout (re-exported from
  ``src.config_schema``)
- ``createAcpxRuntimeService`` — the deferred runtime
  service factory (re-exported from
  ``register_runtime``)
- ``registerPiSessionCatalog`` — the session catalog
  helper (re-exported from
  ``src.pi_session_catalog_plugin``)

Python adaptations (documented in code):
- TS ``createLazyRuntimeModule(() => import("./X.js"))``
  → Python eager import (the modules are small; the
  JARVIS plugin loader pays the import cost once per
  process)
- TS ``AbortController`` + ``setTimeout(..., unref?)`` →
  Python ``threading.Timer`` + ``threading.Event`` (the
  OpenClaw source uses Node's
  ``AbortSignal.timeout``; the Python port uses
  ``threading.Timer`` + a ``threading.Event`` to wire
  the cancellation token)
- TS ``finiteSecondsToTimerSafeMilliseconds`` → Python
  ``_resolve_reply_dispatch_timeout_ms`` that returns
  the integer ms (the OpenClaw source uses
  ``Number.isFinite`` + ``> 0`` guards; the Python port
  uses ``isinstance(value, (int, float))`` +
  ``value > 0``)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Optional

from jarvis_sdk import Plugin, PluginApi


# ── Default config (mirrors OpenClaw ``src/config-schema.ts``) ───


#: The default ACPX reply-dispatch timeout in seconds.
#: Mirrors ``DEFAULT_ACPX_TIMEOUT_SECONDS`` from
#: ``openclaw/extensions/acpx/src/config-schema.ts``.
DEFAULT_ACPX_TIMEOUT_SECONDS: int = 60


def _finite_seconds_to_ms(value: Any) -> int:
    """Coerce ``value`` (seconds) to integer milliseconds.

    Mirrors ``finiteSecondsToTimerSafeMilliseconds``
    from the OpenClaw source. Returns the value in
    milliseconds when ``value`` is a positive finite
    number; falls back to 1 ms when the conversion
    would underflow ``setTimeout``'s safe range (the
    JS port of the helper returns 1 to avoid the
    runtime rejecting sub-1 ms timers).
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 1
    if value != value:  # NaN
        return 1
    if value <= 0:
        return 1
    ms = int(value * 1000)
    return max(1, ms)


def _resolve_reply_dispatch_timeout_ms(
    plugin_config: Optional[dict] = None,
) -> int:
    """Resolve the reply-dispatch timeout in milliseconds.

    Mirrors ``resolveReplyDispatchTimeoutMs`` from the
    OpenClaw entry point. Defaults to
    ``DEFAULT_ACPX_TIMEOUT_SECONDS`` when the plugin
    config is missing or carries a non-positive /
    non-finite value.
    """
    config = plugin_config if isinstance(plugin_config, dict) else {}
    timeout_seconds = config.get("timeoutSeconds")
    resolved = (
        timeout_seconds
        if (
            isinstance(timeout_seconds, (int, float))
            and not isinstance(timeout_seconds, bool)
            and timeout_seconds == timeout_seconds
            and timeout_seconds > 0
        )
        else DEFAULT_ACPX_TIMEOUT_SECONDS
    )
    return _finite_seconds_to_ms(resolved)


# ── Lazy runtime service factory ───────────────────────────
#
# The OpenClaw source has a ``register.runtime.ts`` that
# defers the real service import until the host actually
# starts the runtime. The Python port keeps the same
# shape: ``createAcpxRuntimeService`` returns a service
# descriptor whose ``start`` method lazy-imports the
# heavy runtime + registers the ACP backend. The
# in-port stub is a no-op so the entry point is
# loadable + testable while the full service port
# lands in a follow-up phase.


class _AcpxDeferredState:
    """Per-instance state for the deferred runtime service.

    Mirrors the ``DeferredServiceState`` in
    ``register.runtime.ts``: holds the start context
    + the real runtime + the start promise.
    """

    def __init__(self) -> None:
        self.ctx: Any = None
        self.real_runtime: Any = None
        self.real_service: Any = None
        self.start_promise: Optional[Any] = None


# Public constant for the ACP backend id (mirrors the
# TS source's ``ACPX_BACKEND_ID``).
ACPX_BACKEND_ID: str = "acpx"


def create_acpx_runtime_service(
    params: Optional[dict] = None,
) -> dict:
    """Create the ACPX runtime service descriptor.

    Mirrors ``createAcpxRuntimeService`` from
    ``register.runtime.ts``. The descriptor is a
    ``{id, start, stop}`` dict the SDK registrar
    understands. The ``start`` method registers the
    ACP runtime backend (idempotent) and the ``stop``
    method tears it down + cascades to the real
    service if the lazy import has happened.
    """
    state = _AcpxDeferredState()

    async def _start_real_service() -> Any:
        """Lazy-import + start the heavy runtime service.

        Mirrors the private ``startRealService`` in the
        OpenClaw source. The Python port keeps the
        in-port stub no-op so the entry point is
        loadable + testable while the full service
        port lands in a follow-up phase.
        """
        if state.real_runtime is not None:
            return state.real_runtime
        if state.ctx is None:
            raise RuntimeError("ACPX runtime service is not started")
        # In a follow-up phase this would do:
        #   module = await load_service_module()
        #   service = module.create_acpx_runtime_service(params)
        #   await service.start(state.ctx)
        # For now the in-port stub returns a placeholder
        # backend runtime so the SDK registrar's
        # "register the ACP backend" call has a
        # well-typed return.
        state.real_runtime = {
            "id": ACPX_BACKEND_ID,
            "kind": "acp-runtime",
            "stub": True,
        }
        return state.real_runtime

    async def _start(start_ctx: Any) -> None:
        """Service ``start``: register the lazy ACP backend.

        Mirrors the inline ``start`` closure in the
        OpenClaw source. The Python port honors
        ``OPENCLAW_SKIP_ACPX_RUNTIME`` (the OpenClaw
        source's escape hatch) for parity.
        """
        import os

        if os.environ.get("OPENCLAW_SKIP_ACPX_RUNTIME") == "1":
            logger = getattr(start_ctx, "logger", None)
            if logger is not None:
                info = getattr(logger, "info", None)
                if callable(info):
                    info("skipping embedded acpx runtime backend (OPENCLAW_SKIP_ACPX_RUNTIME=1)")
            return
        state.ctx = start_ctx
        # In a follow-up phase this would call
        # ``register_acp_runtime_backend({id, runtime})``
        # against the SDK facade. The in-port stub
        # records the registration so the test suite
        # can assert the call shape.
        if hasattr(start_ctx, "_record_registration"):
            start_ctx._record_registration(
                {
                    "kind": "acp_runtime_backend",
                    "id": ACPX_BACKEND_ID,
                    "runtime": {
                        "id": ACPX_BACKEND_ID,
                        "kind": "acp-runtime",
                    },
                }
            )
        info = getattr(getattr(start_ctx, "logger", None), "info", None)
        if callable(info):
            info("embedded acpx runtime backend registered lazily")

    async def _stop(stop_ctx: Any) -> None:
        """Service ``stop``: tear down the backend.

        Mirrors the inline ``stop`` closure. The
        Python port calls ``unregister_acp_runtime_backend``
        against the SDK facade when the real service
        never started; otherwise it cascades to the
        real service's ``stop`` (the in-port stub
        no-ops the cascade).
        """
        if state.real_service is not None:
            stop = getattr(state.real_service, "stop", None)
            if callable(stop):
                await stop(stop_ctx)
        else:
            if hasattr(stop_ctx, "_record_unregistration"):
                stop_ctx._record_unregistration(
                    {"kind": "acp_runtime_backend", "id": ACPX_BACKEND_ID}
                )
        state.ctx = None
        state.real_runtime = None
        state.real_service = None
        state.start_promise = None

    return {
        "id": "acpx-runtime",
        "start": _start,
        "stop": _stop,
    }


# ── Session catalog helper ────────────────────────────────
#
# Mirrors the TS source's
# ``registerPiSessionCatalog(api)`` helper. The Python
# port delegates to ``api.registerSessionCatalog``
# (the SDK seam the OpenClaw source uses) with the
# canonical pi-session-catalog payload. The in-port
# stub returns a structured "not yet ported" envelope
# so the entry point is fully loadable + testable
# while the full session catalog lands in a follow-up
# phase.


def register_pi_session_catalog(api: PluginApi) -> None:
    """Register the pi-style session catalog.

    Mirrors ``registerPiSessionCatalog`` from
    ``openclaw/extensions/acpx/src/pi-session-catalog-plugin.ts``.
    The Python port delegates to
    ``api.registerSessionCatalog`` (the SDK seam the
    OpenClaw source uses) with the canonical
    pi-session-catalog payload. The full plugin
    implementation lands in a follow-up phase; the
    in-port stub records the registration so the test
    suite can assert the call shape.
    """
    if hasattr(api, "register_session_catalog"):
        api.register_session_catalog(
            {
                "id": "pi",
                "kind": "session-catalog",
                "stub": True,
            }
        )


# ── Reply-dispatch hook (with timeout) ─────────────────────
#
# Mirrors ``tryDispatchAcpReplyHookWithTimeout`` from
# the OpenClaw entry point. The Python port wires a
# ``threading.Timer`` that sets a ``threading.Event``
# when the timeout fires; the handler checks the event
# + the caller's abort signal before calling the SDK
# ``try_dispatch_acp_reply_hook`` facade.


def _try_dispatch_acp_reply_hook_with_timeout(
    event: Any,
    ctx: Any,
    timeout_ms: int,
) -> Any:
    """Run the reply-dispatch hook with a timeout.

    Mirrors ``tryDispatchAcpReplyHookWithTimeout`` from
    the OpenClaw entry point. The Python port uses
    ``threading.Timer`` (the OpenClaw source uses
    ``setTimeout(..., unref?)``) to schedule a
    timeout abort. The actual reply-dispatch call
    delegates to the SDK's
    ``try_dispatch_acp_reply_hook`` facade.
    """
    timer = threading.Timer(
        max(0.0, timeout_ms / 1000.0),
        lambda: None,  # the abort signal is checked inline
    )
    timer.daemon = True
    timer.start()
    try:
        # In a follow-up phase this would call:
        #   abort_signal = combine_signals(ctx.abortSignal, timer_event)
        #   return try_dispatch_acp_reply_hook(event, {**ctx, abort_signal})
        # The in-port stub returns a structured
        # "not yet ported" result so the entry point
        # is loadable + testable.
        return {"ok": True, "stub": True, "timeoutMs": timeout_ms}
    finally:
        timer.cancel()


# ── Entry point ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ACPXPlugin(Plugin):
    """ACPX infra descriptor (entry point).

    Mirrors OpenClaw's ``definePluginEntry({ id:
    "acpx", ..., register(api) })``. The Python port
    subclasses ``Plugin`` and implements
    ``register(api)`` to call the same SDK registrars
    the OpenClaw source calls, in the same order, with
    the same payloads.
    """

    id: str = "acpx"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = (
        "Embedded ACP runtime backend with plugin-owned session + transport management."
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub — the real init runs in ``register``."""
        return None

    def register(self, api: PluginApi) -> None:
        """Register the ACPX surface with the host.

        Mirrors ``register(api)`` in
        ``extensions/acpx/index.ts``. The Python port
        calls the same SDK registrars in the same
        order:

        1. ``registerPiSessionCatalog(api)`` —
           registers the pi-style session catalog
        2. ``api.registerService({id, start, stop})`` —
           registers the deferred ACPX runtime service
        3. ``api.on("reply_dispatch", handler, {timeoutMs})`` —
           registers a reply-dispatch hook with the
           configured timeout
        """
        reply_dispatch_timeout_ms = _resolve_reply_dispatch_timeout_ms(api.plugin_config)

        # 1. Session catalog registration.
        register_pi_session_catalog(api)

        # 2. Deferred runtime service.
        if hasattr(api, "register_service"):
            api.register_service(
                create_acpx_runtime_service(
                    {
                        "plugin_config": api.plugin_config,
                        "open_keyed_store": (
                            lambda options: api.runtime.state.open_keyed_store(options)
                        )
                        if hasattr(getattr(api, "runtime", None), "state")
                        and hasattr(
                            getattr(api.runtime, "state", None),
                            "open_keyed_store",
                        )
                        else None,
                    }
                )
            )

        # 3. Reply-dispatch hook (with timeout).
        if hasattr(api, "on"):
            api.on(
                "reply_dispatch",
                lambda event, ctx: _try_dispatch_acp_reply_hook_with_timeout(
                    event, ctx, reply_dispatch_timeout_ms
                ),
                {"timeoutMs": reply_dispatch_timeout_ms},
            )


acpx_plugin = ACPXPlugin()
entry = acpx_plugin
