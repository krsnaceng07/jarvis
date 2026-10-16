"""Phase 5.21 — ACPX entry point tests.

Covers the full ``register(api)`` flow for the ACPX
plugin:
- ``register(api)`` calls the same SDK registrars the
  OpenClaw source calls: session catalog registration,
  runtime service registration, reply-dispatch hook
  with timeout
- the default timeout resolution handles positive,
  zero, negative, NaN, non-numeric, missing values
- the lazy runtime service descriptor exposes the
  expected ``id``, ``start``, ``stop`` shape
- the ``OPENCLAW_SKIP_ACPX_RUNTIME=1`` escape hatch
  suppresses backend registration
- the ``acpx_plugin`` descriptor carries the canonical
  id / kind / version / description
"""
from __future__ import annotations

import importlib.util
import os
import sys


# Load the extension's ``plugin.py`` via
# ``importlib.util.spec_from_file_location`` so the
# import doesn't depend on ``sys.path`` ordering. The
# OpenClaw naming pattern has every extension ship a
# top-level ``plugin.py``, so any extension root on
# ``sys.path`` would resolve ``plugin`` to the wrong
# file when other tests in the same suite have added
# their own extension roots to ``sys.path``.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EXT_PARENT = os.path.dirname(_THIS_DIR)  # tests/extensions/
_TESTS_PARENT = os.path.dirname(_EXT_PARENT)  # tests/
_PROJECT_ROOT = os.path.dirname(_TESTS_PARENT)  # project root
_EXT_ROOT = os.path.join(_PROJECT_ROOT, "extensions", "acpx")
_PLUGIN_PATH = os.path.join(_EXT_ROOT, "plugin.py")
_SPEC = importlib.util.spec_from_file_location(
    "_acpx_plugin_under_test", _PLUGIN_PATH
)
_plugin = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("_acpx_plugin_under_test", _plugin)
_SPEC.loader.exec_module(_plugin)

ACPX_BACKEND_ID = _plugin.ACPX_BACKEND_ID
ACPXPlugin = _plugin.ACPXPlugin
DEFAULT_ACPX_TIMEOUT_SECONDS = _plugin.DEFAULT_ACPX_TIMEOUT_SECONDS
_finite_seconds_to_ms = _plugin._finite_seconds_to_ms
_resolve_reply_dispatch_timeout_ms = (
    _plugin._resolve_reply_dispatch_timeout_ms
)
acpx_plugin = _plugin.acpx_plugin
create_acpx_runtime_service = _plugin.create_acpx_runtime_service
register_pi_session_catalog = _plugin.register_pi_session_catalog


# ── Timeout resolution ────────────────────────────────────


class TestReplyDispatchTimeout:
    def test_default_when_plugin_config_missing(self) -> None:
        assert _resolve_reply_dispatch_timeout_ms(None) == (
            DEFAULT_ACPX_TIMEOUT_SECONDS * 1000
        )

    def test_default_when_plugin_config_empty(self) -> None:
        assert _resolve_reply_dispatch_timeout_ms({}) == (
            DEFAULT_ACPX_TIMEOUT_SECONDS * 1000
        )

    def test_resolves_positive_seconds(self) -> None:
        assert _resolve_reply_dispatch_timeout_ms(
            {"timeoutSeconds": 30}
        ) == 30_000

    def test_resolves_fractional_seconds(self) -> None:
        assert _resolve_reply_dispatch_timeout_ms(
            {"timeoutSeconds": 0.5}
        ) == 500

    def test_falls_back_to_default_for_zero(self) -> None:
        assert _resolve_reply_dispatch_timeout_ms(
            {"timeoutSeconds": 0}
        ) == (DEFAULT_ACPX_TIMEOUT_SECONDS * 1000)

    def test_falls_back_to_default_for_negative(self) -> None:
        assert _resolve_reply_dispatch_timeout_ms(
            {"timeoutSeconds": -1}
        ) == (DEFAULT_ACPX_TIMEOUT_SECONDS * 1000)

    def test_falls_back_to_default_for_non_numeric(self) -> None:
        assert _resolve_reply_dispatch_timeout_ms(
            {"timeoutSeconds": "30"}
        ) == (DEFAULT_ACPX_TIMEOUT_SECONDS * 1000)
        assert _resolve_reply_dispatch_timeout_ms(
            {"timeoutSeconds": None}
        ) == (DEFAULT_ACPX_TIMEOUT_SECONDS * 1000)
        assert _resolve_reply_dispatch_timeout_ms(
            {"timeoutSeconds": {}}
        ) == (DEFAULT_ACPX_TIMEOUT_SECONDS * 1000)

    def test_finite_seconds_to_ms_clamps_to_minimum(self) -> None:
        # Sub-millisecond values clamp to 1 ms (the OpenClaw
        # source's ``finiteSecondsToTimerSafeMilliseconds``
        # behavior).
        assert _finite_seconds_to_ms(0.0001) == 1
        assert _finite_seconds_to_ms(0) == 1
        assert _finite_seconds_to_ms(-1) == 1
        assert _finite_seconds_to_ms(None) == 1
        assert _finite_seconds_to_ms("5") == 1


# ── Plugin descriptor ──────────────────────────────────────


