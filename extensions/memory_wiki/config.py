"""config — memory-wiki plugin configuration.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/config.ts``.

Defines the full plugin config schema (vaultMode,
vault, obsidian, bridge, unsafeLocal, ingest, search,
context, render), the strict validation contract
(``memoryWikiConfigSchema``), the
``resolveMemoryWikiConfig`` defaults-merge function,
and the per-agent config resolver
(``resolveMemoryWikiAgentConfig``).

The OpenClaw source uses ``zod`` for the schema; the
Python port is a manual ``dict`` validator that
preserves the same field set, the same default
values, the same ``superRefine`` cross-field rules
(``vaultMode=unsafe-local`` is incompatible with
``vault.scope=agent``; ``obsidian.useOfficialCli=true``
is incompatible with ``vault.scope=agent``), and the
same homedir expansion (``~/`` -> ``$HOME``).

Parity
======
- ``resolveMemoryWikiConfig(config)`` → ``ResolvedMemoryWikiConfig``
- ``resolveMemoryWikiConfiguredAgentIds(appConfig)`` → ``list[str]``
- ``resolveMemoryWikiAgentConfig({config, appConfig, agentId})``
  → ``ResolvedMemoryWikiConfig``
- ``memoryWikiConfigSchema`` → ``MemoryWikiConfigSchema`` (a
  Python callable that mirrors OpenClaw's
  ``safeParse``-shaped contract: ``None`` input →
  defaults, invalid input → ``(False, issues)``,
  valid input → ``(True, resolved)``).
"""

# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalOperand=false
# pyright: reportOptionalSubscript=false
# pyright: reportOptionalIterable=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportReturnType=false
# pyright: reportTypedDictNotRequiredAccess=false
# pyright: reportOperatorIssue=false
# pyright: reportAssignmentType=false

from __future__ import annotations

# ruff: noqa: N803, PLR0912, PLR0915, SIM102, PIE810 — mirrors OpenClaw's zod schema shape
import os
from typing import Any, Literal, TypedDict

# Type literals mirror OpenClaw's ``as const`` arrays.
WikiVaultMode = Literal["isolated", "bridge", "unsafe-local"]
WikiVaultScope = Literal["global", "agent"]
WikiRenderMode = Literal["native", "obsidian"]
WikiSearchBackend = Literal["shared", "local"]
WikiSearchCorpus = Literal["wiki", "memory", "all"]

WIKI_VAULT_MODES = ("isolated", "bridge", "unsafe-local")
WIKI_VAULT_SCOPES = ("global", "agent")
WIKI_RENDER_MODES = ("native", "obsidian")
WIKI_SEARCH_BACKENDS = ("shared", "local")
WIKI_SEARCH_CORPORA = ("wiki", "memory", "all")

# Defaults mirror OpenClaw's ``DEFAULT_*`` constants.
DEFAULT_WIKI_VAULT_MODE: WikiVaultMode = "isolated"
DEFAULT_WIKI_VAULT_SCOPE: WikiVaultScope = "global"
DEFAULT_WIKI_RENDER_MODE: WikiRenderMode = "native"
DEFAULT_WIKI_SEARCH_BACKEND: WikiSearchBackend = "shared"
DEFAULT_WIKI_SEARCH_CORPUS: WikiSearchCorpus = "wiki"


class VaultConfig(TypedDict, total=False):
    scope: WikiVaultScope
    path: str
    renderMode: WikiRenderMode


class ObsidianConfig(TypedDict, total=False):
    enabled: bool
    useOfficialCli: bool
    vaultName: str
    openAfterWrites: bool


class BridgeConfig(TypedDict, total=False):
    enabled: bool
    readMemoryArtifacts: bool
    indexDreamReports: bool
    indexDailyNotes: bool
    indexMemoryRoot: bool
    followMemoryEvents: bool


class UnsafeLocalConfig(TypedDict, total=False):
    allowPrivateMemoryCoreAccess: bool
    paths: list[str]


class IngestConfig(TypedDict, total=False):
    autoCompile: bool
    maxConcurrentJobs: int
    allowUrlIngest: bool


