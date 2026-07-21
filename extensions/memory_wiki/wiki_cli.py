"""wiki_cli — Memory Wiki command-group CLI (Phase 4.3g-mr7).

OpenClaw parity: mirrors
``extensions/memory-wiki/src/cli.ts``,
adapted from Commander to ``argparse``
(the Python SDK's CLI primitive).

The ``wiki`` command group wires the
memory-wiki plugin's operator surface to
the host's CLI program. The Python port
covers the 19 commands + sub-commands
that the OpenClaw source defines:

  wiki status
  wiki doctor
  wiki init
  wiki compile
  wiki lint
  wiki ingest <path>
  wiki okf import <path>
  wiki search <query>
  wiki get <lookup>
  wiki apply synthesis <title>
  wiki apply metadata <lookup>
  wiki bridge import
  wiki unsafe-local import
  wiki chatgpt import --export <path>
  wiki obsidian status
  wiki obsidian search <query>
  wiki obsidian open <path>
  wiki obsidian command <id>
  wiki obsidian daily

Each handler dispatches with the resolved
:class:`WikiCommandContext` (config +
optional agentId + optional appConfig).
"""

# ruff: noqa: N815, PLR0912, PLR0915, TCH003, RET504 — the registrar
# mirrors OpenClaw's exhaustive
# 19-command ladder; the per-handler
# dispatch + JSON formatting +
# sanitization helpers match the
# OpenClaw ts source line-for-line.
# Field names mirror the OpenClaw
# camelCase JSON shape returned by
# the gateway responses. ``argparse``
# + ``Callable`` are used at runtime
# (not just for type annotations).
# The sanitizer chains a series of
# ``re.sub`` calls into a single
# local; restructuring to inline
# each return would be a cosmetic
# churn for no readability win.

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TextIO

from .apply import (
    CreateSynthesisMutation,
    UpdateMetadataMutation,
    apply_memory_wiki_mutation,
)
from .chatgpt_import import import_chatgpt_export
from .compile_pipeline import compile_wiki_vault
from .config import (
    WIKI_SEARCH_BACKENDS,
    WIKI_SEARCH_CORPORA,
    resolve_memory_wiki_agent_config,
)
from .ingest import ingest_memory_wiki_source
from .lint import lint_memory_wiki_vault
from .obsidian import (
    probe_obsidian_cli,
    run_obsidian_command,
    run_obsidian_daily,
    run_obsidian_open,
    run_obsidian_search,
)
from .okf import format_okf_import_summary, import_memory_wiki_okf_bundle
from .query import (
    WIKI_SEARCH_MODES,
    get_memory_wiki_page,
    search_memory_wiki,
)
from .source_sync import sync_memory_wiki_imported_sources
from .status import (
    build_memory_wiki_doctor_report,
    render_memory_wiki_doctor,
    render_memory_wiki_status,
    resolve_memory_wiki_status,
)
from .vault import initialize_memory_wiki_vault

if TYPE_CHECKING:
    from .config import MemoryWikiConfigResolver, ResolvedMemoryWikiConfig


# Output sanitization limits — mirror the
# OpenClaw ``WIKI_GATEWAY_TIMEOUT_MS`` /
# ``GATEWAY_TERMINAL_STRING_MAX_CHARS``
# constants.
WIKI_GATEWAY_TIMEOUT_MS = "30000"
GATEWAY_TERMINAL_STRING_MAX_CHARS = 2_000
GATEWAY_RESPONSE_MAX_STRING_CHARS = 10_000
GATEWAY_RESPONSE_MAX_CODE_CHARS = 256


# ── Output helpers ──────────────────────────────────────────


def _sanitize_gateway_string_for_terminal(value: str) -> str:
    """Strip ANSI escapes / control chars from
    ``value`` and truncate to the CLI
    string budget.

    Mirrors OpenClaw's
    ``sanitizeGatewayStringForTerminal``.
    """
    import re

    if len(value) > GATEWAY_TERMINAL_STRING_MAX_CHARS:
        value = value[:GATEWAY_TERMINAL_STRING_MAX_CHARS]
    value = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", value)
    value = re.sub(r"[\x00-\x1F\x7F-\x9F]+", " ", value)
    value = re.sub(r"[\u061C\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]", "", value)
    return value


