"""Tests for extensions/memory_wiki/bridge.py.

Phase 4.3f-mr2: ports the OpenClaw
``bridge.ts`` helpers (the artifact sync
loop lands in 4.3g alongside
``source-page-shared``). The tests focus on:

- ``resolve_memory_wiki_vault_agent_id``
  returns ``None`` for global scope and the
  agent id (normalized) for agent scope.
- ``filter_memory_wiki_bridge_artifacts``
  drops artifacts that don't belong to the
  vault's agent.
- ``should_import_bridge_artifact`` honors
  the four boolean toggles.
- ``is_path_inside_or_equal`` correctly
  detects inside / outside relationships.
- ``collect_bridge_artifacts`` dedupes by
  ``syncKey`` + drops in-vault artifacts.
- ``resolve_bridge_title`` builds the
  expected title for ``markdown`` and
  ``memory-events`` artifacts.
- ``resolve_bridge_page_path`` produces a
  stable ``pageId`` + ``pagePath``.
- ``build_bridge_page_body`` emits the
  human-notes block + the raw-source marker.
"""

# ruff: noqa: S108 — the "/tmp/..." paths are test fixtures mirroring the OpenClaw TS source

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

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.memory_wiki.bridge import (  # noqa: E402
    BRIDGE_IMPORT_KINDS,
    BridgeArtifact,
    build_bridge_page_body,
    collect_bridge_artifacts,
    filter_memory_wiki_bridge_artifacts,
    is_path_inside_or_equal,
    resolve_bridge_page_path,
    resolve_bridge_render_fingerprint,
    resolve_bridge_title,
    resolve_memory_wiki_vault_agent_id,
    should_import_bridge_artifact,
)


def _config(*, scope: str = "global", agent_id: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        vault=SimpleNamespace(scope=scope),
        agentId=agent_id,
    )


def _bridge_config(
    *,
    index_memory_root: bool = True,
    index_daily_notes: bool = True,
    index_dream_reports: bool = True,
    follow_memory_events: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        indexMemoryRoot=index_memory_root,
        indexDailyNotes=index_daily_notes,
        indexDreamReports=index_dream_reports,
        followMemoryEvents=follow_memory_events,
    )


def _artifact(
    *,
    kind: str = "daily-note",
    workspace_dir: str = "/tmp/agent-a/workspace",
    relative_path: str = "memory/2026-07-21.md",
    absolute_path: str = "/tmp/agent-a/workspace/memory/2026-07-21.md",
    agent_ids: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        kind=kind,
        workspaceDir=workspace_dir,
        relativePath=relative_path,
        absolutePath=absolute_path,
        agentIds=agent_ids or [],
    )


class TestResolveVaultAgentId:
    def test_global_returns_none(self) -> None:
        assert resolve_memory_wiki_vault_agent_id(_config(scope="global")) is None

    def test_agent_returns_normalized_id(self) -> None:
        result = resolve_memory_wiki_vault_agent_id(_config(scope="agent", agent_id="alpha-1"))
        assert result == "alpha-1"

    def test_agent_scope_without_id_raises(self) -> None:
        with pytest.raises(ValueError, match="agent id"):
            resolve_memory_wiki_vault_agent_id(_config(scope="agent", agent_id=None))

    def test_agent_scope_with_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="agent id"):
            resolve_memory_wiki_vault_agent_id(_config(scope="agent", agent_id="   "))


class TestFilterBridgeArtifacts:
    def test_global_scope_passes_all(self) -> None:
        artifacts = [
            _artifact(agent_ids=["a"]),
            _artifact(agent_ids=["b"]),
        ]
        result = filter_memory_wiki_bridge_artifacts(
            config=_config(scope="global"), artifacts=artifacts
        )
        assert result == artifacts

    def test_agent_scope_filters_by_agent(self) -> None:
        artifacts = [
            _artifact(agent_ids=["a"]),
            _artifact(agent_ids=["b"]),
            _artifact(agent_ids=["a", "c"]),
        ]
        result = filter_memory_wiki_bridge_artifacts(
            config=_config(scope="agent", agent_id="a"),
            artifacts=artifacts,
        )
        # Only the artifacts owned by ``a``.
        assert len(result) == 2
        assert all(a.agentIds == ["a"] or "a" in a.agentIds for a in result)

    def test_caller_agent_id_fills_in_for_global(self) -> None:
        artifacts = [
            _artifact(agent_ids=["a"]),
            _artifact(agent_ids=["b"]),
        ]
        result = filter_memory_wiki_bridge_artifacts(
            config=_config(scope="global"),
            artifacts=artifacts,
            caller_agent_id="a",
        )
        # Global scope + caller agent → still
        # filters (the caller is the diagnostic
        # owner).
        assert len(result) == 1
        assert result[0].agentIds == ["a"]

    def test_empty_artifact_list(self) -> None:
        result = filter_memory_wiki_bridge_artifacts(
            config=_config(scope="agent", agent_id="a"),
            artifacts=[],
        )
        assert result == []