class SearchConfig(TypedDict, total=False):
    backend: WikiSearchBackend
    corpus: WikiSearchCorpus


class ContextConfig(TypedDict, total=False):
    includeCompiledDigestPrompt: bool


class RenderConfig(TypedDict, total=False):
    preserveHumanBlocks: bool
    createBacklinks: bool
    createDashboards: bool


class MemoryWikiPluginConfig(TypedDict, total=False):
    vaultMode: WikiVaultMode
    vault: VaultConfig
    obsidian: ObsidianConfig
    bridge: BridgeConfig
    unsafeLocal: UnsafeLocalConfig
    ingest: IngestConfig
    search: SearchConfig
    context: ContextConfig
    render: RenderConfig


class ResolvedVaultConfig:
    """Resolved (defaults-merged) vault config."""

    __slots__ = ("scope", "path", "renderMode")

    def __init__(
        self,
        *,
        scope: WikiVaultScope,
        path: str,
        renderMode: WikiRenderMode,
    ) -> None:
        self.scope = scope
        self.path = path
        self.renderMode = renderMode


class ResolvedObsidianConfig:
    __slots__ = ("enabled", "useOfficialCli", "vaultName", "openAfterWrites")

    def __init__(
        self,
        *,
        enabled: bool,
        useOfficialCli: bool,
        vault_name: str | None,
        open_after_writes: bool,
    ) -> None:
        self.enabled = enabled
        self.useOfficialCli = useOfficialCli
        self.vaultName = vault_name
        self.openAfterWrites = open_after_writes


class ResolvedBridgeConfig:
    __slots__ = (
        "enabled",
        "readMemoryArtifacts",
        "indexDreamReports",
        "indexDailyNotes",
        "indexMemoryRoot",
        "followMemoryEvents",
    )

    def __init__(
        self,
        *,
        enabled: bool,
        read_memory_artifacts: bool,
        index_dream_reports: bool,
        index_daily_notes: bool,
        index_memory_root: bool,
        follow_memory_events: bool,
    ) -> None:
        self.enabled = enabled
        self.readMemoryArtifacts = read_memory_artifacts
        self.indexDreamReports = index_dream_reports
        self.indexDailyNotes = index_daily_notes
        self.indexMemoryRoot = index_memory_root
        self.followMemoryEvents = follow_memory_events


class ResolvedUnsafeLocalConfig:
    __slots__ = ("allowPrivateMemoryCoreAccess", "paths")

    def __init__(
        self,
        *,
        allow_private_memory_core_access: bool,
        paths: list[str],
    ) -> None:
        self.allowPrivateMemoryCoreAccess = allow_private_memory_core_access
        self.paths = paths


class ResolvedIngestConfig:
    __slots__ = ("autoCompile", "maxConcurrentJobs", "allowUrlIngest")

    def __init__(
        self,
        *,
        auto_compile: bool,
        max_concurrent_jobs: int,
        allow_url_ingest: bool,
    ) -> None:
        self.autoCompile = auto_compile
        self.maxConcurrentJobs = max_concurrent_jobs
        self.allowUrlIngest = allow_url_ingest


class ResolvedSearchConfig:
    __slots__ = ("backend", "corpus")

    def __init__(
        self,
        *,
        backend: WikiSearchBackend,
        corpus: WikiSearchCorpus,
    ) -> None:
        self.backend = backend
        self.corpus = corpus


class ResolvedContextConfig:
    __slots__ = ("includeCompiledDigestPrompt",)

    def __init__(self, *, include_compiled_digest_prompt: bool) -> None:
        self.includeCompiledDigestPrompt = include_compiled_digest_prompt


class ResolvedRenderConfig:
    __slots__ = ("preserveHumanBlocks", "createBacklinks", "createDashboards")

    def __init__(
        self,
        *,
        preserve_human_blocks: bool,
        create_backlinks: bool,
        create_dashboards: bool,
    ) -> None:
        self.preserveHumanBlocks = preserve_human_blocks
        self.createBacklinks = create_backlinks
        self.createDashboards = create_dashboards