def _write_output(output: str, writer: TextIO | None = None) -> None:
    """Write ``output`` to ``writer`` (default
    ``sys.stdout``) and append a trailing
    newline if missing.
    """
    target: TextIO = writer if writer is not None else sys.stdout
    target.write(output if output.endswith("\n") else f"{output}\n")


def _format_json_or_text(result: Any, json_flag: bool, render: Callable[[Any], str]) -> str:
    """Return either JSON or the
    ``render(result)`` text.

    Mirrors OpenClaw's
    ``formatJsonOrText``.
    """
    if json_flag:
        return json.dumps(result, indent=2, default=str)
    return render(result)


# ── Command context ──────────────────────────────────────────


@dataclass
class WikiCommandContext:
    """The resolved context shared by every
    ``wiki`` sub-command.

    Mirrors OpenClaw's
    ``commandContext`` shape (resolved
    config + optional agentId + optional
    appConfig).
    """

    config: ResolvedMemoryWikiConfig
    agent_id: str | None = None
    app_config: Any = None


@dataclass
class MemoryWikiCliRegistration:
    """The registration kwargs for
    :func:`register_wiki_cli`.

    Mirrors OpenClaw's
    ``MemoryWikiCliRegistration`` type.
    """

    config: ResolvedMemoryWikiConfig
    resolve_config: MemoryWikiConfigResolver | None = None
    get_app_config: Callable[[], Any] | None = None


# ── Pre-action resolver ─────────────────────────────────────


def _build_resolve_config(
    registration: MemoryWikiCliRegistration,
) -> MemoryWikiConfigResolver:
    """Build a ``resolveConfig`` closure.

    Mirrors OpenClaw's
    ``registerWikiCli`` resolver builder.
    Falls back to a wrapper around
    :func:`resolve_memory_wiki_agent_config`
    when the caller did not provide one.
    """
    if registration.resolve_config is not None:
        return registration.resolve_config

    def _default_resolve(
        agent_id: str | None, app_config: Any | None = None
    ) -> ResolvedMemoryWikiConfig:
        return resolve_memory_wiki_agent_config(
            config=registration.config,
            app_config=app_config,
            agent_id=agent_id,
        )

    return _default_resolve


def _require_command_context(context: WikiCommandContext | None) -> WikiCommandContext:
    """Return ``context`` or raise if it was
    never resolved (the ``preAction`` hook
    did not run).
    """
    if context is None:
        raise RuntimeError("Memory Wiki CLI agent context was not resolved.")
    return context


# ── Command handlers ─────────────────────────────────────────


def _run_wiki_status(
    context: WikiCommandContext,
    *,
    json_flag: bool,
) -> Any:
    deps: dict[str, Any] = {}
    if context.app_config is not None:
        deps["appConfig"] = context.app_config
    status = asyncio.run(resolve_memory_wiki_status(context.config, deps=deps))
    rendered = _format_json_or_text(status, json_flag, render_memory_wiki_status)
    _write_output(rendered)
    return status


def _run_wiki_doctor(
    context: WikiCommandContext,
    *,
    json_flag: bool,
) -> Any:
    deps: dict[str, Any] = {}
    if context.app_config is not None:
        deps["appConfig"] = context.app_config
    status = asyncio.run(resolve_memory_wiki_status(context.config, deps=deps))
    report = build_memory_wiki_doctor_report(status)
    rendered = _format_json_or_text(report, json_flag, render_memory_wiki_doctor)
    _write_output(rendered)
    if not report.healthy:
        sys.exit(1)
    return report


def _run_wiki_init(
    context: WikiCommandContext,
    *,
    json_flag: bool,
) -> Any:
    result = initialize_memory_wiki_vault(context.config)
    rendered = _format_json_or_text(
        result,
        json_flag,
        lambda v: (
            f"Initialized wiki vault at {v.root_dir} "
            f"({len(v.created_directories)} dirs, "
            f"{len(v.created_files)} files)."
        ),
    )
    _write_output(rendered)
    return result


def _run_wiki_compile(
    context: WikiCommandContext,
    *,
    json_flag: bool,
) -> Any:
    asyncio.run(
        sync_memory_wiki_imported_sources(config=context.config, app_config=context.app_config)
    )
    result = compile_wiki_vault(context.config)
    rendered = _format_json_or_text(
        result,
        json_flag,
        lambda v: (
            f"Compiled wiki vault at {v.vault_path} "
            f"({len(v.pages)} pages, {v.valid_count} valid)."
        ),
    )
    _write_output(rendered)
    return result


