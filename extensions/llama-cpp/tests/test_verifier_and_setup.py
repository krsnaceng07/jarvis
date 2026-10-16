"""Unit tests for model candidate verifier, setup diagnostics, and doctor repairs."""

from __future__ import annotations

from typing import Any

import pytest

from extensions.llama_cpp.src.config import (
    LlamaCppConfig,
    LlamaCppLocalServiceConfig,
)
from extensions.llama_cpp.src.doctor import run_llama_cpp_doctor
from extensions.llama_cpp.src.setup import get_llama_cpp_setup_status
from extensions.llama_cpp.src.verifier import verify_managed_model_candidate


@pytest.mark.asyncio
async def test_verifier_success_flow() -> None:
    async def _mock_handler(phase: str, prompt: str) -> dict[str, Any]:
        if phase == "response_check":
            return {"ok": True, "reply": "pong"}
        if phase == "tool_check":
            return {"ok": True, "tool_called": True, "result": "secret_content"}
        return {"ok": False}

    res = await verify_managed_model_candidate(
        model_id="qwen3.8-27b",
        endpoint="http://127.0.0.1:8080",
        simulated_model_handler=_mock_handler,
    )
    assert res.is_ok
    rep = res.unwrap()
    assert rep.ok is True
    assert rep.response_check_passed is True
    assert rep.tool_check_passed is True


@pytest.mark.asyncio
async def test_verifier_tool_check_failure() -> None:
    # Model replies with plain text only without executing tool call
    async def _mock_handler(phase: str, prompt: str) -> dict[str, Any]:
        if phase == "response_check":
            return {"ok": True, "reply": "pong"}
        if phase == "tool_check":
            # Failed tool check: plain text reply without calling tool
            return {"ok": False, "tool_called": False, "reply": "Here is the file content"}
        return {"ok": False}

    res = await verify_managed_model_candidate(
        model_id="qwen3.8-27b",
        endpoint="http://127.0.0.1:8080",
        simulated_model_handler=_mock_handler,
    )
    assert res.is_ok
    rep = res.unwrap()
    assert rep.ok is False
    assert rep.response_check_passed is True
    assert rep.tool_check_passed is False
    assert rep.error_phase == "tool_check"
    assert "plain text without calling the required tool" in (rep.error_message or "")


def test_setup_status_managed_vs_existing() -> None:
    # 1. Managed mode setup check
    cfg_managed = LlamaCppConfig(
        enabled=True,
        local_service=LlamaCppLocalServiceConfig(model_path="models/qwen.gguf"),
    )
    st_managed = get_llama_cpp_setup_status(cfg_managed)
    assert st_managed.ok is True
    check_ids = {c.id: c.ok for c in st_managed.checks}
    assert check_ids["llama-cpp-enabled"] is True
    assert check_ids["execution-backend"] is True
    assert check_ids["hardware-recommendation"] is True

    # 2. Existing server mode setup check
    cfg_existing = LlamaCppConfig(
        enabled=True,
        base_url="http://127.0.0.1:8080/v1",
        local_service=None,
    )
    st_existing = get_llama_cpp_setup_status(cfg_existing)
    assert st_existing.ok is True
    check_ids_ext = {c.id: c.ok for c in st_existing.checks}
    assert check_ids_ext["existing-server-mode"] is True


@pytest.mark.asyncio
async def test_doctor_repairs() -> None:
    raw_cfg = {
        "localService": {"modelPath": "qwen.gguf"},
        "authProfile": "stale_external_profile",
        "baseUrl": "http://admin:pass@127.0.0.1:8080/v1",
    }

    # Diagnosis only
    res_diag = await run_llama_cpp_doctor(raw_cfg, fix=False)
    assert res_diag.is_ok
    assert len(res_diag.unwrap()["repairs"]) == 2
    assert res_diag.unwrap()["fixed"] is False

    # Auto-fix
    res_fix = await run_llama_cpp_doctor(raw_cfg, fix=True)
    assert res_fix.is_ok
    data_fix = res_fix.unwrap()
    assert data_fix["fixed"] is True
    assert "authProfile" not in data_fix["config"]
    assert "@" not in data_fix["config"]["baseUrl"]
