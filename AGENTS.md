# AGENTS.md

Telegraph style. Root rules only. Read scoped `AGENTS.md` before subtree work.
Skills own workflows; root owns hard policy and routing.

JARVIS is a personal AI assistant that follows the OpenClaw architecture: a multi-package Python workspace with extensions, declarative skills, schema versioning, and a strict plugin contract. This file defines the rules every contributor (human or AI) must follow.

## Start

- **Repo:** local workspace `E:/jarvis/`
- **Migration plan:** `OPENCLAW_MIGRATION_PLAN.md` is the single source of truth for the OpenClaw-architecture migration. Read it before any structural change.
- **Replies:** workspace-relative refs only: `packages/plugin_sdk/src/jarvis_sdk/contract.py:42`. No absolute paths, no `~/`.
- **Existing-solutions preflight:** before proposing or building a custom system, feature, workflow, tool, integration, or automation, do a lightweight check for open-source projects, maintained libraries, existing JARVIS extensions, or free platforms that already solve it well enough. Prefer those when adequate. Build custom only when existing options are unsuitable, too expensive, unmaintained, unsafe, non-compliant, or the user explicitly asks for custom. Avoid paid-service recommendations unless the user explicitly approves spend. Keep this to a brief preflight gate, not a broad research assignment.
- **Fix/triage answers need source, tests, current/shipped behavior, and dependency contract proof.**
- **Reviews/answers:** high confidence required. Default to exhaustive relevant codebase search/read, including owners, callers, siblings, tests, docs, and upstream/dependency contracts before verdict. Diff-only review is insufficient.
- **Review default:** read the whole changed function/module plus callers, callees, sibling implementations, adjacent tests, scoped docs, and dependency contracts before saying `good`, `bad`, `best fix`, `proof sufficient`, or posting a comment. If challenged, keep reading first; do not defend the earlier verdict until the missing path is checked.
- **Dependency-touching work:** direct dependency inspection is mandatory when feasible; do not rely on assumptions, wrappers, or memory. Most dependencies are OSS, so read their source/docs/types. No memory-only API claims.
- **External API work:** live test required. Prefer official docs/source/types; cite current proof.
- **Live-verify when feasible.** Never print secrets.
- **Missing deps:** `uv sync`; retry once, then report first actionable error.
- **CODEOWNERS:** maintainer/refactor/tests ok. Larger behavior/product/security/ownership: owner ask/review.
- **Product/docs/UI/changelog wording:** "extension/extensions"; `extensions/` is internal implementation.
- **New extension/plugin/app/doc surface:** update `.github/labeler.yml` + GH labels.

## Map

- **Apps (user-facing):** `apps/desktop/` (PyQt6 HUD), `apps/cli/` (headless gateway CLI), `apps/tui/` (terminal UI, optional).
- **Core libraries:** `packages/<name>/` — each has its own `pyproject.toml` and is installable as a workspace member. Key packages: `plugin_sdk/`, `agent_runtime/`, `llm_client/`, `memory_host_sdk/`, `channels_core/`, `gateway_protocol/`, `config_core/`, `cron_core/`, `hooks_core/`, `logging_core/`, `secrets_core/`, `events_core/`, `audio_core/`, `live_session/`, `net_policy/`, `normalization/`, `transcript_core/`, `session_core/`, `media_core/`, `markdown_core/`, `cli_backend/`, `tool_call_repair/`, `retry_core/`, `i18n_core/`, `workboard_contract/`.
- **Plugins (extensions):** `extensions/<id>/` — each ships a `jarvis.plugin.json` manifest. Categories: channels, providers, media, memory, tools, productivity, voice, infrastructure, migration.
- **Skills (declarative):** `skills/<id>/SKILL.md` — markdown only, YAML frontmatter.
- **UI:** `ui/` (optional web frontend, Phase 12).
- **Protocol:** `packages/gateway_protocol/` (JSON-RPC schema for gateway ↔ clients).
- **Loader:** `packages/plugin_sdk/src/jarvis_sdk/loader.py` discovers and loads extensions.
- **Docs:** `docs/<category>/`. **Tests:** `test/<category>/`. **Tooling:** `tools/scripts/`, `tools/ci/`, `tools/git-hooks/`, `tools/codegen/`. **Security:** `security/opengrep/` (Phase 12). **QA:** `qa/scenarios/`. **Examples:** `examples/`. **Deploy:** `deploy/`.
- **Installers (future):** sibling `../jarvis.ai` (website, mirrors).
- **Scoped guides:** `extensions/`, `packages/{plugin_sdk,channels_core,agent_runtime,gateway_protocol,memory_host_sdk,config_core}/`, `apps/`, `docs/`, `test/`, `tools/ci/`, `qa/`.

