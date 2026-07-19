# tool_weather Plugin Guide

Read this before any change under `extensions/tool_weather/`. These are
intentional maintainer decisions, not incidental implementation. Also
read `extensions/AGENTS.md` for the plugin boundary rules.

## Scope

- **Phase 1A (shipped) + 1B (refactored to SDK).** Opens a Google weather
  search in the default browser for the requested city. Stateless.
- **Phase 3+ (target):** swap `webbrowser.open` for a real weather API call
  (OpenWeatherMap or wttr.in). Browser fallback stays for graceful degradation
  when the API key is missing.

## Reliability Invariants

- **Missing `city` is rejected.** Return `Err("Sir, the city is missing...",
  code="MISSING_ARG")`. Never URL-encode an empty city.
- **No exceptions leak.** If `webbrowser.open` throws, return
  `Err("Sir, I couldn't open the browser. ...", code="BROWSER_ERROR")` —
  never let a `WebbrowserException` propagate to the LLM.
- **Default `time` is "today".** When the LLM omits `time`, we don't ask —
  we assume today's weather. The user can always re-invoke with a specific
  day.
- **Player is best-effort.** `self._player.write_log(...)` is wrapped in
  `contextlib.suppress(Exception)`. A broken player must never crash a tool
  call.

## Security Invariants

- **URL-encode the query.** Use `urllib.parse.quote_plus` on the search
  string. Never concatenate raw user input into a URL.
- **No network calls beyond the browser open.** The plugin only delegates
  to the OS's default browser. We don't make outbound HTTP requests, so
  the `permissions: ["network:outbound"]` in the manifest is technically
  not needed today; it's reserved for Phase 3's API-based fallback.

## Context And Authorization

- **No pairing/allowlist config.** Weather is a public-information tool;
  any operator (or paired remote user) can call it.
- **Default browser is the operator's choice.** We do not enforce a
  specific browser. The user is responsible for setting their default.

## Review Standard

- Behavior PRs (URL change, new search engine) need a manual test in a
  browser to verify the URL renders correctly.
- Reliability PRs (error code, default time) need unit tests with
  `webbrowser.open` monkeypatched.
- The `tools` property must stay in sync with `openclaw.plugin.json`'s
  `tools[0]` entry. The check is enforced by `tools/ci/check_manifests.py`.

## Dependencies

- `webbrowser` (stdlib) — primary transport.
- `urllib.parse.quote_plus` (stdlib) — URL safety.
- No third-party packages. The `pyproject.toml` declares a stdlib-only
  package.
