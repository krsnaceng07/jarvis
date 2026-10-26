# Universal Agent — Phase 1 Decision Record

Status: **PARTIALLY DECIDED — D1 is not approved.** Phase 2 and the gateway stay
blocked. Decided: D5 deferred, the mechanical split as its own first step, and
legacy `JarvisLive` routed through the same loop. D1 (making
`run_embedded_agent` the single loop) awaits operator approval.
Date: 2026-10-26
Scope: make JARVIS finish arbitrary requests end to end (find or build a missing
capability, do the work, verify it, report honestly) without a per-task tool and
without breaking the existing OpenClaw-aligned pipeline.

This record is the Phase 1 gate. No runtime code for Phases 2-13 is written until
it is approved, per the implementation guide's phase contract.

## Phase 0 evidence (baseline as measured today)

| Gate | Before | After | Owner |
|---|---|---|---|
| `tools.ci.check_imports` | 3 violations | **OK** (999 files) | fixed here |
| `tools.ci.check_boundaries` | 3 violations | **OK** (999 files) | fixed here |
| `tools.ci.check_cycles` | OK (1881 modules) | **OK** | none |
| `tools.ci.check_manifests` | 22 errors | **OK** (167) | fixed here |
| `tools.ci.check_schema_version` | OK | **OK** | none |
| `tools.ci.check_max_lines` | 2 files over 2000 | **FAIL — pre-existing** | see below |

`check_max_lines` failures are pre-existing debt in files this work does not touch:
`packages/voice_pipeline/src/jarvis_voice_pipeline/terminal_app.py` (4160) and
`extensions/browser/src/browser_runtime.py` (2111). Neither is a Phase 2 surface.
The two desktop files named earlier are now under the hard limit after the split
commits `f1c4b1c1` and `12a58c9c`: `apps/desktop/src/jarvis_desktop/app.py` (1692)
and `apps/desktop/src/jarvis_desktop/tool_pipeline.py` (1249). Decision still
needed on the two remaining files: split them, or exempt temporarily.

The "After" column describes the uncommitted working tree. The three gate fixes
(`extensions/cua-computer/src/router.py`, `extensions/memory_lancedb/embeddings.py`,
`tools/ci/check_manifests.py`, plus the new untracked `src/tools/browser_host.py`)
exist only there; no commit contains them, so `HEAD` still fails those three gates.

The 22 manifest errors were 21 untracked `__pycache__`-only ghost directories
(removed) plus `extensions/x`, a single upstream TypeScript reference file that
`pyproject.toml` already excludes from the workspace (`check_manifests.py` now
honors that exclusion).

The 3 import violations: `cua-computer` reached into `extensions.browser` (now goes
through the new `src/tools/browser_host.py` host seam); `memory_lancedb` imported
two sibling adapters to sniff API keys (removed — the existing fallback chain
already selects whichever provider is configured).

## The four execution paths that exist today (verified)

| Surface | Entry | Loop it uses |
|---|---|---|
| Desktop HUD / voice | `apps/desktop/src/jarvis_desktop/app.py` `_execute_tool` | its own loop + `tool_pipeline.execute_desktop_action` |
| Channels | `src/channels/channel_manager.py` → `ChannelAgentPipeline` | own Gemini-only loop, `MAX_AGENT_TURNS = 6` |
| Gateway | `src/gateway/__init__.py` | `_unconfigured_agent_runner` → raises; `chat_handlers` uses `ChannelAgentPipeline` |
| Canonical runner | `packages`/`src/agents/embedded_agent_runner` → `run_embedded_agent` | full loop, but **only** called by claws, `llm-task`, `active_memory` |

So the guide's claim holds: the canonical loop exists and is not on the primary
paths. `ChannelAgentPipeline` is a second agent loop by any reading (its own model
client, its own turn budget, its own tool admission).

## Decisions

### D1 — Single loop: `run_embedded_agent` (recommended)

Chosen over `ChannelAgentPipeline` because it already owns: tool calling,
streaming, step budget, cancellation/abort, approval hooks, transcript
persistence, compaction, and `tool_search` (deferred tool loading). The channel
pipeline owns none of those beyond a fixed 6-turn budget.

