# tool_web_search Plugin Guide

Read this before any change under `extensions/tool_web_search/`. Also
read `extensions/AGENTS.md` for the plugin boundary rules.

## Scope

- **Phase 1C (shipped).** Web search via OpenRouter (`or_client`),
  with DuckDuckGo (`ddgs`) fallback. Includes a `compare` mode.
- **Phase 3+ (target).** Per-region defaults, result caching,
  source-quality ranking.

## Reliability Invariants

- **Two-tier fallback chain.** OpenRouter first (uses the user's
  OpenRouter key for richer answers), DDG second (returns raw results
  formatted as a numbered list). Both must fail before we return
  `Search failed, sir: <err>`.
- **`compare` mode triggers automatically when `items` is present.**
  Even if the LLM passes `mode=search`, we switch to `compare` if
  `items` is non-empty.
- **Never raise.** Every backend call is wrapped in `try/except`; we
  always return a string the LLM can speak.
- **Empty `query` + empty `items` returns `Err(MISSING_ARG)`.**
  The plugin does not invent a query.

## Security Invariants

- **No shell injection.** `subprocess` is not used; all I/O is via
  `requests` (URL-safe) and the `ddgs` library.
- **Read-only network.** We only do GET requests to public endpoints.
  No POST, no cookies, no auth beyond the OpenRouter key.
- **No `shell=True`.** Every `subprocess.run` is list-form (Python
  3.13+ default; ruff S602/S603 pass).

## Context And Authorization

- **No pairing/allowlist config.** Web search is operator-local.
- **Region default is global.** `compare` doesn't filter by region;
  a future `region` parameter lands in Phase 2.

## Review Standard

- Backend swap PRs (e.g. OpenRouter → native Gemini Search) need a
  test that exercises both the new backend and the DDG fallback.
- `compare` mode PRs need a test that asserts the per-item result
  sections are present in the output.

## Dependencies

- `ddgs` (DuckDuckGo search; `duckduckgo_search` is the legacy
  package name — we try the new one first).
- `requests` (transitively via the workspace root).
- The `or_client` module (workspace root) for OpenRouter.
