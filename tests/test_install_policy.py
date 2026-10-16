"""Tests for src/security/install_policy.py.

Mirrors tests of docs/tools/skills-config.md and src/security/install-policy.ts in OpenClaw.
"""

from __future__ import annotations

import sys

from src.security.install_policy import (
    InstallPolicyExecConfig,
    evaluate_install_policy,
)


def test_evaluate_install_policy_allow(tmp_path):
    # Create a mock policy python script that returns allow
    script = tmp_path / "policy.py"
    script.write_text(
        "import sys, json; req = json.load(sys.stdin); print(json.dumps({'protocolVersion': 1, 'decision': 'allow'}))",
        encoding="utf-8",
    )

    exec_cfg = InstallPolicyExecConfig(
        command=sys.executable,
        args=[str(script)],
    )

    res = evaluate_install_policy(
        exec_config=exec_cfg,
        target_type="skill",
        target_name="weather",
        source_path=str(tmp_path),
    )

    assert res.decision == "allow"


def test_evaluate_install_policy_block(tmp_path):
    script = tmp_path / "policy_block.py"
    script.write_text(
        "import sys, json; print(json.dumps({'protocolVersion': 1, 'decision': 'block', 'reason': 'unapproved'}))",
        encoding="utf-8",
    )

    exec_cfg = InstallPolicyExecConfig(
        command=sys.executable,
        args=[str(script)],
    )

    res = evaluate_install_policy(
        exec_config=exec_cfg,
        target_type="plugin",
        target_name="my-plugin",
        source_path=str(tmp_path),
    )

    assert res.decision == "block"
    assert res.reason == "unapproved"


def test_evaluate_install_policy_missing_cmd(tmp_path):
    exec_cfg = InstallPolicyExecConfig(command="/nonexistent/path/cmd")
    res = evaluate_install_policy(
        exec_config=exec_cfg,
        target_type="skill",
        target_name="test",
        source_path=str(tmp_path),
    )
    assert res.decision == "block"
    assert "does not exist" in (res.reason or "")
