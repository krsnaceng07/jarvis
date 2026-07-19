"""Phase 3 tests — gateway (HTTP), Telegram channel, CLI subcommands.

Covers the Phase 3 deliverables:

  - ``jarvis.gateway`` — stdlib HTTP server, route resolution, bearer
    auth, retry on ``EADDRINUSE``, ``GatewayLockError`` after retries
    exhausted, plugin HTTP route registration via ``add_raw`` /
    ``add_route``, and a built-in ``/health`` endpoint.
  - ``extensions.telegram`` — ``TelegramChannel.send`` (with httpx
    monkeypatched), ``TelegramState`` persistence + pairing, and the
    doctor contract.
  - ``jarvis_cli.main`` — argparse parsing of the new
    ``gateway start|status`` and ``telegram setup|status`` commands.

Phase 3 deliberately keeps the gateway's surface stdlib-only
(http.server, no aiohttp) and the Telegram channel minimal
(send + listen + pairing, no threads / accounts / allow-list).
Full OpenClaw parity is a Phase 3.5+ follow-up.
"""

from __future__ import annotations

import json
import socket
import tempfile
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


# ── Gateway: HttpRoute + dispatch ────────────────────────────────


class TestHttpRoute:
    def test_defaults_are_gateway_exact(self) -> None:
        from jarvis.gateway import HttpRoute

        def h(*args, **kwargs):  # pragma: no cover - never called
            return {}

        r = HttpRoute(path="/v1/foo", handler=h)
        assert r.path == "/v1/foo"
        assert r.auth == "gateway"
        assert r.match == "exact"
        assert r.owner_id == ""

    def test_custom_match_and_auth(self) -> None:
        from jarvis.gateway import HttpRoute

        r = HttpRoute(path="/v1/mem/", handler=lambda *a, **k: {}, auth="plugin", match="prefix")
        assert r.auth == "plugin"
        assert r.match == "prefix"

    def test_frozen_dataclass(self) -> None:
        from dataclasses import FrozenInstanceError

        from jarvis.gateway import HttpRoute

        r = HttpRoute(path="/x", handler=lambda *a, **k: {})
        with pytest.raises(FrozenInstanceError):
            r.path = "/y"  # type: ignore[misc]


@pytest.mark.filterwarnings("ignore::ResourceWarning")
class TestGatewayRouteDispatch:
    """Gateway.handle_request — pure dispatch, no socket."""

    def _setup(self) -> tuple:
        from jarvis.gateway import Gateway

        gw = Gateway(host="127.0.0.1", port=0)  # port 0 = don't bind
        return gw, []

    def test_health_endpoint(self) -> None:
        gw, _ = self._setup()
        # No token needed for /health.
        status, payload = gw.handle_request("GET", "/health", b"", {"authorization": ""})
        assert status == 200
        assert payload == {"status": "ok"}

    def test_missing_token_is_401(self) -> None:
        gw, _ = self._setup()
        status, payload = gw.handle_request("POST", "/v1/x", b"{}", {"authorization": ""})
        assert status == 401
        assert "bearer" in payload["error"].lower()

    def test_invalid_token_is_403(self) -> None:
        gw, _ = self._setup()
        # Trigger token creation first, then send a wrong one.
        _ = gw.token
        status, payload = gw.handle_request(
            "POST",
            "/v1/x",
            b"{}",
            {"authorization": "Bearer wrong-token"},
        )
        assert status == 403
        assert "invalid" in payload["error"].lower()

    def test_unknown_route_is_404(self) -> None:
        from jarvis.gateway import HttpRoute

        gw, _ = self._setup()
        gw.add_route(HttpRoute(path="/v1/known", handler=lambda *a, **k: {"ok": True}))
        token = gw.token
        status, payload = gw.handle_request(
            "GET",
            "/v1/unknown",
            b"",
            {"authorization": f"Bearer {token}"},
        )
        assert status == 404
        assert payload["path"] == "/v1/unknown"

    def test_exact_match_wins(self) -> None:
        from jarvis.gateway import HttpRoute

        gw, _ = self._setup()
        gw.add_route(HttpRoute(path="/v1/mem", handler=lambda *a, **k: {"which": "exact"}))
        gw.add_route(
            HttpRoute(
                path="/v1/",
                handler=lambda *a, **k: {"which": "prefix"},
                match="prefix",
            )
        )
        token = gw.token
        status, payload = gw.handle_request(
            "GET",
            "/v1/mem",
            b"",
            {"authorization": f"Bearer {token}"},
        )
        assert status == 200
        assert payload["which"] == "exact"

    def test_prefix_match_used_when_no_exact(self) -> None:
        from jarvis.gateway import HttpRoute

        gw, _ = self._setup()
        gw.add_route(
            HttpRoute(
                path="/v1/",
                handler=lambda *a, **k: {"which": "prefix"},
                match="prefix",
            )
        )
        token = gw.token
        status, payload = gw.handle_request(
            "GET",
            "/v1/mem/search",
            b"",
            {"authorization": f"Bearer {token}"},
        )
        assert status == 200
        assert payload["which"] == "prefix"

    def test_handler_exception_is_500(self) -> None:
        from jarvis.gateway import HttpRoute

        gw, _ = self._setup()
        gw.add_route(
            HttpRoute(
                path="/v1/boom",
                handler=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kaboom")),
            )
        )
        token = gw.token
        status, payload = gw.handle_request(
            "POST",
            "/v1/boom",
            b"{}",
            {"authorization": f"Bearer {token}"},
        )
        assert status == 500
        assert "kaboom" in payload["error"]

    def test_add_raw_validates_keys(self) -> None:
        gw, _ = self._setup()
        with pytest.raises(ValueError, match="missing path/handler"):
            gw.add_raw({"path": "/v1/x"})  # missing handler
        with pytest.raises(ValueError, match="missing path/handler"):
            gw.add_raw({"handler": lambda *a, **k: {}})  # missing path

    def test_add_raw_normalises(self) -> None:
        gw, _ = self._setup()
        gw.add_raw(
            {
                "path": "/v1/x",
                "handler": lambda *a, **k: {"ok": True},
                "auth": "plugin",
                "match": "prefix",
                "_owner_id": "test_plugin",
            }
        )
        routes = gw.routes()
        assert len(routes) == 1
        r = routes[0]
        assert r.path == "/v1/x"
        assert r.auth == "plugin"
        assert r.match == "prefix"
        assert r.owner_id == "test_plugin"


