"""Twilio phone dial-in and DTMF sequence formatting."""

from __future__ import annotations

import math
import re
from typing import Any

DTMF_PATTERN = re.compile(r"^[0-9*#wWpP,]+$")
PHONE_PATTERN = re.compile(r"^\+?[0-9]{5,20}$")
PIN_PATTERN = re.compile(r"^[0-9]+#?$")


def normalize_dial_in_number(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    compact = re.sub(r"[()\s.-]", "", s)
    if not PHONE_PATTERN.match(compact):
        raise ValueError("dialInNumber must be a phone number")
    return compact


def _normalize_dtmf_sequence(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    compact = re.sub(r"\s+", "", s)
    if not DTMF_PATTERN.match(compact):
        raise ValueError("dtmfSequence may only contain digits, *, #, comma, w, p")
    return compact


def build_meet_dtmf_sequence(
    pin: str | None = None,
    dtmf_sequence: str | None = None,
) -> str | None:
    explicit = _normalize_dtmf_sequence(dtmf_sequence)
    if explicit:
        return explicit
    if pin is None:
        return None
    s = str(pin).strip()
    if not s:
        return None
    compact_pin = re.sub(r"\s+", "", s)
    if not PIN_PATTERN.match(compact_pin):
        raise ValueError("pin may only contain digits and an optional trailing #")
    return compact_pin if compact_pin.endswith("#") else f"{compact_pin}#"


def prefix_dtmf_wait(sequence: str | None, delay_ms: int) -> str | None:
    if not sequence or delay_ms <= 0:
        return sequence
    wait_count = math.ceil(delay_ms / 500)
    if wait_count <= 0:
        return sequence
    return f"{'w' * wait_count}{sequence}"
