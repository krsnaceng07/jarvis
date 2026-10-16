"""Phone number normalization and E.164 validation utilities for Voice Call."""

from __future__ import annotations

import re

# Strict E.164 regex: + followed by 1-15 digits, first digit is 1-9
_E164_REGEX = re.compile(r"^\+[1-9]\d{1,14}$")
_DIGITS_ONLY_REGEX = re.compile(r"\D")


def is_valid_e164_phone_number(num: str | None) -> bool:
    """Validate if a string strictly conforms to E.164 phone number format (+15551234567)."""
    if not num or not isinstance(num, str):
        return False
    return bool(_E164_REGEX.match(num.strip()))


def normalize_e164_phone_number(num: str | None, default_country_code: str = "1") -> str:
    """Normalize a phone number string to standard E.164 format if possible.

    If the string starts with '+', strips non-digits after '+' and ensures validity.
    If the string lacks '+', prepends default country code (e.g. '1' for NANP) if 10 digits.
    Raises ValueError if the number cannot be parsed into a valid E.164 number.
    """
    if not num or not isinstance(num, str):
        raise ValueError("Phone number must be a non-empty string")

    raw = num.strip()
    if raw.startswith("+"):
        cleaned = "+" + _DIGITS_ONLY_REGEX.sub("", raw[1:])
        if is_valid_e164_phone_number(cleaned):
            return cleaned
        raise ValueError(f"Invalid E.164 phone number: '{num}'")

    # If starts with digits only
    digits = _DIGITS_ONLY_REGEX.sub("", raw)
    if not digits:
        raise ValueError(f"No digits found in phone number: '{num}'")

    if len(digits) == 10 and default_country_code:
        candidate = f"+{default_country_code}{digits}"
    elif len(digits) == 11 and digits.startswith(default_country_code):
        candidate = f"+{digits}"
    else:
        candidate = f"+{digits}"

    if is_valid_e164_phone_number(candidate):
        return candidate

    raise ValueError(f"Cannot normalize '{num}' to a valid E.164 phone number")