class ResolvedMemoryWikiConfig:
    """Resolved (defaults-merged, paths-expanded) wiki config.

    Mirrors OpenClaw's ``ResolvedMemoryWikiConfig``.
    All fields are required (no Optional) after the
    resolver runs; ``agentId`` is the only field that
    may be ``None`` when ``vault.scope=global``.
    """

    def __init__(
        self,
        *,
        agent_id: str | None,
        vault_mode: WikiVaultMode,
        vault: ResolvedVaultConfig,
        obsidian: ResolvedObsidianConfig,
        bridge: ResolvedBridgeConfig,
        unsafe_local: ResolvedUnsafeLocalConfig,
        ingest: ResolvedIngestConfig,
        search: ResolvedSearchConfig,
        context: ResolvedContextConfig,
        render: ResolvedRenderConfig,
    ) -> None:
        self.agentId = agent_id
        self.vaultMode = vault_mode
        self.vault = vault
        self.obsidian = obsidian
        self.bridge = bridge
        self.unsafeLocal = unsafe_local
        self.ingest = ingest
        self.search = search
        self.context = context
        self.render = render


MemoryWikiConfigResolver = Any  # Callable[[str | None, dict | None], ResolvedMemoryWikiConfig]


# ── Schema validation ──────────────────────────────────────────


class MemoryWikiConfigIssue:
    """A single validation error from ``memory_wiki_config_schema``."""

    __slots__ = ("path", "message")

    def __init__(self, *, path: list[str | int], message: str) -> None:
        self.path = path
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {"path": list(self.path), "message": self.message}

    def __repr__(self) -> str:  # pragma: no cover -- debug aid
        return f"MemoryWikiConfigIssue(path={self.path!r}, message={self.message!r})"


class MemoryWikiConfigSchema:
    """Mirrors OpenClaw's ``OpenClawPluginConfigSchema`` callable.

    Python-side ``safeParse`` shape:
    - ``None`` input → ``(True, resolved_defaults)``
    - valid input → ``(True, resolved)``
    - invalid input → ``(False, {"issues": [...]})``
    """

    def safe_parse(self, value: Any) -> tuple[bool, ResolvedMemoryWikiConfig | dict[str, Any]]:
        if value is None:
            return True, resolve_memory_wiki_config(None)
        issues = _validate_config_shape(value)
        if issues:
            return False, {"issues": [i.to_dict() for i in issues]}
        # Re-resolve from the validated (potentially
        # partially-normalized) input so the schema
        # returns the same shape as ``resolve``.
        return True, resolve_memory_wiki_config(value)


memory_wiki_config_schema = MemoryWikiConfigSchema()