class TestShouldImportBridgeArtifact:
    def test_all_enabled(self) -> None:
        config = _bridge_config()
        assert should_import_bridge_artifact(kind="memory-root", bridge_config=config)
        assert should_import_bridge_artifact(kind="daily-note", bridge_config=config)
        assert should_import_bridge_artifact(kind="dream-report", bridge_config=config)
        assert should_import_bridge_artifact(kind="event-log", bridge_config=config)

    def test_unknown_kind_returns_false(self) -> None:
        assert should_import_bridge_artifact(kind="bogus", bridge_config=_bridge_config()) is False

    def test_disabled_per_kind(self) -> None:
        config = _bridge_config(index_memory_root=False, follow_memory_events=False)
        assert should_import_bridge_artifact(kind="memory-root", bridge_config=config) is False
        assert should_import_bridge_artifact(kind="event-log", bridge_config=config) is False
        # ``daily-note`` + ``dream-report``
        # still enabled.
        assert should_import_bridge_artifact(kind="daily-note", bridge_config=config)
        assert should_import_bridge_artifact(kind="dream-report", bridge_config=config)

    def test_kinds_set(self) -> None:
        assert (
            frozenset({"memory-root", "daily-note", "dream-report", "event-log"})
            == BRIDGE_IMPORT_KINDS
        )


class TestIsPathInsideOrEqual:
    def test_inside(self, tmp_path: Path) -> None:
        parent = str(tmp_path)
        child = str(tmp_path / "sub" / "file.md")
        assert is_path_inside_or_equal(parent, child) is True

    def test_equal(self, tmp_path: Path) -> None:
        assert is_path_inside_or_equal(str(tmp_path), str(tmp_path)) is True

    def test_outside_sibling(self, tmp_path: Path) -> None:
        other = tmp_path.parent / "other"
        assert is_path_inside_or_equal(str(tmp_path), str(other)) is False


class TestCollectBridgeArtifacts:
    def test_filters_disabled_kinds(self, tmp_path: Path) -> None:
        vault = str(tmp_path)
        config = _bridge_config(index_dream_reports=False)
        artifacts = [
            _artifact(kind="daily-note"),
            _artifact(kind="dream-report"),
            _artifact(kind="event-log"),
        ]
        collected = collect_bridge_artifacts(
            bridge_config=config,
            vault_root=vault,
            artifacts=artifacts,
        )
        kinds = {a.artifact_type for a in collected}
        # ``dream-report`` is filtered out.
        assert "memory-events" in kinds
        assert all(a.sync_key for a in collected)

    def test_drops_in_vault_artifacts(self, tmp_path: Path) -> None:
        vault = str(tmp_path)
        config = _bridge_config()
        # An artifact that already lives
        # inside the vault should be dropped.
        in_vault = _artifact(
            workspace_dir=vault,
            relative_path="entities/alpha.md",
            absolute_path=str(tmp_path / "entities" / "alpha.md"),
        )
        outside = _artifact(
            workspace_dir="/tmp/other",
            relative_path="memory/x.md",
            absolute_path="/tmp/other/memory/x.md",
        )
        collected = collect_bridge_artifacts(
            bridge_config=config,
            vault_root=vault,
            artifacts=[in_vault, outside],
        )
        # Only the outside artifact survives.
        assert len(collected) == 1
        assert collected[0].workspace_dir == "/tmp/other"

    def test_dedupes_by_sync_key(self, tmp_path: Path) -> None:
        config = _bridge_config()
        a = _artifact(absolute_path="/tmp/other/x.md")
        b = _artifact(absolute_path="/tmp/other/x.md")
        collected = collect_bridge_artifacts(
            bridge_config=config,
            vault_root=str(tmp_path),
            artifacts=[a, b],
        )
        assert len(collected) == 1

    def test_event_log_artifact_type(self, tmp_path: Path) -> None:
        config = _bridge_config()
        artifact = _artifact(
            kind="event-log",
            absolute_path="/tmp/other/events.jsonl",
        )
        collected = collect_bridge_artifacts(
            bridge_config=config,
            vault_root=str(tmp_path),
            artifacts=[artifact],
        )
        assert collected[0].artifact_type == "memory-events"


