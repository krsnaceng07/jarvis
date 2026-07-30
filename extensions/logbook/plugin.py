"""Logbook infra plugin entry point — full surface port.

Mirrors OpenClaw's ``extensions/logbook/index.ts`` 1:1.
The entry point wires the SDK surface (control-UI
descriptor, service, gateway methods, node-host commands,
node-invoke policy) the same way the OpenClaw source
does, using the focused lib/ modules (config, types,
service stub, store stub, analyze stub, node-host stub,
prompts stub) that the Python port lands incrementally.

The ``LogbookService`` here is a focused in-port stub
that mirrors the OpenClaw ``service.ts`` surface. A
follow-up phase replaces the stub body with the full
``service.ts`` + ``store.ts`` + ``analyze.ts`` port.
The entry-point wiring (control-UI tab + node-invoke
policy + gateway methods + node-host commands) is
already production-shaped: every SDK registrar the
OpenClaw source calls is called with the same surface,
and the underlying service interface matches the
OpenClaw method names so the future full port drops in
without touching the entry point.

Public surface:
- ``LogbookPlugin`` — the plugin descriptor
- ``logbook_plugin`` / ``entry`` — the loaded entry point

OpenClaw parity (every OpenClaw registrar call lands
here):
- ``api.session.controls.registerControlUiDescriptor``
  for the Logbook dashboard tab
- ``api.registerNodeInvokePolicy`` to add
  ``logbook.snapshot`` to the default macOS allowlist +
  honor the screen-capture kill switch
- ``api.registerService`` to start/stop the background
  capture + analysis service
- ``api.registerGatewayMethod`` for the eight RPC
  methods the Control UI calls (status, days, timeline,
  frames, frame, standup, ask, capture.set, analyze.now)
- ``api.registerNodeHostCommand`` for the
  ``logbook.snapshot`` node-host command (lazy-imported
  from ``src/node_host``)
- ``api.pluginConfig`` flows into
  ``logbook_config.resolve_logbook_config`` to clamp
  numeric fields to safe ranges

Python adaptations (documented in code):
- TS ``LogbookService`` class → Python ``LogbookService``
  class with the same method names (status, list_days,
  cards_for_day, day_stats, frames_in_range, frame_by_id,
  standup, ask, set_capture_paused, analyze_now, start,
  stop). The bodies are stubs that return safe defaults
  so the entry point is fully loadable + testable while
  the full service port lands in a follow-up phase.
- TS ``dayKeyFor`` → Python ``datetime.date.today().isoformat()``
  in the validation helper (``read_day_param``); the
  port's day-key format is the same ``YYYY-MM-DD``.
- TS ``readFileSync(frame.path).toString("base64")`` →
  Python ``pathlib.Path(frame["path"]).read_bytes()`` +
  ``base64.b64encode(...)`` in the ``logbook.frame`` RPC
  handler.
- TS ``formatErrorMessage`` + ``errorShape`` + ``ErrorCodes``
  → Python ``LogbookError`` + ``format_error_message``
  helpers (the SDK's runtime facade is a noop in the
  port; the entry point still emits the structured
  error response shape).
"""
from __future__ import annotations

import base64
import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from jarvis_sdk import Plugin, PluginApi

from .src.logbook_config import resolve_logbook_config


# ── Day-key format + read helpers (mirrors OpenClaw) ───────


# ``YYYY-MM-DD`` in the local timezone. The Python port
# uses ``datetime.date.today().isoformat()`` (the same
# format the OpenClaw source writes from ``Date.now()``).
_DAY_PATTERN_STR = "YYYY-MM-DD"


def day_key_for(ms: int) -> str:
    """Return the ``YYYY-MM-DD`` day key for a millisecond timestamp.

    Mirrors OpenClaw's ``dayKeyFor`` (the TS source
    uses ``new Date(ms).toISOString().slice(0, 10)``,
    which is UTC; the Python port uses
    ``datetime.datetime.fromtimestamp(ms / 1000).date().isoformat()``
    which is local. The choice matches the OpenClaw
    default ``TZ=UTC`` environment for server runs and
    is safe to swap via the
    ``extensions.logbook.timezone`` pluginConfig field
    in a follow-up phase).
    """
    return datetime.datetime.fromtimestamp(ms / 1000).date().isoformat()


# ── Input validation helpers (mirrors OpenClaw) ────────────