def _validate_config_shape(value: Any) -> list[MemoryWikiConfigIssue]:
    """Strict-shape validation.

    Mirrors OpenClaw's ``z.strictObject`` per-key check
    plus the ``superRefine`` cross-field rules:
    - ``vaultMode=unsafe-local`` cannot be combined
      with ``vault.scope=agent``.
    - ``obsidian.useOfficialCli=true`` cannot be
      combined with ``vault.scope=agent``.

    Returns the list of issues (empty when valid).
    """
    issues: list[MemoryWikiConfigIssue] = []
    if value is None:
        return issues
    if not isinstance(value, dict):
        issues.append(
            MemoryWikiConfigIssue(
                path=[],
                message="memory-wiki config must be a JSON object",
            )
        )
        return issues

    # vaultMode
    if "vaultMode" in value and value["vaultMode"] is not None:
        if value["vaultMode"] not in WIKI_VAULT_MODES:
            issues.append(
                MemoryWikiConfigIssue(
                    path=["vaultMode"],
                    message=f"vaultMode must be one of {list(WIKI_VAULT_MODES)}",
                )
            )

    # vault
    if "vault" in value and value["vault"] is not None:
        v = value["vault"]
        if not isinstance(v, dict):
            issues.append(
                MemoryWikiConfigIssue(
                    path=["vault"],
                    message="vault must be a JSON object",
                )
            )
        else:
            if "scope" in v and v["scope"] is not None and v["scope"] not in WIKI_VAULT_SCOPES:
                issues.append(
                    MemoryWikiConfigIssue(
                        path=["vault", "scope"],
                        message=f"vault.scope must be one of {list(WIKI_VAULT_SCOPES)}",
                    )
                )
            if (
                "renderMode" in v
                and v["renderMode"] is not None
                and v["renderMode"] not in WIKI_RENDER_MODES
            ):
                issues.append(
                    MemoryWikiConfigIssue(
                        path=["vault", "renderMode"],
                        message=f"vault.renderMode must be one of {list(WIKI_RENDER_MODES)}",
                    )
                )
            if "path" in v and v["path"] is not None and not isinstance(v["path"], str):
                issues.append(
                    MemoryWikiConfigIssue(
                        path=["vault", "path"],
                        message="vault.path must be a string",
                    )
                )

    # obsidian
    if "obsidian" in value and value["obsidian"] is not None:
        o = value["obsidian"]
        if not isinstance(o, dict):
            issues.append(
                MemoryWikiConfigIssue(
                    path=["obsidian"],
                    message="obsidian must be a JSON object",
                )
            )
        else:
            for key in ("enabled", "useOfficialCli", "openAfterWrites"):
                if key in o and o[key] is not None and not isinstance(o[key], bool):
                    issues.append(
                        MemoryWikiConfigIssue(
                            path=["obsidian", key],
                            message=f"obsidian.{key} must be a boolean",
                        )
                    )
            if (
                "vaultName" in o
                and o["vaultName"] is not None
                and not isinstance(o["vaultName"], str)
            ):
                issues.append(
                    MemoryWikiConfigIssue(
                        path=["obsidian", "vaultName"],
                        message="obsidian.vaultName must be a string",
                    )
                )

    # bridge
    if "bridge" in value and value["bridge"] is not None:
        b = value["bridge"]
        if not isinstance(b, dict):
            issues.append(
                MemoryWikiConfigIssue(
                    path=["bridge"],
                    message="bridge must be a JSON object",
                )
            )
        else:
            for key in (
                "enabled",
                "readMemoryArtifacts",
                "indexDreamReports",
                "indexDailyNotes",
                "indexMemoryRoot",
                "followMemoryEvents",
            ):
                if key in b and b[key] is not None and not isinstance(b[key], bool):
                    issues.append(
                        MemoryWikiConfigIssue(
                            path=["bridge", key],
                            message=f"bridge.{key} must be a boolean",
                        )
                    )

    # unsafeLocal
    if "unsafeLocal" in value and value["unsafeLocal"] is not None:
        u = value["unsafeLocal"]
        if not isinstance(u, dict):
            issues.append(
                MemoryWikiConfigIssue(
                    path=["unsafeLocal"],
                    message="unsafeLocal must be a JSON object",
                )
            )
        else:
            if (
                "allowPrivateMemoryCoreAccess" in u
                and u["allowPrivateMemoryCoreAccess"] is not None
                and not isinstance(u["allowPrivateMemoryCoreAccess"], bool)
            ):
                issues.append(
                    MemoryWikiConfigIssue(
                        path=["unsafeLocal", "allowPrivateMemoryCoreAccess"],
                        message="unsafeLocal.allowPrivateMemoryCoreAccess must be a boolean",
                    )
                )
            if "paths" in u and u["paths"] is not None:
                if not isinstance(u["paths"], list) or not all(
                    isinstance(p, str) for p in u["paths"]
                ):
                    issues.append(
                        MemoryWikiConfigIssue(
                            path=["unsafeLocal", "paths"],
                            message="unsafeLocal.paths must be a list of strings",
                        )
                    )

    # ingest
    if "ingest" in value and value["ingest"] is not None:
        i = value["ingest"]
        if not isinstance(i, dict):
            issues.append(
                MemoryWikiConfigIssue(
                    path=["ingest"],
                    message="ingest must be a JSON object",
                )
            )
        else:
            for key in ("autoCompile", "allowUrlIngest"):
                if key in i and i[key] is not None and not isinstance(i[key], bool):
                    issues.append(
                        MemoryWikiConfigIssue(
                            path=["ingest", key],
                            message=f"ingest.{key} must be a boolean",
                        )
                    )
            if "maxConcurrentJobs" in i and i["maxConcurrentJobs"] is not None:
                val = i["maxConcurrentJobs"]
                if isinstance(val, bool) or not isinstance(val, int) or val < 1:
                    issues.append(
                        MemoryWikiConfigIssue(
                            path=["ingest", "maxConcurrentJobs"],
                            message="ingest.maxConcurrentJobs must be a positive integer",
                        )
                    )

    # search
    if "search" in value and value["search"] is not None:
        s = value["search"]
        if not isinstance(s, dict):
            issues.append(
                MemoryWikiConfigIssue(
                    path=["search"],
                    message="search must be a JSON object",
                )
            )
        else:
            if (
                "backend" in s
                and s["backend"] is not None
                and s["backend"] not in WIKI_SEARCH_BACKENDS
            ):
                issues.append(
                    MemoryWikiConfigIssue(
                        path=["search", "backend"],
                        message=f"search.backend must be one of {list(WIKI_SEARCH_BACKENDS)}",
                    )
                )
            if "corpus" in s and s["corpus"] is not None and s["corpus"] not in WIKI_SEARCH_CORPORA:
                issues.append(
                    MemoryWikiConfigIssue(
                        path=["search", "corpus"],
                        message=f"search.corpus must be one of {list(WIKI_SEARCH_CORPORA)}",
                    )
                )

    # context
    if "context" in value and value["context"] is not None:
        c = value["context"]
        if not isinstance(c, dict):
            issues.append(
                MemoryWikiConfigIssue(
                    path=["context"],
                    message="context must be a JSON object",
                )
            )
        elif (
            "includeCompiledDigestPrompt" in c
            and c["includeCompiledDigestPrompt"] is not None
            and not isinstance(c["includeCompiledDigestPrompt"], bool)
        ):
            issues.append(
                MemoryWikiConfigIssue(
                    path=["context", "includeCompiledDigestPrompt"],
                    message="context.includeCompiledDigestPrompt must be a boolean",
                )
            )

    # render
    if "render" in value and value["render"] is not None:
        r = value["render"]
        if not isinstance(r, dict):
            issues.append(
                MemoryWikiConfigIssue(
                    path=["render"],
                    message="render must be a JSON object",
                )
            )
        else:
            for key in ("preserveHumanBlocks", "createBacklinks", "createDashboards"):
                if key in r and r[key] is not None and not isinstance(r[key], bool):
                    issues.append(
                        MemoryWikiConfigIssue(
                            path=["render", key],
                            message=f"render.{key} must be a boolean",
                        )
                    )

    # Cross-field rules (mirror OpenClaw's
    # ``superRefine`` checks).
    vault_scope = (
        value.get("vault", {}).get("scope") if isinstance(value.get("vault"), dict) else None
    )
    if vault_scope == "agent" and value.get("vaultMode") == "unsafe-local":
        issues.append(
            MemoryWikiConfigIssue(
                path=["vaultMode"],
                message="vaultMode=unsafe-local cannot be combined with vault.scope=agent",
            )
        )
    if (
        vault_scope == "agent"
        and isinstance(value.get("obsidian"), dict)
        and value["obsidian"].get("useOfficialCli") is True
    ):
        issues.append(
            MemoryWikiConfigIssue(
                path=["obsidian", "useOfficialCli"],
                message="obsidian.useOfficialCli cannot be enabled with vault.scope=agent",
            )
        )

    return issues


