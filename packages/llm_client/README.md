# jarvis-llm-client

JARVIS's LLM contracts, ported from OpenClaw's `packages/llm-core/` plus the
`StreamFn` facade in `src/llm/stream.ts`. This is **Phase 5.7** of
[`docs/OPENCLAW_BRAIN_PORT_PLAN_V2.md`](../../docs/OPENCLAW_BRAIN_PORT_PLAN_V2.md).

This package is the foundation of the brain port. Everything above it — the
agent loop, session tree, compaction, routing — imports these types and never
redefines them. Like `packages/plugin_sdk`, it is **stdlib-only**: the
contracts must not drag provider SDKs into core, and providers live in
extensions.

## The one contract to internalize

A provider (`StreamFn`) **never raises**. Failures are encoded in the returned
stream as an `error` event carrying an `AssistantMessage` whose `stop_reason`
is `"error"` or `"aborted"`, with a non-empty `error_message`.

```python
from jarvis_llm import guard_stream_fn

safe = guard_stream_fn(my_provider)
stream = await safe(model, context, options)

async for event in stream:      # incremental deltas
    ...
result = await stream.result()  # always an AssistantMessage, never a raise
```

Wrap every provider in `guard_stream_fn` and the contract holds even when the
provider misbehaves. It converts three failure modes into stream data:

1. the provider raises before producing a stream,
2. the provider raises mid-stream (earlier events are preserved), and
3. the provider's stream ends with no terminal event — without this,
   `result()` would await forever and hang the run.

**Why this matters more than it looks.** Every layer above assumes a run
terminates with a well-formed `AssistantMessage`. A provider that raises
instead unwinds the loop without emitting `turn_end`/`agent_end`, leaving a
dangling `toolUse` message that compaction later summarizes from. That
corruption is silent, persistent, and unrepairable after the fact.

## Module map

| Python | OpenClaw source |
| --- | --- |
| `types.py` | `packages/llm-core/src/types.ts` |
| `diagnostics.py` | `packages/llm-core/src/utils/diagnostics.ts` |
| `event_stream.py` | `packages/llm-core/src/utils/event-stream.ts` |
| `validation.py` | `packages/llm-core/src/validation.ts` |
| `stream.py` | `src/llm/stream.ts` + the `StreamFn` contract in `types.ts` |
| `abort.py` | the `AbortSignal`/`AbortController` pair (no single TS file) |

## Deliberate deviations from the TypeScript

Each is load-bearing and documented at the site in code.

**Abort is an explicit object, not `asyncio.CancelledError`.** OpenClaw checks
`signal?.aborted` at chosen points and then synthesizes a complete event
sequence before returning. Cancellation would unwind at an arbitrary `await`
instead, tearing out mid-turn — exactly the corruption above. So abort is data
the loop polls; nothing raises. See `abort.py`.

**TypeBox is replaced by a hand-written checker.** `validation.ts` compiles
`tool.parameters` with TypeBox. This package is dependency-free, so `Check`
and `Errors` are implemented over the JSON Schema subset tool parameters
actually use. The *coercion* pass — the part that does the real work, since
TypeBox's own `Convert` is too conservative for plain JSON schemas — is ported
verbatim. Consequence: an exotic keyword outside that subset is ignored rather
than enforced, making this validator equal-or-more permissive than TypeBox,
never stricter. That direction is the safe one: wrongly *rejecting* a valid
call breaks a turn the model got right.

**Diagnostics are appended immutably.** `appendAssistantMessageDiagnostic`
mutates `message.diagnostics` in place; JARVIS messages are frozen dataclasses,
so the helper returns a new list and the caller rebuilds with
`dataclasses.replace`.

**Naming.** Python-level names are `snake_case`; the JSON wire format stays
`camelCase` for byte-compatibility with OpenClaw. `None` fields are *omitted*
from serialized payloads rather than emitted as `null`, matching TypeScript's
`undefined`.

## Tests

The authoritative suites are in `tests/` and run under the repo's pytest:

```bash
uv run pytest packages/llm_client
```

`tests/test_stream_contract_phase57.py` is the Phase 5.7 gate. It injects
timeout, 4xx, 5xx, malformed-payload, connection-reset, mid-stream raise,
mid-stream abort, unterminated-stream, and wrong-return-type faults, and
asserts the guard never raises and always terminates correctly.

`tools/` holds two stdlib-only verification aids for environments without
pytest (`verify_stream_contract.py`, `run_tests_without_pytest.py`). They are
development conveniences, not a replacement — if a suite passes there but
fails under pytest, trust pytest.