# ── Gateway: token persistence + EADDRINUSE retry ─────────────────


# stdlib http.server + Windows has a known ResourceWarning for the
# listening socket after server_close(). The tests assert the right
# behavior; the warning is harmless GC noise.
@pytest.mark.filterwarnings("ignore::ResourceWarning")
class TestGatewayToken:
    def test_token_persists_across_instances(self, tmp_path: Path) -> None:
        from jarvis.gateway import Gateway

        token_path = tmp_path / "gw.token"
        gw1 = Gateway(host="127.0.0.1", port=0, token_path=token_path)
        t1 = gw1.token
        assert token_path.exists()

        # Second instance reads the same file.
        gw2 = Gateway(host="127.0.0.1", port=0, token_path=token_path)
        t2 = gw2.token
        assert t1 == t2

    def test_token_is_urlsafe(self, tmp_path: Path) -> None:
        from jarvis.gateway import Gateway

        gw = Gateway(host="127.0.0.1", port=0, token_path=tmp_path / "t")
        token = gw.token
        # tokens.token_urlsafe(32) is 43 base64-ish chars
        assert len(token) >= 30
        assert "\n" not in token  # no newlines


@pytest.mark.filterwarnings("ignore::ResourceWarning")
class TestGatewayBindAndRetry:
    """EADDRINUSE retry + GatewayLockError path."""

    def test_bind_free_port_succeeds(self) -> None:
        from jarvis.gateway import Gateway

        # Pick a free port via socket, then close + bind via Gateway.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        gw = Gateway(host="127.0.0.1", port=port)
        gw.start()  # should succeed
        try:
            assert gw.is_running()
        finally:
            gw.stop()

    def test_eaddrinuse_raises_lock_error(self) -> None:
        from jarvis.gateway import Gateway, GatewayLockError

        # Hold a port in another socket.
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        try:
            gw = Gateway(host="127.0.0.1", port=port)
            # Disable retry → first attempt should fail fast.
            with pytest.raises(GatewayLockError):
                gw.start(retry_eaddrinuse=False)
        finally:
            blocker.close()

    def test_retry_constants_match_openclaw(self) -> None:
        """OpenClaw's gateway uses 20 x 500ms retries on EADDRINUSE.

        We don't drive a full release-then-rebind here because
        Windows TIME_WAIT keeps the port busy for ~30s after the
        holder releases it (and Linux's behavior differs). The
        constants below are what the actual retry loop uses; if
        you change them, change this assertion too.
        """
        from jarvis.gateway import EADDRINUSE_MAX_RETRIES, EADDRINUSE_RETRY_INTERVAL_MS

        assert EADDRINUSE_MAX_RETRIES == 20
        assert EADDRINUSE_RETRY_INTERVAL_MS == 500