# ── Defaults + homedir expansion ──────────────────────────────


def expand_home_path(input_path: str, homedir: str) -> str:
    """Expand a leading ``~`` / ``~/`` to ``homedir``.

    Mirrors OpenClaw's ``expandHomePath``. Returns the
    input unchanged when it does not start with ``~``.
    """
    if not isinstance(input_path, str):
        return input_path
    if input_path == "~":
        return homedir
    if input_path.startswith("~/") or input_path.startswith("~\\"):
        return os.path.join(homedir, input_path[2:])
    return input_path


def resolve_default_memory_wiki_vault_path(homedir: str | None = None) -> str:
    """Return ``$HOMEDIR/.openclaw/wiki/main``.

    Mirrors OpenClaw's ``resolveDefaultMemoryWikiVaultPath``.
    """
    if homedir is None:
        homedir = os.path.expanduser("~")
    return os.path.join(homedir, ".openclaw", "wiki", "main")


def resolve_default_memory_wiki_vault_root(homedir: str | None = None) -> str:
    """Return ``$HOMEDIR/.openclaw/wiki`` (the per-agent parent).

    Mirrors OpenClaw's ``resolveDefaultMemoryWikiVaultRoot``.
    """
    if homedir is None:
        homedir = os.path.expanduser("~")
    return os.path.join(homedir, ".openclaw", "wiki")


