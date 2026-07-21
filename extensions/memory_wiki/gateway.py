"""gateway — Memory Wiki ``memory.wiki.*`` RPC methods (Phase 4.3f-mr4).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/gateway.ts``.

The memory-wiki plugin exposes 19 RPC
methods on the gateway. Each method takes
a ``params`` object + an optional
``appConfig`` + an optional
``resolveRequestContext`` (so the host can
override the per-request config) and
returns a :class:`WikiGatewayResponse`.

For Phase 4.3f-mr4, the 5 tool-mirroring
methods (``wiki.status`` / ``wiki.search`` /
``wiki.apply`` / ``wiki.get`` /
``wiki.lint``) + the supporting
``wiki.init`` / ``wiki.compile`` methods
are fully implemented. The remaining 12
methods (``wiki.importRuns`` /
``wiki.importInsights`` / ``wiki.palace`` /
``wiki.doctor`` / ``wiki.ingest`` /
``wiki.bridge.import`` /
``wiki.unsafeLocal.import`` /
``wiki.obsidian.*``) are registered as
stubs that return a "not yet implemented
in 4.3f-mr4" error so the gateway surface
is fully wired. The full implementations
land in 4.3g.

The OpenClaw scope field
(``operator.read`` / ``operator.write`` /
``operator.admin``) is preserved on each
method's :class:`WikiGatewayMethod` record
so the host can apply scope-based access
control when the methods are registered
with the SDK's gateway surface.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable  # noqa: TCH003 — needed at runtime for WikiGatewayMethod type
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from .apply import (
    apply_memory_wiki_mutation,
    normalize_memory_wiki_mutation_input,
)
from .compile_pipeline import compile_wiki_vault
from .lint import lint_memory_wiki_vault
from .query import (
    WIKI_SEARCH_MODES,
    get_memory_wiki_page,
    search_memory_wiki,
)
from .status import (
    MemoryWikiStatus,
    render_memory_wiki_status,
    resolve_memory_wiki_status,
)
from .vault import initialize_memory_wiki_vault

if TYPE_CHECKING:
    from .config import ResolvedMemoryWikiConfig


# OpenClaw scope constants. The Python
# port preserves the literal values so the
# host can apply scope-based ACL when the
# methods are registered with the SDK.
READ_SCOPE: Literal["operator.read"] = "operator.read"
WRITE_SCOPE: Literal["operator.write"] = "operator.write"
ADMIN_SCOPE: Literal["operator.admin"] = "operator.admin"
LOCAL_FILE_INGEST_SCOPE: Literal["operator.admin"] = ADMIN_SCOPE

GatewayScope = Literal["operator.read", "operator.write", "operator.admin"]


# ── response shape ─────────────────────────────────────────


@dataclass
class WikiGatewayError:
    """An error payload returned by a gateway method.

    Mirrors the OpenClaw
    ``{ code, message }`` error shape.
    """

    code: str
    message: str


@dataclass
class WikiGatewayResponse:
    """The result of a wiki gateway call.

    Mirrors the OpenClaw
    ``(ok, value, error)`` respond tuple.
    ``ok`` is ``True`` for success; ``value``
    carries the method's payload on success;
    ``error`` carries the error dict on
    failure.
    """

    ok: bool
    value: Any = None
    error: WikiGatewayError | None = None


# ── param helpers ─────────────────────────────────────────


def read_string_param(params: dict[str, Any], key: str, *, required: bool = False) -> str | None:
    """Read a required-or-optional string param.

    Mirrors the OpenClaw
    ``readStringParam``. Trims whitespace;
    returns ``None`` for empty strings.
    """
    value = params.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if required:
        raise ValueError(f"{key} is required.")
    return None


def read_positive_integer_param(params: dict[str, Any], key: str) -> int | None:
    """Read a positive integer param.

    Mirrors the OpenClaw
    ``readPositiveIntegerParam``. Returns
    ``None`` for missing or non-positive
    integers.
    """
    value = params.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    if value < 1:
        return None
    return int(value)


def read_enum_param(params: dict[str, Any], key: str, allowed: tuple[str, ...]) -> str | None:
    """Read a string param constrained to a fixed enum.

    Mirrors the OpenClaw
    ``readEnumParam``. Raises ``ValueError``
    when the value is set but not in the
    allowed set.
    """
    value = read_string_param(params, key)
    if value is None:
        return None
    if value not in allowed:
        raise ValueError(f"{key} must be one of: {', '.join(allowed)}.")
    return value


# ── per-method context ───────────────────────────────────


@dataclass
class WikiGatewayRequest:
    """The per-request context for a wiki gateway method.

    Mirrors the OpenClaw
    ``GatewayMethodContext`` shape.
    """

    params: dict[str, Any] = field(default_factory=dict)
    app_config: Any = None
    agent_id: str | None = None
    agent_session_key: str | None = None
    sandboxed: bool = False
    config: Any = None  # ResolvedMemoryWikiConfig


@dataclass
class WikiGatewayMethod:
    """A registered wiki gateway method.

    Mirrors the OpenClaw
    ``{ handler, scope }`` record. The
    handler is sync (the Python port's
    gateway matches the rest of the
    compile / apply / query stack -- the
    per-method handler does its own
    sync filesystem work; the per-vault
    async lock is driven internally by
    :func:`mutation_coordinator`).
    """

    name: str
    handler: Callable[[WikiGatewayRequest], WikiGatewayResponse]
    scope: GatewayScope = READ_SCOPE
    description: str = ""


# ── respond helper ────────────────────────────────────────


def _respond_error(error: BaseException) -> WikiGatewayResponse:
    """Build a standard error response.

    Mirrors the OpenClaw ``respondError``.
    The error code is ``"internal_error"``
    for unhandled exceptions; callers can
    raise their own ``WikiGatewayError``-
    compatible dataclass for typed errors.
    """
    return WikiGatewayResponse(
        ok=False,
        error=WikiGatewayError(
            code="internal_error",
            message=str(error) if str(error) else error.__class__.__name__,
        ),
    )


# ── method handlers ───────────────────────────────────────


def _wiki_status(req: WikiGatewayRequest) -> WikiGatewayResponse:
    config = req.config
    if config is None:
        return _respond_error(ValueError("wiki.status requires a resolved config"))
    _sync_imported_sources_if_needed(config, req.app_config)
    status = resolve_memory_wiki_status(config, caller_agent_id=req.agent_id)
    return WikiGatewayResponse(ok=True, value=_status_to_dict(status))


def _wiki_search(req: WikiGatewayRequest) -> WikiGatewayResponse:
    config = req.config
    if config is None:
        return _respond_error(ValueError("wiki.search requires a resolved config"))
    try:
        query_text = read_string_param(req.params, "query", required=True)
    except ValueError as exc:
        return _respond_error(exc)
    assert isinstance(query_text, str)  # required=True guarantees non-None
    max_results = read_positive_integer_param(req.params, "maxResults")
    try:
        mode_value = read_enum_param(req.params, "mode", tuple(WIKI_SEARCH_MODES))
    except ValueError as exc:
        return _respond_error(exc)
    results = search_memory_wiki(
        config=config,
        query=query_text,
        max_results=max_results,
        mode=mode_value,
    )
    return WikiGatewayResponse(
        ok=True,
        value={
            "results": [dataclasses.asdict(r) for r in results],
            "rendered": _format_search_results(results),
        },
    )


def _wiki_apply(req: WikiGatewayRequest) -> WikiGatewayResponse:
    config = req.config
    if config is None:
        return _respond_error(ValueError("wiki.apply requires a resolved config"))
    try:
        mutation = normalize_memory_wiki_mutation_input(req.params)
    except ValueError as exc:
        return _respond_error(exc)
    result = apply_memory_wiki_mutation(config=config, mutation=mutation)
    return WikiGatewayResponse(
        ok=True,
        value={
            "changed": result.changed,
            "operation": result.operation,
            "pagePath": result.page_path,
            "pageId": result.page_id,
            "scannedCount": result.scanned_count,
            "invalidCount": result.invalid_count,
            "ignoredCount": result.ignored_count,
        },
    )


def _wiki_get(req: WikiGatewayRequest) -> WikiGatewayResponse:
    config = req.config
    if config is None:
        return _respond_error(ValueError("wiki.get requires a resolved config"))
    try:
        lookup = read_string_param(req.params, "lookup", required=True)
    except ValueError as exc:
        return _respond_error(exc)
    assert isinstance(lookup, str)  # required=True guarantees non-None
    from_line = read_positive_integer_param(req.params, "fromLine")
    line_count = read_positive_integer_param(req.params, "lineCount")
    result = get_memory_wiki_page(
        config=config,
        lookup=lookup,
        from_line=from_line,
        line_count=line_count,
    )
    if result is None:
        return WikiGatewayResponse(
            ok=False,
            error=WikiGatewayError(
                code="not_found",
                message=f"Wiki page not found: {lookup}",
            ),
        )
    return WikiGatewayResponse(
        ok=True,
        value={
            "corpus": result.corpus,
            "path": result.path,
            "title": result.title,
            "kind": result.kind,
            "content": result.content,
            "fromLine": result.from_line,
            "lineCount": result.line_count,
            "totalLines": result.total_lines,
            "truncated": result.truncated,
            "id": result.id,
        },
    )


def _wiki_init(req: WikiGatewayRequest) -> WikiGatewayResponse:
    config = req.config
    if config is None:
        return _respond_error(ValueError("wiki.init requires a resolved config"))
    result = initialize_memory_wiki_vault(config)
    return WikiGatewayResponse(
        ok=True,
        value={
            "vaultPath": str(getattr(result, "vault_path", config.vault.path)),
            "createdDirectories": list(getattr(result, "created_directories", [])),
            "createdFiles": list(getattr(result, "created_files", [])),
        },
    )


def _wiki_compile(req: WikiGatewayRequest) -> WikiGatewayResponse:
    config = req.config
    if config is None:
        return _respond_error(ValueError("wiki.compile requires a resolved config"))
    result = compile_wiki_vault(config)
    return WikiGatewayResponse(
        ok=True,
        value={
            "vaultPath": result.vault_path,
            "pages": [dataclasses.asdict(p) for p in result.pages],
            "scannedCount": result.scanned_count,
            "invalidCount": result.invalid_count,
            "ignoredCount": result.ignored_count,
        },
    )


def _wiki_lint(req: WikiGatewayRequest) -> WikiGatewayResponse:
    config = req.config
    if config is None:
        return _respond_error(ValueError("wiki.lint requires a resolved config"))
    result = lint_memory_wiki_vault(config)
    return WikiGatewayResponse(
        ok=True,
        value={
            "vaultPath": result.vault_path,
            "issueCount": result.issue_count,
            "issues": [dataclasses.asdict(i) for i in result.issues],
            "issuesByCategory": {
                key: [dataclasses.asdict(i) for i in issues]
                for key, issues in result.issues_by_category.items()
            },
            "reportPath": result.report_path,
            "rendered": (
                "No wiki lint issues."
                if result.issue_count == 0
                else f"Issues: {result.issue_count}."
            ),
        },
    )


def _not_yet_implemented(req: WikiGatewayRequest) -> WikiGatewayResponse:
    """Stub handler for gateway methods not yet ported.

    The full implementations land in
    Phase 4.3g (importRuns, importInsights,
    palace, doctor, ingest) + the obsidian
    / bridge / unsafe-local import paths.
    """
    return _respond_error(
        NotImplementedError(
            f"{req.params.get('__method__', 'wiki method')} is not yet "
            "implemented in 4.3f-mr4; the full implementation lands in 4.3g."
        )
    )


# ── helpers ───────────────────────────────────────────────


def _status_to_dict(status: MemoryWikiStatus) -> dict[str, Any]:
    """Convert a :class:`MemoryWikiStatus` to a JSON-friendly dict."""
    return {
        "vaultPath": status.vault_path,
        "vaultMode": status.vault_mode,
        "renderMode": status.render_mode,
        "obsidianCliAvailable": status.obsidian_cli_available,
        "unsafeLocalPath": status.unsafe_local_path,
        "bridgeEnabled": status.bridge_enabled,
        "agentIds": status.agent_ids,
        "rendered": render_memory_wiki_status(status),
    }


def _format_search_results(results: list[Any]) -> str:
    """Format the search hits as a plain-text block.

    Mirrors the OpenClaw ``wiki_search``
    tool's text rendering.
    """
    if not results:
        return "No wiki or memory results."
    lines: list[str] = []
    for index, result in enumerate(results, start=1):
        parts = [
            f"{index}. {result.title} ({result.corpus}/{result.kind})",
            f"Path: {result.path}",
        ]
        if isinstance(result.start_line, int) and isinstance(result.end_line, int):
            parts.append(f"Lines: {result.start_line}-{result.end_line}")
        if result.provenance_label:
            parts.append(f"Provenance: {result.provenance_label}")
        if result.matched_claim_id:
            parts.append(f"Claim: {result.matched_claim_id}")
        if result.evidence_kinds:
            parts.append(f"Evidence: {', '.join(result.evidence_kinds)}")
        parts.append(f"Snippet: {result.snippet}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _sync_imported_sources_if_needed(config: Any, app_config: Any) -> None:
    """Sync imported sources (best-effort) before each method.

    Mirrors the OpenClaw
    ``syncImportedSourcesIfNeeded``. The
    full implementation lands in 4.3g;
    the current stub returns a no-op.
    """
    from .source_sync import sync_memory_wiki_imported_sources

    # The OpenClaw implementation is async
    # (it dispatches a real sync); the
    # Python port's stub is sync. When the
    # full implementation lands in 4.3g
    # (async), this helper will need to be
    # re-shaped to match.
    sync_memory_wiki_imported_sources(config=config, app_config=app_config)


# ── method registry ───────────────────────────────────────


def _stub_handler(name: str) -> Callable[[WikiGatewayRequest], Any]:
    """Build a stub handler that names the unimplemented method."""

    def _handler(req: WikiGatewayRequest) -> WikiGatewayResponse:
        return _respond_error(
            NotImplementedError(f"{name} is not yet implemented in 4.3f-mr4; " "lands in 4.3g.")
        )

    return _handler


def register_wiki_gateway_methods(
    *,
    config: ResolvedMemoryWikiConfig,
    app_config: Any = None,
) -> dict[str, WikiGatewayMethod]:
    """Register all 19 wiki gateway methods.

    Mirrors the OpenClaw
    ``registerMemoryWikiGatewayMethods``.
    Returns a dict keyed by method name
    (e.g. ``"wiki.status"`` →
    :class:`WikiGatewayMethod`).
    """
    return {
        # ── read-scope methods ─────────────────────
        "wiki.status": WikiGatewayMethod(
            name="wiki.status",
            handler=_wiki_status,
            scope=READ_SCOPE,
            description=(
                "Inspect the current memory wiki vault mode, health, "
                "and Obsidian CLI availability."
            ),
        ),
        "wiki.importRuns": WikiGatewayMethod(
            name="wiki.importRuns",
            handler=_stub_handler("wiki.importRuns"),
            scope=READ_SCOPE,
            description="List ChatGPT import runs (4.3g).",
        ),
        "wiki.importInsights": WikiGatewayMethod(
            name="wiki.importInsights",
            handler=_stub_handler("wiki.importInsights"),
            scope=READ_SCOPE,
            description="List import insights (4.3g).",
        ),
        "wiki.palace": WikiGatewayMethod(
            name="wiki.palace",
            handler=_stub_handler("wiki.palace"),
            scope=READ_SCOPE,
            description="List memory palace scenes (4.3f-mr7).",
        ),
        "wiki.init": WikiGatewayMethod(
            name="wiki.init",
            handler=_wiki_init,
            scope=READ_SCOPE,
            description="Initialize a memory-wiki vault at the given path.",
        ),
        "wiki.doctor": WikiGatewayMethod(
            name="wiki.doctor",
            handler=_stub_handler("wiki.doctor"),
            scope=READ_SCOPE,
            description="Run the memory-wiki doctor report (4.3g).",
        ),
        "wiki.compile": WikiGatewayMethod(
            name="wiki.compile",
            handler=_wiki_compile,
            scope=READ_SCOPE,
            description="Recompile the memory-wiki vault and return the digest.",
        ),
        "wiki.ingest": WikiGatewayMethod(
            name="wiki.ingest",
            handler=_stub_handler("wiki.ingest"),
            scope=READ_SCOPE,
            description="Ingest a markdown source into the vault (4.3g).",
        ),
        "wiki.lint": WikiGatewayMethod(
            name="wiki.lint",
            handler=_wiki_lint,
            scope=READ_SCOPE,
            description=(
                "Lint the wiki vault and surface structural issues, "
                "provenance gaps, contradictions, and open questions."
            ),
        ),
        "wiki.bridge.import": WikiGatewayMethod(
            name="wiki.bridge.import",
            handler=_stub_handler("wiki.bridge.import"),
            scope=READ_SCOPE,
            description="Trigger a memory-bridge sync (4.3g).",
        ),
        "wiki.unsafeLocal.import": WikiGatewayMethod(
            name="wiki.unsafeLocal.import",
            handler=_stub_handler("wiki.unsafeLocal.import"),
            scope=READ_SCOPE,
            description="Trigger an unsafe-local sync (4.3g).",
        ),
        "wiki.search": WikiGatewayMethod(
            name="wiki.search",
            handler=_wiki_search,
            scope=READ_SCOPE,
            description=(
                "Search wiki pages and, when shared search is enabled, "
                "the active memory corpus by title, path, id, or body "
                "text."
            ),
        ),
        # ── write-scope methods ────────────────────
        "wiki.apply": WikiGatewayMethod(
            name="wiki.apply",
            handler=_wiki_apply,
            scope=WRITE_SCOPE,
            description=("Apply narrow wiki mutations for syntheses and page " "metadata."),
        ),
        "wiki.get": WikiGatewayMethod(
            name="wiki.get",
            handler=_wiki_get,
            scope=WRITE_SCOPE,
            description=(
                "Read a wiki page by id or relative path; falls back to "
                "the active memory corpus when shared search is enabled."
            ),
        ),
        # ── admin-scope methods (obsidian CLI) ─────
        "wiki.obsidian.status": WikiGatewayMethod(
            name="wiki.obsidian.status",
            handler=_stub_handler("wiki.obsidian.status"),
            scope=ADMIN_SCOPE,
            description="Probe the official Obsidian CLI (4.3g).",
        ),
        "wiki.obsidian.search": WikiGatewayMethod(
            name="wiki.obsidian.search",
            handler=_stub_handler("wiki.obsidian.search"),
            scope=ADMIN_SCOPE,
            description="Search Obsidian via the official CLI (4.3g).",
        ),
        "wiki.obsidian.open": WikiGatewayMethod(
            name="wiki.obsidian.open",
            handler=_stub_handler("wiki.obsidian.open"),
            scope=ADMIN_SCOPE,
            description="Open a note in Obsidian (4.3g).",
        ),
        "wiki.obsidian.command": WikiGatewayMethod(
            name="wiki.obsidian.command",
            handler=_stub_handler("wiki.obsidian.command"),
            scope=ADMIN_SCOPE,
            description="Run an arbitrary Obsidian CLI command (4.3g).",
        ),
        "wiki.obsidian.daily": WikiGatewayMethod(
            name="wiki.obsidian.daily",
            handler=_stub_handler("wiki.obsidian.daily"),
            scope=LOCAL_FILE_INGEST_SCOPE,
            description="Open (or create) today's daily note in Obsidian (4.3g).",
        ),
    }


def dispatch_wiki_gateway(
    method: str,
    *,
    params: dict[str, Any] | None = None,
    config: ResolvedMemoryWikiConfig | None = None,
    app_config: Any = None,
    agent_id: str | None = None,
    agent_session_key: str | None = None,
    sandboxed: bool = False,
    methods: dict[str, WikiGatewayMethod] | None = None,
) -> WikiGatewayResponse:
    """Dispatch a single wiki gateway method.

    Mirrors the OpenClaw
    ``api.registerGatewayMethod`` round-trip
    in a Python-friendly shape. Returns a
    :class:`WikiGatewayResponse` so the
    caller can branch on ``ok``.
    """
    method_record = (methods or {}).get(method)
    if method_record is None:
        return _respond_error(ValueError(f"unknown wiki gateway method: {method}"))
    request = WikiGatewayRequest(
        params=dict(params or {}),
        app_config=app_config,
        agent_id=agent_id,
        agent_session_key=agent_session_key,
        sandboxed=sandboxed,
        config=config,
    )
    try:
        result = method_record.handler(request)
        if isinstance(result, WikiGatewayResponse):
            return result
        return WikiGatewayResponse(ok=True, value=result)
    except Exception as exc:
        return _respond_error(exc)


def reset_wiki_gateway_state_for_tests() -> None:
    """Reset module-level state (test-only helper)."""
    return


__all__ = [
    "ADMIN_SCOPE",
    "LOCAL_FILE_INGEST_SCOPE",
    "READ_SCOPE",
    "WRITE_SCOPE",
    "GatewayScope",
    "WikiGatewayError",
    "WikiGatewayMethod",
    "WikiGatewayRequest",
    "WikiGatewayResponse",
    "dispatch_wiki_gateway",
    "read_enum_param",
    "read_positive_integer_param",
    "read_string_param",
    "register_wiki_gateway_methods",
    "reset_wiki_gateway_state_for_tests",
]