class TestResolveBridgeTitle:
    def test_markdown_title_without_agents(self) -> None:
        artifact = BridgeArtifact(
            sync_key="k",
            artifact_type="markdown",
            workspace_dir="/tmp/ws",
            relative_path="memory/2026-07-21.md",
            absolute_path="/tmp/ws/memory/2026-07-21.md",
        )
        title = resolve_bridge_title(artifact=artifact, agent_ids=[])
        assert "2026-07-21" in title
        assert title.startswith("Memory Bridge:")

    def test_markdown_title_with_agents(self) -> None:
        artifact = BridgeArtifact(
            sync_key="k",
            artifact_type="markdown",
            workspace_dir="/tmp/ws",
            relative_path="memory/foo.md",
            absolute_path="/tmp/ws/memory/foo.md",
        )
        title = resolve_bridge_title(artifact=artifact, agent_ids=["a", "b"])
        assert "a, b" in title

    def test_memory_events_title(self) -> None:
        artifact = BridgeArtifact(
            sync_key="k",
            artifact_type="memory-events",
            workspace_dir="/tmp/ws",
            relative_path="events.jsonl",
            absolute_path="/tmp/ws/events.jsonl",
        )
        assert "event journal" in resolve_bridge_title(artifact=artifact, agent_ids=[])
        assert "agent-x" in resolve_bridge_title(artifact=artifact, agent_ids=["agent-x"])


class TestResolveBridgePagePath:
    def test_returns_expected_shape(self) -> None:
        out = resolve_bridge_page_path(
            workspace_dir="/tmp/agent-a/workspace",
            relative_path="memory/2026-07-21.md",
        )
        assert out["pagePath"].startswith("sources/")
        assert out["pagePath"].endswith(".md")
        assert out["pageId"].startswith("source.bridge.")
        # Slugs are stable for the same input.
        out2 = resolve_bridge_page_path(
            workspace_dir="/tmp/agent-a/workspace",
            relative_path="memory/2026-07-21.md",
        )
        assert out == out2

    def test_different_workspaces_produce_different_paths(self) -> None:
        out_a = resolve_bridge_page_path(
            workspace_dir="/tmp/ws-a",
            relative_path="memory/x.md",
        )
        out_b = resolve_bridge_page_path(
            workspace_dir="/tmp/ws-b",
            relative_path="memory/x.md",
        )
        assert out_a["pageId"] != out_b["pageId"]


class TestResolveBridgeRenderFingerprint:
    def test_stable_for_same_input(self) -> None:
        artifact = BridgeArtifact(
            sync_key="k",
            artifact_type="markdown",
            workspace_dir="/tmp/ws",
            relative_path="memory/x.md",
            absolute_path="/tmp/ws/memory/x.md",
        )
        f1 = resolve_bridge_render_fingerprint(artifact=artifact, agent_ids=["a"])
        f2 = resolve_bridge_render_fingerprint(artifact=artifact, agent_ids=["a"])
        assert f1 == f2

    def test_changes_with_agents(self) -> None:
        artifact = BridgeArtifact(
            sync_key="k",
            artifact_type="markdown",
            workspace_dir="/tmp/ws",
            relative_path="memory/x.md",
            absolute_path="/tmp/ws/memory/x.md",
        )
        f1 = resolve_bridge_render_fingerprint(artifact=artifact, agent_ids=["a"])
        f2 = resolve_bridge_render_fingerprint(artifact=artifact, agent_ids=["a", "b"])
        assert f1 != f2


class TestBuildBridgePageBody:
    def test_includes_human_notes_block(self) -> None:
        artifact = BridgeArtifact(
            sync_key="k",
            artifact_type="markdown",
            workspace_dir="/tmp/ws",
            relative_path="memory/x.md",
            absolute_path="/tmp/ws/memory/x.md",
        )
        body = build_bridge_page_body(
            artifact=artifact,
            title="Memory Bridge: x",
            raw="# x\n\nbody\n",
            agent_ids=["a"],
            updated_at="2026-07-21T00:00:00.000Z",
        )
        assert "<!-- openclaw:human:start -->" in body
        assert "<!-- openclaw:human:end -->" in body
        assert "## Bridge Source" in body
        assert "## Content" in body
        assert "```markdown" in body
        assert "# x" in body

    def test_event_log_uses_json_fence(self) -> None:
        artifact = BridgeArtifact(
            sync_key="k",
            artifact_type="memory-events",
            workspace_dir="/tmp/ws",
            relative_path="events.jsonl",
            absolute_path="/tmp/ws/events.jsonl",
        )
        body = build_bridge_page_body(
            artifact=artifact,
            title="event journal",
            raw='{"event":"x"}\n',
            agent_ids=[],
            updated_at="2026-07-21T00:00:00.000Z",
        )
        assert "```json" in body
        assert '{"event":"x"}' in body

    def test_no_agents_falls_back_to_unknown(self) -> None:
        artifact = BridgeArtifact(
            sync_key="k",
            artifact_type="markdown",
            workspace_dir="/tmp/ws",
            relative_path="memory/x.md",
            absolute_path="/tmp/ws/memory/x.md",
        )
        body = build_bridge_page_body(
            artifact=artifact,
            title="t",
            raw="r",
            agent_ids=[],
            updated_at="2026-07-21T00:00:00.000Z",
        )
        assert "Agents: unknown" in body