# ── Gateway: live HTTP server (httplib, stdlib) ─────────────────


# Windows ThreadingHTTPServer has a known issue where the listening
# socket raises a ResourceWarning on GC after server_close(). We
# silence the warning here so pytest doesn't escalate it to an
# unraisable exception during teardown.
@pytest.mark.filterwarnings("ignore::ResourceWarning")
class TestGatewayLiveServer:
    """Spin up the real ThreadingHTTPServer and hit it with HTTPConnection."""

    def _live_gateway(self) -> tuple:
        from jarvis.gateway import Gateway

        gw = Gateway(host="127.0.0.1", port=0)
        # /health and an example plugin route
        from jarvis.gateway import HttpRoute

        gw.add_route(
            HttpRoute(
                path="/v1/ping",
                handler=lambda m, u, b, h: {"pong": True, "method": m},
            )
        )
        gw.start()
        # Find the actual port the server bound to (we passed 0 to let
        # the OS pick a free port for the test).
        port = gw._server.server_address[1]  # type: ignore[union-attr]
        return gw, port

    def test_health_endpoint(self) -> None:
        gw, port = self._live_gateway()
        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=2.0)
            conn.request("GET", "/health")
            r = conn.getresponse()
            assert r.status == 200
            assert json.loads(r.read()) == {"status": "ok"}
        finally:
            gw.stop()

    def test_plugin_route_via_http(self) -> None:
        gw, port = self._live_gateway()
        try:
            token = gw.token
            conn = HTTPConnection("127.0.0.1", port, timeout=2.0)
            conn.request(
                "GET",
                "/v1/ping",
                headers={"Authorization": f"Bearer {token}"},
            )
            r = conn.getresponse()
            assert r.status == 200
            payload = json.loads(r.read())
            assert payload["pong"] is True
            assert payload["method"] == "GET"
        finally:
            gw.stop()

    def test_unauthorized_request(self) -> None:
        gw, port = self._live_gateway()
        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=2.0)
            conn.request("GET", "/v1/ping")
            r = conn.getresponse()
            assert r.status == 401
        finally:
            gw.stop()


# ── Telegram channel ─────────────────────────────────────────────


# httpx + monkeypatch can leave unclosed sockets on Windows when the
# post() function raises. The test asserts the correct return value
# regardless; the unclosed socket is harmless GC noise.
@pytest.mark.filterwarnings("ignore::ResourceWarning")
class TestTelegramState:
    def test_default_persists_to_home(self, tmp_path: Path, monkeypatch) -> None:
        from extensions.telegram import runtime

        # Use a placeholder-shaped token. The literal is a test
        # fixture, not a real credential — the S105 check is
        # over-zealous for our test-only bot tokens.
        _dummy = "test:token-123"

        monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
        # Reset cached default.
        runtime.TelegramState._default = None
        state = runtime.TelegramState.default()
        assert state.bot_token == ""
        assert state.paired_chat_id == ""
        state.set_bot_token(_dummy)
        state.set_paired_chat_id("999")
        # Reload
        runtime.TelegramState._default = None
        again = runtime.TelegramState.default()
        assert again.bot_token == _dummy
        assert again.paired_chat_id == "999"

    def test_env_token_overrides(self, tmp_path: Path, monkeypatch) -> None:
        from extensions.telegram import runtime

        _env_token = "env-fixture-token"  # noqa: S105 (test fixture)
        monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("JARVIS_TELEGRAM_BOT_TOKEN", _env_token)
        runtime.TelegramState._default = None
        state = runtime.TelegramState.default()
        assert state.bot_token == _env_token

    def test_set_polling_interval_min_1(self, tmp_path: Path, monkeypatch) -> None:
        from extensions.telegram import runtime

        monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
        runtime.TelegramState._default = None
        state = runtime.TelegramState.default()
        state.set_polling_interval(0)
        assert state.polling_interval_sec == 1
        state.set_polling_interval(7)
        assert state.polling_interval_sec == 7


