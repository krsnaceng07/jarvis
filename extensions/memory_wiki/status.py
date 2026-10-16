"""status — Memory Wiki status report (Phase 4.3g-mr1 deep port).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/status.ts``.

A small async helper that walks the
wiki vault + probes the Obsidian CLI +
checks the public-artifact pipeline + emits
a single ``MemoryWikiStatus`` payload.
The host consumes this from the
``wiki.status`` gateway method and from
the ``wiki status`` / ``wiki doctor``
CLI commands.

The deep checks land here: vault
existence, per-kind page counts, per-
provenance source counts (native,
bridge, bridge-events, unsafe-local,
other), and a list of actionable
warnings (vault-missing, obsidian-cli-
missing, bridge-disabled, bridge-
artifacts-missing, unsafe-local-
disabled, unsafe-local-paths-missing,
unsafe-local-without-mode). The
``build_memory_wiki_doctor_report`` and
``render_memory_wiki_doctor`` helpers
turn those warnings into actionable
fix suggestions.
"""

# ruff: noqa: N815, TCH003, PLR0911, PLR0912 — field names mirror the
# OpenClaw camelCase JSON shape so the
# ``wiki.status`` / ``wiki.doctor``
# gateway responses are byte-compatible
# with the OpenClaw host; the
# ``Awaitable`` / ``Callable`` imports
# stay at runtime so the resolved-config
# type-aliases are usable as the public
# shape; the vault-counts walker +
# doctor-fix lookups mirror OpenClaw's
# per-branch ladder (intentionally long).

from __future__ import annotations

import dataclasses
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import obsidian as _obsidian
from .bridge import filter_memory_wiki_bridge_artifacts, resolve_memory_wiki_vault_agent_id

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


# Mirrors the OpenClaw
# ``MemoryWikiStatusWarning["code"]`` union.
WIKI_STATUS_WARNING_CODES: tuple[str, ...] = (
    "vault-missing",
    "obsidian-cli-missing",
    "bridge-disabled",
    "bridge-artifacts-missing",
    "unsafe-local-disabled",
    "unsafe-local-paths-missing",
    "unsafe-local-without-mode",
)


@dataclass(frozen=True, slots=True)
class MemoryWikiStatusWarning:
    """A single warning emitted by the status checker.

    Mirrors the OpenClaw
    ``MemoryWikiStatusWarning`` type.
    """

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class MemoryWikiStatusObsidianCli:
    """The Obsidian CLI sub-payload of :class:`MemoryWikiStatus`.

    Mirrors the OpenClaw
    ``MemoryWikiStatus["obsidianCli"]``
    type.
    """

    enabled: bool
    requested: bool
    available: bool
    command: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryWikiStatusUnsafeLocal:
    """The unsafe-local sub-payload of :class:`MemoryWikiStatus`.

    Mirrors the OpenClaw
    ``MemoryWikiStatus["unsafeLocal"]``
    type.
    """

    allowPrivateMemoryCoreAccess: bool
    pathCount: int


@dataclass(frozen=True, slots=True)
class MemoryWikiStatusSourceCounts:
    """The source-provenance counts of :class:`MemoryWikiStatus`.

    Mirrors the OpenClaw
    ``MemoryWikiStatus["sourceCounts"]``
    type.
    """

    native: int
    bridge: int
    bridgeEvents: int
    unsafeLocal: int
    other: int


@dataclass(frozen=True, slots=True)
class MemoryWikiStatus:
    """The full status payload.

    Mirrors the OpenClaw ``MemoryWikiStatus``
    type. All field names are camelCase so
    the gateway response is byte-compatible
    with the OpenClaw host.
    """

    vaultScope: str
    agentId: str | None
    vaultMode: str
    renderMode: str
    vaultPath: str
    vaultExists: bool
    bridge: Any  # ResolvedBridgeConfig (camelCase) — kept as Any to avoid the type check
    bridgePublicArtifactCount: int | None
    obsidianCli: MemoryWikiStatusObsidianCli
    unsafeLocal: MemoryWikiStatusUnsafeLocal
    pageCounts: dict[str, int]
    sourceCounts: MemoryWikiStatusSourceCounts
    warnings: list[MemoryWikiStatusWarning]


