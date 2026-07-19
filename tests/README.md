# tests/

Cross-package tests. Mirrors OpenClaw's `test/` layout (singular there,
plural here because pytest's default discovery is `tests/`).

## Layout

```
tests/
├── README.md
├── test_smoke.py             # PR 0.2 deliverable (verify toolchain works)
├── e2e/                      # cross-package end-to-end (Phase 5+)
├── fixtures/                 # sample configs, messages, transcripts
├── helpers/                  # shared pytest helpers
├── mocks/                    # provider/channel mocks
├── plugins/                  # test-only extensions (loaded by pytest)
└── scripts/                  # test-runner scripts
```

## Convention

- File names: `test_<thing>.py` or `<thing>_test.py` (pytest config).
- Class names: `Test*` (e.g. `class TestWeatherPlugin:`).
- Function names: `test_*` (e.g. `def test_search_returns_results`).
- Markers: `@pytest.mark.slow`, `@pytest.mark.integration`,
  `@pytest.mark.e2e`, `@pytest.mark.contract`.
- Use `hypothesis` for property-based tests on boundaries and parsers.
- Tests prove **behavior**, not branches. Don't test that the code does
  what the code does — test the contract.

## Running

```bash
# All tests
uv run pytest

# One file
uv run pytest tests/test_smoke.py -v

# One test
uv run pytest tests/test_smoke.py::TestToolchain::test_tool_available -v

# By marker
uv run pytest -m "not slow"
uv run pytest -m contract

# With coverage
uv run pytest --cov=apps --cov=packages --cov=extensions
```

## Test rules (from `AGENTS.md`)

- Tests may use observed examples from real systems.
- Prod literals (in non-test code) need a short contract reason.
- Tests are NOT the only proof — type checks, linters, and manual
  validation all matter. Tests prove behavior; they don't prove intent.
- Coverage is a signal, not a goal. 100% coverage with tautological
  tests is worse than 80% coverage with meaningful contract tests.

See `OPENCLAW_MIGRATION_PLAN.md` §1 and `AGENTS.md` Map.