@pytest.mark.filterwarnings("ignore::ResourceWarning")
class TestTelegramChannelSend:
    def test_send_without_token(self) -> None:
        from extensions.telegram.plugin import TelegramChannel
        from extensions.telegram.runtime import TelegramState

        state = TelegramState()
        state.bot_token = ""
        ch = TelegramChannel(state)
        result = ch.send("123", "hi")
        assert result["ok"] is False
        assert "bot_token" in result["error"]

    def test_send_with_mocked_httpx(self, tmp_path: Path, monkeypatch) -> None:
        from extensions.telegram import runtime
        from extensions.telegram.plugin import TelegramChannel

        monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
        runtime.TelegramState._default = None
        state = runtime.TelegramState.default()
        state.set_bot_token("dummy")

        captured: dict = {}

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def json(self):
                return self._payload

        def fake_post(url, json, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return FakeResponse({"ok": True, "result": {"message_id": 42}})

        import httpx

        monkeypatch.setattr(httpx, "post", fake_post)
        ch = TelegramChannel(state)
        result = ch.send("chat-1", "hello")
        assert result["ok"] is True
        assert result["message_id"] == 42
        assert captured["url"].endswith("/botdummy/sendMessage")
        assert captured["json"] == {"chat_id": "chat-1", "text": "hello"}

    def test_send_empty_text(self, tmp_path: Path, monkeypatch) -> None:
        from extensions.telegram import runtime
        from extensions.telegram.plugin import TelegramChannel

        monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
        runtime.TelegramState._default = None
        state = runtime.TelegramState.default()
        state.set_bot_token("dummy")
        ch = TelegramChannel(state)
        assert ch.send("c", "")["ok"] is False
        assert ch.send("c", "   ")["ok"] is False

    def test_send_handles_httpx_exception(self, tmp_path: Path, monkeypatch) -> None:
        from extensions.telegram import runtime
        from extensions.telegram.plugin import TelegramChannel

        monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
        runtime.TelegramState._default = None
        state = runtime.TelegramState.default()
        state.set_bot_token("dummy")

        import httpx

        def boom(*args, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(httpx, "post", boom)
        ch = TelegramChannel(state)
        result = ch.send("c", "hi")
        assert result["ok"] is False
        assert "network down" in result["error"]


@pytest.mark.filterwarnings("ignore::ResourceWarning")
class TestTelegramChannelListen:
    def test_listen_without_token_no_start(self) -> None:
        from extensions.telegram.plugin import TelegramChannel
        from extensions.telegram.runtime import TelegramState

        state = TelegramState()
        state.bot_token = ""
        ch = TelegramChannel(state)
        # Should return immediately (no token = no polling).
        ch.listen(lambda msg: None)
        # We can't easily assert "no work was done" without a logger
        # capture; the important behavior is that it doesn't crash.

    def test_listen_pairing(self, tmp_path: Path, monkeypatch) -> None:
        """First inbound message sets paired_chat_id and invokes the callback."""
        from extensions.telegram import runtime
        from extensions.telegram.plugin import TelegramChannel

        monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
        runtime.TelegramState._default = None
        state = runtime.TelegramState.default()
        state.set_bot_token("dummy")
        state.polling_interval_sec = 0  # fast retry

        # Mock httpx.get to return one update, then set stop_flag so
        # the listen loop exits cleanly.
        call_count = {"n": 0}
        seen: list = []

        class FakeResp:
            def __init__(self, payload):
                self._payload = payload

            def json(self):
                return self._payload

        def fake_get(url, params, timeout):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return FakeResp(
                    {
                        "ok": True,
                        "result": [
                            {
                                "update_id": 10,
                                "message": {
                                    "message_id": 1,
                                    "chat": {"id": 555},
                                    "from": {"id": 555},
                                    "text": "hi",
                                },
                            }
                        ],
                    }
                )
            # After the first message, set stop_flag so the listen
            # loop exits. Then return an empty result to keep the
            # call shape consistent.
            state.stop_flag = True
            return FakeResp({"ok": True, "result": []})

        import httpx

        monkeypatch.setattr(httpx, "get", fake_get)
        ch = TelegramChannel(state)
        ch.listen(lambda msg: seen.append(msg))
        # After listen returns, state should be paired.
        assert state.paired_chat_id == "555"
        assert len(seen) == 1
        assert seen[0]["chat_id"] == "555"
        assert seen[0]["text"] == "hi"


class TestTelegramDoctorContract:
    def test_detect_flags_missing_credentials(self, tmp_path: Path) -> None:
        from extensions.telegram.doctor import detect_telegram_credentials

        # No env var, no state file → finding expected.
        with patch.dict("os.environ", {}, clear=True):
            findings = detect_telegram_credentials(tmp_path, {})
        assert len(findings) == 1
        assert "bot token" in findings[0].label.lower()

    def test_detect_silent_when_state_file_exists(self, tmp_path: Path) -> None:
        from extensions.telegram.doctor import detect_telegram_credentials

        (tmp_path / "telegram.json").write_text("{}", encoding="utf-8")
        with patch.dict("os.environ", {}, clear=True):
            findings = detect_telegram_credentials(tmp_path, {})
        assert findings == []


# ── Telegram plugin entry ───────────────────────────────────────


class TestTelegramPluginEntry:
    def test_entry_shape(self) -> None:
        from extensions.telegram import entry

        assert entry.id == "telegram"
        assert entry.kind == "channel"
        assert entry.activation == "on_startup"
        assert "network:outbound" in entry.permissions

    def test_register_adds_channel_and_doctor(self) -> None:
        from extensions.telegram import _register
        from jarvis_sdk import PluginApi, PluginContext

        ctx = PluginContext(
            plugin_id="telegram",
            plugin_kind="channel",
            data_dir=Path(tempfile.gettempdir()),
            workspace=REPO_ROOT,
        )
        api = PluginApi(ctx)
        # Channel registration requires no token to be set.
        _register(api)
        assert api.channel is not None
        assert api.channel["id"] == "telegram"
        assert "send" in api.channel
        assert "listen" in api.channel
        assert api.doctor_contracts  # at least one


# ── CLI: new Phase 3 subcommands ────────────────────────────────


class TestCliPhase3Commands:
    def test_parser_accepts_gateway_start(self) -> None:
        from jarvis_cli.main import _build_parser_v2

        parser = _build_parser_v2()
        args = parser.parse_args(["gateway", "start", "--host", "127.0.0.1", "--port", "7433"])
        assert args.command == "gateway"
        assert args.subcommand == "start"
        assert args.host == "127.0.0.1"
        assert args.port == "7433"

    def test_parser_accepts_gateway_status(self) -> None:
        from jarvis_cli.main import _build_parser_v2

        parser = _build_parser_v2()
        args = parser.parse_args(["gateway", "status"])
        assert args.command == "gateway"
        assert args.subcommand == "status"

    def test_parser_accepts_telegram_setup_with_token(self) -> None:
        from jarvis_cli.main import _build_parser_v2

        _token = "test:parser-fixture"  # noqa: S105 (test fixture)
        parser = _build_parser_v2()
        args = parser.parse_args(["telegram", "setup", "--token", _token])
        assert args.command == "telegram"
        assert args.subcommand == "setup"
        assert args.token == _token
        assert args.reset is False

    def test_parser_accepts_telegram_setup_reset(self) -> None:
        from jarvis_cli.main import _build_parser_v2

        parser = _build_parser_v2()
        args = parser.parse_args(["telegram", "setup", "--reset"])
        assert args.subcommand == "setup"
        assert args.reset is True

    def test_parser_accepts_telegram_status(self) -> None:
        from jarvis_cli.main import _build_parser_v2

        parser = _build_parser_v2()
        args = parser.parse_args(["telegram", "status"])
        assert args.command == "telegram"
        assert args.subcommand == "status"

    def test_help_lists_new_subcommands(self, capsys) -> None:
        from jarvis_cli.main import _build_parser_v2

        parser = _build_parser_v2()
        with pytest.raises(SystemExit) as ei:
            parser.parse_args(["--help"])
        assert ei.value.code == 0
        out = capsys.readouterr().out
        assert "gateway" in out
        assert "telegram" in out


# ── CLI: gateway status reports running state ──────────────────


class TestCliGatewayStatus:
    def test_status_reports_free_port(self, tmp_path: Path, monkeypatch) -> None:
        from argparse import Namespace

        from jarvis_cli.main import _cmd_gateway_status

        # Pick a free port.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        monkeypatch.setattr("jarvis.gateway.DEFAULT_PORT", port)
        # Even with no running gateway, the status check should NOT
        # return 0 if the port is free.
        rc = _cmd_gateway_status(Namespace(), tmp_path)
        assert rc == 1