@dataclass(frozen=True, slots=True)
class MemoryWikiDoctorFix:
    """A single suggested fix from the doctor report.

    Mirrors the OpenClaw
    ``MemoryWikiDoctorFix`` type.
    """

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class MemoryWikiDoctorReport:
    """The doctor report payload.

    Mirrors the OpenClaw
    ``MemoryWikiDoctorReport`` type.
    """

    healthy: bool
    warningCount: int
    status: MemoryWikiStatus
    fixes: list[MemoryWikiDoctorFix]


# ── Dependency injection type ────────────────────────────────


ResolveMemoryWikiStatusDeps = dict[str, Any]


# ── Vault walker ────────────────────────────────────────────


_QUERY_DIRS: tuple[str, ...] = (
    "entities",
    "concepts",
    "sources",
    "syntheses",
    "reports",
)


def _empty_page_counts() -> dict[str, int]:
    return {
        "entity": 0,
        "concept": 0,
        "source": 0,
        "synthesis": 0,
        "report": 0,
    }


def _empty_source_counts() -> MemoryWikiStatusSourceCounts:
    return MemoryWikiStatusSourceCounts(
        native=0,
        bridge=0,
        bridgeEvents=0,
        unsafeLocal=0,
        other=0,
    )


def _collect_vault_counts(vault_path: str) -> tuple[dict[str, int], MemoryWikiStatusSourceCounts]:
    """Walk every ``.md`` file under the per-kind
    subdirectories of ``vault_path`` and
    compute the per-kind + per-provenance
    counts.

    Mirrors the OpenClaw
    ``collectVaultCounts`` helper. Recurses
    into nested subdirectories (OpenClaw
    uses ``fs.readdir({ recursive: true })``
    — the Python port uses
    :func:`os.walk`).
    """
    page_counts = _empty_page_counts()
    source_counts = _empty_source_counts()
    for relative_dir in _QUERY_DIRS:
        dir_path = os.path.join(vault_path, relative_dir)
        if not os.path.isdir(dir_path):
            continue
        for current_root, _dirs, files in os.walk(dir_path):
            for name in files:
                if not name.endswith(".md") or name == "index.md":
                    continue
                absolute = os.path.join(current_root, name)
                relative = os.path.relpath(absolute, vault_path).replace(os.sep, "/")
                page = _summarize_page_file(absolute, relative)
                if page is None:
                    continue
                kind = page.get("kind")
                if kind in page_counts and isinstance(kind, str):
                    page_counts[kind] += 1
                if kind != "source":
                    continue
                if page.get("sourceType") == "memory-bridge-events":
                    source_counts = dataclasses.replace(
                        source_counts, bridgeEvents=source_counts.bridgeEvents + 1
                    )
                elif page.get("sourceType") == "memory-bridge":
                    source_counts = dataclasses.replace(
                        source_counts, bridge=source_counts.bridge + 1
                    )
                elif (
                    page.get("provenanceMode") == "unsafe-local"
                    or page.get("sourceType") == "memory-unsafe-local"
                ):
                    source_counts = dataclasses.replace(
                        source_counts, unsafeLocal=source_counts.unsafeLocal + 1
                    )
                elif not page.get("sourceType"):
                    source_counts = dataclasses.replace(
                        source_counts, native=source_counts.native + 1
                    )
                else:
                    source_counts = dataclasses.replace(
                        source_counts, other=source_counts.other + 1
                    )
    return page_counts, source_counts


