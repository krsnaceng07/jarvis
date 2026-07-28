"""Tests for ``extensions/bonjour/src/ciao.py``.

Mirrors OpenClaw's ``extensions/bonjour/src/ciao.test.ts``.
"""
from __future__ import annotations

import pytest

from extensions.bonjour.src.ciao import (
    InterfaceEnumerationFailure,
    NetmaskAssertion,
    classify_ciao_process_error,
)


class TestBonjourCiao:
    """Mirrors the ``bonjour-ciao`` describe block."""

    def test_classifies_ciao_netmask_assertions_separately_from_side_effects(
        self,
    ) -> None:
        """Netmask assertions classify as ``netmask-assertion``."""
        err = RuntimeError(
            "IP address version must match. Netmask cannot have a "
            "version different from the address!"
        )
        err.name = "AssertionError"
        result = classify_ciao_process_error(err)
        assert result == NetmaskAssertion(
            formatted=(
                "AssertionError: IP address version must match. "
                "Netmask cannot have a version different from the address!"
            )
        )

    def test_suppresses_ciao_netmask_assertion_errors_as_non_fatal(self) -> None:
        """The classifier returns non-null for netmask errors."""
        err = RuntimeError(
            "IP address version must match. Netmask cannot have a "
            "version different from the address!"
        )
        err.name = "AssertionError"
        assert classify_ciao_process_error(err) is not None

    def test_classifies_network_interfaces_system_error_failures(
        self,
    ) -> None:
        """Restricted-sandbox failures classify as ``interface-enumeration-failure``."""
        err = RuntimeError(
            "A system error occurred: uv_interface_addresses returned "
            "Unknown system error 1"
        )
        err.name = "SystemError"
        result = classify_ciao_process_error(err)
        assert result == InterfaceEnumerationFailure(
            formatted=(
                "SystemError: A system error occurred: "
                "uv_interface_addresses returned Unknown system error 1"
            )
        )

    def test_suppresses_network_interfaces_failures_wrapped_in_cause_chains(
        self,
    ) -> None:
        """Cause chains are walked for classification."""
        inner = RuntimeError(
            "A system error occurred: uv_interface_addresses returned "
            "Unknown system error 1"
        )
        inner.name = "SystemError"
        wrapper = RuntimeError("ciao NetworkManager init failed")
        wrapper.__cause__ = inner
        assert classify_ciao_process_error(wrapper) is not None

    def test_keeps_unrelated_rejections_visible(self) -> None:
        """Unknown error patterns return ``None`` (let them surface)."""
        assert classify_ciao_process_error(RuntimeError("boom")) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