class TestPluginDescriptor:
    def test_descriptor_metadata(self) -> None:
        assert acpx_plugin.id == "acpx"
        assert acpx_plugin.kind == "infra"
        assert acpx_plugin.version == "0.1.0"
        assert "ACP" in acpx_plugin.description

    def test_init_is_noop(self) -> None:
        assert acpx_plugin.init({}) is None

    def test_acpx_backend_id_constant(self) -> None:
        assert ACPX_BACKEND_ID == "acpx"


# ── Lazy runtime service factory ──────────────────────────


class TestLazyRuntimeService:
    def test_returns_service_descriptor(self) -> None:
        service = create_acpx_runtime_service({})
        assert service["id"] == "acpx-runtime"
        assert callable(service["start"])
        assert callable(service["stop"])

    def test_start_skips_when_escape_hatch_set(self, monkeypatch) -> None:
        """``OPENCLAW_SKIP_ACPX_RUNTIME=1`` suppresses backend
        registration (matches the OpenClaw source)."""
        monkeypatch.setenv("OPENCLAW_SKIP_ACPX_RUNTIME", "1")
        service = create_acpx_runtime_service({})
        recordings: list[dict] = []

        class _StubCtx:
            logger = type(
                "_Logger",
                (),
                {
                    "info": staticmethod(lambda *_a, **_k: None),
                },
            )()

            def _record_registration(self, payload: dict) -> None:
                recordings.append({"kind": "register", **payload})

        import asyncio
        asyncio.run(service["start"](_StubCtx()))
        assert recordings == []

    def test_start_registers_backend_when_not_skipped(self) -> None:
        service = create_acpx_runtime_service({})
        recordings: list[dict] = []

        class _StubCtx:
            logger = type(
                "_Logger",
                (),
                {
                    "info": staticmethod(lambda *_a, **_k: None),
                },
            )()

            def _record_registration(self, payload: dict) -> None:
                recordings.append(payload)

        import asyncio
        asyncio.run(service["start"](_StubCtx()))
        assert len(recordings) == 1
        registration = recordings[0]
        assert registration["kind"] == "acp_runtime_backend"
        assert registration["id"] == ACPX_BACKEND_ID

    def test_stop_records_unregistration_when_service_never_started(
        self,
    ) -> None:
        service = create_acpx_runtime_service({})
        unregistrations: list[dict] = []

        class _StubCtx:
            logger = type(
                "_Logger",
                (),
                {
                    "info": staticmethod(lambda *_a, **_k: None),
                },
            )()

            def _record_registration(self, payload: dict) -> None:
                pass

            def _record_unregistration(
                self, payload: dict
            ) -> None:
                unregistrations.append(payload)

        import asyncio
        asyncio.run(service["start"](_StubCtx()))
        asyncio.run(service["stop"](_StubCtx()))
        assert len(unregistrations) == 1
        assert unregistrations[0]["id"] == ACPX_BACKEND_ID


# ── Session catalog helper ────────────────────────────────


class TestSessionCatalog:
    def test_register_pi_session_catalog_records_call(self) -> None:
        class _StubApi:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def register_session_catalog(self, payload: dict) -> None:
                self.calls.append(payload)

        api = _StubApi()
        register_pi_session_catalog(api)
        assert len(api.calls) == 1
        assert api.calls[0]["id"] == "pi"
        assert api.calls[0]["kind"] == "session-catalog"

    def test_register_pi_session_catalog_skips_when_seam_missing(self) -> None:
        class _NoCatalogApi:
            pass

        # No raise when the SDK seam is missing.
        register_pi_session_catalog(_NoCatalogApi())


# ── register(api) flow ──────────────────────────────────────


class TestRegisterApi:
    def test_register_calls_every_openclaw_registrar(self) -> None:
        api = _RecordingApi()
        acpx_plugin.register(api)
        # The session catalog helper records its call.
        assert len(api.session_catalog_calls) == 1
        # The runtime service is registered.
        assert len(api.services) == 1
        assert api.services[0]["id"] == "acpx-runtime"
        # The reply-dispatch hook is registered with a
        # timeout.
        assert len(api.hooks) == 1
        hook = api.hooks[0]
        assert hook["event"] == "reply_dispatch"
        assert hook["options"]["timeoutMs"] == (
            DEFAULT_ACPX_TIMEOUT_SECONDS * 1000
        )

    def test_register_resolves_configured_timeout(self) -> None:
        api = _RecordingApi()
        api.plugin_config = {"timeoutSeconds": 30}
        acpx_plugin.register(api)
        hook = api.hooks[0]
        assert hook["options"]["timeoutMs"] == 30_000


class _StateNamespace:
    def open_keyed_store(self, options: dict) -> dict:
        return {"id": "stub-keyed-store", "options": options}


class _RuntimeNamespace:
    state = _StateNamespace()


class _RecordingApi:
    """Minimal API surface for the register() flow tests."""

    def __init__(self) -> None:
        self.session_catalog_calls: list[dict] = []
        self.services: list[dict] = []
        self.hooks: list[dict] = []
        self.plugin_config: dict = {}
        self.runtime = _RuntimeNamespace()

    def register_session_catalog(self, payload: dict) -> None:
        self.session_catalog_calls.append(payload)

    def register_service(self, service: dict) -> None:
        self.services.append(service)

    def on(
        self, event: str, handler, options: Optional[dict] = None
    ) -> None:
        self.hooks.append(
            {"event": event, "handler": handler, "options": options or {}}
        )