def _summarize_page_file(absolute: str, relative: str) -> dict[str, Any] | None:
    """Read a single page file and return a minimal
    summary ``{kind, sourceType, provenanceMode}``.

    Mirrors the relevant subset of the
    OpenClaw ``toWikiPageSummary`` helper.
    Returns ``None`` for unreadable /
    un-parseable files (so the
    ``#96125`` malformed-frontmatter
    exclusion is honored).
    """
    try:
        with open(absolute, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return None
    from .markdown import parse_wiki_frontmatter

    parsed = parse_wiki_frontmatter(raw)
    if parsed is None or not parsed.has_frontmatter:
        # Treat as a no-op — the file is
        # either unreadable or has no
        # frontmatter to inspect.
        return None
    frontmatter = parsed.frontmatter or {}
    kind = frontmatter.get("pageType")
    if not isinstance(kind, str):
        return None
    source_type = frontmatter.get("sourceType")
    provenance_mode = frontmatter.get("provenanceMode")
    return {
        "kind": kind,
        "sourceType": source_type if isinstance(source_type, str) else None,
        "provenanceMode": (provenance_mode if isinstance(provenance_mode, str) else None),
    }


# ── Warning builder ──────────────────────────────────────────


def build_warnings(
    *,
    config: ResolvedMemoryWikiConfig,
    bridge_public_artifact_count: int | None,
    vault_exists: bool,
    obsidian_command: str | None,
) -> list[MemoryWikiStatusWarning]:
    """Build the list of status warnings.

    Mirrors the OpenClaw ``buildWarnings``
    helper.
    """
    warnings: list[MemoryWikiStatusWarning] = []
    if not vault_exists:
        warnings.append(
            MemoryWikiStatusWarning(
                code="vault-missing",
                message="Wiki vault has not been initialized yet.",
            )
        )
    obsidian_cfg = getattr(config, "obsidian", None)
    obsidian_enabled = bool(getattr(obsidian_cfg, "enabled", False))
    obsidian_use_official_cli = bool(getattr(obsidian_cfg, "useOfficialCli", False))
    if obsidian_enabled and obsidian_use_official_cli and not obsidian_command:
        warnings.append(
            MemoryWikiStatusWarning(
                code="obsidian-cli-missing",
                message=(
                    "Obsidian CLI is enabled in config but `obsidian` is not available on PATH."
                ),
            )
        )
    bridge_cfg = getattr(config, "bridge", None)
    bridge_enabled = bool(getattr(bridge_cfg, "enabled", False))
    bridge_read_memory_artifacts = bool(getattr(bridge_cfg, "readMemoryArtifacts", False))
    vault_mode = str(getattr(config, "vaultMode", "single"))
    if vault_mode == "bridge" and not bridge_enabled:
        warnings.append(
            MemoryWikiStatusWarning(
                code="bridge-disabled",
                message="vaultMode is `bridge` but bridge.enabled is false.",
            )
        )
    if (
        vault_mode == "bridge"
        and bridge_enabled
        and bridge_read_memory_artifacts
        and bridge_public_artifact_count == 0
    ):
        warnings.append(
            MemoryWikiStatusWarning(
                code="bridge-artifacts-missing",
                message=(
                    "Bridge mode is enabled but the active memory plugin is "
                    "not exporting any public memory artifacts yet."
                ),
            )
        )
    unsafe_local_cfg = getattr(config, "unsafeLocal", None)
    allow_private = bool(getattr(unsafe_local_cfg, "allowPrivateMemoryCoreAccess", False))
    unsafe_local_paths = getattr(unsafe_local_cfg, "paths", []) or []
    if vault_mode == "unsafe-local" and not allow_private:
        warnings.append(
            MemoryWikiStatusWarning(
                code="unsafe-local-disabled",
                message=("vaultMode is `unsafe-local` but private memory-core access is disabled."),
            )
        )
    if vault_mode == "unsafe-local" and allow_private and len(unsafe_local_paths) == 0:
        warnings.append(
            MemoryWikiStatusWarning(
                code="unsafe-local-paths-missing",
                message=("unsafe-local access is enabled but no private paths are configured."),
            )
        )
    if vault_mode != "unsafe-local" and allow_private:
        warnings.append(
            MemoryWikiStatusWarning(
                code="unsafe-local-without-mode",
                message=("Private memory-core access is enabled outside unsafe-local mode."),
            )
        )
    return warnings


# ── Public API ──────────────────────────────────────────────


async def resolve_memory_wiki_status(
    config: ResolvedMemoryWikiConfig,
    deps: ResolveMemoryWikiStatusDeps | None = None,
) -> MemoryWikiStatus:
    """Resolve the per-vault status payload.

    Mirrors the OpenClaw
    :func:`resolveMemoryWikiStatus`. Walks
    the vault + probes the Obsidian CLI +
    counts public memory artifacts (when
    the bridge pipeline is enabled) +
    returns the assembled status.
    """
    deps = deps or {}
    path_exists: Callable[[str], Awaitable[bool]] = deps.get("pathExists", _default_path_exists)
    list_public_artifacts: Callable[[dict[str, Any]], Awaitable[list[Any]]] = deps.get(
        "listPublicArtifacts", _default_list_public_artifacts
    )
    resolve_command: Callable[[str], Awaitable[str | None]] = deps.get("resolveCommand", None)
    app_config: Any = deps.get("appConfig")
    caller_agent_id: str | None = deps.get("callerAgentId")

    agent_id = resolve_memory_wiki_vault_agent_id(config)
    if config.vault.scope == "agent" and not agent_id:
        raise ValueError("Memory Wiki agent-scoped vault requires a resolved agent id")
    vault_exists = await path_exists(config.vault.path)
    bridge_public_artifact_count: int | None = None
    if (
        app_config is not None
        and config.vaultMode == "bridge"
        and config.bridge.enabled
        and config.bridge.readMemoryArtifacts
    ):
        artifacts = await list_public_artifacts({"cfg": app_config})
        bridge_public_artifact_count = len(
            filter_memory_wiki_bridge_artifacts(
                config=config,
                caller_agent_id=caller_agent_id,
                artifacts=artifacts,
            )
        )
    if resolve_command is not None:
        probe = await _obsidian.probe_obsidian_cli(
            _obsidian.ObsidianCliDeps(resolve_command=resolve_command)
        )
    else:
        probe = await _obsidian.probe_obsidian_cli()
    if vault_exists:
        page_counts, source_counts = _collect_vault_counts(config.vault.path)
    else:
        page_counts = _empty_page_counts()
        source_counts = _empty_source_counts()

    unsafe_local_cfg = getattr(config, "unsafeLocal", None)
    allow_private = bool(getattr(unsafe_local_cfg, "allowPrivateMemoryCoreAccess", False))
    unsafe_local_paths = getattr(unsafe_local_cfg, "paths", []) or []
    warnings = build_warnings(
        config=config,
        bridge_public_artifact_count=bridge_public_artifact_count,
        vault_exists=vault_exists,
        obsidian_command=probe.command,
    )
    obsidian_cfg = getattr(config, "obsidian", None)
    obsidian_enabled = bool(getattr(obsidian_cfg, "enabled", False))
    obsidian_use_official_cli = bool(getattr(obsidian_cfg, "useOfficialCli", False))
    return MemoryWikiStatus(
        vaultScope=config.vault.scope,
        agentId=agent_id,
        vaultMode=config.vaultMode,
        renderMode=config.vault.renderMode,
        vaultPath=config.vault.path,
        vaultExists=vault_exists,
        bridge=config.bridge,
        bridgePublicArtifactCount=bridge_public_artifact_count,
        obsidianCli=MemoryWikiStatusObsidianCli(
            enabled=obsidian_enabled,
            requested=obsidian_enabled and obsidian_use_official_cli,
            available=probe.available,
            command=probe.command,
        ),
        unsafeLocal=MemoryWikiStatusUnsafeLocal(
            allowPrivateMemoryCoreAccess=allow_private,
            pathCount=len(unsafe_local_paths),
        ),
        pageCounts=page_counts,
        sourceCounts=source_counts,
        warnings=warnings,
    )


# ── Doctor ───────────────────────────────────────────────────


def build_memory_wiki_doctor_report(
    status: MemoryWikiStatus,
) -> MemoryWikiDoctorReport:
    """Build the doctor report from a status.

    Mirrors the OpenClaw
    :func:`buildMemoryWikiDoctorReport`.
    """
    fixes = [
        MemoryWikiDoctorFix(
            code=warning.code,
            message=_fix_message_for(warning.code),
        )
        for warning in status.warnings
    ]
    return MemoryWikiDoctorReport(
        healthy=len(status.warnings) == 0,
        warningCount=len(status.warnings),
        status=status,
        fixes=fixes,
    )


def _fix_message_for(code: str) -> str:
    if code == "vault-missing":
        return "Run `openclaw wiki init` to create the vault layout."
    if code == "obsidian-cli-missing":
        return "Install the official Obsidian CLI or disable `obsidian.useOfficialCli`."
    if code == "bridge-disabled":
        return (
            "Enable `plugins.entries.memory-wiki.config.bridge.enabled` or "
            "switch vaultMode away from `bridge`."
        )
    if code == "bridge-artifacts-missing":
        return (
            "Use a memory plugin that exports public artifacts, "
            "create/import memory artifacts first, or switch the wiki back "
            "to isolated mode."
        )
    if code == "unsafe-local-disabled":
        return (
            "Enable `unsafeLocal.allowPrivateMemoryCoreAccess` or switch "
            "vaultMode away from `unsafe-local`."
        )
    if code == "unsafe-local-paths-missing":
        return "Add explicit `unsafeLocal.paths` entries before running unsafe-local imports."
    return "Disable private memory-core access unless you explicitly want unsafe-local mode."


# ── Renderers ───────────────────────────────────────────────


def render_memory_wiki_status(status: MemoryWikiStatus) -> str:
    """Render ``status`` as a plain-text block.

    Mirrors the OpenClaw
    :func:`renderMemoryWikiStatus`.
    """
    lines = [
        f"Wiki vault mode: {status.vaultMode}",
        f"Vault scope: {status.vaultScope}{f' ({status.agentId})' if status.agentId else ''}",
        f"Vault: {'ready' if status.vaultExists else 'missing'} ({status.vaultPath})",
        f"Render mode: {status.renderMode}",
        (
            f"Obsidian CLI: {'available' if status.obsidianCli.available else 'missing'}"
            f"{' (requested)' if status.obsidianCli.requested else ''}"
        ),
        (
            f"Bridge: {'enabled' if status.bridge.enabled else 'disabled'}"
            + (
                f" ({status.bridgePublicArtifactCount} exported artifact"
                f"{'' if status.bridgePublicArtifactCount == 1 else 's'})"
                if isinstance(status.bridgePublicArtifactCount, int)
                else ""
            )
        ),
        (
            f"Unsafe local: {'enabled' if status.unsafeLocal.allowPrivateMemoryCoreAccess else 'disabled'}"
            + (
                f" ({status.unsafeLocal.pathCount} paths)"
                if status.unsafeLocal.allowPrivateMemoryCoreAccess
                else ""
            )
        ),
        (
            f"Pages: {status.pageCounts['source']} sources, "
            f"{status.pageCounts['entity']} entities, "
            f"{status.pageCounts['concept']} concepts, "
            f"{status.pageCounts['synthesis']} syntheses, "
            f"{status.pageCounts['report']} reports"
        ),
        (
            "Source provenance: "
            f"{status.sourceCounts.native} native, "
            f"{status.sourceCounts.bridge} bridge, "
            f"{status.sourceCounts.bridgeEvents} bridge-events, "
            f"{status.sourceCounts.unsafeLocal} unsafe-local, "
            f"{status.sourceCounts.other} other"
        ),
    ]
    if status.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in status.warnings:
            lines.append(f"- {warning.message}")
    return "\n".join(lines)


def render_memory_wiki_doctor(report: MemoryWikiDoctorReport) -> str:
    """Render the doctor report as a plain-text block.

    Mirrors the OpenClaw
    :func:`renderMemoryWikiDoctor`.
    """
    lines = [
        (
            "Wiki doctor: healthy"
            if report.healthy
            else f"Wiki doctor: {report.warningCount} issue(s) found"
        ),
        "",
        render_memory_wiki_status(report.status),
    ]
    if report.fixes:
        lines.append("")
        lines.append("Suggested fixes:")
        for fix in report.fixes:
            lines.append(f"- {fix.message}")
    return "\n".join(lines)


# ── Default dependency implementations ──────────────────────


async def _default_path_exists(path: str) -> bool:
    return os.path.isdir(Path(path))


async def _default_list_public_artifacts(_params: dict[str, Any]) -> list[Any]:
    # The Python port doesn't yet ship the
    # memory-core artifact registry; the
    # default returns an empty list so the
    # status check still works for
    # bridge-disabled configurations. The
    # tests inject their own
    # ``listPublicArtifacts`` to assert on
    # the per-agent artifact count.
    return []


def reset_memory_wiki_status_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


__all__ = [
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
]