Load-bearing condition: `run_embedded_agent` must accept the host tool surface as
an injected dependency. `PluginApi.run_embedded_agent` already exists
(`packages/plugin_sdk/src/jarvis_sdk/api.py:326`), which proves the seam exists.

Routes:
- Channels: `ChannelAgentPipeline` becomes a thin adapter that builds the host
  tool surface (`build_effective_tool_inventory`) and calls `run_embedded_agent`.
  Keep its channel-specific executors (shutdown refusal, memory bridge) as
  `control_executors`.
- Gateway: pass a real runner to `AgentRunService` instead of `_unconfigured_agent_runner`.
- Desktop: `_execute_tool` delegates to the same surface; the voice model keeps
  only `delegate_task` + conversational tools.
- Legacy desktop `JarvisLive` fallback: route to the same loop or delete. Ask.

### D2 — Events: `HookBus` only

No third event system. Add: `tool.requested|started|completed|failed`,
`capability.installed`, `skill.loaded`, `verification.passed|failed`,
`task.step`. `jarvis_events_core.EventBus` stays unused.

### D3 — Tool registration: SDK `api.register_tool`

New bootstrap tools register through the SDK like every other tool. No new seam.

### D4 — Channel origin policy

Until exactly-once delivery is proven, any `computer`, install, or
filesystem-write request arriving from a channel requires approval or is refused.
Encoded as a policy rule in the approval gate, not per-channel code.

### D5 — Storage: additive tables only, no schema bump

Per `AGENTS.md`, purely additive tables do not bump the schema version. Proposed
(as the guide sketches), declared in the canonical schema plus a one-time
idempotent ensure via `jarvis_state_core.schema_additive`:

```sql
CREATE TABLE IF NOT EXISTS capabilities (
  id TEXT PRIMARY KEY, kind TEXT, name TEXT, version TEXT,
  source_url TEXT, source_sha TEXT, env_path TEXT, purpose TEXT,
  approved_by TEXT, installed_at TEXT, last_used_at TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS capability_events (
  id TEXT PRIMARY KEY, capability_id TEXT, event TEXT, detail TEXT, at TEXT
);
```

**This needs explicit operator approval** (guide hard stop: any new table).

### D6 — Status vocabulary

Final answers use exactly: `completed and verified`, `completed, partially
verified` (naming what is not), `not completed` (naming the blocker). Never
`done` when verification did not run.

## Gap matrix (what is actually missing)

| Guide phase | State today | Work |
|---|---|---|
| 0 baseline | green except pre-existing max-lines | done here |
| 1 decision record | this file | approve |
| 2 one loop | 4 paths, canonical unused | **build** |
| 3 sandbox + tiers + audit | `src/agents/sandbox/`, `security/policy_engine.py`, `audit_logger.py` exist; no Tier 0/1/2 model | **build tier gate** |
| 4 bootstrap kit | 46 host tools incl. exec/read/write/edit/find/grep/web/browser/computer/ask_user/sessions_spawn; **missing** `skill_load`, `capability_search`, `task_list`, `send_file`, `delegate_task`; results not uniformly `{ok,data,evidence,duration}` | **build 5 tools + envelope** |
| 5 research pipeline | `web_search`/`web_fetch` exist; no enforced decompose→fetch→notes→cross-check | **build** |
| 6 capability ladder + installer + ledger | `capability_ladder.py` is *plugin permission tiers*, unrelated; no installer, no ledger | **build** |
| 7 skill manager | `skills/` tree, `skill_workshop.py` (GitHub archive install), `discovery/scanner.py`, `security/validator.py`, index in `plugin_sdk/loader.py` | mostly done; add SHA pinning + scan report |
| 8 tool factory | none | **build** |
| 9 subagents | `src/agents/subagents/` (spawner/runner/registry/contract), `sessions_spawn`, swarm tables | mostly done; add least-privilege enforcement |
| 10 compaction + tool_search | `embedded_agent_runner/compact*`, `src/agents/tool_search.py` | done |
| 11 voice delegation | none (`delegate_task` absent) | **build** |
| 12 computer use | `cua-computer` router/arbiter/verifier; `compare()` never called; PyAutoGUI fallback | **finish** |
| 13 eval suite | none | **build 30+ task harness** |

