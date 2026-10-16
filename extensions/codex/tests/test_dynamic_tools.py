from __future__ import annotations

from extensions.codex.src.dynamic_tools import project_codex_dynamic_tools
from extensions.codex.src.web_search import resolve_codex_web_search_plan


def test_dynamic_tools_match_openclaw_namespace_and_loading_contract():
    result = project_codex_dynamic_tools(
        [
            {"name": "message", "description": "send", "inputSchema": {}},
            {"name": "sessions_spawn", "description": "spawn", "inputSchema": {}},
            {"name": "computer", "catalogMode": "direct-only", "inputSchema": {}},
            {"name": "exec", "inputSchema": {}},
        ]
    )
    specs = result["specs"]
    assert specs[0]["name"] == "sessions_spawn"
    assert specs[1]["name"] == "openclaw"
    assert specs[1]["tools"][0]["name"] == "message"
    assert specs[2]["name"] == "openclaw_direct"
    assert result["quarantined"] == []


def test_web_search_never_exposes_managed_search_alongside_native_domains():
    plan = resolve_codex_web_search_plan(
        {"tools": {"web": {"search": {"openaiCodex": {"allowedDomains": ["example.com"]}}}}}
    )
    assert plan["kind"] == "native-hosted"
    assert plan["suppressManagedWebSearch"] is True
    assert plan["threadConfig"]["features.standalone_web_search"] is False

    unknown = resolve_codex_web_search_plan({}, native_provider_support="unknown")
    assert unknown["kind"] == "managed"
    assert unknown["suppressManagedWebSearch"] is False

    managed = resolve_codex_web_search_plan({"tools": {"web": {"search": {"provider": "brave"}}}})
    assert managed["kind"] == "managed"
    assert managed["suppressManagedWebSearch"] is False
