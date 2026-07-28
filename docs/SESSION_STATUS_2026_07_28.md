# Session Status — 2026-07-28

## Match-progress milestone: 100% extensions/ structural parity

JARVIS's `extensions/` directory now matches OpenClaw 1:1 by
directory name. 154 extensions in JARVIS (6 originals + 148
scaffolded); 152 directories in OpenClaw; the only "missing"
is `test-support` which is a TypeScript test fixture (not a
real extension — it ships `.test-helpers.ts` files used by
other extensions' test suites).

**154 = 6 original + 148 scaffolded across 6 match-progress batches:**

| Commit | Batch | New extensions | Cumulative |
|---|---|---|---|
| `20e0c7e` | 1 | 3 (discord, anthropic, openai) | 9 |
| `e32320e` | 2 | 8 (groq, mistral, cohere, huggingface, deepseek, image-generation-core, video-generation-core, media-understanding-core) | 17 |
| `cbedd62` | 3 | 9 (line, irc, twitch, qqbot, zalo, imessage, bonjour, device-pair, qianfan) | 26 |
| `62fe5b9` | 4 | 56 (8 infra + 1 channel + 47 providers) | 82 |
| `b5820f4` | 5 | 69 (41 infra + 16 channels + 12 providers) | 151 |
| `6d11eef` | 6 | 3 (workboard, voice-call, browser) | 154 |

## Scaffold shape

Each scaffolded extension is a 5-7 file Python package that
mirrors OpenClaw's structural location:

**Plugin extensions** (channel/provider/generic): 5 files
- `openclaw.plugin.json` (mirrors OpenClaw's manifest, with
  dict-shape `activation` + `providers`/`channels`/`channelEnvVars`)
- `pyproject.toml` (uv workspace member, `package = false`)
- `__init__.py` (public re-exports)
- `plugin.py` (`ChannelPlugin` / `ProviderPlugin` / `Plugin`
  dataclass with abstract method stubs)
- `AGENTS.md` (parity doc vs OpenClaw's file)

**Channel extensions** add 2 more files: `runtime.py`
(set/get/reset module-level singleton, threading.Lock
guarded) + `doctor.py` (healthy stub).

## Bug fixes captured this session

1. **qianfan** (batch 3): `Qianfan (Baidu)` display name
   produced `Qianfan(Baidu)Provider` — invalid Python
   identifier. Fixed at the script level via
   `safe_class_name()` that strips parentheticals.
2. **msteams** (batch 4): empty `models=[]` produced
   `return [\n            ,\n        ]` (trailing comma
   syntax error). Fixed: empty list → `return []`.
3. **onepassword** (batch 5): `1Password` display name
   produced `1PasswordPlugin` — invalid Python identifier
   (leading digit). Fixed: prefix with `_` → `_1PasswordPlugin`.
   `safe_class_name()` updated to handle this case for
   future batches.
4. **check_manifests.py** (batch 2): validator only
   accepted string-shape `activation`; OpenClaw's manifests
   use dict-shape `{"onStartup": false}`. Updated to accept
   both forms, plus skip "core" packages that have
   `pyproject.toml` but no `openclaw.plugin.json` (matches
   the 3 utility extensions: image-generation-core, etc.).
5. **tzdata** (session start): `uv sync` pruned the
   `tzdata` package that 3 dreaming tests rely on
   (Asia/Kathmandu timezone). Re-installed.
6. **sounddevice** (session start): `uv sync` pruned
   sounddevice + google-genai + psutil + PyQt6 that the
   desktop app needs. Re-installed after each sync.

## What lands next (Phase 5.16+)

The full streaming + tool-use + send/listen + auth flow
for each scaffolded extension lands incrementally. Each
scaffolded `complete()` / `send()` / `init()` returns
`Result.err("provider_stub" / "channel_stub", "Phase 5.15
stub")` so callers can detect un-wired state without
crashing.

## Test status

- **2602 tests pass + 4 skip** (fully green)
- 3 Linux-only `/proc/<pid>/stat` skips
- 1 case-insensitive-FS skip (dreaming test)
- No new tests added (scaffolds are stub-only)

## Commits this session (8)

```
6d11eef chore(match): port final 3 OpenClaw extensions (workboard/voice-call/browser)
b5820f4 chore(match): port 69 more OpenClaw extensions (41 infra + 16 channels + 12 providers)
62fe5b9 chore(match): port 56 more OpenClaw extensions (8 infra + 1 channel + 47 providers)
cbedd62 chore(match): port 6 channels + 2 infra + 1 provider (line/irc/twitch/qqbot/zalo/imessage/bonjour/device-pair/qianfan)
e32320e chore(match): port 5 provider + 3 utility extensions (groq/mistral/cohere/huggingface/deepseek + image-generation-core/video-generation-core/media-understanding-core)
20e0c7e chore(match): port 50 OpenClaw skills + 59 missing src/ subdirs + discord/anthropic/openai extension scaffolds
8b25085 chore(scripts): add memory_host_sdk README + capture fully-green test milestone
837b445 fix(4.3k): wire set_manifest so plugin tool declarations are honored
```

## Match-progress by area (now vs before this session)

| Area | Before this session | After this session | Status |
|---|---|---|---|
| `extensions/` (count) | 6 | 154 | ✅ 100% match (1 missing is a test fixture) |
| `skills/` (count) | 1 | 51 | ✅ match |
| `src/` subdirs | 20 | 79 | ✅ match (no missing top-level) |
| `packages/` (OpenClaw-shaped) | 0 | 7 | partial (~7/24) |
| `src/sessions/` (count) | 1 | 4 | partial (4/38 — Phase 5.14b pending) |
| `src/context_engine/` | 0 | 12 + 4 tests | ✅ match (5.12 + 5.12b) |
| `src/routing/` | 0 | 19 + 4 tests | ✅ match (5.13) |

## Open work

- Phase 5.14b: full `src/sessions/` (33 remaining files)
- Phase 5.15+: real surface ports (replace stubs with
  actual streaming/send/listen for each scaffolded
  extension)
- Phase 5.16: gateway
- 17 remaining `packages/` to port
