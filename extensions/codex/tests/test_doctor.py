"""Tests for Codex managed app-server doctor check.

OpenClaw parity: ``extensions/codex/src/doctor.test.ts``.
"""

from __future__ import annotations

import os
import tempfile

from extensions.codex.src.doctor import (
    CODEX_MANAGED_APP_SERVER_CHECK_ID,
    check_codex_managed_app_server,
    parse_codex_version,
)


def test_parse_codex_version():
    assert parse_codex_version("codex 0.153.4") == "0.153.4"
    assert parse_codex_version("codex-app-server v0.149.0-alpha.1") == "0.149.0-alpha.1"
    assert parse_codex_version("invalid output") is None


def test_doctor_check_missing_binary():
    with tempfile.TemporaryDirectory() as tmpdir:
        findings = check_codex_managed_app_server(plugin_root=tmpdir)
        assert len(findings) == 1
        assert findings[0].check_id == CODEX_MANAGED_APP_SERVER_CHECK_ID
        assert findings[0].severity == "error"
        assert "Reinstall" in (findings[0].fix_hint or "")


def test_doctor_check_valid_version():
    with tempfile.TemporaryDirectory() as tmpdir:
        bin_dir = os.path.join(tmpdir, "vendor")
        os.makedirs(bin_dir, exist_ok=True)
        bin_path = os.path.join(bin_dir, "codex.exe")
        with open(bin_path, "w") as f:
            f.write("mock binary")

        def mock_version_runner(cmd: str) -> str:
            return "codex 0.153.4"

        findings = check_codex_managed_app_server(
            plugin_root=tmpdir,
            version_runner=mock_version_runner,
        )
        assert len(findings) == 0


def test_doctor_check_floor_version_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        bin_dir = os.path.join(tmpdir, "vendor")
        os.makedirs(bin_dir, exist_ok=True)
        bin_path = os.path.join(bin_dir, "codex.exe")
        with open(bin_path, "w") as f:
            f.write("mock binary")

        def mock_version_runner(cmd: str) -> str:
            return "codex 0.145.0"

        findings = check_codex_managed_app_server(
            plugin_root=tmpdir,
            version_runner=mock_version_runner,
        )
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "below minimum supported version" in findings[0].message


def test_doctor_check_rejects_unverified_wrapper_binary():
    with tempfile.TemporaryDirectory() as tmpdir:
        bin_dir = os.path.join(tmpdir, "vendor")
        os.makedirs(bin_dir, exist_ok=True)
        bin_path = os.path.join(bin_dir, "codex.exe")
        with open(bin_path, "w") as f:
            f.write("#!/usr/bin/env bash\necho wrapper\n")

        findings = check_codex_managed_app_server(plugin_root=tmpdir)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "official @openai/codex package" in findings[0].message
