"""Test-support helpers for session-lock run module.

Provides a tiny test API that mirrors the OpenClaw test-support surface:
- `reset_embedded_attempt_session_file_owners_for_test()`

The OpenClaw TS exposes a Symbol-backed global test API; the Python
port stores the test API on the `builtins` module under the
attribute name `openclaw_embeddedAttemptSessionFileOwnersTestApi`.
Test harnesses can set that object with a callable `resetEmbeddedAttemptSessionFileOwnersForTest()`
or the helper will no-op if not present.
"""
from __future__ import annotations

import builtins
from typing import Any


_BUILTIN_API_NAME = "openclaw_embeddedAttemptSessionFileOwnersTestApi"


def _get_test_api() -> Any:
    return getattr(builtins, _BUILTIN_API_NAME, None)


def reset_embedded_attempt_session_file_owners_for_test() -> None:
    """Call the registered test API to reset session-file owners.

    If no test API is registered, this is a no-op.
    """
    api = _get_test_api()
    if api is None:
        return
    # follow the TS naming to allow test harnesses to provide either
    # snake_case or camelCase method names.
    if hasattr(api, "resetEmbeddedAttemptSessionFileOwnersForTest"):
        getattr(api, "resetEmbeddedAttemptSessionFileOwnersForTest")()
    elif hasattr(api, "reset_embedded_attempt_session_file_owners_for_test"):
        getattr(api, "reset_embedded_attempt_session_file_owners_for_test")()


__all__ = ["reset_embedded_attempt_session_file_owners_for_test"]