## File-level plan

- Phase 2: `src/channels/channel_agent_pipeline.py` (adapter), `src/gateway/__init__.py`,
  `apps/desktop/src/jarvis_desktop/app.py`, `apps/desktop/src/jarvis_desktop/tool_pipeline.py`.
- Phase 3: `src/security/approval_tiers.py` (new), `src/agents/sandbox/*`,
  `packages/hooks_core` wiring.
- Phase 4: `src/agents/sessions/tools/{skill_load,capability_search,task_list,send_file,delegate_task}.py` (new),
  `src/agents/sessions/tools/__init__.py` (register).
- Phase 5: `src/agents/research/` (new).
- Phase 6: `extensions/capability_manager/` (new) + `state_core/schema_additive.py`.
- Phase 7: `src/skills/skill_workshop.py`, `src/skills/security/validator.py`.
- Phase 8: `src/agents/sessions/tools/tool_factory.py` (new).
- Phase 9: `src/agents/subagents/capabilities.py`.
- Phase 11: `apps/desktop/src/jarvis_desktop/app.py`, `src/talk/*`.
- Phase 12: `extensions/cua-computer/src/router.py`, `verifier.py`.
- Phase 13: `qa/eval/` (new).

## Operator decisions (recorded 2026-10-26)

1. **D5 approved in principle, deferred.** Additive tables, no schema version
   bump, declared in the canonical schema plus an idempotent ensure in
   `schema_additive.py`. **Not implemented before Phase 6.** Phases 2-5 must not
   create `capabilities` or `capability_events`. Before Phase 6 starts, the exact
   DDL and the test plan are shown for approval. Tests use a temporary database,
   never `~/.jarvis`.
2. **Split as its own first step.** Pure mechanical extraction (move code only,
   no behavior change) with the same tests run before and after and identical
   results, in its own diff. New Phase 2 code goes into new modules; the
   oversized files only get thin call sites. If a file cannot get under 2000
   lines without risky changes, or before/after results differ, stop and ask.
   Never suppress or weaken `check_max_lines`.
3. **Legacy desktop `JarvisLive`** is routed to the same loop (not deleted).

## Phase 2 execution rules (recorded 2026-10-26)

1. Work happens on `phase2-loop-unification`. The two mechanical-split commits
   (`f1c4b1c1`, `12a58c9c`) stay untouched on `main`.
2. One surface per commit, each with its own gate run and report:
   **gateway → channels → desktop normal `_execute_tool` → legacy `JarvisLive`**.
   Stop and report after each surface.
3. Channel-origin computer-use and installs stay refused or approval-gated
   until exactly-once dispatch is proven.