# ── Resolver ──────────────────────────────────────────────────


def resolve_memory_wiki_config(
    config: MemoryWikiPluginConfig | None | dict[str, Any],
    *,
    homedir: str | None = None,
) -> ResolvedMemoryWikiConfig:
    """Resolve the memory-wiki config with all defaults applied.

    Mirrors OpenClaw's ``resolveMemoryWikiConfig``.
    Returns a fully-populated :class:`ResolvedMemoryWikiConfig`
    whose ``vault.path`` has been homedir-expanded.
    """
    if homedir is None:
        homedir = os.path.expanduser("~")
    safe = config if isinstance(config, dict) else {}
    vault = safe.get("vault") if isinstance(safe.get("vault"), dict) else {}
    vault_scope = vault.get("scope") or DEFAULT_WIKI_VAULT_SCOPE
    default_path = (
        resolve_default_memory_wiki_vault_root(homedir)
        if vault_scope == "agent"
        else resolve_default_memory_wiki_vault_path(homedir)
    )
    raw_path = vault.get("path") or default_path
    expanded_path = expand_home_path(raw_path, homedir)

    obsidian_raw = safe.get("obsidian") if isinstance(safe.get("obsidian"), dict) else {}
    obsidian_vault_name = obsidian_raw.get("vaultName")
    return ResolvedMemoryWikiConfig(
        agent_id=None,
        vault_mode=safe.get("vaultMode") or DEFAULT_WIKI_VAULT_MODE,
        vault=ResolvedVaultConfig(
            scope=vault_scope,
            path=expanded_path,
            renderMode=vault.get("renderMode") or DEFAULT_WIKI_RENDER_MODE,
        ),
        obsidian=ResolvedObsidianConfig(
            enabled=bool(obsidian_raw.get("enabled", False)),
            useOfficialCli=bool(obsidian_raw.get("useOfficialCli", False)),
            vault_name=str(obsidian_vault_name) if obsidian_vault_name else None,
            open_after_writes=bool(obsidian_raw.get("openAfterWrites", False)),
        ),
        bridge=ResolvedBridgeConfig(
            enabled=bool(safe.get("bridge", {}).get("enabled", False))
            if isinstance(safe.get("bridge"), dict)
            else False,
            read_memory_artifacts=_coalesce(
                safe.get("bridge", {}).get("readMemoryArtifacts")
                if isinstance(safe.get("bridge"), dict)
                else None,
                True,
            ),
            index_dream_reports=_coalesce(
                safe.get("bridge", {}).get("indexDreamReports")
                if isinstance(safe.get("bridge"), dict)
                else None,
                True,
            ),
            index_daily_notes=_coalesce(
                safe.get("bridge", {}).get("indexDailyNotes")
                if isinstance(safe.get("bridge"), dict)
                else None,
                True,
            ),
            index_memory_root=_coalesce(
                safe.get("bridge", {}).get("indexMemoryRoot")
                if isinstance(safe.get("bridge"), dict)
                else None,
                True,
            ),
            follow_memory_events=_coalesce(
                safe.get("bridge", {}).get("followMemoryEvents")
                if isinstance(safe.get("bridge"), dict)
                else None,
                True,
            ),
        ),
        unsafe_local=ResolvedUnsafeLocalConfig(
            allow_private_memory_core_access=_coalesce(
                safe.get("unsafeLocal", {}).get("allowPrivateMemoryCoreAccess")
                if isinstance(safe.get("unsafeLocal"), dict)
                else None,
                False,
            ),
            paths=list(safe.get("unsafeLocal", {}).get("paths", []))
            if isinstance(safe.get("unsafeLocal"), dict)
            else [],
        ),
        ingest=ResolvedIngestConfig(
            auto_compile=_coalesce(
                safe.get("ingest", {}).get("autoCompile")
                if isinstance(safe.get("ingest"), dict)
                else None,
                True,
            ),
            max_concurrent_jobs=int(
                safe.get("ingest", {}).get("maxConcurrentJobs", 1)
                if isinstance(safe.get("ingest"), dict)
                else 1
            ),
            allow_url_ingest=_coalesce(
                safe.get("ingest", {}).get("allowUrlIngest")
                if isinstance(safe.get("ingest"), dict)
                else None,
                True,
            ),
        ),
        search=ResolvedSearchConfig(
            backend=(
                safe.get("search", {}).get("backend")
                if isinstance(safe.get("search"), dict)
                else None
            )
            or DEFAULT_WIKI_SEARCH_BACKEND,
            corpus=(
                safe.get("search", {}).get("corpus")
                if isinstance(safe.get("search"), dict)
                else None
            )
            or DEFAULT_WIKI_SEARCH_CORPUS,
        ),
        context=ResolvedContextConfig(
            include_compiled_digest_prompt=bool(
                safe.get("context", {}).get("includeCompiledDigestPrompt", False)
                if isinstance(safe.get("context"), dict)
                else False
            ),
        ),
        render=ResolvedRenderConfig(
            preserve_human_blocks=_coalesce(
                safe.get("render", {}).get("preserveHumanBlocks")
                if isinstance(safe.get("render"), dict)
                else None,
                True,
            ),
            create_backlinks=_coalesce(
                safe.get("render", {}).get("createBacklinks")
                if isinstance(safe.get("render"), dict)
                else None,
                True,
            ),
            create_dashboards=_coalesce(
                safe.get("render", {}).get("createDashboards")
                if isinstance(safe.get("render"), dict)
                else None,
                True,
            ),
        ),
    )


