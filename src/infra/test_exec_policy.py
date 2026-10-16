"""Tests for exec_policy layer merging and mode resolvers.

OpenClaw parity: mirrors ``openclaw-main/src/infra/exec-approvals-policy.test.ts``.
"""

from src.infra.exec_approvals import (
    resolve_exec_mode_from_policy,
    resolve_exec_mode_policy,
)
from src.infra.exec_policy import apply_exec_policy_layer


def test_resolve_exec_mode_from_policy() -> None:
    assert resolve_exec_mode_from_policy("deny", "off") == "deny"
    assert resolve_exec_mode_from_policy("allowlist", "off") == "allowlist"
    assert resolve_exec_mode_from_policy("allowlist", "on-miss") == "ask"
    assert resolve_exec_mode_from_policy("full", "off") == "full"


def test_resolve_exec_mode_policy() -> None:
    # Uses provided mode
    res1 = resolve_exec_mode_policy("auto", "deny", "off")
    assert res1 == {"mode": "auto", "security": "allowlist", "ask": "on-miss", "autoReview": True}
    
    # Derives mode from base security/ask if mode is missing
    res2 = resolve_exec_mode_policy(None, "allowlist", "on-miss")
    assert res2 == {"mode": "ask", "security": "allowlist", "ask": "on-miss", "autoReview": False}


def test_apply_exec_policy_layer_no_layer() -> None:
    base = {"security": "allowlist", "ask": "off"}
    assert apply_exec_policy_layer(base, None) == base


def test_apply_exec_policy_layer_mode_override() -> None:
    base = {"security": "deny", "ask": "off"}
    layer = {"mode": "auto"}
    merged = apply_exec_policy_layer(base, layer)
    assert merged["mode"] == "auto"
    assert merged["security"] == "allowlist"
    assert merged["ask"] == "on-miss"


def test_apply_exec_policy_layer_raw_security_override_strips_mode() -> None:
    base = {"mode": "auto", "security": "allowlist", "ask": "on-miss"}
    layer = {"security": "full"}
    merged = apply_exec_policy_layer(base, layer)
    assert "mode" not in merged
    assert merged["security"] == "full"
    assert merged["ask"] == "on-miss"


def test_apply_exec_policy_layer_raw_ask_override_strips_mode() -> None:
    base = {"mode": "auto", "security": "allowlist", "ask": "on-miss"}
    layer = {"ask": "off"}
    merged = apply_exec_policy_layer(base, layer)
    assert "mode" not in merged
    assert merged["security"] == "allowlist"
    assert merged["ask"] == "off"