def _run_wiki_lint(
    context: WikiCommandContext,
    *,
    json_flag: bool,
) -> Any:
    asyncio.run(
        sync_memory_wiki_imported_sources(config=context.config, app_config=context.app_config)
    )
    result = asyncio.run(lint_memory_wiki_vault(context.config))
    rendered = _format_json_or_text(
        result,
        json_flag,
        lambda v: (
            f"Linted wiki vault at {v.vault_root} "
            f"({v.issue_count} issues, report: {v.report_path})."
        ),
    )
    _write_output(rendered)
    return result


def _run_wiki_ingest(
    context: WikiCommandContext,
    *,
    input_path: str,
    title: str | None,
    json_flag: bool,
) -> Any:
    result = asyncio.run(
        ingest_memory_wiki_source(
            config=context.config,
            input_path=input_path,
            title=title,
        )
    )
    rendered = _format_json_or_text(
        result,
        json_flag,
        lambda v: (
            f"Ingested {v.source_path} into {v.page_path}. "
            f"Refreshed {len(v.index_updated_files)} index file"
            f"{'' if len(v.index_updated_files) == 1 else 's'}."
        ),
    )
    _write_output(rendered)
    return result


def _run_wiki_okf_import(
    context: WikiCommandContext,
    *,
    bundle_path: str,
    json_flag: bool,
) -> Any:
    result = asyncio.run(
        import_memory_wiki_okf_bundle(
            config=context.config,
            bundle_path=bundle_path,
        )
    )
    rendered = _format_json_or_text(result, json_flag, format_okf_import_summary)
    _write_output(rendered)
    return result


def _run_wiki_search(
    context: WikiCommandContext,
    *,
    query: str,
    max_results: int | None,
    backend: str | None,
    corpus: str | None,
    mode: str | None,
    json_flag: bool,
) -> list[Any]:
    if mode is not None and mode not in WIKI_SEARCH_MODES:
        raise ValueError(f"wiki search --mode must be one of: {', '.join(WIKI_SEARCH_MODES)}.")
    asyncio.run(
        sync_memory_wiki_imported_sources(config=context.config, app_config=context.app_config)
    )
    results: list[Any] = list(
        search_memory_wiki(
            config=context.config,
            app_config=context.app_config,
            agent_id=context.agent_id,
            query=query,
            max_results=max_results,
            search_backend=backend,
            search_corpus=corpus,
            mode=mode,
        )
    )
    if json_flag:
        _write_output(json.dumps(results, indent=2, default=str))
    elif not results:
        _write_output("No wiki or memory results.")
    else:
        blocks: list[str] = []
        for idx, result in enumerate(results, 1):
            title = getattr(result, "title", "?")
            corpus_val = getattr(result, "corpus", "?")
            kind = getattr(result, "kind", "?")
            path = getattr(result, "path", "?")
            block = f"{idx}. {title} ({corpus_val}/{kind})\nPath: {path}"
            start_line = getattr(result, "startLine", None)
            end_line = getattr(result, "endLine", None)
            if isinstance(start_line, int) and isinstance(end_line, int):
                block += f"\nLines: {start_line}-{end_line}"
            provenance_label = getattr(result, "provenanceLabel", None)
            if provenance_label:
                block += f"\nProvenance: {provenance_label}"
            matched_claim = getattr(result, "matchedClaimId", None)
            if matched_claim:
                block += f"\nClaim: {matched_claim}"
            evidence = getattr(result, "evidenceKinds", None) or []
            if evidence:
                block += f"\nEvidence: {', '.join(evidence)}"
            snippet = getattr(result, "snippet", "")
            block += f"\nSnippet: {snippet}"
            blocks.append(block)
        _write_output("\n\n".join(blocks))
    return results


def _run_wiki_get(
    context: WikiCommandContext,
    *,
    lookup: str,
    from_line: int | None,
    line_count: int | None,
    backend: str | None,
    corpus: str | None,
    json_flag: bool,
) -> Any:
    asyncio.run(
        sync_memory_wiki_imported_sources(config=context.config, app_config=context.app_config)
    )
    result: Any = get_memory_wiki_page(
        config=context.config,
        app_config=context.app_config,
        agent_id=context.agent_id,
        lookup=lookup,
        from_line=from_line,
        line_count=line_count,
        search_backend=backend,
        search_corpus=corpus,
    )
    if json_flag:
        _write_output(json.dumps(result, indent=2, default=str))
    else:
        content = getattr(result, "content", None) or f"Wiki page not found: {lookup}"
        _write_output(content)
    return result