## Architecture

- **Core stays plugin-agnostic.** No bundled ids/defaults/policy in core when manifest/registry/capability contracts work.
- **Plugins cross into core only via `jarvis_sdk.*`**, manifest metadata, injected runtime helpers, documented barrels (`contract.py`, `runtime.py`).
- **Plugin prod code:** no `packages/*/src/**` (except `plugin_sdk`), no other extension's `src/**`, no relative paths outside the package. Enforced by `tools/ci/check-imports.py`.
- **Core/tests:** no deep plugin internals (`extensions/*/src/**`, `onboard.py`). Use public barrels, SDK facade, generic contracts.
- **Owner boundary:** owner-specific repair/detection/onboarding/auth/defaults/provider behavior lives in owner plugin. Shared/core gets generic seams only.
- **Dependency ownership follows runtime ownership:** plugin-only deps stay plugin-local; root deps only for core imports or intentionally internalized bundled plugin runtime.
- **Internal bundled plugins ship in core dist; bundled-only facade loader ok only for them.**
- **Externalizing a bundled plugin:** update package excludes, official catalogs, docs, tests, and prove core runtime paths resolve installed plugin roots before root-dep removal.
- **Runtime reads canonical config only.** No silent compat for old/malformed config keys. If a config change invalidates existing files, add a matching `jarvis doctor --fix` migration. Core/auth config repairs live in core doctor; plugin-owned config repairs live in that plugin's doctor contract.
- **Config/env surface bar is high:** `~/.jarvis/config.json` and environment variables are already large. Before adding a config option or env var, first prove existing product behavior, provider selection, defaults, or doctor migration cannot solve it. Prefer removing or consolidating config/env options when touching these surfaces. Core supports only the latest config shape; `jarvis doctor --fix` migrates older shipped shapes into the current one.
- **CLI setup flows are public API** when external docs, installers, or integrations can copy them. Changes to `jarvis onboard`, `jarvis configure`, their documented flags, non-interactive behavior, or generated config shape are compatibility-sensitive API contract changes; prefer additive flags/aliases, deprecation windows, and backward-preserving migrations over breaking existing snippets.
- **Fix shape:** default to clean bounded refactor, not smallest patch. Move ownership to right boundary; delete stale abstractions, duplicate policy, dead branches, wrappers, fallback stacks.
- **New fallible-operation results use `Result` from `jarvis_sdk.normalization.result`;** domain-rich outcomes keep named discriminated unions.
- **Fix observed local failures with generic product rules;** do not hardcode names, ids, log phrases, or user examples in prod code unless they are an explicit contract.
- **Tests may use observed examples,** but prod literals need a short contract reason.
- **Compatibility is opt-in.** "Shipped" means reachable from a release Git tag; main/unreleased code is not shipped.
- **Refactor default: one canonical path.** Delete the old path unless user explicitly wants compat or the shipped public contract is obvious and cited.
- **Core runtime consumes only current canonical shapes/config/data.** Legacy or retired shapes normalize only in doctor/migration code before runtime; no runtime shims, aliases, or fallback readers.
- **State/storage migrations are database-first.** Runtime reads/writes the canonical store only. Old file stores, sidecars, aliases, and fallback readers belong in `jarvis doctor --fix` migration code only, never steady-state runtime.
- **Storage default: SQLite only.** Do not add JSON/JSONL/TXT/sidecar files for JARVIS-owned runtime state, caches, queues, registries, indexes, cursors, checkpoints, or plugin scratch data.
- **Any SQLite change requiring a schema-version bump needs explicit user discussion and acceptance before implementation.** Agents must not advance SQLite schema versions autonomously.
- **Purely additive SQLite surface** (new tables; downgraded builds keep working, just without the new feature): do not bump the schema version. Declare in the canonical schema file plus a one-time idempotent lazy ensure on first feature use; fold into the migration path at the next natural bump. Bumps are reserved for changes older readers cannot tolerate.
- **SQLite runtime access uses SQLAlchemy 2.0 helpers, not raw SQL statement strings,** except schema DDL, migrations, low-level DB bootstrap, or narrowly justified SQLite primitives.
- **SQLite write transactions are synchronous commit sections only.** Finish async planning, filesystem access, plugin hooks, and predicates before `BEGIN`; then reread and validate authoritative rows before writing. Never return a Promise or execute `await` from a transaction callback.
- **Use the shared state DB** (`~/.jarvis/state/jarvis.sqlite`) for global runtime state and plugin KV data. Use the per-agent DB (`~/.jarvis/agents/<agentId>/agent.sqlite`) for agent-scoped state/cache. Use a dedicated SQLite DB only when schema, volume, or lifecycle clearly does not fit those stores.
- **Vector storage:** LanceDB tables live in the same SQLite-managed workspace (`~/.jarvis/state/lance/`), not as a separate service. Embedding providers are plug-in (`jarvis_sdk.embeddings`).
- **Legacy state/cache files are migration debt.** When touching code that reads/writes them, prefer moving the data into SQLite or calling out the refactor follow-up; do not add parallel file paths.
- **File storage must be a named product artifact:** import/export, user attachment, log, backup, or external tool contract. If it is app state or cache, it belongs in SQLite.
- **Before adding any path under state dirs, choose one:** shared state DB, plugin KV, agent DB, or dedicated SQLite schema. If none fits, design the SQLite owner/schema first.
- **Cache/transient state gets no compat migration** unless a shipped user contract is cited. Prefer delete/drop/rebuild over import. If old state can be lost without user-visible data loss, remove the old path entirely.
- **Persistent user state gets one migration owner.** Doctor migrates, verifies, and then runtime assumes the new shape. No dual-write, read-through fallback, lazy import, or "if SQLite fails use JSON" branches.
- **Fallback is a product decision, not an implementation convenience.** Before adding one, name the shipped contract, failure mode, removal plan, and why doctor cannot solve it. Otherwise delete it.
- **Keep old behavior only for** an explicit public API/config/plugin SDK/data contract, tagged upgrade path, security/migration boundary, dependency contract, or observed prod state.
- **If unsure, ask before preserving compat.** Do not keep aliases, shims, fallback stacks, stale names, or obsolete tests just in case.
- **Tests alone do not make internals contracts.** If compat stays, name the contract and migration/removal plan in code, test, or PR.
- **Lean code is a goal.** No internal shims, aliases, legacy names, broad fallbacks, or defensive branches just to reduce diff or handle unrealistic edge cases.
- **Handle real production states,** tagged upgrade paths, security boundaries, and dependency contracts. Public/hostile/observed malformed input gets care; hypothetical malformed input does not.
- **Deprecate shipped public contracts only.**
- **Plugin SDK exception:** shipped external API gets new API first plus named compat/deprecation, small tests/docs if useful, removal plan.
- **Migrate internal/bundled callers to modern API in the same change.** Do not let internal compat become permanent architecture.
- **Channels are implementation under `packages/channels_core/`;** plugin authors get SDK seams. Providers own auth/catalog/runtime hooks; core owns generic loop.
- **Message/channel plugins stay transport-only.** They render portable presentation/actions, enforce transport limits, and map native callback envelopes. They do not own product command trees, plugin/provider policy, or feature-specific menus.
- **Portable command UI must use typed presentation actions, not raw string inference.** Do not make channels guess that `value` starting with `/` means a native command; core/owner plugins declare command actions, channels map them when supported.
- **Raw callback data is transport/private.** Approval, command, URL, web-app, and select actions must stay distinguishable before channel encoding so transport adapters do not special-case product strings.
- **Agent run terminal state:** normalize/merge via `packages/agent_runtime/terminal_outcome.py`; do not rederive timeout/cancel precedence in projections.
- **Hot paths should carry prepared facts forward:** provider id, model ref, channel id, target, capability family, attachment class. Do not rediscover with broad plugin/provider/channel/capability loaders.
- **Do not fix repeated request-time discovery with scattered caches.** Move the canonical fact earlier; reuse prepared runtime objects; delete duplicate lookup branches.
- **Extension/plugin metadata is process-stable:** installs, manifests, catalogs, generated paths, bundled metadata. Changes require restart or explicit owner reload/install/doctor flow.
- **Runtime hot paths:** no freshness polling (`stat`/`realpath`/JSON reread/hash). Reuse current snapshots, install records, discovery, lookup tables, root scopes, resolved paths.
- **Process-local metadata caches ok** when lifecycle-owned and bounded/single-slot. Freshness exceptions need named owner + tests.
- **Inline comments: preserve reviewer context at the code site.** Required for non-obvious cross-path/state invariants, lifecycle ordering, ownership boundaries, queue/dedupe symmetry, TTL/cache expiry, cleanup/release coupling, session/id adoption, fallback behavior, platform/dependency caps, deterministic ordering, compact encoded state, or intentional caller differences.
- **Comment shape:** 1-3 short lines; state why the branch/helper exists, what contract it protects, and the bad outcome if removed. Cite nearby constants/helpers when useful. No syntax narration, PR/user-specific lore, or obvious mechanics.
- **Gateway protocol changes:** additive first; incompatible needs versioning/docs/client follow-through.
- **Protocol version bumps:** explicit owner confirmation only; never automatic/generated.
- **Config contract:** exported types, schema/help, metadata, baselines, docs aligned. Retired public keys stay retired; compat in raw migration/doctor only.
- **Prompt cache:** deterministic ordering for maps/sets/registries/plugin lists/files/network results before model/tool payloads. Preserve old transcript bytes when possible.
- **Agent tool schema cleanup:** remove stale args cleanly; no hidden compat for model-facing params just to avoid churn.