4. Every surface is checked against a frozen full-suite baseline, not just the
   desktop suite. Baseline lives outside tracked files in
   `%TEMP%\opencode\phase2-baseline\` (failing IDs, pass count,
   `git status --porcelain`, per-testpath logs).
5. Hard stops: no new SQLite tables (`capabilities`/`capability_events` stay
   deferred to Phase 6), no writes to `~/.jarvis`, no real messages, no
   deletions or real desktop input in tests.
6. `TESTED WITH MOCKS` is the ceiling until a human runs the live voice path.
   A green short run is reported as "worked in one short run", never as
   `VERIFIED IN REAL RUNTIME`.
7. The 14 dirty files present at Phase 2 start are not uniformly someone else's
   work. Comparing each file against the `phase0b-working-tree-snapshot-2026-10-23`
   stash (`stash@{0}`) and `HEAD` splits them into exactly four groups:
   **this session's Phase 0 edits (3)** — `extensions/cua-computer/src/router.py`,
   `extensions/memory_lancedb/embeddings.py`, `tools/ci/check_manifests.py`, plus
   the new untracked `src/tools/browser_host.py`;
   **another writer (10)** —
   `packages/voice_pipeline/src/jarvis_voice_pipeline/pipeline_builder.py`,
   `packages/voice_pipeline/src/jarvis_voice_pipeline/terminal_app.py`,
   `packages/voice_pipeline/tests/test_tool_audio_ordering.py`,
   `src/agents/sessions/tools/__init__.py`, and the six
   `src/agents/sessions/tools/{image,music,video}_generate_{background,tool}.py`
   modules;
   **test output (1)** — `MEMORY.md`, appended by
   `tests/test_web_bridge_ui.py:126` through `POST /api/memories`, whose handler
   (`apps/desktop/src/jarvis_desktop/web_bridge.py:586-598`) writes the repo-root
   file. `HEAD` already holds twelve copies of that appended line and the working
   tree holds thirteen, so the file is polluted only by repeated test runs;
   **mixed (0)**. None of these files belongs to Phase 2, and none is ever staged
   with it. File mtimes were not used to decide this: the machine clock moved
   during the session. Separately, the working copy is missing two `wishes/*`
   lines that `HEAD` still contains. That removal is not test output either: the
   only writer that deletes `MEMORY.md` lines is `MemoryRuntime.forget`
   (`extensions/memory_core/runtime.py:837-897`), reachable from
   `jarvis memory forget` (`extensions/memory_core/cli.py:354`) and from no test,
   so the lines are real data lost from the working copy and come back only by
   restoring the file from `HEAD`.
8. `ruff format --check` stays failing on the two split modules until a
   separate format-only commit after Phase 2. Making them format-exempt needs
   explicit operator approval.

## Phase 2 baseline findings (measured 2026-10-26, HEAD `aaeb8f6b`)

Frozen record: `%TEMP%\opencode\phase2-baseline\baseline.json`. Counts:
10682 collected, 10627 passed, 42 failed, 7 skipped, 5 test-level errors,
52 collection-error modules, 1 deselected.

Four findings block Phase 2 proper; none is caused by the two splits.

1. **The canonical loop does not import.** `src/agents/embedded_agent_runner/`
   `run_loop.py:20` imports `plugin_runtime_refresh`, a module that has never
   existed in any commit (introduced in `20526b95`). 51 of the 52 collection
   errors are this one root cause, so the loop D1 selects has no working test
   surface. Phase 2 cannot start on this package until the module is restored
   or the import is removed by its owner.
   The package actually needs seven never-committed modules. All seven survive as
   untracked files in `stash@{1}^3` (`phase0b-preflight-2026-10-23`):
   `plugin_runtime_refresh.py`, `run/permission_change.py`,
   `run/provider_review_run.py`, `run/retry_budget.py`, `run/runtime.py`,
   `run/turn_taint_state.py`, `turn_settlement.py` (about 400 lines total). In a
   temporary worktree, restoring all seven made the package import and
   `tests/test_phase70_layer3_embedded_runner_foundation.py` collect 58 tests;
   restoring only `plugin_runtime_refresh.py` failed on the next missing module.
   The owner chooses between restoring the seven files, writing a minimal module
   set from the call-site contract, or removing the import.
2. **One test kills the interpreter by design.**
   `test_training_pipeline_phase7_hardening.py::test_p7_62_job_object_memory_limit_breach`
   assigns the pytest process itself to a Windows Job Object with a 256 MB cap
   and `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, then closes the handle, terminating
   the run (exit code 0, no summary). It is pre-existing (`5383f064`) and is
   deselected in the baseline; 1312 packages tests would otherwise be unmeasured.
3. **The suite writes live state despite `JARVIS_STATE_DIR`.** During the run
   window it wrote `~/.jarvis/learning/learning.sqlite`, LanceDB memory files, and
   a real Chrome profile (`extensions/browser/selenium_dom_engine.py:42` hardcodes
   `~/.jarvis/browser/chrome_profile`). Rule 5 ("no writes to `~/.jarvis`") cannot
   be proven for any suite run until those paths are redirectable.
4. **Real-desktop tests are not gated.** The `live`/`integration`/`e2e` markers
   exist but nothing filters on them; the only hard gate is `UV_LIVE_TEST=1`
   (`tests/test_mcp_session.py:36`). The browser grounding tests launch Selenium
   against the live Chrome profile during a plain `pytest extensions`.