def _read_day_param(params: Any) -> str:
    """Validate the optional ``day`` request param.

    Mirrors ``readDayParam``. Accepts ``YYYY-MM-DD`` or
    omits the field (defaults to today).
    """
    day = None
    if isinstance(params, dict):
        day = params.get("day")
    elif params is not None:
        day = getattr(params, "day", None)
    if day is None or day == "":
        return day_key_for(_now_ms())
    if not isinstance(day, str) or len(day) != 10 or day[4] != "-" or day[7] != "-":
        raise ValueError("day must be YYYY-MM-DD")
    return day


def _read_number_param(params: Any, key: str) -> int:
    """Validate a positive-number request param.

    Mirrors ``readNumberParam``. Raises ``ValueError``
    when the param is missing, non-numeric, non-finite,
    or non-positive.
    """
    value: Any = None
    if isinstance(params, dict):
        value = params.get(key)
    elif params is not None:
        value = getattr(params, key, None)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} must be a positive number")
    if value != value:  # NaN
        raise ValueError(f"{key} must be a positive number")
    if value <= 0:
        raise ValueError(f"{key} must be a positive number")
    return int(value)


def _read_string_param(params: Any, key: str) -> str:
    """Validate a required non-empty string request param.

    Mirrors the inline ``typeof question !== "string" ||
    question.trim().length === 0`` check in
    ``logbook.ask`` (TS) and the
    ``typeof params.refresh`` check in
    ``logbook.standup`` (TS).
    """
    value: Any = None
    if isinstance(params, dict):
        value = params.get(key)
    elif params is not None:
        value = getattr(params, key, None)
    if not isinstance(value, str):
        raise ValueError(f"{key} is required")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{key} is required")
    return trimmed


def _read_bool_param(params: Any, key: str) -> bool:
    """Validate an optional boolean request param.

    Mirrors the inline ``params.refresh === true`` check
    in ``logbook.standup`` (TS) and the
    ``params.paused === true`` check in
    ``logbook.capture.set`` (TS). Defaults to ``False``
    when the field is missing.
    """
    if isinstance(params, dict):
        return params.get(key) is True
    if params is None:
        return False
    return getattr(params, key, None) is True


def _now_ms() -> int:
    """Return the current Unix epoch in milliseconds."""
    import time

    return int(time.time() * 1000)


# ── LogbookService stub (mirrors OpenClaw ``service.ts``) ─


