"""Tests for extensions/memory_wiki/status.py.

Phase 4.3g-mr1: ports the OpenClaw
``status.ts`` test surface. The tests
focus on:

- ``resolve_memory_wiki_status`` reports
  the right vault / Obsidian / bridge /
  unsafe-local metadata.
- The warning builder emits the right
  codes for each known failure mode.
- The doctor report turns warnings into
  actionable fixes.
- Vault walks count pages per kind
  (including nested subdirectories) and
  count source provenance per category.
- Malformed frontmatter is excluded
  from the counts.
- The status text renderer produces the
  right key: value lines.
"""

# ruff: noqa: S108 — tests use hard-coded
# ``/tmp/wiki`` paths because they're
# config-shape fixtures, not real
# filesystem paths.

# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportReturnType=false

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.memory_wiki import status as st  # noqa: E402
from extensions.memory_wiki.config import resolve_memory_wiki_config  # noqa: E402
from extensions.memory_wiki.markdown_pages import render_wiki_markdown  # noqa: E402

if TYPE_CHECKING:
    from extensions.memory_wiki.config import ResolvedMemoryWikiConfig


def _global_config(**overrides: object) -> ResolvedMemoryWikiConfig:
    raw: dict = {
        "vault": {"scope": "global", "path": "/tmp/wiki"},
    }
    raw.update(overrides)
    return resolve_memory_wiki_config(raw)


def _deps(
    *,
    path_exists: bool | None = True,
    command: str | None = None,
    artifacts: list | None = None,
    app_config: object = None,
    caller_agent_id: str | None = None,
) -> dict:
    return {
        "pathExists": (lambda _p: asyncio.sleep(0, result=path_exists))
        if path_exists is not None
        else None,
        "resolveCommand": (lambda _c: asyncio.sleep(0, result=command)),
        "listPublicArtifacts": (
            lambda _p: asyncio.sleep(0, result=artifacts if artifacts is not None else [])
        ),
        "appConfig": app_config,
        "callerAgentId": caller_agent_id,
    }


