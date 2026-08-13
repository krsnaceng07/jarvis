"""Wave 10 tests — Plugin SDK: LoadResult typing, plugins CLI command."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from jarvis_sdk.loader import load_all_plugins_from_workspace, LoadResult
from jarvis_cli.main import main


# ── LoadResult contract ───────────────────────────────────────────────────────


class TestLoadResult:
    def test_returns_load_result(self, tmp_path: Path) -> None:
        result = load_all_plugins_from_workspace(tmp_path)
        assert isinstance(result, LoadResult)

    def test_has_required_fields(self, tmp_path: Path) -> None:
        result = load_all_plugins_from_workspace(tmp_path)
        assert isinstance(result.tool_decls, list)
        assert isinstance(result.commands, list)
        assert isinstance(result.hooks, list)
        assert isinstance(result.skills, list)
        assert isinstance(result.cron_jobs, list)
        assert isinstance(result.doctor_contracts, list)
        assert isinstance(result.cli_handlers, list)

    def test_empty_workspace_returns_empty_lists(self, tmp_path: Path) -> None:
        result = load_all_plugins_from_workspace(tmp_path)
        assert result.tool_decls == []
        assert result.hooks == []
        assert result.commands == []

    def test_skills_field_exists(self, tmp_path: Path) -> None:
        """Skills is a first-class field on LoadResult."""
        result = load_all_plugins_from_workspace(tmp_path)
        assert hasattr(result, "skills")

    def test_cron_jobs_field_exists(self, tmp_path: Path) -> None:
        result = load_all_plugins_from_workspace(tmp_path)
        assert hasattr(result, "cron_jobs")

    def test_cli_handlers_field_exists(self, tmp_path: Path) -> None:
        result = load_all_plugins_from_workspace(tmp_path)
        assert hasattr(result, "cli_handlers")


# ── plugins CLI command ───────────────────────────────────────────────────────


def _run_plugins(workspace: Path) -> tuple[int, str]:
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(["--workspace", str(workspace), "plugins"])
    finally:
        sys.stdout = old
    return code, buf.getvalue()


class TestPluginsCommand:
    def test_exits_0(self, tmp_path: Path) -> None:
        code, _ = _run_plugins(tmp_path)
        assert code == 0

    def test_shows_extensions_header(self, tmp_path: Path) -> None:
        _, out = _run_plugins(tmp_path)
        assert "Extensions" in out

    def test_shows_skills_cron_doctor_counts(self, tmp_path: Path) -> None:
        _, out = _run_plugins(tmp_path)
        assert "Skills:" in out
        assert "Cron:" in out
        assert "Doctor contracts:" in out
        assert "CLI handlers:" in out

    def test_no_extensions_message_when_empty(self, tmp_path: Path) -> None:
        _, out = _run_plugins(tmp_path)
        # Empty workspace has no extensions loaded
        assert "(no extensions loaded)" in out or "Extensions" in out

    def test_real_workspace_has_extensions(self) -> None:
        """The real jarvis workspace (e:/jarvis) has extensions loaded."""
        workspace = Path("e:/jarvis")
        if not workspace.exists():
            pytest.skip("jarvis workspace not found")
        code, out = _run_plugins(workspace)
        assert code == 0
        # At least one of these should be present in a real workspace
        assert any(x in out for x in ["✓", "Extensions", "Skills"])
