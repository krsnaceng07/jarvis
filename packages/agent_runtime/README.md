# jarvis-agent-runtime

JARVIS's agent core, ported from OpenClaw's `packages/agent-core/`. This is
**Phase 5.8** of
[`docs/OPENCLAW_BRAIN_PORT_PLAN_V2.md`](../../docs/OPENCLAW_BRAIN_PORT_PLAN_V2.md).

This package sits directly above [`packages/llm_client`](../llm_client): it
owns the harness primitives — message conversion, the session tree, prompt
templates, truncation — that the agent loop, compaction, and routing all build
on. It imports LLM contracts from `jarvis_llm` and never redefines them.

## What Phase 5.8 covers

The foundation layer only. The agent loop, the `Agent` class, compaction, and
branch summarization are later phases; their exports join `__init__.py` as they
land, keeping `index.ts` order.

| OpenClaw source | Python module |
| --- | --- |
| `src/types.ts` | `types.py` |
| `src/harness/types.ts` | `harness_types.py` |
| `src/harness/messages.ts` | `messages.py` |
| `src/harness/session/session.ts` | `session_context.py` |
| `src/harness/session/uuid.ts` | `uuid7.py` |
| `src/harness/utils/truncate.ts` | `truncate.py` |
| `src/harness/prompt-template-arguments.ts` | `prompt_template_arguments.py` |
| `src/reasoning.ts` | `reasoning.py` |
| `src/runtime-deps.ts` | `runtime_deps.py` |
| `src/errors.ts` | `errors.py` |
| `src/validation.ts` | `validation.py` (facade over `jarvis_llm.validation`) |

`src/model-contracts/anthropic.ts` is ported to `jarvis_llm.model_contracts`,
not here — OpenClaw keeps it in `llm-core`, and `reasoning.py` imports it from
there. Package boundaries are preserved even when only the agent uses a helper.

## Building model context

`build_session_context` turns an ordered root-to-leaf session path into the
messages, thinking level, and model to send:

```python
from jarvis_agent import build_session_context, convert_to_llm

context = build_session_context(path_entries)
messages = convert_to_llm(context.messages)
```

Two behaviours in that function are load-bearing and easy to break silently:

- **State markers use last-one-wins.** The scan runs over the whole path, so a
  model or thinking level set before a compaction still applies even though its
  entry is not replayed. Stopping at the first match pins the session to a
  stale model.
- **Compaction replays a window, not a prefix.** The synthetic summary replaces
  history *before* `first_kept_entry_id`; that entry and everything after the
  compaction still replay. An off-by-one here deletes real turns from model
  context while the session tree on disk still looks correct.

## Timestamps: strict on write, lenient on read

The three message constructors raise on an invalid timestamp. Reading is
deliberately not symmetric:

```python
require_session_timestamp_ms("nope", "custom message timestamp")  # raises
parse_session_timestamp_ms("nope")                                # -> None
normalize_compaction_summary_timestamp("nope")                    # -> 0
```

A caller passing garbage can still be fixed, so it fails loudly. Data already
persisted cannot — so one corrupt row costs a single timestamp rather than
making the whole session unloadable.

## Divergences from OpenClaw

Each is deliberate and documented at its definition:

- **`Result` is local.** `harness_types.Ok`/`Err` are generic and carry typed
  error objects (`CompactionError`). `jarvis_sdk.result.Err` takes a string
  `error` and a `code`, and is the published plugin wire format — it cannot
  carry an exception. Unifying them would change the plugin contract, so it
  belongs in its own phase.
- **`UNSET` sentinel.** TypeScript distinguishes an absent property from
  `undefined` from `null`; Python has only `None`, and `None` is itself a valid
  value for several hook results. `types.UNSET` represents "not provided".
- **JavaScript whitespace is spelled out.** `parse_command_args` cannot use
  `str.isspace()`: JS `\s` includes U+FEFF and excludes U+001C–U+001F and
  U+0085, so the same template would tokenize differently in the two runtimes.
- **`AgentLoopConfig.stream_options` stays nested** rather than flattening
  `SimpleStreamOptions`.

## Tests

Every OpenClaw `.test.ts` vector for a ported module is ported verbatim, then
extended with the branches the TypeScript cannot reach (Python-specific traps
like `isinstance(True, int)`, and `re.sub` treating `\1` in replacement text as
a group reference).

Run them with the repo toolchain:

```
uv run pytest packages/agent_runtime
```

`tools/run_tests_without_pytest.py` is a fallback shim for environments without
pytest. It is not a substitute for the real run — treat `uv run pytest` as
authoritative.
