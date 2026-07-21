"""bridge — Memory Wiki bridge (memory-core re-export) path.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/bridge.ts``.

The bridge path implements the
``vaultMode=bridge`` read-only mirror of
the memory-core's public artifacts
(memory-root, daily-note, dream-report,
event-log) into the memory-wiki vault. The
Python port preserves the same shape:

- ``resolve_memory_wiki_vault_agent_id``
  resolves the vault owner (global → no
  agent; agent-scoped → the agent id).
- ``filter_memory_wiki_bridge_artifacts``
  drops artifacts that don't belong to the
  vault's agent.
- ``sync_memory_wiki_bridge_sources`` is
  the public entry point that walks the
  filtered artifacts, computes a per-
  artifact ``syncKey``, and writes a
  ``sources/`` page for each (delegating to
  :func:`source_page_shared.write_imported_source_page`
  once Phase 4.3g lands the file).

Phase 4.3f-mr2 ships the agent-id filter +
artifact collection + per-artifact
``syncKey`` derivation. The actual
``write_bridge_source_page`` +
``sync_memory_wiki_bridge_sources`` write
loops land in 4.3g alongside
``source-page-shared.ts``.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from jarvis_sdk import normalize_agent_id

from .markdown_pages import slugify_wiki_segment
from .source_path_shared import resolve_artifact_key

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .config import ResolvedMemoryWikiConfig


# Mirrors the OpenClaw ``BridgeArtifact`` /
# ``BridgeMemoryWikiResult`` shapes.
BridgeArtifactType = Literal["markdown", "memory-events"]


@dataclass(frozen=True, slots=True)
class BridgeArtifact:
    """One filtered bridge artifact ready for sync.

    Mirrors the OpenClaw
    ``BridgeArtifact`` shape.
    """

    sync_key: str
    artifact_type: BridgeArtifactType
    workspace_dir: str
    relative_path: str
    absolute_path: str


@dataclass(frozen=True, slots=True)
class BridgeMemoryWikiResult:
    """The ``syncMemoryWikiBridgeSources`` return shape."""

    imported_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    removed_count: int = 0
    artifact_count: int = 0
    workspaces: int = 0
    page_paths: list[str] = field(default_factory=list)


# The set of memory-core artifact kinds the
# bridge re-exports. Mirrors the OpenClaw
# ``shouldImportArtifact`` switch.
BRIDGE_IMPORT_KINDS: frozenset[str] = frozenset(
    {"memory-root", "daily-note", "dream-report", "event-log"}
)


def resolve_memory_wiki_vault_agent_id(
    config: ResolvedMemoryWikiConfig,
) -> str | None:
    """Return the vault owner id (``None`` for global).

    Mirrors the OpenClaw
    ``resolveMemoryWikiVaultAgentId``.
    Global-scope vaults return ``None``;
    agent-scope vaults return the normalized
    agent id. Raises ``ValueError`` when the
    scope is ``agent`` but no agent id is
    configured.
    """
    scope = getattr(config.vault, "scope", "global")
    if scope == "global":
        return None
    agent_id_raw = getattr(config, "agentId", None)
    agent_id: str | None = None
    if isinstance(agent_id_raw, str):
        trimmed = agent_id_raw.strip()
        if trimmed:
            agent_id = trimmed
    if not agent_id:
        raise ValueError("Memory Wiki agent-scoped vault requires a resolved agent id")
    return normalize_agent_id(agent_id)


def filter_memory_wiki_bridge_artifacts(
    *,
    config: ResolvedMemoryWikiConfig,
    artifacts: Iterable[Any],
    caller_agent_id: str | None = None,
) -> list[Any]:
    """Filter a list of public artifacts to the vault's agent scope.

    Mirrors the OpenClaw
    ``filterMemoryWikiBridgeArtifacts``.
    Agent-scoped vaults only see artifacts
    whose ``agentIds`` include the vault's
    owner id (or the caller's agent id when
    the vault is global). Global-scope
    vaults pass every artifact through.
    """
    out: list[Any] = []
    artifact_list = list(artifacts)
    vault_agent_id = resolve_memory_wiki_vault_agent_id(config)
    caller_trimmed = caller_agent_id.strip() if isinstance(caller_agent_id, str) else None
    agent_id: str | None = vault_agent_id
    if agent_id is None and caller_trimmed:
        agent_id = normalize_agent_id(caller_trimmed)
    if not agent_id:
        return artifact_list
    for artifact in artifact_list:
        artifact_agent_ids_raw = getattr(artifact, "agentIds", None)
        artifact_agent_ids: list[str] = (
            list(artifact_agent_ids_raw) if isinstance(artifact_agent_ids_raw, list) else []
        )
        if any(
            isinstance(artifact_agent_id, str)
            and artifact_agent_id.strip()
            and normalize_agent_id(artifact_agent_id) == agent_id
            for artifact_agent_id in artifact_agent_ids
        ):
            out.append(artifact)
    return out


def should_import_bridge_artifact(
    *,
    kind: str,
    bridge_config: Any,
) -> bool:
    """Return True iff the bridge should import an artifact of ``kind``.

    Mirrors the OpenClaw
    ``shouldImportArtifact``. The decision
    is driven by the four boolean toggles on
    the bridge config:
    ``indexMemoryRoot`` / ``indexDailyNotes`` /
    ``indexDreamReports`` / ``followMemoryEvents``.
    """
    if kind == "memory-root":
        return bool(getattr(bridge_config, "indexMemoryRoot", False))
    if kind == "daily-note":
        return bool(getattr(bridge_config, "indexDailyNotes", False))
    if kind == "dream-report":
        return bool(getattr(bridge_config, "indexDreamReports", False))
    if kind == "event-log":
        return bool(getattr(bridge_config, "followMemoryEvents", False))
    return False


def is_path_inside_or_equal(  # noqa: PLR0911 — mirrors OpenClaw's per-check returns
    parent_path: str, candidate_path: str
) -> bool:
    """True iff ``candidate_path`` is inside (or equal to) ``parent_path``.

    Mirrors the OpenClaw
    ``isPathInsideOrEqual``. Used to drop
    artifacts that already live under the
    wiki vault (the bridge should not
    re-import its own pages).

    The OpenClaw implementation uses
    ``path.relative``; the Python port uses
    :func:`os.path.relpath` and falls back to
    a string-prefix check when the two paths
    live on different drives (the relpath
    call returns an absolute path on
    Windows in that case, which would
    otherwise be misread as "not inside").
    """
    if candidate_path == parent_path:
        return True
    try:
        relative = os.path.relpath(candidate_path, parent_path)
    except ValueError:
        # Different drives on Windows.
        return False
    if relative == "":
        return True
    if relative == "..":
        return False
    if relative.startswith(".." + os.sep):
        return False
    if os.path.isabs(relative):
        return False
    # Prefix check: if the candidate is a
    # string-prefix of the parent (or
    # vice-versa) on a different OS, treat as
    # inside. Useful for the cross-OS test
    # path (``/tmp/...`` vs
    # ``C:\\Users\\...``).
    parent_norm = parent_path.replace("\\", "/").rstrip("/")
    candidate_norm = candidate_path.replace("\\", "/").rstrip("/")
    if candidate_norm == parent_norm:
        return True
    return candidate_norm.startswith(parent_norm + "/")


def collect_bridge_artifacts(
    *,
    bridge_config: Any,
    vault_root: str,
    artifacts: Iterable[Any],
) -> list[BridgeArtifact]:
    """Collect the bridge artifacts eligible for sync.

    Mirrors the OpenClaw
    ``collectBridgeArtifacts``. Drops
    artifacts that:
    - are not in :data:`BRIDGE_IMPORT_KINDS`,
    - the bridge config has disabled,
    - live inside the wiki vault.
    """
    collected: list[BridgeArtifact] = []
    vault_root_key = resolve_artifact_key(vault_root)
    for artifact in artifacts:
        kind = getattr(artifact, "kind", None)
        if not isinstance(kind, str):
            continue
        if not should_import_bridge_artifact(kind=kind, bridge_config=bridge_config):
            continue
        absolute_path = getattr(artifact, "absolutePath", None)
        if not isinstance(absolute_path, str) or not absolute_path:
            continue
        relative_path = getattr(artifact, "relativePath", None)
        if not isinstance(relative_path, str) or not relative_path:
            continue
        workspace_dir = getattr(artifact, "workspaceDir", None)
        if not isinstance(workspace_dir, str) or not workspace_dir:
            continue
        sync_key = resolve_artifact_key(absolute_path)
        if is_path_inside_or_equal(vault_root_key, sync_key):
            continue
        artifact_type: BridgeArtifactType = "memory-events" if kind == "event-log" else "markdown"
        collected.append(
            BridgeArtifact(
                sync_key=sync_key,
                artifact_type=artifact_type,
                workspace_dir=workspace_dir,
                relative_path=relative_path,
                absolute_path=absolute_path,
            )
        )
    # Dedupe by syncKey (the last write wins).
    deduped: dict[str, BridgeArtifact] = {}
    for artifact in collected:
        deduped[artifact.sync_key] = artifact
    return list(deduped.values())


def resolve_bridge_title(
    *,
    artifact: BridgeArtifact,
    agent_ids: list[str],
) -> str:
    """Build the page title for a bridge artifact.

    Mirrors the OpenClaw
    ``resolveBridgeTitle``. ``memory-events``
    artifacts get a fixed "event journal"
    title; ``markdown`` artifacts derive
    their title from the relative path
    (``memory/foo.md`` → ``"foo"``).
    """
    if artifact.artifact_type == "memory-events":
        if not agent_ids:
            return "Memory Bridge: event journal"
        return f"Memory Bridge ({', '.join(agent_ids)}): event journal"
    base = artifact.relative_path
    if base.lower().endswith(".md"):
        base = base[:-3]
    if base.startswith("memory/"):
        base = base[len("memory/") :]
    base = base.replace("/", " / ")
    if not agent_ids:
        return f"Memory Bridge: {base}"
    return f"Memory Bridge ({', '.join(agent_ids)}): {base}"


def resolve_bridge_page_path(*, workspace_dir: str, relative_path: str) -> dict[str, str]:
    """Compute the page id + relative path for a bridge artifact.

    Mirrors the OpenClaw
    ``resolveBridgePagePath``. The page is
    stored under ``sources/`` with a
    ``bridge-{workspaceSlug}-{artifactSlug}``
    filename. The slugs are derived from the
    workspace dir + the relative path; a
    SHA-1 hash (first 8 hex chars) is
    appended to keep the slug stable across
    re-normalization.
    """
    workspace_base = slugify_wiki_segment(os.path.basename(workspace_dir))
    workspace_hash = hashlib.sha1(  # noqa: S324 — SHA-1 is the OpenClaw slug hash
        os.path.abspath(workspace_dir).encode("utf-8")
    ).hexdigest()
    artifact_relative = relative_path
    if artifact_relative.lower().endswith(".md"):
        artifact_relative = artifact_relative[:-3]
    artifact_base = slugify_wiki_segment(artifact_relative.replace("/", "-"))
    artifact_hash = hashlib.sha1(  # noqa: S324 — SHA-1 is the OpenClaw slug hash
        relative_path.encode("utf-8")
    ).hexdigest()
    workspace_slug = f"{workspace_base}-{workspace_hash[:8]}"
    artifact_slug = f"{artifact_base}-{artifact_hash[:8]}"
    file_stem = f"bridge-{workspace_slug}-{artifact_slug}"
    page_id = f"source.bridge.{workspace_slug}.{artifact_slug}"
    page_path = os.path.join("sources", f"{file_stem}.md").replace("\\", "/")
    return {
        "pageId": page_id,
        "pagePath": page_path,
        "workspaceSlug": workspace_slug,
        "artifactSlug": artifact_slug,
    }


def resolve_bridge_render_fingerprint(
    *,
    artifact: BridgeArtifact,
    agent_ids: list[str],
) -> str:
    """Compute the SHA-1 render fingerprint for a bridge artifact.

    Mirrors the OpenClaw
    ``writeBridgeSourcePage`` SHA-1
    fingerprint over the
    ``{artifactType, workspaceDir,
    relativePath, agentIds}`` tuple. The
    fingerprint is used by the
    ``source_sync_state`` to skip a re-write
    when the upstream artifact + agent
    membership hasn't changed.
    """
    payload = {
        "artifactType": artifact.artifact_type,
        "workspaceDir": artifact.workspace_dir,
        "relativePath": artifact.relative_path,
        "agentIds": list(agent_ids),
    }
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(  # noqa: S324 — SHA-1 is the OpenClaw render fingerprint
        serialized.encode("utf-8")
    ).hexdigest()


def _render_markdown_fence(content: str, language: str) -> str:
    """Wrap ``content`` in a triple-backtick fence.

    Mirrors the OpenClaw
    ``renderMarkdownFence`` from
    ``openclaw/plugin-sdk/memory-host-markdown``.
    """
    return f"```{language}\n{content}\n```"


def build_bridge_page_body(
    *,
    artifact: BridgeArtifact,
    title: str,
    raw: str,
    agent_ids: list[str],
    updated_at: str,
) -> str:
    """Build the rendered body for a bridge source page.

    Mirrors the OpenClaw ``writeBridgeSourcePage``
    ``buildRendered`` callback. The body
    includes the
    ``<!-- openclaw:human:start/end -->``
    human-notes block so operators can add
    notes that the bridge re-import won't
    clobber.
    """
    from .markdown import WIKI_RAW_SOURCE_MARKER

    content_language = "json" if artifact.artifact_type == "memory-events" else "markdown"
    lines: list[str] = [
        f"# {title}",
        "",
        WIKI_RAW_SOURCE_MARKER,
        "## Bridge Source",
        f"- Workspace: `{artifact.workspace_dir}`",
        f"- Relative path: `{artifact.relative_path}`",
        f"- Kind: `{artifact.artifact_type}`",
        f"- Agents: {', '.join(agent_ids) if agent_ids else 'unknown'}",
        f"- Updated: {updated_at}",
        "",
        "## Content",
        _render_markdown_fence(raw, content_language),
        "",
        "## Notes",
        "<!-- openclaw:human:start -->",
        "<!-- openclaw:human:end -->",
        "",
    ]
    return "\n".join(lines)


def reset_memory_wiki_bridge_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


async def sync_memory_wiki_bridge_sources(
    *,
    config: Any,
    app_config: Any = None,
) -> BridgeMemoryWikiResult:
    """Sync the bridge-imported sources (Phase 4.3g-mr2 stub).

    The full implementation walks every
    workspace listed in
    ``app_config.agents.list[*].workspace``,
    enumerates the public memory artifacts
    + per-agent events, and writes a
    ``source.memory-bridge`` /
    ``source.memory-bridge-events`` page
    for each (via
    :func:`write_imported_source_page`).
    The full port lands in Phase 4.3g-mr3
    alongside the
    ``chatgpt-import.ts`` / ``import-runs.ts``
    / ``import-insights.ts`` surfaces.

    For now, the orchestrator returns a
    no-op result so the dispatch path is
    fully wired and the source-sync
    / source-page-shared modules can be
    tested in isolation.
    """
    return BridgeMemoryWikiResult(
        imported_count=0,
        updated_count=0,
        skipped_count=0,
        removed_count=0,
        artifact_count=0,
        workspaces=0,
        page_paths=[],
    )


__all__ = [
    "BRIDGE_IMPORT_KINDS",
    "BridgeArtifact",
    "BridgeArtifactType",
    "BridgeMemoryWikiResult",
    "build_bridge_page_body",
    "collect_bridge_artifacts",
    "filter_memory_wiki_bridge_artifacts",
    "is_path_inside_or_equal",
    "reset_memory_wiki_bridge_state_for_tests",
    "resolve_bridge_page_path",
    "resolve_bridge_render_fingerprint",
    "resolve_bridge_title",
    "resolve_memory_wiki_vault_agent_id",
    "should_import_bridge_artifact",
]
