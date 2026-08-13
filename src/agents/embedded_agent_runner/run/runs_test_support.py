"""Minimal test-support shim for runs.test-support.ts.

Provides a tiny `testing` object that test harnesses can patch or call.
The default implementation is a no-op; tests that need richer behavior
should register a test API on ``builtins`` under
``openclaw_runsTestApi``.
"""
from __future__ import annotations

import builtins
from typing import Any, Optional


_BUILTIN_API_NAME = "openclaw_runsTestApi"


def _get_test_api() -> Optional[Any]:
    return getattr(builtins, _BUILTIN_API_NAME, None)


class _Testing:
    def resetRunsForTest(self) -> None:
        api = _get_test_api()
        if api is None:
            return
        if hasattr(api, "resetRunsForTest"):
            getattr(api, "resetRunsForTest")()
        elif hasattr(api, "reset_runs_for_test"):
            getattr(api, "reset_runs_for_test")()


testing = _Testing()


__all__ = ["testing"]
