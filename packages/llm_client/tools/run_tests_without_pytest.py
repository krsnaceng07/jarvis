"""Minimal pytest shim so Phase 5.7 suites can run without pytest installed.

Why this exists: the dev sandbox for this port has no pytest and no network
to install it. Rather than *assume* the committed suites in
``packages/llm_client/tests/`` pass, this shim implements just enough of
pytest — ``raises``, ``mark.parametrize``, fixtures-by-default-arg,
``asyncio_mode = "auto"`` behaviour — to execute them and report real
results.

This is a verification aid, not a test framework. The authoritative run is
``uv run pytest`` on a machine with the real toolchain. If a suite passes
here but fails there, trust pytest.

Run: python3 packages/llm_client/tools/run_tests_without_pytest.py
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import traceback
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


# ── build the fake `pytest` module ───────────────────────────────────


class _Raises:
    def __init__(self, expected: type[BaseException]) -> None:
        self.expected = expected
        self.value: BaseException | None = None

    def __enter__(self) -> "_Raises":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            raise AssertionError(f"DID NOT RAISE {self.expected.__name__}")
        if not issubclass(exc_type, self.expected):
            return False
        self.value = exc
        return True


def _raises(expected: type[BaseException]) -> _Raises:
    return _Raises(expected)


def _parametrize(argnames, argvalues, **kwargs):
    names = (
        [n.strip() for n in argnames.split(",")] if isinstance(argnames, str) else list(argnames)
    )

    def decorate(func):
        cases = getattr(func, "_shim_params", [])
        rows = []
        for value in argvalues:
            row = value if isinstance(value, tuple) else (value,)
            rows.append(dict(zip(names, row)))
        func._shim_params = cases + [rows]
        return func

    return decorate


def _fixture(func=None, **kwargs):
    def decorate(f):
        f._shim_fixture = True
        return f

    return decorate(func) if func is not None else decorate


_mark = types.SimpleNamespace(parametrize=_parametrize, asyncio=lambda f: f)
_pytest = types.ModuleType("pytest")
_pytest.raises = _raises  # type: ignore[attr-defined]
_pytest.mark = _mark  # type: ignore[attr-defined]
_pytest.fixture = _fixture  # type: ignore[attr-defined]
_pytest.skip = lambda *a, **k: None  # type: ignore[attr-defined]
sys.modules.setdefault("pytest", _pytest)


# ── collect and run ──────────────────────────────────────────────────


def _expand(func):
    """Yield (label, kwargs) for each parametrized combination."""
    param_sets = getattr(func, "_shim_params", None)
    if not param_sets:
        yield "", {}
        return

    combos: list[dict] = [{}]
    for rows in param_sets:
        combos = [{**base, **row} for base in combos for row in rows]
    for combo in combos:
        label = ",".join(f"{k}={v!r}" for k, v in combo.items())
        yield f"[{label}]", combo


def _invoke(func, kwargs) -> None:
    result = func(**kwargs)
    if inspect.iscoroutine(result):
        asyncio.run(result)


def run_module(path: Path) -> tuple[int, int, list[str]]:
    # Register a real module object before exec. `dataclasses` resolves
    # `sys.modules[cls.__module__].__dict__` when a field uses `field(...)`,
    # so exec-ing into a bare dict raises AttributeError on None. Real
    # pytest imports suites as modules, so this matches its behaviour.
    module = types.ModuleType(path.stem)
    module.__file__ = str(path)
    sys.modules[path.stem] = module
    namespace = module.__dict__
    exec(compile(path.read_text(), str(path), "exec"), namespace)

    passed = 0
    failures: list[str] = []
    total = 0

    for name, obj in sorted(namespace.items()):
        if not name.startswith("test_") or not callable(obj):
            continue
        for suffix, kwargs in _expand(obj):
            total += 1
            try:
                _invoke(obj, kwargs)
                passed += 1
            except Exception:
                failures.append(f"{path.name}::{name}{suffix}\n{traceback.format_exc()}")

    return total, passed, failures


def main() -> int:
    suites = sorted((ROOT / "tests").glob("test_*.py"))
    if not suites:
        print("no suites found")
        return 1

    grand_total = 0
    grand_passed = 0
    all_failures: list[str] = []

    for suite in suites:
        total, passed, failures = run_module(suite)
        grand_total += total
        grand_passed += passed
        all_failures.extend(failures)
        status = "OK" if not failures else f"{len(failures)} FAILED"
        print(f"{suite.name}: {passed}/{total} {status}")

    for failure in all_failures:
        print("\n" + "=" * 70)
        print(failure)

    print("\n" + "-" * 70)
    print(f"total {grand_passed}/{grand_total} passed")
    return 0 if not all_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
