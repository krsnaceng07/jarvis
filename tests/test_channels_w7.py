"""Wave 7 tests — config.get / config.patch RPC handlers + config_core wiring."""

from __future__ import annotations

import json
from pathlib import Path


from jarvis_config_core import JarvisConfig, load_config, save_config
from src.gateway.rpc_dispatcher import (
    GatewayRPCDispatcher,
    RPCDispatchError,
    make_status_handler,
)
from jarvis_gateway_protocol import RPCRequest


# ── Shared helpers ──────────────────────────────────────────────────────────


def _make_config_get_handler(config: JarvisConfig):
    """Factory matching the app's _config_get_handler pattern."""
    def _handler(params: dict) -> dict:
        d = config.to_dict()
        if d.get("gemini_api_key"):
            d["gemini_api_key"] = "***"
        return d
    return _handler


def _make_config_patch_handler(cfg_path: Path):
    """Factory matching the app's _config_patch_handler pattern."""
    from jarvis_config_core import patch_config as _patch
    state = {"config": load_config(cfg_path)}

    def _handler(params: dict) -> dict:
        if not isinstance(params, dict):
            raise RPCDispatchError(-32602, "config.patch params must be a dict")
        params.pop("gemini_api_key", None)
        try:
            state["config"] = _patch(params, cfg_path)
        except Exception as e:
            raise RPCDispatchError(-32603, f"config.patch failed: {e}") from e
        result = state["config"].to_dict()
        result["gemini_api_key"] = "***"
        return result

    return _handler, state


# ── config.get handler ──────────────────────────────────────────────────────


class TestConfigGetHandler:
    def test_returns_config_dict(self) -> None:
        c = JarvisConfig(gemini_api_key="mykey", model="gemini-pro")
        h = _make_config_get_handler(c)
        result = h({})
        assert result["model"] == "gemini-pro"

    def test_api_key_redacted(self) -> None:
        c = JarvisConfig(gemini_api_key="mysecret")
        h = _make_config_get_handler(c)
        result = h({})
        assert result["gemini_api_key"] == "***"

    def test_api_key_empty_not_replaced(self) -> None:
        c = JarvisConfig(gemini_api_key="")
        h = _make_config_get_handler(c)
        result = h({})
        # Empty key stays empty (no "***" for missing keys)
        assert result["gemini_api_key"] == ""

    def test_gateway_port_present(self) -> None:
        c = JarvisConfig(gemini_api_key="k", gateway_port=8080)
        h = _make_config_get_handler(c)
        assert h({})["gateway_port"] == 8080

    def test_via_rpc_dispatcher(self) -> None:
        c = JarvisConfig(gemini_api_key="k", model="gemini-flash")
        d = GatewayRPCDispatcher({"config.get": _make_config_get_handler(c)})
        resp = d.dispatch(RPCRequest(method="config.get", id="1"))
        assert resp.ok
        assert resp.result["model"] == "gemini-flash"


# ── config.patch handler ────────────────────────────────────────────────────


class TestConfigPatchHandler:
    def test_patch_model(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        save_config(JarvisConfig(gemini_api_key="k", model="old-model"), cfg_path)
        h, state = _make_config_patch_handler(cfg_path)
        result = h({"model": "new-model"})
        assert result["model"] == "new-model"
        assert state["config"].model == "new-model"

    def test_patch_persists_to_disk(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        save_config(JarvisConfig(gemini_api_key="k"), cfg_path)
        h, _ = _make_config_patch_handler(cfg_path)
        h({"model": "patched"})
        reloaded = load_config(cfg_path)
        assert reloaded.model == "patched"

    def test_patch_cannot_set_api_key(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        save_config(JarvisConfig(gemini_api_key="original"), cfg_path)
        h, state = _make_config_patch_handler(cfg_path)
        result = h({"gemini_api_key": "hacked", "model": "gemini-pro"})
        # api_key stripped — stays original
        assert state["config"].gemini_api_key == "original"
        assert result["gemini_api_key"] == "***"

    def test_patch_result_redacts_api_key(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        save_config(JarvisConfig(gemini_api_key="k"), cfg_path)
        h, _ = _make_config_patch_handler(cfg_path)
        result = h({"model": "gemini-pro"})
        assert result["gemini_api_key"] == "***"

    def test_patch_preserves_unpatched_fields(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        save_config(JarvisConfig(gemini_api_key="k", gateway_port=9000), cfg_path)
        h, state = _make_config_patch_handler(cfg_path)
        h({"model": "new"})
        assert state["config"].gateway_port == 9000

    def test_patch_via_rpc_dispatcher(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        save_config(JarvisConfig(gemini_api_key="k"), cfg_path)
        h, _ = _make_config_patch_handler(cfg_path)
        dispatcher = GatewayRPCDispatcher({"config.patch": h})
        resp = dispatcher.dispatch(RPCRequest(
            method="config.patch", id="p1",
            params={"model": "gemini-ultra"}
        ))
        assert resp.ok
        assert resp.result["model"] == "gemini-ultra"

    def test_patch_via_http(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        save_config(JarvisConfig(gemini_api_key="k"), cfg_path)
        h, _ = _make_config_patch_handler(cfg_path)
        dispatcher = GatewayRPCDispatcher({"config.patch": h})
        body = json.dumps({
            "jsonrpc": "2.0", "method": "config.patch", "id": "1",
            "params": {"log_level": "DEBUG"}
        }).encode()
        result = dispatcher.handle_http("POST", "/rpc", body, {})
        assert result.get("result", {}).get("log_level") == "DEBUG"


# ── config_core + gateway integration ───────────────────────────────────────


class TestConfigCoreGatewayIntegration:
    """Full-stack: config_core → RPC dispatcher → handle_http."""

    def _make_full_dispatcher(self, tmp_path: Path) -> GatewayRPCDispatcher:
        cfg_path = tmp_path / "config.json"
        save_config(JarvisConfig(gemini_api_key="secret", model="flash"), cfg_path)
        cfg = load_config(cfg_path)
        get_h = _make_config_get_handler(cfg)
        patch_h, _ = _make_config_patch_handler(cfg_path)
        return GatewayRPCDispatcher({
            "admin.status": make_status_handler("W7"),
            "config.get": get_h,
            "config.patch": patch_h,
        })

    def test_admin_status(self, tmp_path: Path) -> None:
        d = self._make_full_dispatcher(tmp_path)
        resp = d.dispatch(RPCRequest(method="admin.status"))
        assert resp.ok
        assert resp.result["version"] == "W7"

    def test_config_get_over_http(self, tmp_path: Path) -> None:
        d = self._make_full_dispatcher(tmp_path)
        body = json.dumps({"method": "config.get", "id": "1"}).encode()
        result = d.handle_http("POST", "/rpc", body, {})
        assert result["result"]["model"] == "flash"
        assert result["result"]["gemini_api_key"] == "***"

    def test_config_patch_over_http(self, tmp_path: Path) -> None:
        d = self._make_full_dispatcher(tmp_path)
        body = json.dumps({
            "method": "config.patch", "id": "2",
            "params": {"gateway_port": 8888}
        }).encode()
        result = d.handle_http("POST", "/rpc", body, {})
        assert result["result"]["gateway_port"] == 8888

    def test_unknown_method_returns_error(self, tmp_path: Path) -> None:
        d = self._make_full_dispatcher(tmp_path)
        resp = d.dispatch(RPCRequest(method="nope.method"))
        assert not resp.ok
        assert resp.error is not None
        assert resp.error.code == -32601
