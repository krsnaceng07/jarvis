"""jarvis.plugins.memory_wiki — Memory Wiki plugin & durable knowledge compiler.

OpenClaw parity: mirrors
``openclaw-main/extensions/memory-wiki/src/config.ts`` and
``openclaw-main/extensions/memory-wiki/index.ts``.

Features:
- `MEMORY_WIKI_PLUGIN_ID`: `"memory-wiki"`
- `WIKI_VAULT_MODES`: `"isolated"`, `"bridge"`, `"unsafe-local"`
- `WIKI_VAULT_SCOPES`: `"global"`, `"agent"`
- `WIKI_RENDER_MODES`: `"native"`, `"obsidian"`
- `WIKI_SEARCH_BACKENDS`: `"shared"`, `"local"`
- `WIKI_SEARCH_CORPORA`: `"wiki"`, `"memory"`, `"all"`
- `WIKI_SEARCH_MODES`: `"auto"`, `"find-person"`, `"route-question"`, `"source-evidence"`, `"raw-claim"`
- `WIKI_AGENT_TOOLS`: List of 5 agent tools (`wiki_status`, `wiki_search`, `wiki_get`, `wiki_apply`, `wiki_lint`).
- `WIKI_RPC_METHODS`: List of 3 RPC methods (`wiki.overview`, `wiki.get`, `wiki.importInsights`).
- `WIKI_REPORTS`: List of 9 Markdown health report filenames.
- `ResolvedMemoryWikiConfig`: Dataclass containing resolved options.
- `resolve_memory_wiki_config()`: Resolves and validates Memory Wiki plugin configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

MEMORY_WIKI_PLUGIN_ID: str = "memory-wiki"

WikiVaultMode = Literal["isolated", "bridge", "unsafe-local"]
WikiVaultScope = Literal["global", "agent"]
WikiRenderMode = Literal["native", "obsidian"]
WikiSearchBackend = Literal["shared", "local"]
WikiSearchCorpus = Literal["wiki", "memory", "all"]
WikiSearchMode = Literal["auto", "find-person", "route-question", "source-evidence", "raw-claim"]

WIKI_VAULT_MODES: list[WikiVaultMode] = ["isolated", "bridge", "unsafe-local"]
WIKI_VAULT_SCOPES: list[WikiVaultScope] = ["global", "agent"]
WIKI_RENDER_MODES: list[WikiRenderMode] = ["native", "obsidian"]
WIKI_SEARCH_BACKENDS: list[WikiSearchBackend] = ["shared", "local"]
WIKI_SEARCH_CORPORA: list[WikiSearchCorpus] = ["wiki", "memory", "all"]
WIKI_SEARCH_MODES: list[WikiSearchMode] = [
    "auto",
    "find-person",
    "route-question",
    "source-evidence",
    "raw-claim",
]

WIKI_AGENT_TOOLS: list[str] = [
    "wiki_status",
    "wiki_search",
    "wiki_get",
    "wiki_apply",
    "wiki_lint",
]

WIKI_RPC_METHODS: list[str] = [
    "wiki.overview",
    "wiki.get",
    "wiki.importInsights",
]

WIKI_REPORTS: list[str] = [
    "reports/open-questions.md",
    "reports/contradictions.md",
    "reports/low-confidence.md",
    "reports/claim-health.md",
    "reports/stale-pages.md",
    "reports/person-agent-directory.md",
    "reports/relationship-graph.md",
    "reports/provenance-coverage.md",
    "reports/privacy-review.md",
]


@dataclass
class ResolvedMemoryWikiConfig:
    vaultMode: WikiVaultMode = "isolated"
    vaultScope: WikiVaultScope = "global"
    vaultPath: str = "~/.jarvis/wiki/main"
    renderMode: WikiRenderMode = "native"
    searchBackend: WikiSearchBackend = "shared"
    searchCorpus: WikiSearchCorpus = "wiki"
    includeCompiledDigestPrompt: bool = False
    createBacklinks: bool = True
    createDashboards: bool = True
    agentId: str = "main"


def resolve_memory_wiki_config(
    plugin_cfg: dict[str, Any] | None, agent_id: str = "main"
) -> ResolvedMemoryWikiConfig:
    """Resolve and validate Memory Wiki plugin configuration options."""
    val = plugin_cfg if isinstance(plugin_cfg, dict) else {}

    raw_mode = str(val.get("vaultMode") or "isolated").lower()
    mode: WikiVaultMode = (
        raw_mode if raw_mode in ("isolated", "bridge", "unsafe-local") else "isolated"  # type: ignore[assignment]
    )

    vault_cfg = val.get("vault") if isinstance(val.get("vault"), dict) else {}
    raw_scope = str(vault_cfg.get("scope") or "global").lower()
    scope: WikiVaultScope = (
        raw_scope if raw_scope in ("global", "agent") else "global"  # type: ignore[assignment]
    )

    if scope == "agent" and mode == "unsafe-local":
        raise ValueError("Memory Wiki vault scope 'agent' cannot be combined with 'unsafe-local' vaultMode.")

    raw_path = str(vault_cfg.get("path") or "").strip()
    if not raw_path:
        raw_path = "~/.jarvis/wiki" if scope == "agent" else "~/.jarvis/wiki/main"

    raw_render = str(vault_cfg.get("renderMode") or "native").lower()
    render: WikiRenderMode = (
        raw_render if raw_render in ("native", "obsidian") else "native"  # type: ignore[assignment]
    )

    search_cfg = val.get("search") if isinstance(val.get("search"), dict) else {}
    raw_backend = str(search_cfg.get("backend") or "shared").lower()
    backend: WikiSearchBackend = (
        raw_backend if raw_backend in ("shared", "local") else "shared"  # type: ignore[assignment]
    )

    raw_corpus = str(search_cfg.get("corpus") or "wiki").lower()
    corpus: WikiSearchCorpus = (
        raw_corpus if raw_corpus in ("wiki", "memory", "all") else "wiki"  # type: ignore[assignment]
    )

    ctx_cfg = val.get("context") if isinstance(val.get("context"), dict) else {}
    inc_digest = bool(ctx_cfg.get("includeCompiledDigestPrompt", False))

    rnd_cfg = val.get("render") if isinstance(val.get("render"), dict) else {}
    backlinks = bool(rnd_cfg.get("createBacklinks", True))
    dashboards = bool(rnd_cfg.get("createDashboards", True))

    return ResolvedMemoryWikiConfig(
        vaultMode=mode,
        vaultScope=scope,
        vaultPath=raw_path,
        renderMode=render,
        searchBackend=backend,
        searchCorpus=corpus,
        includeCompiledDigestPrompt=inc_digest,
        createBacklinks=backlinks,
        createDashboards=dashboards,
        agentId=agent_id,
    )


__all__ = [
    "MEMORY_WIKI_PLUGIN_ID",
    "ResolvedMemoryWikiConfig",
    "WIKI_AGENT_TOOLS",
    "WIKI_RENDER_MODES",
    "WIKI_REPORTS",
    "WIKI_RPC_METHODS",
    "WIKI_SEARCH_BACKENDS",
    "WIKI_SEARCH_CORPORA",
    "WIKI_SEARCH_MODES",
    "WIKI_VAULT_MODES",
    "WIKI_VAULT_SCOPES",
    "WikiRenderMode",
    "WikiSearchBackend",
    "WikiSearchCorpus",
    "WikiSearchMode",
    "WikiVaultMode",
    "WikiVaultScope",
    "resolve_memory_wiki_config",
]