def _run_wiki_apply_synthesis(
    context: WikiCommandContext,
    *,
    title: str,
    body: str | None,
    body_file: str | None,
    source_ids: list[str] | None,
    contradictions: list[str] | None,
    questions: list[str] | None,
    confidence: float | None,
    status: str | None,
    json_flag: bool,
) -> Any:
    if not source_ids:
        raise ValueError("wiki apply synthesis requires at least one --source-id.")
    if body is None or not body.strip():
        if body_file and body_file.strip():
            with open(body_file, encoding="utf-8") as f:
                body = f.read()
        else:
            raise ValueError("wiki apply synthesis requires --body or --body-file.")
    asyncio.run(
        sync_memory_wiki_imported_sources(config=context.config, app_config=context.app_config)
    )
    mutation = CreateSynthesisMutation(
        title=title,
        body=body or "",
        source_ids=list(source_ids),
        contradictions=list(contradictions) if contradictions else [],
        questions=list(questions) if questions else [],
        confidence=confidence,
        status=status.strip() if status else None,
    )
    result = apply_memory_wiki_mutation(config=context.config, mutation=mutation)
    rendered = _format_json_or_text(
        result,
        json_flag,
        lambda v: (
            f"{'Updated' if v.changed else 'No changes for'} {v.page_path} " f"via {v.operation}."
        ),
    )
    _write_output(rendered)
    return result


def _run_wiki_apply_metadata(
    context: WikiCommandContext,
    *,
    lookup: str,
    source_ids: list[str] | None,
    contradictions: list[str] | None,
    questions: list[str] | None,
    confidence: float | None,
    clear_confidence: bool,
    status: str | None,
    json_flag: bool,
) -> Any:
    asyncio.run(
        sync_memory_wiki_imported_sources(config=context.config, app_config=context.app_config)
    )
    mutation_kwargs: dict[str, Any] = {"lookup": lookup}
    if source_ids:
        mutation_kwargs["source_ids"] = list(source_ids)
    if contradictions:
        mutation_kwargs["contradictions"] = list(contradictions)
    if questions:
        mutation_kwargs["questions"] = list(questions)
    if clear_confidence:
        mutation_kwargs["confidence"] = None
    elif confidence is not None:
        mutation_kwargs["confidence"] = confidence
    if status and status.strip():
        mutation_kwargs["status"] = status.strip()
    mutation = UpdateMetadataMutation(**mutation_kwargs)
    result = apply_memory_wiki_mutation(config=context.config, mutation=mutation)
    rendered = _format_json_or_text(
        result,
        json_flag,
        lambda v: (
            f"{'Updated' if v.changed else 'No changes for'} {v.page_path} " f"via {v.operation}."
        ),
    )
    _write_output(rendered)
    return result


def _run_wiki_bridge_import(
    context: WikiCommandContext,
    *,
    json_flag: bool,
) -> Any:
    result = asyncio.run(
        sync_memory_wiki_imported_sources(config=context.config, app_config=context.app_config)
    )
    rendered = _format_json_or_text(
        result,
        json_flag,
        lambda v: (
            f"Bridge import synced {v.artifact_count} artifacts across "
            f"{v.workspaces} workspaces "
            f"({v.imported_count} new, {v.updated_count} updated, "
            f"{v.skipped_count} unchanged, {v.removed_count} removed). "
            f"Indexes {v.indexes_refreshed} "
            f"({len(v.index_updated_files)} files)."
        ),
    )
    _write_output(rendered)
    return result


def _run_wiki_unsafe_local_import(
    context: WikiCommandContext,
    *,
    json_flag: bool,
) -> Any:
    if context.config.vault.scope == "agent":
        raise ValueError("Unsafe-local import does not support memory-wiki vault.scope=agent.")
    result = asyncio.run(
        sync_memory_wiki_imported_sources(config=context.config, app_config=context.app_config)
    )
    rendered = _format_json_or_text(
        result,
        json_flag,
        lambda v: (
            f"Unsafe-local import synced {v.artifact_count} artifacts "
            f"({v.imported_count} new, {v.updated_count} updated, "
            f"{v.skipped_count} unchanged, {v.removed_count} removed)."
        ),
    )
    _write_output(rendered)
    return result


