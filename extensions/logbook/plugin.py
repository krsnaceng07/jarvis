"""Logbook infra plugin entry point.

Mirrors OpenClaw's ``extensions/logbook/index.ts`` 1:1.
The entry point wires the SDK surface (control-UI descriptor, service,
gateway methods, node-host commands, node-invoke policy).
"""

from __future__ import annotations

import base64
import inspect
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import sys
import time
from typing import Any, Callable, Optional

from jarvis_sdk import Plugin, PluginApi

from .src.logbook_config import resolve_logbook_config
from .src.service import LogbookService
from .src.store import day_key_for


# ── Day-key format + read helpers (mirrors OpenClaw) ───────

_DAY_PATTERN_STR = "YYYY-MM-DD"


def _now_ms() -> int:
    """Return current Unix epoch in milliseconds."""
    return int(time.time() * 1000)


def _read_day_param(params: Any) -> str:
    """Validate the optional ``day`` request param.

    Mirrors OpenClaw's ``readDayParam``. Accepts ``YYYY-MM-DD`` or
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

    Mirrors OpenClaw's ``readNumberParam``.
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
    """Validate a required non-empty string request param."""
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
    """Validate an optional boolean request param."""
    if isinstance(params, dict):
        return params.get(key) is True
    if params is None:
        return False
    return getattr(params, key, None) is True


# ── Error shape helpers (mirrors OpenClaw SDK runtime) ─────

_LOGBOOK_ERROR_CODES = {
    "UNAVAILABLE": "UNAVAILABLE",
    "INVALID_ARGUMENT": "INVALID_ARGUMENT",
    "NOT_FOUND": "NOT_FOUND",
}


def _format_error_message(err: Any) -> str:
    """Format an exception into a single-line message."""
    if isinstance(err, BaseException):
        message = str(err) or type(err).__name__
        return f"{type(err).__name__}: {message}"
    return str(err)


def _logbook_error_shape(code: str, message: str) -> dict[str, Any]:
    """Build the typed error response envelope."""
    return {"code": code, "message": message}


# ── Entry point ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LogbookPlugin(Plugin):
    """Logbook infra descriptor (entry point).

    Mirrors OpenClaw's ``LogbookPlugin``.
    """

    id: str = "logbook"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Automatic work journal with screen snapshots."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook."""
        return None

    def register(self, api: PluginApi) -> None:
        """Register the Logbook surface with the host.

        Mirrors ``register(api)`` in ``extensions/logbook/index.ts``.
        """
        raw_config = getattr(api, "pluginConfig", getattr(api, "plugin_config", {}))
        config = resolve_logbook_config(raw_config)
        service_holder: list[Optional[LogbookService]] = [None]
        retired_holder: list[bool] = [False]

        def _require_service() -> LogbookService:
            if service_holder[0] is None:
                raise RuntimeError("Logbook service is not running")
            return service_holder[0]

        def _send_error(
            respond: Callable[..., Any],
            err: Any,
        ) -> None:
            message = _format_error_message(err)
            respond(
                False,
                {"error": message},
                _logbook_error_shape(_LOGBOOK_ERROR_CODES["UNAVAILABLE"], message),
            )

        def _handle(run: Callable[[Any], Any]) -> Callable[[Any], Any]:
            async def _wrapped(payload: Any) -> None:
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
                    res = run(params)
                    if inspect.isawaitable(res):
                        res = await res
                    if callable(respond):
                        respond(True, res)
                except Exception as err:
                    if callable(respond):
                        _send_error(respond, err)

            return _wrapped

        # ── Control UI descriptor (the Logbook dashboard tab) ─
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

        # ── Node-invoke policy ───────────────────────────────
        api.register_node_invoke_policy(
            {
                "commands": ["logbook.snapshot"],
                "defaultPlatforms": ["macos"],
                "handle": lambda ctx: _handle_logbook_node_invoke(ctx),
            }
        )

        # ── Background service (start/stop) ──────────────────
        def _start_service(start_ctx: Any) -> None:
            if retired_holder[0]:
                raise RuntimeError("Logbook plugin runtime has been retired")
            state_dir = getattr(start_ctx, "state_dir", getattr(start_ctx, "stateDir", ""))
            data_dir = os.path.join(str(state_dir or ""), "logbook") if state_dir else "logbook"
            service_holder[0] = LogbookService(
                config=config,
                deps={
                    "runtime": getattr(api, "runtime", None),
                    "fullConfig": getattr(start_ctx, "config", getattr(start_ctx, "fullConfig", {})),
                    "logger": getattr(start_ctx, "logger", None),
                    "dataDir": data_dir,
                },
            )
            service_holder[0].start()

        def _stop_service(_stop_ctx: Any = None) -> Any:
            current = service_holder[0]
            service_holder[0] = None
            if current is not None:
                return current.stop()
            return None

        api.register_service(
            {
                "id": "logbook",
                "start": _start_service,
                "stop": _stop_service,
            }
        )

        # ── Runtime lifecycle ────────────────────────────────
        if hasattr(api, "lifecycle") and hasattr(api.lifecycle, "register_runtime_lifecycle"):
            def _cleanup(lifecycle_ctx: Any) -> Any:
                reason = lifecycle_ctx.get("reason") if isinstance(lifecycle_ctx, dict) else getattr(lifecycle_ctx, "reason", None)
                session_key = lifecycle_ctx.get("sessionKey") if isinstance(lifecycle_ctx, dict) else getattr(lifecycle_ctx, "sessionKey", None)
                run_id = lifecycle_ctx.get("runId") if isinstance(lifecycle_ctx, dict) else getattr(lifecycle_ctx, "runId", None)
                if session_key is None and run_id is None and reason in ("restart", "disable"):
                    retired_holder[0] = True
                    return _stop_service()
                return None

            api.lifecycle.register_runtime_lifecycle(
                {
                    "id": "logbook-service",
                    "cleanup": _cleanup,
                }
            )

        # ── Gateway methods ──────────────────────────────────
        def _register_read(method: str, run: Callable[[Any], Any], extra_opts: dict[str, Any] | None = None) -> None:
            opts: dict[str, Any] = {"scope": "operator.read"}
            if extra_opts:
                opts.update(extra_opts)
            api.register_gateway_method(method, _handle(run), opts)

        def _register_write(method: str, run: Callable[[Any], Any]) -> None:
            api.register_gateway_method(method, _handle(run), {"scope": "operator.write"})

        _register_read(
            "logbook.status",
            lambda _params: _require_service().status(),
            extra_opts={"profileAccess": "independent"},
        )
        _register_read("logbook.days", lambda _params: {"days": _require_service().list_days()})

        def _timeline(params: Any) -> dict[str, Any]:
            day = _read_day_param(params)
            svc = _require_service()
            return svc.timeline_for_day(day)

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
                "width": frame.get("width"),
                "height": frame.get("height"),
                "format": "jpeg",
                "base64": base64.b64encode(binary).decode("ascii"),
            }

        _register_write("logbook.frame", _frame)

        async def _standup(params: Any) -> dict[str, Any]:
            refresh = _read_bool_param(params, "refresh")
            res = _require_service().standup(_read_day_param(params), refresh)
            if inspect.isawaitable(res):
                res = await res
            return res

        _register_write("logbook.standup", _standup)

        async def _ask(params: Any) -> dict[str, Any]:
            question = _read_string_param(params, "question")
            res = _require_service().ask(_read_day_param(params), question)
            if inspect.isawaitable(res):
                res = await res
            if isinstance(res, dict) and "answer" in res:
                return res
            return {"answer": res}

        _register_write("logbook.ask", _ask)

        def _capture_set(params: Any) -> dict[str, Any]:
            paused = _read_bool_param(params, "paused")
            svc = _require_service()
            svc.set_capture_paused(paused)
            return svc.status()

        _register_write("logbook.capture.set", _capture_set)

        async def _analyze_now(_params: Any) -> dict[str, Any]:
            res = _require_service().analyze_now()
            if inspect.isawaitable(res):
                res = await res
            return res

        _register_write("logbook.analyze.now", _analyze_now)

        # ── Node-host command ────────────────────────────────
        if hasattr(api, "register_node_host_command"):
            api.register_node_host_command(
                {
                    "command": "logbook.snapshot",
                    "cap": "screen",
                    "dangerous": False,
                    "handler": _handle_logbook_snapshot,
                    "handle": _handle_logbook_snapshot,
                }
            )

    def node_host_commands(self) -> list[dict[str, Any]]:
        """Return node-host command descriptors."""
        return [
            {
                "command": "logbook.snapshot",
                "cap": "screen",
                "dangerous": False,
                "handler": _handle_logbook_snapshot,
                "handle": _handle_logbook_snapshot,
            }
        ]


