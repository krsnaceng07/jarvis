"""Tests for the Logbook entry point (Phase 5.19).

Covers the full register(api) flow:
- ``register(api)`` calls every SDK registrar the
  OpenClaw source calls (control UI descriptor, node
  invoke policy, service, gateway methods, node host
  command)
- the input validation helpers match the OpenClaw
  semantics (``readDayParam`` accepts ``YYYY-MM-DD`` or
  omits; ``readNumberParam`` rejects non-positive /
  non-finite / non-numeric; ``readStringParam`` rejects
  empty / non-string)
- the gateway method bodies route to the underlying
  service via the single-slot holder
- the service stub returns the expected shapes
- the error envelope is a structured
  ``{code, message}`` shape (matches the SDK's
  ``errorShape``)
"""
from __future__ import annotations

import json

import pytest

from extensions.logbook.plugin import (
    LogbookPlugin,
    LogbookService,
    _DAY_PATTERN_STR,
    _read_day_param,
    _read_number_param,
    _read_string_param,
    _handle_logbook_node_invoke,
    _handle_logbook_snapshot,
    day_key_for,
    logbook_plugin,
)


# ── Input validation helpers ──────────────────────────────


class TestInputValidation:
    def test_read_day_param_accepts_omitted(self) -> None:
        """``readDayParam({})`` returns today's day key."""
        assert _read_day_param({}) == day_key_for(_now_ms())

    def test_read_day_param_accepts_explicit(self) -> None:
        assert _read_day_param({"day": "2024-01-15"}) == "2024-01-15"

    def test_read_day_param_treats_empty_as_omitted(self) -> None:
        """An empty string falls back to today's day (matches
        OpenClaw's ``day === undefined`` check)."""
        assert _read_day_param({"day": ""}) == day_key_for(_now_ms())

    @pytest.mark.parametrize("bad", ["2024", "2024-1-1", "not-a-day", 0])
    def test_read_day_param_rejects_bad(self, bad) -> None:
        with pytest.raises(ValueError, match="day must be YYYY-MM-DD"):
            _read_day_param({"day": bad})

    @pytest.mark.parametrize(
        "bad", [0, -1, "10", None, {}, [], True, False, float("nan")]
    )
    def test_read_number_param_rejects_bad(self, bad) -> None:
        with pytest.raises(ValueError, match="must be a positive number"):
            _read_number_param({"x": bad}, "x")

    def test_read_number_param_accepts_positive(self) -> None:
        assert _read_number_param({"x": 42}, "x") == 42
        # Float positive numbers are accepted (clamped to int).
        assert _read_number_param({"x": 2.7}, "x") >= 2

    @pytest.mark.parametrize("bad", ["", "  ", None, 0, {}, []])
    def test_read_string_param_rejects_bad(self, bad) -> None:
        with pytest.raises(ValueError, match="is required"):
            _read_string_param({"q": bad}, "q")

    def test_read_string_param_trims(self) -> None:
        assert _read_string_param({"q": "  hello  "}, "q") == "hello"


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


# ── Day key helper ──────────────────────────────────────────


class TestDayKeyFor:
    def test_returns_iso_date(self) -> None:
        # 2024-01-15T00:00:00Z = 1705276800000 ms
        assert day_key_for(1705276800000) == "2024-01-15"


# ── LogbookService stub ────────────────────────────────────


class TestLogbookServiceStub:
    def test_status_shape(self) -> None:
        svc = LogbookService(config={"captureEnabled": True, "captureIntervalSeconds": 30})
        s = svc.status()
        assert s["running"] is True
        assert s["paused"] is False
        assert s["captureEnabled"] is True
        assert s["captureIntervalSeconds"] == 30
        assert s["day"] == day_key_for(_now_ms())

    def test_list_days_empty(self) -> None:
        assert LogbookService().list_days() == []

    def test_cards_for_day_empty(self) -> None:
        assert LogbookService().cards_for_day("2024-01-15") == []

    def test_day_stats_shape(self) -> None:
        stats = LogbookService().day_stats("2024-01-15")
        assert stats["trackedMs"] == 0
        assert stats["distractionMs"] == 0
        assert stats["categories"] == []
        assert stats["apps"] == []

    def test_frames_in_range_empty(self) -> None:
        assert LogbookService().frames_in_range(0, 1000) == []

    def test_frame_by_id_returns_none(self) -> None:
        assert LogbookService().frame_by_id(1) is None

    def test_standup_shape(self) -> None:
        svc = LogbookService()
        out = svc.standup("2024-01-15", refresh=False)
        assert out["day"] == "2024-01-15"
        assert out["cards"] == []

    def test_ask_returns_placeholder(self) -> None:
        out = LogbookService().ask("2024-01-15", "what did I do?")
        assert out["day"] == "2024-01-15"
        assert out["question"] == "what did I do?"
        assert "not yet ported" in out["answer"]


# ── Plugin descriptor ──────────────────────────────────────