def _coalesce(value: Any, default: bool) -> bool:
    """Return ``value`` when it's a bool, else ``default``.

    Mirrors the ``?? true`` coalesce in OpenClaw's
    bridge default. The Python port treats ``None`` and
    any non-bool as "use the default".
    """
    return bool(value) if isinstance(value, bool) else default


# ── Per-agent resolution ────────────────────────────────────


def resolve_memory_wiki_configured_agent_ids(
    app_config: dict[str, Any] | None,
) -> list[str]:
    """Return the list of agent ids this plugin is configured for.

    Mirrors OpenClaw's
    ``resolveMemoryWikiConfiguredAgentIds``. Falls
    back to the default agent id when the host config
    has no agent list.
    """
    configured_agents = (
        app_config.get("agents", {}).get("list", []) if isinstance(app_config, dict) else []
    )
    if not isinstance(configured_agents, list):
        return [resolve_default_agent_id(app_config)]
    ids: list[str] = []
    for entry in configured_agents:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("id")
        if not isinstance(raw, str) or not raw.strip():
            continue
        resolved = resolve_session_agent_id(app_config, raw.strip())
        if resolved and resolved not in ids:
            ids.append(resolved)
    if not ids:
        ids = [resolve_default_agent_id(app_config)]
    return ids


def resolve_memory_wiki_agent_config(
    *,
    config: ResolvedMemoryWikiConfig,
    app_config: dict[str, Any] | None = None,
    agent_id: str | None = None,
) -> ResolvedMemoryWikiConfig:
    """Resolve the per-agent memory-wiki config.

    Mirrors OpenClaw's ``resolveMemoryWikiAgentConfig``.
    In ``vault.scope=global`` mode, returns the input
    unchanged. In ``vault.scope=agent`` mode, appends
    the normalized agent id to ``vault.path`` and
    validates the unsafe-local / official-CLI
    incompatibilities. Requires an explicit
    ``agentId`` when more than one agent is configured.
    """
    if config.vault.scope == "global":
        return config
    if config.vaultMode == "unsafe-local":
        raise ValueError("memory-wiki vault.scope=agent does not support vaultMode=unsafe-local.")

    configured = resolve_memory_wiki_configured_agent_ids(app_config)
    requested = (agent_id or "").strip() or None
    if not requested and len(configured) > 1:
        raise ValueError("agentId is required for memory-wiki when vault.scope=agent.")
    resolved_agent_id = resolve_session_agent_id(
        app_config, requested or resolve_default_agent_id(app_config)
    )
    if resolved_agent_id not in configured:
        raise ValueError(f"Unknown memory-wiki agentId: {requested or resolved_agent_id}.")

    new_vault = ResolvedVaultConfig(
        scope=config.vault.scope,
        path=os.path.join(config.vault.path, resolved_agent_id),
        renderMode=config.vault.renderMode,
    )
    # Build a copy with the new agent id and path.
    return ResolvedMemoryWikiConfig(
        agent_id=resolved_agent_id,
        vault_mode=config.vaultMode,
        vault=new_vault,
        obsidian=config.obsidian,
        bridge=config.bridge,
        unsafe_local=config.unsafeLocal,
        ingest=config.ingest,
        search=config.search,
        context=config.context,
        render=config.render,
    )