# ── Node-invoke policy + node-host command handlers ───────


def _handle_logbook_node_invoke(ctx: Any) -> Any:
    """Honor the screen-capture kill switch then call ``ctx.invokeNode()``."""
    if isinstance(ctx, dict):
        cfg = ctx.get("config") or {}
        invoke = ctx.get("invokeNode")
        gateway = cfg.get("gateway", {}) or {}
        nodes = gateway.get("nodes", {}) or {}
        commands = nodes.get("commands", {}) or {}
        denied = commands.get("deny", []) or nodes.get("denyCommands", []) or []

        if isinstance(denied, list) and "screen.snapshot" in denied:
            return {
                "ok": False,
                "code": "SCREEN_CAPTURE_DENIED",
                "message": (
                    "screen capture is denied by gateway.nodes.commands.deny "
                    "(screen.snapshot); Logbook capture stays blocked until it is removed"
                ),
            }
        if callable(invoke):
            res = invoke()
            return res or {"ok": True}
        return {"ok": True}
    return {"ok": True}


def _handle_logbook_snapshot(params_json: Any) -> str:
    """Node-host command handler for screen capture."""
    params: Any = None
    if isinstance(params_json, str) and params_json:
        try:
            params = json.loads(params_json)
        except Exception:
            params = None
    elif isinstance(params_json, dict):
        params = params_json

    if sys.platform != "darwin":
        return json.dumps(
            {
                "ok": False,
                "code": "NOT_PORTED",
                "message": f"Logbook snapshot is not supported on {sys.platform}",
                "params": params,
            }
        )

    from .src.node_host import handle_logbook_snapshot

    res = handle_logbook_snapshot(params)
    return json.dumps(res)


logbook_plugin = LogbookPlugin()
entry = logbook_plugin

__all__ = [
    "LogbookPlugin",
    "LogbookService",
    "_DAY_PATTERN_STR",
    "_handle_logbook_node_invoke",
    "_handle_logbook_snapshot",
    "_read_bool_param",
    "_read_day_param",
    "_read_number_param",
    "_read_string_param",
    "day_key_for",
    "entry",
    "logbook_plugin",
]
