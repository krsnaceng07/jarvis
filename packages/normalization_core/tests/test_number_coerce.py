"""Parity tests for number coercion.

Mirrors ``packages/normalization-core/src/number-coercion.ts`` and its
test vectors: finite checks reject bools/NaN/inf, strict parsers reject
partial tokens, safe integers respect the 2**53-1 bound.
"""

from __future__ import annotations

from jarvis_normalization_core.number_coerce import (
    as_finite_number,
    as_finite_number_in_range,
    as_non_negative_finite_number,
    as_positive_finite_number,
    as_positive_safe_integer,
    as_safe_integer_in_range,
    parse_finite_number,
    parse_strict_finite_number,
    parse_strict_integer,
)


def test_as_finite_number_rejects_bool_nan_inf() -> None:
    assert as_finite_number(3) == 3
    assert as_finite_number(3.5) == 3.5
    assert as_finite_number(True) is None
    assert as_finite_number(float("nan")) is None
    assert as_finite_number(float("inf")) is None
    assert as_finite_number("3") is None


def test_positive_and_non_negative() -> None:
    assert as_positive_finite_number(1) == 1
    assert as_positive_finite_number(0) is None
    assert as_positive_finite_number(-1) is None
    assert as_non_negative_finite_number(0) == 0
    assert as_non_negative_finite_number(-1) is None


def test_in_range_bounds() -> None:
    assert as_finite_number_in_range(5, min=0, max=10) == 5
    assert as_finite_number_in_range(0, min=0, min_exclusive=True) is None
    assert as_finite_number_in_range(10, max=10, max_exclusive=True) is None
    assert as_finite_number_in_range(10, max=10) == 10
    assert as_finite_number_in_range("x", min=0) is None
    assert as_safe_integer_in_range(5, min=0, max=10) == 5
    assert as_safe_integer_in_range(2**53, min=0) is None
    assert as_safe_integer_in_range(3.5) is None


def test_parse_strict_finite_number() -> None:
    assert parse_strict_finite_number("12.5") == 12.5
    assert parse_strict_finite_number("1e3") == 1000.0
    assert parse_strict_finite_number("  -2  ") == -2.0
    assert parse_strict_finite_number("12px") is None
    assert parse_strict_finite_number("nan") is None
    assert parse_strict_finite_number("inf") is None
    assert parse_strict_finite_number("1e999") is None
    assert parse_strict_finite_number(7) == 7
    assert parse_strict_finite_number(None) is None
    assert parse_finite_number("2.5") == 2.5
    assert parse_finite_number(True) is None


def test_parse_strict_integer() -> None:
    assert parse_strict_integer("42") == 42
    assert parse_strict_integer("  -7  ") == -7
    assert parse_strict_integer("4.5") is None
    assert parse_strict_integer(3.0) == 3
    assert parse_strict_integer(3.5) is None
    assert parse_strict_integer(str(2**53)) is None
    assert as_positive_safe_integer(5) == 5
    assert as_positive_safe_integer(0) is None
    assert as_positive_safe_integer("5") is None
    assert as_positive_safe_integer(True) is None