# ── Local helpers (SDK parity stubs) ────────────────────────


def resolve_default_agent_id(app_config: dict[str, Any] | None) -> str:
    """Return the default agent id (``"main"`` unless overridden).

    Mirrors ``openclaw/plugin-sdk/memory-host-core``'s
    ``resolveDefaultAgentId`` for the memory-wiki port.
    The Python SDK ships its own copy in
    ``jarvis_sdk.agent_runtime``; this local stub
    keeps the memory_wiki port self-contained.
    """
    if isinstance(app_config, dict):
        default = app_config.get("agents", {}).get("default", "main")
        if isinstance(default, str) and default.strip():
            return default
    return "main"


def resolve_session_agent_id(
    app_config: dict[str, Any] | None,
    agent_id: str,
) -> str:
    """Return the agent id, falling back to the default if absent.

    Mirrors ``openclaw/plugin-sdk/memory-host-core``'s
    ``resolveSessionAgentId``.
    """
    if isinstance(agent_id, str) and agent_id.strip():
        return agent_id.strip()
    return resolve_default_agent_id(app_config)


__all__ = [
    "BridgeConfig",
    "ContextConfig",
    "DEFAULT_WIKI_RENDER_MODE",
    "DEFAULT_WIKI_SEARCH_BACKEND",
    "DEFAULT_WIKI_SEARCH_CORPUS",
    "DEFAULT_WIKI_VAULT_MODE",
    "DEFAULT_WIKI_VAULT_SCOPE",
    "IngestConfig",
    "MemoryWikiConfigIssue",
    "MemoryWikiConfigSchema",
    "MemoryWikiConfigResolver",
    "MemoryWikiPluginConfig",
    "ObsidianConfig",
    "RenderConfig",
    "ResolvedBridgeConfig",
    "ResolvedContextConfig",
    "ResolvedIngestConfig",
    "ResolvedMemoryWikiConfig",
    "ResolvedObsidianConfig",
    "ResolvedRenderConfig",
    "ResolvedSearchConfig",
    "ResolvedUnsafeLocalConfig",
    "ResolvedVaultConfig",
    "SearchConfig",
    "UnsafeLocalConfig",
    "VaultConfig",
    "WIKI_RENDER_MODES",
    "WIKI_SEARCH_BACKENDS",
    "WIKI_SEARCH_CORPORA",
    "WIKI_VAULT_MODES",
    "WIKI_VAULT_SCOPES",
    "WikiRenderMode",
    "WikiSearchBackend",
    "WikiSearchCorpus",
    "WikiVaultMode",
    "WikiVaultScope",
    "expand_home_path",
    "memory_wiki_config_schema",
    "resolve_default_memory_wiki_vault_path",
    "resolve_default_memory_wiki_vault_root",
    "resolve_memory_wiki_agent_config",
    "resolve_memory_wiki_config",
    "resolve_memory_wiki_configured_agent_ids",
]
