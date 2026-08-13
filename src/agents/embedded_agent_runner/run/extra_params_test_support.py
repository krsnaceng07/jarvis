"""Test-support shim for extra-params.test-support.ts.

Provides the small test API used by OpenClaw's extra-params tests.
This exposes a ``testing`` object with:

- ``setProviderRuntimeDepsForTest(deps)``
- ``resetProviderRuntimeDepsForTest()``

The implementation delegates to the runtime functions in
``src.agents.embedded_agent_runner.extra_params``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.agents.embedded_agent_runner import extra_params


class _TestingApi:
    def setProviderRuntimeDepsForTest(self, deps: Optional[Dict[str, Any]] = None) -> None:
        extra_params.set_provider_runtime_deps_for_test(deps)

    def resetProviderRuntimeDepsForTest(self) -> None:
        extra_params.reset_provider_runtime_deps_for_test()


testing = _TestingApi()


__all__ = ["testing"]
