"""Tests for ``extensions/bonjour/src/errors.py``.

Mirrors OpenClaw's ``extensions/bonjour/src/errors.test.ts``.
"""
from __future__ import annotations

import pytest

from extensions.bonjour.src.errors import format_bonjour_error


class TestFormatBonjourError:
    """Mirrors the ``formatBonjourError`` describe block."""

    def test_formats_named_errors_with_their_type_prefix(self) -> None:
        """Named errors get the ``<Name>: <message>`` form."""
        err = RuntimeError("timed out")
        err.name = "AbortError"
        assert format_bonjour_error(err) == "AbortError: timed out"

    def test_avoids_duplicating_named_errors_with_blank_messages(self) -> None:
        """When the message is blank, only the name is returned."""
        err = RuntimeError("")
        err.name = "AbortError"
        assert format_bonjour_error(err) == "AbortError"

    def test_treats_whitespace_only_messages_as_blank(self) -> None:
        """Whitespace-only messages are treated as blank."""
        named = Exception("   ")
        named.name = "AbortError"
        assert format_bonjour_error(named) == "AbortError"

        # Without a name override, an unnamed exception with a blank
        # message falls back to the class name. In Python the
        # ``Exception`` base class names itself ``"Exception"``
        # (the TS equivalent ``Error`` names itself ``"Error"``).
        # The algorithm is the same-to-same — only the bare
        # class name differs because Python's stdlib exception
        # hierarchy has no exact JS ``Error`` analogue.
        assert format_bonjour_error(Exception("   ")) == "Exception"

    def test_falls_back_to_plain_error_strings_and_non_error_values(self) -> None:
        """Non-error values are stringified."""
        assert format_bonjour_error(Exception("")) == "Exception"
        assert format_bonjour_error("boom") == "boom"
        assert format_bonjour_error(42) == "42"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
