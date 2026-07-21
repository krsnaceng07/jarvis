"""Tests for extensions/memory_wiki/config.py.

Phase 4.3b: ports the OpenClaw config helpers
(``resolveMemoryWikiConfig``,
``resolveMemoryWikiAgentConfig``,
``resolveMemoryWikiConfiguredAgentIds``,
``expandHomePath``,
``resolveDefaultMemoryWikiVaultPath`` /
``resolveDefaultMemoryWikiVaultRoot``,
``memoryWikiConfigSchema``). The tests focus on:

- The schema's ``safeParse`` shape: ``None`` input
  resolves to defaults; valid input resolves to a
  populated config; invalid input returns
  ``{"issues": [...]}`` with the OpenClaw field-path
  shape.
- Defaults match the OpenClaw constants
  (``isolated`` vaultMode, ``global`` scope, ``native``
  renderMode, ``shared`` search backend, ``wiki``
  search corpus, etc.).
- Homedir expansion (``~`` / ``~/foo``) is applied to
  ``vault.path``.
- The two cross-field rules
  (``vaultMode=unsafe-local`` +
  ``vault.scope=agent`` → invalid; ``obsidian.
  useOfficialCli=true`` + ``vault.scope=agent`` →
  invalid).
- ``resolveMemoryWikiAgentConfig`` returns the
  input unchanged for ``vault.scope=global``;
  appends the agent id to ``vault.path`` for
  ``vault.scope=agent``; raises on
  ``vaultMode=unsafe-local`` + ``vault.scope=agent``;
  raises when no ``agentId`` is given in multi-agent
  setups.
"""

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
# pyright: reportTypedDictNotRequiredAccess=false
# pyright: reportOperatorIssue=false
# pyright: reportAssignmentType=false

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.memory_wiki.config import (  # noqa: E402
    DEFAULT_WIKI_RENDER_MODE,
    DEFAULT_WIKI_SEARCH_BACKEND,
    DEFAULT_WIKI_SEARCH_CORPUS,
    DEFAULT_WIKI_VAULT_MODE,
    DEFAULT_WIKI_VAULT_SCOPE,
    expand_home_path,
    memory_wiki_config_schema,
    resolve_default_memory_wiki_vault_path,
    resolve_default_memory_wiki_vault_root,
    resolve_memory_wiki_agent_config,
    resolve_memory_wiki_config,
    resolve_memory_wiki_configured_agent_ids,
)


class TestSchemaSafeParse:
    def test_none_input_resolves_to_defaults(self) -> None:
        ok, payload = memory_wiki_config_schema.safe_parse(None)
        assert ok is True
        assert isinstance(payload, object)
        resolved = payload  # type: ignore[assignment]
        assert resolved.vaultMode == DEFAULT_WIKI_VAULT_MODE
        assert resolved.vault.scope == DEFAULT_WIKI_VAULT_SCOPE
        assert resolved.vault.renderMode == DEFAULT_WIKI_RENDER_MODE
        assert resolved.search.backend == DEFAULT_WIKI_SEARCH_BACKEND
        assert resolved.search.corpus == DEFAULT_WIKI_SEARCH_CORPUS
        assert resolved.obsidian.enabled is False
        assert resolved.ingest.autoCompile is True
        assert resolved.render.preserveHumanBlocks is True

    def test_valid_input_resolves(self) -> None:
        ok, payload = memory_wiki_config_schema.safe_parse(
            {
                "vaultMode": "bridge",
                "vault": {"scope": "agent", "path": "~/wiki"},
                "bridge": {"enabled": True, "readMemoryArtifacts": False},
            }
        )
        assert ok is True
        resolved = payload  # type: ignore[assignment]
        assert resolved.vaultMode == "bridge"
        assert resolved.vault.scope == "agent"
        assert resolved.bridge.enabled is True
        assert resolved.bridge.readMemoryArtifacts is False

    def test_invalid_input_returns_issues(self) -> None:
        ok, payload = memory_wiki_config_schema.safe_parse({"vaultMode": "not-a-mode"})
        assert ok is False
        assert "issues" in payload
        assert any(issue["path"] == ["vaultMode"] for issue in payload["issues"])

    def test_non_object_input_rejected(self) -> None:
        ok, payload = memory_wiki_config_schema.safe_parse("nope")
        assert ok is False
        assert payload["issues"]


class TestCrossFieldRules:
    def test_unsafe_local_plus_agent_scope_is_invalid(self) -> None:
        ok, payload = memory_wiki_config_schema.safe_parse(
            {"vaultMode": "unsafe-local", "vault": {"scope": "agent"}}
        )
        assert ok is False
        assert any("unsafe-local" in issue["message"] for issue in payload["issues"])

    def test_official_cli_plus_agent_scope_is_invalid(self) -> None:
        ok, payload = memory_wiki_config_schema.safe_parse(
            {
                "vault": {"scope": "agent"},
                "obsidian": {"useOfficialCli": True},
            }
        )
        assert ok is False
        assert any("useOfficialCli" in issue["message"] for issue in payload["issues"])

    def test_global_scope_allows_official_cli(self) -> None:
        ok, _ = memory_wiki_config_schema.safe_parse(
            {
                "vault": {"scope": "global"},
                "obsidian": {"useOfficialCli": True},
            }
        )
        assert ok is True


