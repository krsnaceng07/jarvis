# tool_youtube_video Plugin Guide

Read this before any change under `extensions/tool_youtube_video/`. Also
read `extensions/AGENTS.md` for the plugin boundary rules.

## Scope

- **Phase 1C (shipped).** YouTube controller via web scraping (no
  YouTube Data API key required). Four actions: `play`, `summarize`,
  `get_info`, `trending`.
- **Phase 3+ (target).** YouTube Data API v3 integration for richer
  metadata (description, channel avatar, comments). The scraper stays
  as the no-key fallback.

## Reliability Invariants

- **Action dispatch is strict.** Unknown actions return
  `Err(UNKNOWN_ACTION)` immediately. The LLM must pick from
  `play | summarize | get_info | trending`.
- **`summarize` requires `youtube-transcript-api`.** Missing package
  returns `Err(MISSING_DEP)` with the install command, not a crash.
- **Transcripts fail soft.** `get_transcript()` returns `None` on any
  error; the caller turns it into `Err(NO_TRANSCRIPT)`.
- **Scraping is best-effort.** A YouTube layout change can break
  the regex extractors; we fail to a search-page fallback
  (action=play) or to a clear error string (other actions). We never
  hang or loop on a bad page.
- **Summary truncation at 80k chars.** We don't blow the LLM's
  context window on a long video; 80k chars is ~20k tokens.

## Security Invariants

- **Read-only network.** `requests.get(...)` with a custom User-Agent
  is the only outbound traffic. No cookies, no auth, no POSTs.
- **No `shell=True`.** Every `subprocess.Popen` is list-form.
- **Tkinter URL dialog.** `askstring(...)` is a synchronous UI prompt;
  it can be cancelled by the user (returns None) and we handle that
  cleanly.
- **Desktop write is the operator's home.** `save_summary` writes to
  `~/Desktop/youtube_summary_<ts>.txt` — never to a system path. We
  mkdir if it doesn't exist.

## Context And Authorization

- **No pairing/allowlist config.** YouTube calls are operator-local.
- **Region default is `TR`.** Trending uses YouTube's per-region
  feed; Phase 2 adds a per-agent default.

## Review Standard

- Action table changes (new action, renamed param) need a test that
  asserts the dispatch routes correctly.
- Scraper regex changes (YouTube layout shifts) need a manual test
  on a real query; CI can't see YouTube's HTML.

## Dependencies

- `requests` (required).
- `youtube-transcript-api` (required for `summarize`).
- `tkinter` (stdlib) for the URL dialog.
- `config.is_windows / is_mac / is_linux` from the workspace root.
- `or_client` (workspace root) for the summary LLM call.