## Commands

- **Runtime:** Python 3.12+. Keep `uv` paths working.
- **Package manager/runtime:** `uv` only. No swaps without approval.
- **Install:** `uv sync` (keeps `uv.lock` aligned). Add deps: `uv add <pkg>` (runtime), `uv add --dev <pkg>` (dev).
- **Desktop app:** `uv run python -m jarvis_desktop` (or `uv run apps/desktop` once `project.scripts` is set).
- **CLI:** `uv run jarvis ...` (or `uv run python -m jarvis_cli ...`).
- **Build:** `uv build` (sdist + wheel). Bundled QA tooling is source-only by default.
- **Test:** `uv run pytest <path-or-filter> [pytest args...]`; never raw `pytest` if you can help it; `uv run pytest -x` for fast local proof.
- **Lint:** `uv run ruff check` (uses `ruff.toml`); `uv run ruff format` for auto-format.
- **Typecheck:** `uv run pyright` (uses `pyrightconfig.json`); strict on `packages/`, basic on `extensions/`.
- **Schema surface gate:** `uv run python -m tools.ci.check_manifests`; `uv run python -m tools.ci.check_schema_version`.
- **Import-cycle gate:** `uv run python -m tools.ci.check_imports`.
- **Pre-commit:** `uv run pre-commit run --all-files`.