class TestResolveMemoryWikiConfig:
    def test_default_vault_path_global(self) -> None:
        resolved = resolve_memory_wiki_config(None, homedir="/home/tester")
        # Use os.path.join to match the platform's
        # separator (the implementation calls
        # ``os.path.join``; on Windows that produces
        # backslashes, on POSIX forward slashes).
        assert resolved.vault.path == os.path.join("/home/tester", ".openclaw", "wiki", "main")

    def test_default_vault_path_agent(self) -> None:
        resolved = resolve_memory_wiki_config({"vault": {"scope": "agent"}}, homedir="/home/tester")
        assert resolved.vault.path == os.path.join("/home/tester", ".openclaw", "wiki")

    def test_home_expansion(self) -> None:
        resolved = resolve_memory_wiki_config({"vault": {"path": "~/wiki"}}, homedir="/home/tester")
        # ``pathlib.join`` may keep a trailing slash on
        # some platforms; the parent should always
        # resolve to the homedir.
        assert resolved.vault.path.startswith("/home/tester")

    def test_search_defaults(self) -> None:
        resolved = resolve_memory_wiki_config(None)
        assert resolved.search.backend == "shared"
        assert resolved.search.corpus == "wiki"

    def test_render_defaults_all_true(self) -> None:
        resolved = resolve_memory_wiki_config(None)
        assert resolved.render.preserveHumanBlocks is True
        assert resolved.render.createBacklinks is True
        assert resolved.render.createDashboards is True

    def test_obsidian_vault_name_dropped_when_empty(self) -> None:
        resolved = resolve_memory_wiki_config({"obsidian": {"vaultName": "OpenClaw Wiki"}})
        assert resolved.obsidian.vaultName == "OpenClaw Wiki"
        resolved2 = resolve_memory_wiki_config({"obsidian": {}})
        assert resolved2.obsidian.vaultName is None


class TestExpandHomePath:
    def test_tilde_alone(self) -> None:
        assert expand_home_path("~", "/h") == "/h"

    def test_tilde_slash(self) -> None:
        out = expand_home_path("~/wiki", "/h")
        # On Windows the separator is ``\``; on POSIX
        # it's ``/``. Compare with os.path.join
        # semantics.
        assert out == os.path.join("/h", "wiki")

    def test_absolute_path_unchanged(self) -> None:
        assert expand_home_path("/var/wiki", "/h") == "/var/wiki"

    def test_relative_path_unchanged(self) -> None:
        assert expand_home_path("wiki/main", "/h") == "wiki/main"


class TestResolveMemoryWikiAgentConfig:
    def test_global_scope_passthrough(self) -> None:
        resolved = resolve_memory_wiki_config({"vault": {"path": "/var/wiki"}}, homedir="/h")
        out = resolve_memory_wiki_agent_config(config=resolved, app_config=None, agent_id="any")
        assert out.vault.path == "/var/wiki"

    def test_agent_scope_appends_id(self) -> None:
        resolved = resolve_memory_wiki_config(
            {"vault": {"scope": "agent", "path": "/var/wiki"}},
            homedir="/h",
        )
        out = resolve_memory_wiki_agent_config(
            config=resolved,
            app_config={"agents": {"list": [{"id": "support"}]}},
            agent_id="support",
        )
        assert out.vault.path == os.path.join("/var/wiki", "support")
        assert out.agentId == "support"

    def test_agent_scope_multi_agent_requires_id(self) -> None:
        resolved = resolve_memory_wiki_config({"vault": {"scope": "agent"}}, homedir="/h")
        with pytest.raises(ValueError, match="agentId is required"):
            resolve_memory_wiki_agent_config(
                config=resolved,
                app_config={"agents": {"list": [{"id": "support"}, {"id": "marketing"}]}},
                agent_id=None,
            )

    def test_agent_scope_unknown_id_raises(self) -> None:
        resolved = resolve_memory_wiki_config({"vault": {"scope": "agent"}}, homedir="/h")
        with pytest.raises(ValueError, match="Unknown memory-wiki agentId"):
            resolve_memory_wiki_agent_config(
                config=resolved,
                app_config={"agents": {"list": [{"id": "support"}]}},
                agent_id="marketing",
            )

    def test_agent_scope_with_unsafe_local_raises(self) -> None:
        # Cross-field rule is also enforced at
        # resolver-time (defense in depth).
        resolved = resolve_memory_wiki_config(
            {"vaultMode": "unsafe-local", "vault": {"scope": "agent"}},
            homedir="/h",
        )
        with pytest.raises(ValueError, match="unsafe-local"):
            resolve_memory_wiki_agent_config(
                config=resolved,
                app_config={"agents": {"list": [{"id": "support"}]}},
                agent_id="support",
            )


class TestResolveMemoryWikiConfiguredAgentIds:
    def test_empty_app_config_falls_back_to_main(self) -> None:
        ids = resolve_memory_wiki_configured_agent_ids(None)
        assert ids == ["main"]

    def test_app_config_with_one_agent(self) -> None:
        ids = resolve_memory_wiki_configured_agent_ids({"agents": {"list": [{"id": "support"}]}})
        assert ids == ["support"]

    def test_app_config_with_multiple_agents(self) -> None:
        ids = resolve_memory_wiki_configured_agent_ids(
            {
                "agents": {
                    "list": [
                        {"id": "support"},
                        {"id": "marketing"},
                        {"id": "support"},  # dedupe
                    ]
                }
            }
        )
        assert ids == ["support", "marketing"]


class TestDefaultVaultPaths:
    def test_default_main_path(self) -> None:
        assert resolve_default_memory_wiki_vault_path("/h") == os.path.join(
            "/h", ".openclaw", "wiki", "main"
        )

    def test_default_agent_parent(self) -> None:
        assert resolve_default_memory_wiki_vault_root("/h") == os.path.join(
            "/h", ".openclaw", "wiki"
        )
