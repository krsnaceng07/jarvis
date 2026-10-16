"""jarvis.canvas.documents — Canvas document materialization.

OpenClaw parity: mirrors ``openclaw-main/src/canvas/documents.ts``.

Manages on-disk Canvas document directories, manifests, and the
hosted-path ↔ local-path URL scheme.

Design decisions ported directly:
- Each document lives under ``<canvas_dir>/<id>/``.
- The manifest is always ``manifest.json``.
- HTML entrypoints are written as ``index.html``.
- Scope-based pruning caps per-session widget count.
- Document IDs are random UUIDs normalised to lower-hex.
- ``retentionScope`` uses a SHA-256 digest of the session/agent key
  (identical to OpenClaw's ``resolveRetentionScope``).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from typing import Literal, Optional

from .constants import CANVAS_DOCUMENTS_PATH
from src.config.paths import resolve_state_dir


# ---------------------------------------------------------------------------
# Types (mirrors CanvasDocumentManifest + CreateInput)
# ---------------------------------------------------------------------------

CanvasDocumentKind = Literal["html_bundle", "url_embed", "document", "image", "video_asset"]
CanvasDocumentSurface = Literal["assistant_message", "tool_card", "sidebar"]
CanvasCspSandbox = Literal["scripts"]


@dataclass(frozen=True, slots=True)
class CanvasDocumentAsset:
    logical_path: str
    source_path: str
    content_type: Optional[str] = None


@dataclass(frozen=True, slots=True)
class CanvasDocumentEntrypointHtml:
    type: Literal["html"] = "html"
    value: str = ""


@dataclass(frozen=True, slots=True)
class CanvasDocumentEntrypointUrl:
    type: Literal["url"] = "url"
    value: str = ""


@dataclass(frozen=True, slots=True)
class CanvasDocumentEntrypointPath:
    type: Literal["path"] = "path"
    value: str = ""


CanvasDocumentEntrypoint = (
    CanvasDocumentEntrypointHtml
    | CanvasDocumentEntrypointUrl
    | CanvasDocumentEntrypointPath
)


@dataclass
class CanvasDocumentCreateInput:
    kind: CanvasDocumentKind
    entrypoint: Optional[CanvasDocumentEntrypoint] = None
    title: Optional[str] = None
    surface: Optional[CanvasDocumentSurface] = None
    retention_scope: Optional[str] = None
    csp_sandbox: Optional[CanvasCspSandbox] = None
    assets: list[CanvasDocumentAsset] = field(default_factory=list)
    preferred_height: Optional[int] = None
    id: Optional[str] = None


@dataclass
class CanvasDocumentManifest:
    id: str
    kind: CanvasDocumentKind
    entry_url: str
    created_at: str
    title: Optional[str] = None
    local_entrypoint: Optional[str] = None
    external_url: Optional[str] = None
    surface: Optional[CanvasDocumentSurface] = None
    retention_scope: Optional[str] = None
    csp_sandbox: Optional[CanvasCspSandbox] = None
    preferred_height: Optional[int] = None
    assets: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "kind": self.kind,
            "entryUrl": self.entry_url,
            "createdAt": self.created_at,
            "assets": self.assets,
        }
        if self.title:
            d["title"] = self.title
        if self.local_entrypoint:
            d["localEntrypoint"] = self.local_entrypoint
        if self.external_url:
            d["externalUrl"] = self.external_url
        if self.surface:
            d["surface"] = self.surface
        if self.retention_scope:
            d["retentionScope"] = self.retention_scope
        if self.csp_sandbox:
            d["cspSandbox"] = self.csp_sandbox
        if self.preferred_height is not None:
            d["preferredHeight"] = self.preferred_height
        return d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def _has_control_character(value: str) -> bool:
    return bool(_CONTROL_CHAR_RE.search(value))


def _canvas_document_id() -> str:
    return uuid.uuid4().hex


def _normalize_canvas_document_id(raw: str) -> str:
    cleaned = raw.strip().lower().replace("-", "")
    if not re.fullmatch(r"[0-9a-f]{32}", cleaned):
        raise ValueError(f"Invalid canvas document id: {raw!r}")
    return cleaned


def _normalize_logical_path(value: str) -> str:
    # Strip leading slashes, collapse ../, sanitise separators
    parts = [p for p in value.replace("\\", "/").split("/") if p and p != "."]
    safe: list[str] = []
    for part in parts:
        if part == "..":
            if safe:
                safe.pop()
        else:
            safe.append(part)
    return "/".join(safe) if safe else "index"


def _resolve_canvas_documents_dir(state_dir: Optional[str] = None) -> str:
    base = state_dir or resolve_state_dir()
    return os.path.join(base, "canvas", "documents")


def _resolve_canvas_document_dir(document_id: str, state_dir: Optional[str] = None) -> str:
    return os.path.join(_resolve_canvas_documents_dir(state_dir), document_id)


def _build_canvas_document_entry_url(document_id: str, entrypoint: str) -> str:
    normalized = _normalize_logical_path(entrypoint)
    encoded = "/".join(
        _url_encode_segment(seg) for seg in normalized.split("/")
    )
    return f"{CANVAS_DOCUMENTS_PATH}/{_url_encode_segment(document_id)}/{encoded}"


def _url_encode_segment(s: str) -> str:
    """Percent-encode a single URL path segment."""
    import urllib.parse
    return urllib.parse.quote(s, safe="")


def resolve_canvas_http_path_to_local_path(
    request_path: str,
    state_dir: Optional[str] = None,
) -> Optional[str]:
    """Map a Canvas hosted URL path back to the managed local file."""
    trimmed = request_path.strip()
    prefix = f"{CANVAS_DOCUMENTS_PATH}/"
    if not trimmed.startswith(prefix):
        return None
    # Strip query / fragment
    path_only = re.sub(r"[?#].*$", "", trimmed)
    relative = path_only[len(prefix):]
    import urllib.parse
    segments = []
    for seg in relative.split("/"):
        if not seg:
            continue
        try:
            segments.append(urllib.parse.unquote(seg))
        except Exception:
            return None
    if len(segments) < 2:
        return None
    raw_id, *entry_parts = segments
    if not raw_id:
        return None
    try:
        doc_id = _normalize_canvas_document_id(raw_id)
        normalized_entry = _normalize_logical_path("/".join(entry_parts))
        docs_dir = _resolve_canvas_documents_dir(state_dir)
        candidate = os.path.realpath(
            os.path.join(_resolve_canvas_document_dir(doc_id, state_dir), normalized_entry)
        )
        if not candidate.startswith(os.path.realpath(docs_dir) + os.sep):
            return None
        return candidate
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------

def _prune_canvas_documents_for_scope(
    *,
    documents_dir: str,
    retention_scope: str,
    max_documents: int,
) -> None:
    """Remove oldest documents for a scope when over the cap."""
    scoped: list[dict] = []
    try:
        for entry in os.scandir(documents_dir):
            if not entry.is_dir():
                continue
            manifest_path = os.path.join(entry.path, "manifest.json")
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                if manifest.get("retentionScope") == retention_scope:
                    scoped.append({
                        "id": entry.name,
                        "path": entry.path,
                        "created_at": manifest.get("createdAt", ""),
                    })
            except Exception:
                continue
    except FileNotFoundError:
        return

    if len(scoped) <= max_documents:
        return

    delete_count = len(scoped) - max_documents
    oldest = sorted(scoped, key=lambda d: (d["created_at"], d["id"]))[:delete_count]
    for doc in oldest:
        shutil.rmtree(doc["path"], ignore_errors=True)


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------

def _escape_html(value: str) -> str:
    return (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _materialize_entrypoint(
    root_dir: str,
    input: CanvasDocumentCreateInput,
    doc_id: str,
) -> dict:
    """Write entrypoint, return {entry_url, local_entrypoint?, external_url?}."""
    ep = input.entrypoint
    if ep is None:
        raise ValueError("canvas document entrypoint required")

    if ep.type == "html":
        file_name = "index.html"
        _write_file(root_dir, file_name, ep.value)
        return {
            "local_entrypoint": file_name,
            "entry_url": _build_canvas_document_entry_url(doc_id, file_name),
        }

    if ep.type == "url":
        return {
            "external_url": ep.value,
            "entry_url": ep.value,
        }

    # type == "path"
    resolved_path = (
        os.path.expanduser(ep.value)
        if ep.value.startswith("~")
        else os.path.abspath(ep.value)
    )
    file_name = os.path.basename(resolved_path) or "document"
    dest = os.path.join(root_dir, file_name)
    shutil.copy2(resolved_path, dest)
    return {
        "local_entrypoint": file_name,
        "entry_url": _build_canvas_document_entry_url(doc_id, file_name),
    }


def _write_file(dir_path: str, filename: str, content: str) -> None:
    os.makedirs(dir_path, exist_ok=True)
    with open(os.path.join(dir_path, filename), "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_canvas_document(
    input: CanvasDocumentCreateInput,
    *,
    state_dir: Optional[str] = None,
    max_documents_per_scope: Optional[int] = None,
) -> CanvasDocumentManifest:
    """Create a Canvas document directory, write its manifest, and return it.

    OpenClaw parity: mirrors ``createCanvasDocument`` in ``documents.ts``.
    """
    from datetime import datetime, timezone

    doc_id = (
        _normalize_canvas_document_id(input.id)
        if (input.id and input.id.strip())
        else _canvas_document_id()
    )
    root_dir = _resolve_canvas_document_dir(doc_id, state_dir)

    # Remove stale version first, then create fresh.
    shutil.rmtree(root_dir, ignore_errors=True)
    os.makedirs(root_dir, exist_ok=True)

    # Copy assets
    assets_out: list[dict] = []
    for asset in input.assets:
        logical = _normalize_logical_path(asset.logical_path)
        src = (
            os.path.expanduser(asset.source_path)
            if asset.source_path.startswith("~")
            else os.path.abspath(asset.source_path)
        )
        dest = os.path.join(root_dir, logical)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)
        asset_entry: dict = {"logicalPath": logical}
        if asset.content_type:
            asset_entry["contentType"] = asset.content_type
        assets_out.append(asset_entry)

    # Materialise entrypoint
    entry = _materialize_entrypoint(root_dir, input, doc_id)

    created_at = datetime.now(timezone.utc).isoformat()

    manifest = CanvasDocumentManifest(
        id=doc_id,
        kind=input.kind,
        entry_url=entry["entry_url"],
        created_at=created_at,
        title=input.title.strip() if input.title and input.title.strip() else None,
        local_entrypoint=entry.get("local_entrypoint"),
        external_url=entry.get("external_url"),
        surface=input.surface,
        retention_scope=input.retention_scope,
        csp_sandbox=input.csp_sandbox,
        preferred_height=input.preferred_height,
        assets=assets_out,
    )

    # Write manifest
    manifest_path = os.path.join(root_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, indent=2)

    # Scope-based pruning
    if input.retention_scope and max_documents_per_scope:
        _prune_canvas_documents_for_scope(
            documents_dir=_resolve_canvas_documents_dir(state_dir),
            retention_scope=input.retention_scope,
            max_documents=max_documents_per_scope,
        )

    return manifest


def resolve_retention_scope(session_id: Optional[str], agent_id: Optional[str]) -> str:
    """Build a SHA-256 retention scope key.

    OpenClaw parity: mirrors ``resolveRetentionScope`` in ``widget-tool.ts``.
    """
    scope = f"session:{session_id}" if session_id else f"agent:{agent_id or 'default'}"
    return hashlib.sha256(scope.encode()).hexdigest()


__all__ = [
    "CanvasDocumentAsset",
    "CanvasDocumentCreateInput",
    "CanvasDocumentEntrypointHtml",
    "CanvasDocumentEntrypointPath",
    "CanvasDocumentEntrypointUrl",
    "CanvasDocumentManifest",
    "create_canvas_document",
    "resolve_canvas_http_path_to_local_path",
    "resolve_retention_scope",
]