def _run_wiki_chatgpt_import(
    context: WikiCommandContext,
    *,
    export_path: str,
    dry_run: bool,
    json_flag: bool,
) -> Any:
    # The 4.3g-mr3 stub doesn't accept
    # ``dry_run``; we capture it for
    # future use and pass the rest of
    # the kwargs.
    _ = dry_run
    result = asyncio.run(
        import_chatgpt_export(
            config=context.config,
            export_path=export_path,
        )
    )
    if json_flag:
        _write_output(json.dumps(result, indent=2, default=str))
        return result
    if result.dry_run:
        summary = (
            f"ChatGPT import dry run scanned {result.conversation_count} "
            f"conversations ({result.created_count} new, "
            f"{result.updated_count} updated, "
            f"{result.skipped_count} unchanged)."
        )
    else:
        run_suffix = f" Run id: {result.run_id}." if result.run_id else ""
        summary = (
            f"ChatGPT import applied {result.conversation_count} "
            f"conversations ({result.created_count} new, "
            f"{result.updated_count} updated, "
            f"{result.skipped_count} unchanged)."
            f"{run_suffix}"
        )
    _write_output(summary)
    return result


def _run_wiki_obsidian_status(context: WikiCommandContext, *, json_flag: bool) -> Any:
    probe = asyncio.run(probe_obsidian_cli())
    rendered = _format_json_or_text(
        probe,
        json_flag,
        lambda v: (
            f"Obsidian CLI available at {v.command}"
            if v.available
            else "Obsidian CLI is not available on PATH."
        ),
    )
    _write_output(rendered)
    return probe


def _assert_official_obsidian_cli_supported(
    context: WikiCommandContext,
) -> None:
    """Refuse obsidian actions on agent-scoped vaults.

    Mirrors OpenClaw's
    ``assertOfficialObsidianCliSupported``.
    """
    if context.config.vault.scope == "agent":
        raise ValueError(
            "Official Obsidian CLI actions do not support memory-wiki vault.scope=agent."
        )


def _run_wiki_obsidian_search(context: WikiCommandContext, *, query: str, json_flag: bool) -> Any:
    _assert_official_obsidian_cli_supported(context)
    result = asyncio.run(run_obsidian_search(config=context.config, query=query))
    rendered = _format_json_or_text(
        result, json_flag, lambda v: (v.get("stdout", "") or "").strip()
    )
    _write_output(rendered)
    return result


def _run_wiki_obsidian_open(
    context: WikiCommandContext, *, vault_path: str, json_flag: bool
) -> Any:
    _assert_official_obsidian_cli_supported(context)
    result = asyncio.run(run_obsidian_open(config=context.config, vault_path=vault_path))
    rendered = _format_json_or_text(
        result,
        json_flag,
        lambda v: (v.get("stdout", "") or "").strip() or "Opened in Obsidian.",
    )
    _write_output(rendered)
    return result


def _run_wiki_obsidian_command(context: WikiCommandContext, *, id: str, json_flag: bool) -> Any:
    _assert_official_obsidian_cli_supported(context)
    result = asyncio.run(run_obsidian_command(config=context.config, id=id))
    rendered = _format_json_or_text(
        result,
        json_flag,
        lambda v: (v.get("stdout", "") or "").strip() or "Command sent to Obsidian.",
    )
    _write_output(rendered)
    return result


def _run_wiki_obsidian_daily(context: WikiCommandContext, *, json_flag: bool) -> Any:
    _assert_official_obsidian_cli_supported(context)
    result = asyncio.run(run_obsidian_daily(config=context.config))
    rendered = _format_json_or_text(
        result,
        json_flag,
        lambda v: (v.get("stdout", "") or "").strip() or "Opened today's daily note.",
    )
    _write_output(rendered)
    return result


# ── Registrar ────────────────────────────────────────────────