@dataclass
class LogbookService:
    """Focused in-port stub of the OpenClaw ``LogbookService``.

    Mirrors the public method names + return shapes of
    ``extensions/logbook/src/service.ts`` (status,
    list_days, cards_for_day, day_stats, frames_in_range,
    frame_by_id, standup, ask, set_capture_paused,
    analyze_now, start, stop). The bodies are minimal
    safe defaults so the entry point is loadable +
    testable while the full port lands in a follow-up
    phase; the method signatures stay identical so the
    future full port drops in without changing the
    entry point.
    """

    config: dict[str, Any] = field(default_factory=dict)
    runtime: Any = None
    full_config: Any = None
    logger: Any = None
    data_dir: str = ""

    def start(self) -> None:
        """Begin the background capture + analysis loops.

        The stub is a no-op; the full port schedules a
        capture timer + an analysis queue.
        """
        return None

    def stop(self) -> None:
        """Stop the background loops and close any handles.

        The stub is a no-op; the full port cancels the
        capture + analysis timers.
        """
        return None

    def status(self) -> dict[str, Any]:
        """Return the current capture / analysis status snapshot.

        Mirrors ``LogbookService.status``.
        """
        return {
            "running": True,
            "paused": False,
            "captureEnabled": self.config.get("captureEnabled", True),
            "captureIntervalSeconds": self.config.get("captureIntervalSeconds", 30),
            "nodeId": self.config.get("nodeId"),
            "day": day_key_for(_now_ms()),
        }

    def list_days(self) -> list[str]:
        """Return the list of days that have a captured frame.

        Mirrors ``LogbookService.listDays``. The stub
        returns an empty list (no frames yet).
        """
        return []

    def cards_for_day(self, day: str) -> list[dict[str, Any]]:
        """Return the analyzed cards for one day.

        Mirrors ``LogbookService.cardsForDay``. The stub
        returns an empty list.
        """
        return []

    def day_stats(self, day: str) -> dict[str, Any]:
        """Return the per-day stats rollup.

        Mirrors ``LogbookService.dayStats``.
        """
        return {
            "trackedMs": 0,
            "distractionMs": 0,
            "categories": [],
            "apps": [],
        }

    def frames_in_range(self, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
        """Return the captured frames in ``[start_ms, end_ms]``.

        Mirrors ``LogbookService.framesInRange``.
        """
        return []

    def frame_by_id(self, frame_id: int) -> Optional[dict[str, Any]]:
        """Return a single frame by id.

        Mirrors ``LogbookService.frameById``. The stub
        returns ``None``.
        """
        return None

    def standup(self, day: str, refresh: bool) -> dict[str, Any]:
        """Return a standup summary for the day.

        Mirrors ``LogbookService.standup``.
        """
        return {
            "day": day,
            "summary": "",
            "cards": self.cards_for_day(day),
        }

    def ask(self, day: str, question: str) -> dict[str, Any]:
        """Answer a free-form question about the day.

        Mirrors ``LogbookService.ask``. The stub returns
        a structured "not yet ported" answer so the
        Control UI surfaces the placeholder cleanly.
        """
        return {
            "day": day,
            "question": question,
            "answer": "Logbook ask is not yet ported in this JARVIS build.",
        }

    def set_capture_paused(self, paused: bool) -> None:
        """Pause / resume the capture loop.

        Mirrors ``LogbookService.setCapturePaused``.
        """
        return None

    def analyze_now(self) -> dict[str, Any]:
        """Trigger an analysis pass immediately.

        Mirrors ``LogbookService.analyzeNow``.
        """
        return {"triggered": True}


# ── Error shape helpers (mirrors OpenClaw SDK runtime) ─────


_LOGBOOK_ERROR_CODES = {
    "UNAVAILABLE": "UNAVAILABLE",
    "INVALID_ARGUMENT": "INVALID_ARGUMENT",
    "NOT_FOUND": "NOT_FOUND",
}


def _format_error_message(err: Any) -> str:
    """Format an exception into a single-line message.

    Mirrors ``formatErrorMessage`` from
    ``openclaw/plugin-sdk/error-runtime``.
    """
    if isinstance(err, BaseException):
        message = str(err) or type(err).__name__
        return f"{type(err).__name__}: {message}"
    return str(err)


def _logbook_error_shape(code: str, message: str) -> dict[str, Any]:
    """Build the typed error response envelope.

    Mirrors ``errorShape(ErrorCodes.X, message)``. The
    Python port returns a dict the gateway can route
    to the Control UI as a typed error response.
    """
    return {"code": code, "message": message}


# ── Entry point ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LogbookPlugin(Plugin):
    """Logbook infra descriptor (entry point).

    Mirrors OpenClaw's ``LogbookPlugin`` declared via
    ``definePluginEntry({ id, name, description, ...,
    register(api) })``. The Python port subclasses
    ``Plugin`` and implements ``register(api)`` to call
    the same SDK registrars the OpenClaw source calls
    with the same payloads.
    """

    id: str = "logbook"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Automatic work journal with screen snapshots."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub — the real init runs in ``register``. """
        return None

    def register(self, api: PluginApi) -> None:
        """Register the Logbook surface with the host.

        Mirrors ``register(api)`` in
        ``extensions/logbook/index.ts``. The Python
        port calls the same SDK registrars the OpenClaw
        source calls, in the same order, with the same
        payloads; the only Python-specific adaptations
        are documented in the module docstring.
        """
        config = resolve_logbook_config(api.plugin_config)
        service_holder: list[Optional[LogbookService]] = [None]

        def _require_service() -> LogbookService:
            if service_holder[0] is None:
                raise RuntimeError("Logbook service is not running")
            return service_holder[0]

        def _send_error(
            respond: Callable[[bool, Any, Any], None],
            err: Any,
        ) -> None:
            """Send a typed error response to the gateway.

            Mirrors ``sendError`` from the OpenClaw
            entry point. The Python port uses a callable
            ``respond`` (the gateway request handler
            passes one in) instead of the
            ``GatewayRequestHandlerOptions.respond``
            object.
            """
            message = _format_error_message(err)
            respond(
                False,
                {"error": message},
                _logbook_error_shape(_LOGBOOK_ERROR_CODES["UNAVAILABLE"], message),
            )

        def _handle(
            run: Callable[[Any], Any],
        ) -> Callable[[Any], Any]:
            """Wrap a method body in the standard try/except.

            Mirrors the ``handle`` closure in the OpenClaw
            entry point. The Python port accepts a dict
            ``{"respond": callable, "params": any}``
            payload (matches the gateway request handler
            contract).
            """

            def _wrapped(payload: Any) -> None:
                respond = (
                    payload.get("respond")
                    if isinstance(payload, dict)
                    else getattr(payload, "respond", None)
                )
                params = (
                    payload.get("params")
                    if isinstance(payload, dict)
                    else getattr(payload, "params", None)
                )
                try:
                    respond(True, run(params))
                except Exception as err:  # noqa: BLE001
                    _send_error(respond, err)

            return _wrapped

        # ── Control UI descriptor (the Logbook dashboard tab) ─
        #
        # Mirrors ``api.session.controls.registerControlUiDescriptor``
        # in the OpenClaw entry point. The descriptor is
        # registered even when the service hasn't started
        # yet so the Control UI can render the tab.
        if hasattr(api, "session") and hasattr(api.session, "controls"):
            api.session.controls.register_control_ui_descriptor(
                {
                    "surface": "tab",
                    "id": "logbook",
                    "label": "Logbook",
                    "description": "Your day as a timeline, built from screen snapshots.",
                    "icon": "sun",
                    "group": "control",
                    "requiredScopes": ["operator.write"],
                }
            )

        # ── Node-invoke policy (macOS allowlist + screen-capture
        # ── kill switch) ─
        #
        # Mirrors ``api.registerNodeInvokePolicy`` in the
        # OpenClaw entry point. The handler honors the
        # operator's screen-capture kill switch (a
        # ``screen.snapshot`` deny must block this
        # capture command too, not just the app node's).
        api.register_node_invoke_policy(
            {
                "commands": ["logbook.snapshot"],
                "defaultPlatforms": ["macos"],
                "handle": lambda ctx: _handle_logbook_node_invoke(ctx),
            }
        )

        # ── Background service (start/stop) ─
        #
        # Mirrors ``api.registerService``. The Python
        # port keeps the service handle in a single-slot
        # holder (``service_holder``) so the gateway
        # methods can require it without a global.
        def _start_service(start_ctx: Any) -> None:
            service_holder[0] = LogbookService(
                config=config,
                runtime=getattr(api, "runtime", None),
                full_config=getattr(start_ctx, "config", None),
                logger=getattr(start_ctx, "logger", None),
                data_dir=str(getattr(start_ctx, "state_dir", "") or "") + "/logbook",
            )
            service_holder[0].start()

        def _stop_service(_stop_ctx: Any) -> None:
            if service_holder[0] is not None:
                service_holder[0].stop()
                service_holder[0] = None

        api.register_service(
            {
                "id": "logbook",
                "start": _start_service,
                "stop": _stop_service,
            }
        )

        # ── Gateway methods (the eight RPCs the Control UI
        # ── calls) ─
        #
        # Mirrors the eight ``api.registerGatewayMethod`` calls
        # in the OpenClaw entry point. The Python port routes
        # them through ``_handle`` so the typed error
        # response shape is uniform.
        def _register_read(method: str, run: Callable[[Any], Any]) -> None:
            api.register_gateway_method(
                method, _handle(run), {"scope": "operator.read"}
            )

        def _register_write(method: str, run: Callable[[Any], Any]) -> None:
            api.register_gateway_method(
                method, _handle(run), {"scope": "operator.write"}
            )

        _register_read("logbook.status", lambda _params: _require_service().status())
        _register_read(
            "logbook.days", lambda _params: {"days": _require_service().list_days()}
        )

        def _timeline(params: Any) -> dict[str, Any]:
            day = _read_day_param(params)
            svc = _require_service()
            return {"day": day, "cards": svc.cards_for_day(day), "stats": svc.day_stats(day)}

        _register_read("logbook.timeline", _timeline)

        def _frames(params: Any) -> dict[str, Any]:
            start_ms = _read_number_param(params, "startMs")
            end_ms = _read_number_param(params, "endMs")
            frames = _require_service().frames_in_range(start_ms, end_ms)
            return {
                "frames": [
                    {"id": f["id"], "capturedAtMs": f["capturedAtMs"], "idle": f.get("idle", False)}
                    for f in frames
                ]
            }

        _register_write("logbook.frames", _frames)

        def _frame(params: Any) -> dict[str, Any]:
            frame_id = _read_number_param(params, "frameId")
            frame = _require_service().frame_by_id(frame_id)
            if frame is None:
                raise ValueError(f"frame {frame_id} not found")
            frame_path = frame.get("path")
            if not frame_path:
                raise ValueError(f"frame {frame_id} has no path")
            binary = Path(frame_path).read_bytes()
            return {
                "frameId": frame["id"],
                "capturedAtMs": frame["capturedAtMs"],
                "width": frame.get("width", 0),
                "height": frame.get("height", 0),
                "format": "jpeg",
                "base64": base64.b64encode(binary).decode("ascii"),
            }

        _register_write("logbook.frame", _frame)

        def _standup(params: Any) -> dict[str, Any]:
            refresh = _read_bool_param(params, "refresh")
            return _require_service().standup(_read_day_param(params), refresh)

        _register_write("logbook.standup", _standup)

        async def _ask(params: Any) -> dict[str, Any]:
            question = _read_string_param(params, "question")
            return _require_service().ask(_read_day_param(params), question)

        _register_write("logbook.ask", _ask)

        def _capture_set(params: Any) -> dict[str, Any]:
            paused = _read_bool_param(params, "paused")
            svc = _require_service()
            svc.set_capture_paused(paused)
            return svc.status()

        _register_write("logbook.capture.set", _capture_set)

        _register_write(
            "logbook.analyze.now", lambda _params: _require_service().analyze_now()
        )

        # ── Node-host command (lazy-imported) ─
        #
        # Mirrors ``logbookNodeHostCommands`` in the
        # OpenClaw entry point. The Python port defers the
        # import of the node-host module until the host
        # actually invokes the command (matches the
        # ``await import(...)`` lazy pattern in the TS
        # source).
        if hasattr(api, "register_node_host_command"):
            api.register_node_host_command(
                {
                    "command": "logbook.snapshot",
                    "cap": "screen",
                    "dangerous": False,
                    "handle": _handle_logbook_snapshot,
                }
            )

    def node_host_commands(self) -> list[dict[str, Any]]:
        """Return the node-host command list (for the manifest).

        Mirrors ``logbookNodeHostCommands`` in the
        OpenClaw entry point. The Python port exposes the
        same shape so the host can install the commands
        via the manifest contract even when the entry
        point's ``register`` hasn't run yet.
        """
        return [
            {
                "command": "logbook.snapshot",
                "cap": "screen",
                "dangerous": False,
                "handle": _handle_logbook_snapshot,
            }
        ]


# ── Node-invoke policy + node-host command handlers ───────


def _handle_logbook_node_invoke(ctx: Any) -> dict[str, Any]:
    """Honor the screen-capture kill switch then call ``ctx.invokeNode()``.

    Mirrors the inline ``handle`` in
    ``api.registerNodeInvokePolicy`` from the OpenClaw
    entry point. The Python port accepts a dict-style
    context with ``config`` + ``invokeNode`` (matches
    the SDK's runtime facade).
    """
    if isinstance(ctx, dict):
        config = ctx.get("config")
        invoke = ctx.get("invokeNode")
        if config is None or not callable(invoke):
            return {"ok": True}
        denied = (config.get("gateway", {}) or {}).get("nodes", {}).get("denyCommands", []) if isinstance(config, dict) else []
        if isinstance(denied, list) and "screen.snapshot" in denied:
            return {
                "ok": False,
                "code": "SCREEN_CAPTURE_DENIED",
                "message": (
                    "screen capture is denied by gateway.nodes.denyCommands "
                    "(screen.snapshot); Logbook capture stays blocked until it is removed"
                ),
            }
        return invoke() or {"ok": True}
    return {"ok": True}


def _handle_logbook_snapshot(params_json: str) -> str:
    """Lazy node-host command handler.

    Mirrors ``logbook.snapshot`` in the OpenClaw entry
    point. The Python port accepts a JSON-encoded
    ``params`` string (the node-host command contract)
    and returns a JSON-encoded result. The stub returns
    a structured "not yet ported" envelope so the host
    can route the response to the gateway without
    surfacing an exception.
    """
    params: Any = None
    if params_json:
        try:
            params = json.loads(params_json)
        except (TypeError, ValueError):
            params = None
    # The full port lazy-imports ``./src/node_host`` and
    # delegates to ``handleLogbookSnapshot(params)``. The
    # in-port stub returns a structured envelope so the
    # gateway + Control UI surfaces the placeholder
    # cleanly.
    return json.dumps(
        {
            "ok": False,
            "code": "NOT_PORTED",
            "message": "Logbook snapshot is not yet ported in this JARVIS build.",
            "params": params,
        }
    )


logbook_plugin = LogbookPlugin()
entry = logbook_plugin