## Validation

- **Test runner:** `uv run pytest` (focused local proof). `uv run pytest --co` to collect only.
- **Property-based tests:** hypothesis is enabled by default in `pytest.ini`. Use `given(...)` and `@settings(...)` for boundary cases.
- **Lint:** `uv run ruff check` + `uv run ruff format --check`. Never `prettier`/`black`; ruff owns formatting.
- **Typecheck:** `uv run pyright` (Python equivalent of OpenClaw's `tsgo`).
- **Architecture checks:** `uv run python -m tools.ci.check_imports` (no cross-extension imports), `uv run python -m tools.ci.check_boundaries`, `uv run python -m tools.ci.check_max_lines`.
- **Manifest validation:** `uv run python -m tools.ci.check_manifests` (every `extensions/*/jarvis.plugin.json` validates against schema).
- **Schema version check:** `uv run python -m tools.ci.check_schema_version` (no autonomous schema version bumps).
- **Full suites, changed gates, builds, typechecks, lint fan-out, Docker/package/E2E/live/cross-OS proof: CI handles it.**
- **Before handoff/push:** prove touched surface. Before landing to `main`: proof matches actual risk. Bounded behavior-neutral refactor: focused tests/checks enough; no issue proof or full/broad suite by default.
- **CI polling:** exact SHA, relevant checks only, minimal fields. Skip routine noise.
- **Do not land related failing format/lint/type/build/tests.** If unrelated on latest `main`, say so with scoped proof.
- **Docs/changelog-only and CI/workflow metadata-only:** `git diff --check` plus relevant docs/workflow sanity; escalate only if scripts/config/generated/package/runtime behavior changed.

## Code

- **Python 3.12, strict type hints on public surface.** Avoid `Any`; prefer real types, `Unknown`, narrow adapters.
- **No `type: ignore` without reason.** Lint suppressions only intentional + explained.
- **External boundaries:** prefer `pydantic` v2 or existing schema helpers.
- **Runtime branching:** discriminated unions/closed codes over freeform strings. Avoid semantic sentinels (`?? 0`, empty object/string).
- **Cross-function state:** when valid combos matter, return a closed mode/result shape. Avoid parallel nullable fields or derived booleans that callers must keep in sync; make impossible states unrepresentable.
- **Formatter-friendly shape:** when ruff explodes an expression vertically, extract named booleans, payloads, or small helpers. Do not change line length or use format-ignore for local compactness.
- **Calls should be boring:** complex decisions happen above; call args/object fields are names, literals, or simple property reads.
- **Prefer early returns over nested condition pyramids.** Split code into gather -> normalize -> decide -> act.
- **Use named intermediates only for domain meaning or readability;** avoid temp-variable soup.
- **Correct but not over-engineered.** Correctness on real inputs/states is mandatory; extra layers, guards, and generality for imagined ones are defects, not rigor.
- **Codebase is already large; pragmatism wins.** Extremely unlikely edge cases are tradable for real simplification — name the accepted tradeoff (comment or PR) so it is a decision, not an oversight.
- **Code size matters.** Prefer small clear code; maintainability includes not growing LOC without payoff.
- **Refactors should delete about as much local complexity as they add.** If LOC grows, the new ownership/API needs to clearly pay for it.
- **Refactors should reduce non-test LOC unless they remove a larger architectural cost.** Treat positive prod LOC as a smell. Before closeout, run `git diff --numstat`; if non-test LOC grew, trim or explicitly justify why fewer paths now exist.
- **Prefer deleting branches, modes, adapters, and tests over preserving them.** A refactor that adds a second path has probably failed unless the old path is a cited shipped contract.
- **New helpers/files must pay rent immediately:** fewer call paths, fewer concepts, or less repeated logic. No helpers for one-off compat, naming translation, or speculative resilience.
- **Before adding helpers/files,** check whether existing code can absorb the behavior with less new surface.
- **Keep APIs narrow:** export only current caller needs; keep types/helpers local by default.
- **Return the smallest useful shape.** Avoid broad result objects, flags, metadata unless callers use them.
- **Avoid adapter layers that only rename fields.** Move real responsibility or leave code local.
- **Inline simple one-use objects/spreads when clearer.** Extract only when it removes duplication or hard logic.
- **Tests prove behavior/regressions, not every internal branch.**
- **Tests are welcome, but review them before landing for duplication and value.** Delete useless tests, such as assertions for behavior or paths just removed.
- **Tests protect canonical behavior and migration boundaries, not obsolete internals.** Delete tests for removed fallback paths instead of updating them.
- **For non-trivial refactors, check `git diff --numstat` before closeout.** If LOC grew, trim or explain why.
- **Prefer existing narrow helpers over repeated casts/guards.** Add local helpers when 2+ nearby call sites share real boundary logic.
- **Prefer `dataclass(frozen=True, slots=True)` for value objects.** Avoid bare `dict` for structured data.
- **Table-drive repetitive tests when it reduces code and keeps failure names clear.**
- **Dynamic import:** no static+dynamic import for same prod module. Use `*.runtime.py` lazy boundary. After edits: `uv build`; check for ineffective dynamic imports.
- **Cycles: keep `tools.ci.check_imports` + `tools.ci.check_cycles` green.**
- **Classes:** no prototype mixins/mutations. Prefer inheritance/composition. Tests prefer per-instance stubs.
- **Split files around ~700 LOC** when clarity/testability improves.
- **Never add a `max-lines` suppression.** Existing suppressions are grandfathered TODOs; split the file and remove its suppression plus baseline entry.
- **Naming:** **JARVIS** product/docs; `jarvis` CLI/package/path/config; `jarvis_sdk` for the SDK; `jarvis_desktop`, `jarvis_cli`, etc. for app entry points.
- **English:** American spelling.

## Tests

- **pytest.** Colocated `test_*.py`; e2e `test_*.e2e.py`.
- **hypothesis** for property-based tests. Use `@given(...)` for boundary cases. Default `max_examples=100`, raise for suspected invariants.
- **Prefer behavior tests over workflow/docs string greps.** Put operator policy reminders in AGENTS/docs.
- **Clean timers/env/globals/mocks/sockets/temp dirs/module state;** `--isolate=false` safe.
- **Tests asserting resolver/root-containment paths:** `pathlib.Path.resolve()` first. Windows `os.tmpdir()` can be a symlink; prod resolvers return canonical paths.
- **Prefer injection and narrow `*.runtime.py` mocks** over broad barrels or `jarvis_sdk.*`.
- **Do not edit baseline/inventory/ignore/snapshot/expected-failure files to silence checks without explicit approval.**
- **Do not run independent pytest commands concurrently in one worktree;** pytest cache races with `ENOTEMPTY`. Group one command.
- **Live:** `UV_LIVE_TEST=1 uv run pytest -m live`; verbose `UV_LIVE_TEST_QUIET=0`.
- **Live gateway tests:** session-owned dev gateway only — isolated `JARVIS_STATE_DIR` + free port. Never bind the operator's real gateway port (default 7433) while their gateway runs.
- **Never stop/restart/kickstart a gateway service you did not start** or edit its live `~/.jarvis` state/config; that is the operator's running instance — explicit per-task operator approval required.
- **Realistic data:** copy the state/DB into your dev state dir and test the copy. In-place migration of a live gateway's state needs explicit operator approval.
- **Guide:** `docs/development/testing.md`.

## Docs / Changelog

- **Use `$technical-documentation` for docs writing/review.** Docs change with behavior/API.
- **Docs final answers:** include relevant full `docs/<category>/<file>.md` URL(s) when published. If issue/PR work too, GitHub URL last.
- **`CHANGELOG.md`:** release-only. Do not edit for normal PRs, direct `main` fixes, or `ship it`; release generation owns it. Do not ask contributors/agents for changelog edits.
- **User-facing `fix`/`feat`/`perf`:** put release-note context in PR body, squash message, or direct commit: behavior, surface, issue/PR refs, credited human author/reporter.
- **Release generation:** derive `CHANGELOG.md` from merged PRs + all direct `main` commits. Entries: active `### Changes`/`### Fixes`, single-line, thank credited humans; never thank bots/forbidden handles.

## Git

- **Commit messages:** conventional-ish, concise, grouped. Example: `feat(memory): add sqlite-vec extension point` / `fix(tools): handle empty input in tool_browser`.
- **No manual stash/autostash unless explicit.** Branch switches ok when useful; no new worktrees unless requested.
- **`main`:** no merge commits; rebase on latest `origin/main` before push. After one green run plus clean rebase sanity, do not chase moving `main` with repeated full gates.
- **User says `commit`:** your changes only. `commit all`: all changes in grouped chunks. `push`: may `git pull --rebase` first.
- **User says `ship it`:** commit intended changes, pull --rebase, push.
- **Do not delete/rename unexpected files;** ask if blocking, else ignore.
- **Bulk PR close/reopen >50:** ask with count/scope.

## Security / Release

- **Never commit real phone numbers, videos, credentials, live config.**
- **Secrets:** channel/provider creds in `~/.jarvis/credentials/`; model auth profiles in `~/.jarvis/agents/<agentId>/auth-profiles.json`.
- **SecretRef failures isolate to the smallest known owning surface.** Proven-inactive surfaces skip; unknown ownership fails closed. Gateway refuses startup only when its own ingress protection cannot be established, config is structurally invalid, or the owning surface is unknown. Otherwise start, mark the exact capability/account/route configured-unavailable, emit a typed redacted diagnostic, and forbid implicit credential fallback. On reload, retain last-known-good only for an unchanged ref+provider; a changed unresolved ref makes that owner cold. Doctor and status must list every degraded owner.
- **Dependency patches/overrides/vendor changes need explicit approval.** `pyproject.toml` overrides use exact versions only.
- **Lockfiles are security surface:** review `uv.lock`, `requirements.txt`, `poetry.lock`; root/plugin Python packages ship lockfiles, not loose `requirements.txt`.
- **Releases/publish/version bumps need explicit approval.** Use `$release-jarvis-maintainer`.
- **Active release scope lock:** freeze the operator-selected cut SHA and release identity through publish and verification. Moving `main`, unrelated CI, optional backports, refactors, cleanup, and normal forward-ports are not part of the release work queue.
- **Touch `main` during a release only** when the operator requests it or the smallest critical main-owned blocker prevents that release. Return to the release branch immediately; defer broader main work until closeout.

## Contribution rules (one-liner)

One PR = one issue/topic. Do not bundle multiple unrelated fixes/features. PRs over ~5,000 changed lines are reviewed only in exceptional circumstances. Do not open large batches of tiny PRs at once; each PR has review cost. For very small related fixes, grouping into one focused PR is encouraged.
