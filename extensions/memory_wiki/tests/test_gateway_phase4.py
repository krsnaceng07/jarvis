"""Tests for extensions/memory_wiki/gateway.py.

Phase 4.3f-mr4: ports the OpenClaw
``gateway.ts`` dispatcher. The tests focus
on:

- ``register_wiki_gateway_methods`` returns
  all 19 methods in OpenClaw's order with
  the correct scopes.
- The 5 tool-mirroring methods
  (``wiki.status`` / ``wiki.search`` /
  ``wiki.apply`` / ``wiki.get`` /
  ``wiki.lint``) + the supporting
  ``wiki.init`` / ``wiki.compile`` methods
  are fully functional.
- The remaining 12 methods return
  ``NotImplementedError`` (4.3g stubs).
- ``dispatch_wiki_gateway`` returns a
  :class:`WikiGatewayResponse` with
  ``ok=False`` for unknown methods.
- Param readers validate + clamp the
  OpenClaw-style input.
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

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

from extensions.memory_wiki.gateway import (  # noqa: E402
    ADMIN_SCOPE,
    READ_SCOPE,
    WRITE_SCOPE,
    WikiGatewayError,
    WikiGatewayMethod,
    WikiGatewayRequest,
    WikiGatewayResponse,
    dispatch_wiki_gateway,
    read_enum_param,
    read_positive_integer_param,
    read_string_param,
    register_wiki_gateway_methods,
)
from extensions.memory_wiki.markdown_pages import render_wiki_markdown  # noqa: E402


def _config(vault_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        vaultMode="single",
        vault=SimpleNamespace(path=str(vault_path), scope="global", renderMode="native"),
        search=SimpleNamespace(corpus="wiki", backend="auto"),
        bridge=SimpleNamespace(enabled=False),
    )


def _seed_vault(vault: Path) -> None:
    for sub in ("entities", "concepts", "sources", "syntheses", "reports"):
        (vault / sub).mkdir(parents=True, exist_ok=True)
    (vault / "entities" / "alpha.md").write_text(
        render_wiki_markdown(
            frontmatter={"pageType": "entity", "id": "entity.alpha"},
            body="# Alpha\n\nFirst line.\nSecond line.\n",
        ),
        encoding="utf-8",
    )


class TestParamHelpers:
    def test_read_string_param_required(self) -> None:
        with pytest.raises(ValueError, match="query is required"):
            read_string_param({}, "query", required=True)

    def test_read_string_param_trims(self) -> None:
        assert read_string_param({"k": "  hi  "}, "k") == "hi"

    def test_read_string_param_missing(self) -> None:
        assert read_string_param({}, "k") is None

    def test_read_string_param_empty(self) -> None:
        assert read_string_param({"k": "   "}, "k") is None

    def test_read_positive_integer_param(self) -> None:
        assert read_positive_integer_param({"k": 5}, "k") == 5
        assert read_positive_integer_param({"k": 0}, "k") is None
        assert read_positive_integer_param({"k": -1}, "k") is None
        assert read_positive_integer_param({"k": "5"}, "k") is None
        assert read_positive_integer_param({"k": True}, "k") is None
        assert read_positive_integer_param({}, "k") is None

    def test_read_enum_param_valid(self) -> None:
        assert read_enum_param({"k": "auto"}, "k", ("auto", "wiki")) == "auto"

    def test_read_enum_param_missing(self) -> None:
        assert read_enum_param({}, "k", ("auto", "wiki")) is None

    def test_read_enum_param_invalid(self) -> None:
        with pytest.raises(ValueError, match="must be one of"):
            read_enum_param({"k": "bogus"}, "k", ("auto", "wiki"))


class TestRegisterWikiGatewayMethods:
    def test_returns_19_methods(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        assert len(methods) == 19

    def test_openclaw_method_order(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        expected_order = [
            "wiki.status",
            "wiki.importRuns",
            "wiki.importInsights",
            "wiki.palace",
            "wiki.init",
            "wiki.doctor",
            "wiki.compile",
            "wiki.ingest",
            "wiki.lint",
            "wiki.bridge.import",
            "wiki.unsafeLocal.import",
            "wiki.search",
            "wiki.apply",
            "wiki.get",
            "wiki.obsidian.status",
            "wiki.obsidian.search",
            "wiki.obsidian.open",
            "wiki.obsidian.command",
            "wiki.obsidian.daily",
        ]
        assert list(methods) == expected_order

    def test_method_scopes(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        # Read-scope methods.
        for name in [
            "wiki.status",
            "wiki.importRuns",
            "wiki.importInsights",
            "wiki.palace",
            "wiki.init",
            "wiki.doctor",
            "wiki.compile",
            "wiki.ingest",
            "wiki.lint",
            "wiki.bridge.import",
            "wiki.unsafeLocal.import",
            "wiki.search",
        ]:
            assert methods[name].scope == READ_SCOPE, f"{name} expected READ"
        # Write-scope methods.
        for name in ["wiki.apply", "wiki.get"]:
            assert methods[name].scope == WRITE_SCOPE, f"{name} expected WRITE"
        # Admin-scope methods (obsidian).
        for name in [
            "wiki.obsidian.status",
            "wiki.obsidian.search",
            "wiki.obsidian.open",
            "wiki.obsidian.command",
            "wiki.obsidian.daily",
        ]:
            assert methods[name].scope == ADMIN_SCOPE, f"{name} expected ADMIN"

    def test_each_method_has_handler(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        for name, method in methods.items():
            assert isinstance(method, WikiGatewayMethod)
            assert method.name == name
            assert callable(method.handler)
            assert method.description


class TestDispatchWikiGateway:
    def test_unknown_method_returns_error(self, tmp_path: Path) -> None:
        result = dispatch_wiki_gateway("wiki.bogus", config=_config(tmp_path))
        assert isinstance(result, WikiGatewayResponse)
        assert result.ok is False
        assert isinstance(result.error, WikiGatewayError)
        assert "unknown wiki gateway method" in result.error.message

    def test_wiki_status_returns_payload(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        result = dispatch_wiki_gateway("wiki.status", config=config, methods=methods)
        assert result.ok is True
        assert result.value["vaultMode"] == "single"
        assert result.value["renderMode"] == "native"
        assert "rendered" in result.value

    def test_wiki_init_initializes_vault(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        result = dispatch_wiki_gateway("wiki.init", config=config, methods=methods)
        assert result.ok is True
        assert (tmp_path / ".openclaw-wiki").is_dir()

    def test_wiki_search_returns_results(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        result = dispatch_wiki_gateway(
            "wiki.search",
            config=config,
            methods=methods,
            params={"query": "Alpha"},
        )
        assert result.ok is True
        assert "results" in result.value
        assert "rendered" in result.value
        # The title match is in the rendered
        # text.
        assert "Alpha" in result.value["rendered"]

    def test_wiki_search_empty_query_rejected(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        result = dispatch_wiki_gateway(
            "wiki.search",
            config=config,
            methods=methods,
            params={"query": ""},
        )
        assert result.ok is False
        assert "query is required" in result.error.message

    def test_wiki_apply_creates_synthesis(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        result = dispatch_wiki_gateway(
            "wiki.apply",
            config=config,
            methods=methods,
            params={
                "op": "create_synthesis",
                "title": "My synthesis",
                "body": "Summary body.",
                "sourceIds": ["s1"],
            },
        )
        assert result.ok is True
        assert result.value["operation"] == "create_synthesis"
        assert any(tmp_path.glob("syntheses/*.md"))

    def test_wiki_get_returns_page_body(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        result = dispatch_wiki_gateway(
            "wiki.get",
            config=config,
            methods=methods,
            params={"lookup": "entities/alpha.md"},
        )
        assert result.ok is True
        assert "# Alpha" in result.value["content"]
        assert result.value["path"] == "entities/alpha.md"

    def test_wiki_get_missing_returns_not_found(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        result = dispatch_wiki_gateway(
            "wiki.get",
            config=config,
            methods=methods,
            params={"lookup": "entities/missing.md"},
        )
        assert result.ok is False
        assert result.error.code == "not_found"

    def test_wiki_lint_returns_no_issues(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        result = dispatch_wiki_gateway("wiki.lint", config=config, methods=methods)
        assert result.ok is True
        assert result.value["issueCount"] == 0
        assert result.value["rendered"] == "No wiki lint issues."

    def test_wiki_compile_returns_payload(self, tmp_path: Path) -> None:
        _seed_vault(tmp_path)
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        result = dispatch_wiki_gateway("wiki.compile", config=config, methods=methods)
        assert result.ok is True
        assert result.value["scannedCount"] >= 1
        assert isinstance(result.value["pages"], list)


class TestStubMethods:
    @pytest.mark.parametrize(
        "method_name",
        [
            "wiki.importRuns",
            "wiki.importInsights",
            "wiki.palace",
            "wiki.doctor",
            "wiki.ingest",
            "wiki.bridge.import",
            "wiki.unsafeLocal.import",
            "wiki.obsidian.status",
            "wiki.obsidian.search",
            "wiki.obsidian.open",
            "wiki.obsidian.command",
            "wiki.obsidian.daily",
        ],
    )
    def test_stub_returns_not_implemented(self, tmp_path: Path, method_name: str) -> None:
        config = _config(tmp_path)
        methods = register_wiki_gateway_methods(config=config)
        result = dispatch_wiki_gateway(method_name, config=config, methods=methods)
        assert result.ok is False
        assert "not yet implemented" in result.error.message
        assert "4.3g" in result.error.message


class TestWikiGatewayRequest:
    def test_default_request(self) -> None:
        req = WikiGatewayRequest()
        assert req.params == {}
        assert req.app_config is None
        assert req.agent_id is None

    def test_custom_request(self) -> None:
        req = WikiGatewayRequest(
            params={"k": "v"},
            app_config={"a": 1},
            agent_id="alpha",
            agent_session_key="sess-1",
            sandboxed=True,
        )
        assert req.params == {"k": "v"}
        assert req.agent_id == "alpha"
        assert req.sandboxed is True