def register_wiki_cli(
    program: argparse.ArgumentParser,
    registration: MemoryWikiCliRegistration,
) -> None:
    """Register the ``wiki`` command group on
    ``program`` (the host's CLI program).

    Mirrors OpenClaw's
    ``registerWikiCli`` (Commander) → Python
    ``argparse`` adapter. Each sub-command
    dispatches to the matching
    ``_run_wiki_*`` handler with the
    resolved :class:`WikiCommandContext`.
    """
    resolve_config = _build_resolve_config(registration)
    state: dict[str, WikiCommandContext] = {}

    wiki = program.add_subparsers(dest="wiki_command").add_parser(
        "wiki",
        help="Inspect and initialize the memory wiki vault",
    )
    wiki.add_argument(
        "--agent",
        dest="agent",
        default=None,
        help="Agent id for agent-scoped wiki vaults",
    )

    def _resolve_context() -> WikiCommandContext:
        """Resolve the command context from the
        pending agent + the registration's
        ``getAppConfig``.

        Mirrors OpenClaw's
        ``requireCommandContext`` — the
        ``preAction`` hook stores the
        resolved context in a closure
        variable that every handler reads.
        """
        opts = state.get("__opts__")
        requested_agent = opts.agent_id if opts is not None else None
        current_app_config = registration.get_app_config() if registration.get_app_config else None
        config = resolve_config(requested_agent, current_app_config)
        agent_id = config.agent_id or requested_agent
        ctx = WikiCommandContext(
            config=config,
            agent_id=agent_id,
            app_config=current_app_config,
        )
        state["__ctx__"] = ctx
        return ctx

    def _store_opts(opts: argparse.Namespace) -> None:
        """Stash the requested agent id so
        ``_resolve_context`` can read it.
        """
        agent_id = (opts.agent or "").strip() or None
        state["__opts__"] = WikiCommandContext(config=registration.config, agent_id=agent_id)

    wiki_actions = wiki.add_subparsers(dest="wiki_action", required=True)

    def _bind(parser: argparse.ArgumentParser, handler: Callable[..., Any]) -> None:
        """Attach a single sub-command parser
        to the shared ``wiki_actions``
        container, with a ``__handler``
        attribute the dispatcher reads.
        """
        parser.set_defaults(__handler=handler)

    def _dispatch(args: argparse.Namespace) -> Any:
        _store_opts(args)
        handler = getattr(args, "__handler", None)
        if not callable(handler):
            return None
        ctx = _resolve_context()
        return handler(args, _require_command_context(ctx))

    wiki.set_defaults(func=_dispatch)

    # status
    p_status = wiki_actions.add_parser("status", help="Show wiki vault status")
    p_status.add_argument("--json", dest="json_flag", action="store_true")
    _bind(p_status, lambda ns, ctx: _run_wiki_status(ctx, json_flag=ns.json_flag))

    # doctor
    p_doctor = wiki_actions.add_parser(
        "doctor", help="Audit wiki vault setup and report actionable fixes"
    )
    p_doctor.add_argument("--json", dest="json_flag", action="store_true")
    _bind(p_doctor, lambda ns, ctx: _run_wiki_doctor(ctx, json_flag=ns.json_flag))

    # init
    p_init = wiki_actions.add_parser("init", help="Initialize the wiki vault layout")
    p_init.add_argument("--json", dest="json_flag", action="store_true")
    _bind(p_init, lambda ns, ctx: _run_wiki_init(ctx, json_flag=ns.json_flag))

    # compile
    p_compile = wiki_actions.add_parser("compile", help="Refresh generated wiki indexes")
    p_compile.add_argument("--json", dest="json_flag", action="store_true")
    _bind(p_compile, lambda ns, ctx: _run_wiki_compile(ctx, json_flag=ns.json_flag))

    # lint
    p_lint = wiki_actions.add_parser("lint", help="Lint the wiki vault and write a report")
    p_lint.add_argument("--json", dest="json_flag", action="store_true")
    _bind(p_lint, lambda ns, ctx: _run_wiki_lint(ctx, json_flag=ns.json_flag))

    # ingest
    p_ingest = wiki_actions.add_parser(
        "ingest", help="Ingest a local file into the wiki sources folder"
    )
    p_ingest.add_argument("input_path", help="Local file path to ingest")
    p_ingest.add_argument("--title", dest="title", default=None)
    p_ingest.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_ingest,
        lambda ns, ctx: _run_wiki_ingest(
            ctx,
            input_path=ns.input_path,
            title=ns.title,
            json_flag=ns.json_flag,
        ),
    )

    # okf import
    p_okf = wiki_actions.add_parser("okf", help="Import Open Knowledge Format bundles")
    p_okf_actions = p_okf.add_subparsers(dest="okf_action", required=True)
    p_okf_import = p_okf_actions.add_parser(
        "import",
        help="Import an unpacked OKF bundle into wiki concept pages",
    )
    p_okf_import.add_argument("bundle_path", help="OKF bundle directory")
    p_okf_import.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_okf_import,
        lambda ns, ctx: _run_wiki_okf_import(
            ctx, bundle_path=ns.bundle_path, json_flag=ns.json_flag
        ),
    )

    # search
    p_search = wiki_actions.add_parser(
        "search",
        help="Search wiki pages and, when configured, the active memory corpus",
    )
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--max-results", dest="max_results", type=int, default=None)
    p_search.add_argument("--backend", dest="backend", choices=WIKI_SEARCH_BACKENDS, default=None)
    p_search.add_argument("--corpus", dest="corpus", choices=WIKI_SEARCH_CORPORA, default=None)
    p_search.add_argument("--mode", dest="mode", choices=WIKI_SEARCH_MODES, default=None)
    p_search.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_search,
        lambda ns, ctx: _run_wiki_search(
            ctx,
            query=ns.query,
            max_results=ns.max_results,
            backend=ns.backend,
            corpus=ns.corpus,
            mode=ns.mode,
            json_flag=ns.json_flag,
        ),
    )

    # get
    p_get = wiki_actions.add_parser(
        "get",
        help="Read a wiki page by id or relative path, with optional active-memory fallback",
    )
    p_get.add_argument("lookup", help="Relative path or page id")
    p_get.add_argument("--from", dest="from_line", type=int, default=None)
    p_get.add_argument("--lines", dest="line_count", type=int, default=None)
    p_get.add_argument("--backend", dest="backend", choices=WIKI_SEARCH_BACKENDS, default=None)
    p_get.add_argument("--corpus", dest="corpus", choices=WIKI_SEARCH_CORPORA, default=None)
    p_get.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_get,
        lambda ns, ctx: _run_wiki_get(
            ctx,
            lookup=ns.lookup,
            from_line=ns.from_line,
            line_count=ns.line_count,
            backend=ns.backend,
            corpus=ns.corpus,
            json_flag=ns.json_flag,
        ),
    )

    # apply
    p_apply = wiki_actions.add_parser("apply", help="Apply narrow wiki mutations")
    p_apply_actions = p_apply.add_subparsers(dest="apply_action", required=True)
    p_apply_synth = p_apply_actions.add_parser(
        "synthesis",
        help="Create or refresh a synthesis page with managed summary content",
    )
    p_apply_synth.add_argument("title", help="Synthesis title")
    p_apply_synth.add_argument("--body", dest="body", default=None)
    p_apply_synth.add_argument("--body-file", dest="body_file", default=None)
    p_apply_synth.add_argument("--source-id", dest="source_ids", action="append", default=None)
    p_apply_synth.add_argument(
        "--contradiction", dest="contradictions", action="append", default=None
    )
    p_apply_synth.add_argument("--question", dest="questions", action="append", default=None)
    p_apply_synth.add_argument("--confidence", dest="confidence", type=float, default=None)
    p_apply_synth.add_argument("--status", dest="status", default=None)
    p_apply_synth.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_apply_synth,
        lambda ns, ctx: _run_wiki_apply_synthesis(
            ctx,
            title=ns.title,
            body=ns.body,
            body_file=ns.body_file,
            source_ids=ns.source_ids,
            contradictions=ns.contradictions,
            questions=ns.questions,
            confidence=ns.confidence,
            status=ns.status,
            json_flag=ns.json_flag,
        ),
    )
    p_apply_meta = p_apply_actions.add_parser(
        "metadata", help="Update metadata on an existing page"
    )
    p_apply_meta.add_argument("lookup", help="Relative path or page id")
    p_apply_meta.add_argument("--source-id", dest="source_ids", action="append", default=None)
    p_apply_meta.add_argument(
        "--contradiction", dest="contradictions", action="append", default=None
    )
    p_apply_meta.add_argument("--question", dest="questions", action="append", default=None)
    p_apply_meta.add_argument("--confidence", dest="confidence", type=float, default=None)
    p_apply_meta.add_argument("--clear-confidence", dest="clear_confidence", action="store_true")
    p_apply_meta.add_argument("--status", dest="status", default=None)
    p_apply_meta.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_apply_meta,
        lambda ns, ctx: _run_wiki_apply_metadata(
            ctx,
            lookup=ns.lookup,
            source_ids=ns.source_ids,
            contradictions=ns.contradictions,
            questions=ns.questions,
            confidence=ns.confidence,
            clear_confidence=ns.clear_confidence,
            status=ns.status,
            json_flag=ns.json_flag,
        ),
    )

    # bridge
    p_bridge = wiki_actions.add_parser(
        "bridge", help="Import public memory artifacts into the wiki vault"
    )
    p_bridge_actions = p_bridge.add_subparsers(dest="bridge_action", required=True)
    p_bridge_import = p_bridge_actions.add_parser(
        "import", help="Sync bridge-backed memory artifacts into wiki source pages"
    )
    p_bridge_import.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_bridge_import,
        lambda ns, ctx: _run_wiki_bridge_import(ctx, json_flag=ns.json_flag),
    )

    # unsafe-local
    p_unsafe = wiki_actions.add_parser(
        "unsafe-local",
        help="Import explicitly configured private local paths into wiki source pages",
    )
    p_unsafe_actions = p_unsafe.add_subparsers(dest="unsafe_action", required=True)
    p_unsafe_import = p_unsafe_actions.add_parser(
        "import", help="Sync unsafe-local configured paths into wiki source pages"
    )
    p_unsafe_import.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_unsafe_import,
        lambda ns, ctx: _run_wiki_unsafe_local_import(ctx, json_flag=ns.json_flag),
    )

    # chatgpt
    p_chatgpt = wiki_actions.add_parser(
        "chatgpt", help="Import ChatGPT export history into wiki source pages"
    )
    p_chatgpt_actions = p_chatgpt.add_subparsers(dest="chatgpt_action", required=True)
    p_chatgpt_import = p_chatgpt_actions.add_parser(
        "import", help="Import a ChatGPT export into draft wiki source pages"
    )
    p_chatgpt_import.add_argument("--export", dest="export", required=True)
    p_chatgpt_import.add_argument("--dry-run", dest="dry_run", action="store_true")
    p_chatgpt_import.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_chatgpt_import,
        lambda ns, ctx: _run_wiki_chatgpt_import(
            ctx,
            export_path=ns.export,
            dry_run=ns.dry_run,
            json_flag=ns.json_flag,
        ),
    )

    # obsidian
    p_obs = wiki_actions.add_parser("obsidian", help="Run official Obsidian CLI helpers")
    p_obs_actions = p_obs.add_subparsers(dest="obs_action", required=True)
    p_obs_status = p_obs_actions.add_parser("status", help="Probe the Obsidian CLI")
    p_obs_status.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_obs_status,
        lambda ns, ctx: _run_wiki_obsidian_status(ctx, json_flag=ns.json_flag),
    )
    p_obs_search = p_obs_actions.add_parser("search", help="Search the current Obsidian vault")
    p_obs_search.add_argument("query", help="Search query")
    p_obs_search.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_obs_search,
        lambda ns, ctx: _run_wiki_obsidian_search(ctx, query=ns.query, json_flag=ns.json_flag),
    )
    p_obs_open = p_obs_actions.add_parser(
        "open", help="Open a file in Obsidian by vault-relative path"
    )
    p_obs_open.add_argument("vault_path", help="Vault-relative path")
    p_obs_open.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_obs_open,
        lambda ns, ctx: _run_wiki_obsidian_open(
            ctx, vault_path=ns.vault_path, json_flag=ns.json_flag
        ),
    )
    p_obs_command = p_obs_actions.add_parser(
        "command", help="Execute an Obsidian command palette command by id"
    )
    p_obs_command.add_argument("obs_id", help="Obsidian command id")
    p_obs_command.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_obs_command,
        lambda ns, ctx: _run_wiki_obsidian_command(ctx, id=ns.obs_id, json_flag=ns.json_flag),
    )
    p_obs_daily = p_obs_actions.add_parser("daily", help="Open today's daily note in Obsidian")
    p_obs_daily.add_argument("--json", dest="json_flag", action="store_true")
    _bind(
        p_obs_daily,
        lambda ns, ctx: _run_wiki_obsidian_daily(ctx, json_flag=ns.json_flag),
    )


__all__ = [
    "GATEWAY_RESPONSE_MAX_CODE_CHARS",
    "GATEWAY_RESPONSE_MAX_STRING_CHARS",
    "GATEWAY_TERMINAL_STRING_MAX_CHARS",
    "MemoryWikiCliRegistration",
    "WIKI_GATEWAY_TIMEOUT_MS",
    "WikiCommandContext",
    "register_wiki_cli",
]
