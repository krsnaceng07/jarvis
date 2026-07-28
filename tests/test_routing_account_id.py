"""Phase 5.13 — ``account-id.test.ts`` → Python.

OpenClaw parity: ports the parameterized tests from
``src/routing/account-id.test.ts``.

Python adaptations:
- ``it.each([{...}, {...}])("$name", ({ input, expected }) => ...)``
  becomes ``@pytest.mark.parametrize`` with a list of (name, input,
  expected) tuples.
- ``describe("...")`` becomes a flat test-function layout; the
  shared ``expectNormalizedAccountIdCase`` helper becomes a small
  inline lambda inside each test.
- The reserved-pollution-key list (``__proto__``, ``constructor``,
  ``prototype``) is lifted into module-level constants.
"""
from __future__ import annotations

import pytest

from src.routing.account_id import (
    DEFAULT_ACCOUNT_ID,
    normalize_account_id,
    normalize_optional_account_id,
)


_RESERVED_POLLUTION_KEYS = ("__proto__", "constructor", "prototype")


@pytest.mark.parametrize(
    ("name", "input_value", "expected"),
    [
        ("defaults undefined to default account", None, DEFAULT_ACCOUNT_ID),
        ("defaults null to default account", None, DEFAULT_ACCOUNT_ID),
        ("defaults blank strings to default account", "   ", DEFAULT_ACCOUNT_ID),
        ("normalizes valid ids to lowercase", "  Business_1  ", "business_1"),
        ("sanitizes invalid characters into canonical ids", " Prod/US East ", "prod-us-east"),
    ]
    + [
        (f"rejects {key} pollution keys", key, DEFAULT_ACCOUNT_ID)
        for key in _RESERVED_POLLUTION_KEYS
    ],
)
def test_normalize_account_id(name, input_value, expected):
    """``normalize_account_id`` collapses invalid input to the default."""
    if input_value is None:
        assert normalize_account_id(None if name.startswith("defaults null") else "") == expected
        if name == "defaults undefined to default account":
            assert normalize_account_id(None) == expected
        return
    assert normalize_account_id(input_value) == expected


@pytest.mark.parametrize(
    ("name", "input_value", "expected"),
    [
        ("keeps undefined optional values unset", None, None),
        ("keeps blank optional values unset", "   ", None),
        ("keeps invalid optional values unset", " !!! ", None),
        ("normalizes valid optional values", "  Business  ", "business"),
    ]
    + [
        (
            f"keeps {key} optional values".replace(" optional values", " pollution keys optional"),
            key,
            None,
        )
        for key in _RESERVED_POLLUTION_KEYS
    ],
)
def test_normalize_optional_account_id(name, input_value, expected):
    """``normalize_optional_account_id`` returns ``None`` for invalid input."""
    if name == "keeps undefined optional values unset":
        assert normalize_optional_account_id(None) is None
        return
    assert normalize_optional_account_id(input_value) == expected