def _write_md(
    path: Path,
    *,
    page_type: str,
    id_: str,
    title: str = "T",
    source_type: str | None = None,
    provenance_mode: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm: dict = {"pageType": page_type, "id": id_, "title": title}
    if source_type is not None:
        fm["sourceType"] = source_type
    if provenance_mode is not None:
        fm["provenanceMode"] = provenance_mode
    path.write_text(
        render_wiki_markdown(frontmatter=fm, body=f"# {title}\n"),
        encoding="utf-8",
    )


class TestResolveMemoryWikiStatus:
    def test_reports_missing_vault_and_missing_obsidian(self) -> None:
        config = _global_config(obsidian={"enabled": True, "useOfficialCli": True})
        status = asyncio.run(
            st.resolve_memory_wiki_status(
                config,
                _deps(path_exists=False, command=None),
            )
        )
        assert status.vaultExists is False
        assert status.vaultScope == "global"
        assert status.agentId is None
        assert status.obsidianCli.requested is True
        assert [w.code for w in status.warnings] == [
            "vault-missing",
            "obsidian-cli-missing",
        ]
        assert status.sourceCounts == st.MemoryWikiStatusSourceCounts(
            native=0, bridge=0, bridgeEvents=0, unsafeLocal=0, other=0
        )

    def test_warns_when_unsafe_local_selected_without_private_access(self) -> None:
        config = _global_config(vaultMode="unsafe-local")
        status = asyncio.run(
            st.resolve_memory_wiki_status(
                config,
                _deps(path_exists=True, command="/usr/local/bin/obsidian"),
            )
        )
        codes = [w.code for w in status.warnings]
        assert "unsafe-local-disabled" in codes

    def test_warns_when_bridge_mode_has_no_exported_artifacts(self) -> None:
        config = _global_config(
            vaultMode="bridge",
            bridge={"enabled": True, "readMemoryArtifacts": True},
        )
        app_config = SimpleNamespace(
            agents=SimpleNamespace(list=[{"id": "main", "default": True, "workspace": "/tmp/w"}])
        )
        status = asyncio.run(
            st.resolve_memory_wiki_status(
                config,
                _deps(
                    path_exists=True,
                    command=None,
                    artifacts=[],
                    app_config=app_config,
                ),
            )
        )
        assert status.bridgePublicArtifactCount == 0
        codes = [w.code for w in status.warnings]
        assert "bridge-artifacts-missing" in codes

    def test_skips_artifact_enumeration_when_disabled(self) -> None:
        config = _global_config(
            vaultMode="bridge",
            bridge={"enabled": True, "readMemoryArtifacts": False},
        )
        calls: list[int] = []

        async def _list(_params: object) -> list[object]:
            calls.append(1)
            return []

        deps = {
            "pathExists": (lambda _p: asyncio.sleep(0, result=True)),
            "resolveCommand": (lambda _c: asyncio.sleep(0, result=None)),
            "listPublicArtifacts": _list,
            "appConfig": SimpleNamespace(agents=SimpleNamespace(list=[])),
        }
        status = asyncio.run(st.resolve_memory_wiki_status(config, deps))
        assert calls == []
        assert status.bridgePublicArtifactCount is None
        codes = [w.code for w in status.warnings]
        assert "bridge-artifacts-missing" not in codes

    def test_rejects_status_for_unresolved_agent_scoped_config(self) -> None:
        config = resolve_memory_wiki_config(
            {"vault": {"scope": "agent", "path": "/tmp/wiki/support"}}
        )
        with pytest.raises(ValueError, match="requires a resolved agent id"):
            asyncio.run(
                st.resolve_memory_wiki_status(config, _deps(path_exists=True, command=None))
            )

    def test_discovers_pages_in_nested_subdirectories(self, tmp_path: Path) -> None:
        (tmp_path / "sources" / "sub").mkdir(parents=True)
        _write_md(
            tmp_path / "sources" / "top.md",
            page_type="source",
            id_="source.top",
            title="Top",
        )
        _write_md(
            tmp_path / "sources" / "sub" / "nested.md",
            page_type="source",
            id_="source.nested",
            title="Nested",
        )
        config = resolve_memory_wiki_config({"vault": {"scope": "global", "path": str(tmp_path)}})
        status = asyncio.run(
            st.resolve_memory_wiki_status(config, _deps(path_exists=True, command=None))
        )
        assert status.pageCounts["source"] == 2
        assert status.sourceCounts.native == 2

    def test_excludes_malformed_pages_from_status_counts(self, tmp_path: Path) -> None:
        (tmp_path / "sources").mkdir(parents=True)
        # Malformed frontmatter (unclosed
        # quoted string) — the parser should
        # drop it from the counts.
        (tmp_path / "sources" / "broken.md").write_text(
            "---\npageType: source\nid: source.broken\nsourceIds:\n"
            '  - **MEMORY.md line 235**:"some quoted, value"\n---\n\n# Broken\n',
            encoding="utf-8",
        )
        _write_md(
            tmp_path / "sources" / "healthy.md",
            page_type="source",
            id_="source.healthy",
            title="Healthy",
        )
        config = resolve_memory_wiki_config({"vault": {"scope": "global", "path": str(tmp_path)}})
        status = asyncio.run(
            st.resolve_memory_wiki_status(config, _deps(path_exists=True, command=None))
        )
        assert status.pageCounts["source"] == 1
        assert status.sourceCounts.native == 1

    def test_counts_source_provenance_per_category(self, tmp_path: Path) -> None:
        (tmp_path / "sources").mkdir(parents=True)
        _write_md(
            tmp_path / "sources" / "native.md",
            page_type="source",
            id_="source.native",
            title="Native",
        )
        _write_md(
            tmp_path / "sources" / "bridge.md",
            page_type="source",
            id_="source.bridge",
            title="Bridge",
            source_type="memory-bridge",
        )
        _write_md(
            tmp_path / "sources" / "events.md",
            page_type="source",
            id_="source.events",
            title="Events",
            source_type="memory-bridge-events",
        )
        _write_md(
            tmp_path / "sources" / "unsafe.md",
            page_type="source",
            id_="source.unsafe",
            title="Unsafe",
            source_type="memory-unsafe-local",
            provenance_mode="unsafe-local",
        )
        config = resolve_memory_wiki_config({"vault": {"scope": "global", "path": str(tmp_path)}})
        status = asyncio.run(
            st.resolve_memory_wiki_status(config, _deps(path_exists=True, command=None))
        )
        assert status.pageCounts["source"] == 4
        assert status.sourceCounts == st.MemoryWikiStatusSourceCounts(
            native=1, bridge=1, bridgeEvents=1, unsafeLocal=1, other=0
        )


class TestRenderMemoryWikiStatus:
    def test_includes_warnings_in_text_output(self) -> None:
        rendered = st.render_memory_wiki_status(
            st.MemoryWikiStatus(
                vaultScope="global",
                agentId=None,
                vaultMode="isolated",
                renderMode="native",
                vaultPath="/tmp/wiki",
                vaultExists=False,
                bridge=SimpleNamespace(
                    enabled=False,
                    readMemoryArtifacts=True,
                    indexDreamReports=True,
                    indexDailyNotes=True,
                    indexMemoryRoot=True,
                    followMemoryEvents=True,
                ),
                bridgePublicArtifactCount=None,
                obsidianCli=st.MemoryWikiStatusObsidianCli(
                    enabled=True,
                    requested=True,
                    available=False,
                    command=None,
                ),
                unsafeLocal=st.MemoryWikiStatusUnsafeLocal(
                    allowPrivateMemoryCoreAccess=False,
                    pathCount=0,
                ),
                pageCounts={
                    "source": 0,
                    "entity": 0,
                    "concept": 0,
                    "synthesis": 0,
                    "report": 0,
                },
                sourceCounts=st.MemoryWikiStatusSourceCounts(
                    native=0, bridge=0, bridgeEvents=0, unsafeLocal=0, other=0
                ),
                warnings=[
                    st.MemoryWikiStatusWarning(
                        code="vault-missing",
                        message="Wiki vault has not been initialized yet.",
                    )
                ],
            )
        )
        assert "Wiki vault mode: isolated" in rendered
        assert "Vault scope: global" in rendered
        assert "Pages: 0 sources, 0 entities, 0 concepts, 0 syntheses, 0 reports" in rendered
        assert (
            "Source provenance: 0 native, 0 bridge, 0 bridge-events, 0 unsafe-local, 0 other"
            in rendered
        )
        assert "Warnings:" in rendered
        assert "Wiki vault has not been initialized yet." in rendered

    def test_renders_agent_id_in_scope_line(self) -> None:
        rendered = st.render_memory_wiki_status(
            st.MemoryWikiStatus(
                vaultScope="agent",
                agentId="support",
                vaultMode="isolated",
                renderMode="native",
                vaultPath="/tmp/wiki",
                vaultExists=True,
                bridge=SimpleNamespace(
                    enabled=False,
                    readMemoryArtifacts=True,
                    indexDreamReports=True,
                    indexDailyNotes=True,
                    indexMemoryRoot=True,
                    followMemoryEvents=True,
                ),
                bridgePublicArtifactCount=None,
                obsidianCli=st.MemoryWikiStatusObsidianCli(
                    enabled=False, requested=False, available=False, command=None
                ),
                unsafeLocal=st.MemoryWikiStatusUnsafeLocal(
                    allowPrivateMemoryCoreAccess=False, pathCount=0
                ),
                pageCounts={
                    "source": 0,
                    "entity": 0,
                    "concept": 0,
                    "synthesis": 0,
                    "report": 0,
                },
                sourceCounts=st.MemoryWikiStatusSourceCounts(
                    native=0, bridge=0, bridgeEvents=0, unsafeLocal=0, other=0
                ),
                warnings=[],
            )
        )
        assert "Vault scope: agent (support)" in rendered


class TestDoctor:
    def test_builds_actionable_fixes_from_status_warnings(self) -> None:
        config = _global_config(obsidian={"enabled": True, "useOfficialCli": True})
        status = asyncio.run(
            st.resolve_memory_wiki_status(config, _deps(path_exists=False, command=None))
        )
        report = st.build_memory_wiki_doctor_report(status)
        rendered = st.render_memory_wiki_doctor(report)
        assert report.healthy is False
        assert report.warningCount == 2
        assert [f.code for f in report.fixes] == [
            "vault-missing",
            "obsidian-cli-missing",
        ]
        assert "Suggested fixes:" in rendered
        assert "openclaw wiki init" in rendered

    def test_suggests_bridge_fixes_when_no_artifacts(self) -> None:
        config = _global_config(
            vaultMode="bridge",
            bridge={"enabled": True, "readMemoryArtifacts": True},
        )
        app_config = SimpleNamespace(agents=SimpleNamespace(list=[{"id": "main", "default": True}]))
        status = asyncio.run(
            st.resolve_memory_wiki_status(
                config,
                _deps(path_exists=True, command=None, artifacts=[], app_config=app_config),
            )
        )
        report = st.build_memory_wiki_doctor_report(status)
        assert "bridge-artifacts-missing" in [f.code for f in report.fixes]
        assert "exports public artifacts" in st.render_memory_wiki_doctor(report)


class TestReset:
    def test_reset_returns_none(self) -> None:
        assert st.reset_memory_wiki_status_state_for_tests() is None


class TestExports:
    def test_all_exports(self) -> None:
        for name in (
            "WIKI_STATUS_WARNING_CODES",
            "MemoryWikiDoctorFix",
            "MemoryWikiDoctorReport",
            "MemoryWikiStatus",
            "MemoryWikiStatusObsidianCli",
            "MemoryWikiStatusSourceCounts",
            "MemoryWikiStatusUnsafeLocal",
            "MemoryWikiStatusWarning",
            "build_memory_wiki_doctor_report",
            "build_warnings",
            "render_memory_wiki_doctor",
            "render_memory_wiki_status",
            "reset_memory_wiki_status_state_for_tests",
            "resolve_memory_wiki_status",
        ):
            assert hasattr(st, name), f"missing export: {name}"