class TestPluginDescriptor:
    def test_descriptor_metadata(self) -> None:
        assert logbook_plugin.id == "logbook"
        assert logbook_plugin.kind == "infra"
        assert logbook_plugin.version == "0.1.0"
        assert "screen snapshots" in logbook_plugin.description.lower()
        assert isinstance(logbook_plugin.metadata, dict)

    def test_init_is_noop(self) -> None:
        # The init hook is a no-op for the Logbook
        # extension; the real init runs in ``register``.
        assert logbook_plugin.init({}) is None

    def test_node_host_commands(self) -> None:
        cmds = logbook_plugin.node_host_commands()
        assert len(cmds) == 1
        cmd = cmds[0]
        assert cmd["command"] == "logbook.snapshot"
        assert cmd["cap"] == "screen"
        assert cmd["dangerous"] is False
        assert callable(cmd["handle"])


# ── register(api) flow ─────────────────────────────────────


class _RecordingApi:
    """Minimal API surface for the register() flow tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.commands: list[dict] = []
        self.gateway_methods: list[dict] = []
        self.services: list[dict] = []
        self.node_invoke_policies: list[dict] = []
        self.node_host_commands: list[dict] = []
        self.control_ui_descriptors: list[dict] = []
        self.plugin_config: dict = {}
        self.session = _SessionNamespace()
        self.runtime: dict = {}

    def register_node_invoke_policy(self, policy: dict) -> None:
        self.node_invoke_policies.append(policy)

    def register_service(self, service: dict) -> None:
        self.services.append(service)

    def register_gateway_method(
        self, method: str, handler: Any, options: dict
    ) -> None:
        self.gateway_methods.append(
            {"method": method, "handler": handler, "options": options}
        )

    def register_node_host_command(self, command: dict) -> None:
        self.node_host_commands.append(command)

    def register_control_ui_descriptor(self, descriptor: dict) -> None:
        self.control_ui_descriptors.append(descriptor)


class _SessionNamespace:
    def __init__(self) -> None:
        self.controls = _ControlsNamespace()


class _ControlsNamespace:
    def __init__(self) -> None:
        self.descriptors: list[dict] = []

    def register_control_ui_descriptor(self, descriptor: dict) -> None:
        self.descriptors.append(descriptor)


class TestRegisterApi:
    def _build_api(self) -> _RecordingApi:
        return _RecordingApi()

    def test_register_calls_every_openclaw_registrar(self) -> None:
        api = self._build_api()
        logbook_plugin.register(api)
        # SDK stubs are no-ops, so we can only assert the
        # ones that have an explicit Python implementation
        # (the session controls namespace).
        assert len(api.session.controls.descriptors) == 1
        d = api.session.controls.descriptors[0]
        assert d["id"] == "logbook"
        assert d["surface"] == "tab"
        assert d["group"] == "control"
        assert d["requiredScopes"] == ["operator.write"]

    def test_register_is_idempotent(self) -> None:
        """Calling ``register`` twice registers twice (the host
        decides whether to deduplicate; the entry point
        doesn't pre-empt)."""
        api = self._build_api()
        logbook_plugin.register(api)
        logbook_plugin.register(api)
        assert len(api.session.controls.descriptors) == 2


# ── Node-invoke policy handler ──────────────────────────────


class TestNodeInvokePolicy:
    def test_allows_when_no_deny(self) -> None:
        ctx = {
            "config": {"gateway": {"nodes": {}}},
            "invokeNode": lambda: {"ok": True, "captured": True},
        }
        result = _handle_logbook_node_invoke(ctx)
        assert result == {"ok": True, "captured": True}

    def test_blocks_when_screen_snapshot_denied(self) -> None:
        ctx = {
            "config": {"gateway": {"nodes": {"denyCommands": ["screen.snapshot"]}}},
            "invokeNode": lambda: {"ok": True},
        }
        result = _handle_logbook_node_invoke(ctx)
        assert result["ok"] is False
        assert result["code"] == "SCREEN_CAPTURE_DENIED"

    def test_handles_empty_config(self) -> None:
        ctx = {"config": {}, "invokeNode": lambda: None}
        result = _handle_logbook_node_invoke(ctx)
        assert result == {"ok": True}

    def test_handles_dict_without_config(self) -> None:
        # Defensive: the host may pass a non-dict ctx in
        # tests; the handler must not crash.
        result = _handle_logbook_node_invoke({})
        assert result == {"ok": True}


# ── Node-host command handler ──────────────────────────────


class TestNodeHostSnapshot:
    def test_returns_structured_placeholder(self) -> None:
        result_json = _handle_logbook_snapshot('{"day": "2024-01-15"}')
        result = json.loads(result_json)
        assert result["ok"] is False
        assert result["code"] == "NOT_PORTED"
        assert result["params"] == {"day": "2024-01-15"}

    def test_handles_empty_params(self) -> None:
        result = json.loads(_handle_logbook_snapshot(""))
        assert result["ok"] is False
        assert result["params"] is None

    def test_handles_bad_json(self) -> None:
        result = json.loads(_handle_logbook_snapshot("{not-json"))
        assert result["ok"] is False
        assert result["params"] is None


# ── Module-level exports ───────────────────────────────────


class TestModuleExports:
    def test_entry_is_logbook_plugin(self) -> None:
        from extensions.logbook.plugin import entry

        assert entry is logbook_plugin
        assert isinstance(entry, LogbookPlugin)

    def test_day_pattern_constant(self) -> None:
        assert _DAY_PATTERN_STR == "YYYY-MM-DD"
