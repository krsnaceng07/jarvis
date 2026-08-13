"""Desktop host wrappers around legacy workspace helpers.

The desktop host entrypoint imports from this wrapper instead of pulling
`src.doctor`, `src.gateway`, or `src.skills` directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis_sdk import SkillDecl

from jarvis_sdk.host import (
    create_doctor_runner as _create_doctor_runner,
    create_gateway as _create_gateway,
    gateway_lock_error as _gateway_lock_error,
    skills_to_prompt_section as _skills_to_prompt_section,
    start_gateway as _start_gateway,
)


def create_doctor_runner(doctor_contracts: list[dict[str, Any]]) -> "DoctorRunner":
    return _create_doctor_runner(doctor_contracts)


def create_gateway(
    http_handlers: list[dict[str, Any]],
    gateway_methods: list[dict[str, Any]] | None = None,
) -> "Gateway":
    gateway = _create_gateway()
    for raw in http_handlers:
        try:
            gateway.add_raw(raw)
        except (ValueError, TypeError) as e:
            print(f"[WARN] gateway: bad route {raw.get('path', '?')!r}: {e}")
    for method in gateway_methods or []:
        try:
            gateway.add_gateway_method(method["method"], method["handler"])
        except (KeyError, ValueError, TypeError, RuntimeError) as e:
            print(f"[WARN] gateway: bad gateway method {method.get('method', '?')!r}: {e}")
    return gateway


def start_gateway(gateway: "Gateway") -> None:
    try:
        _start_gateway(gateway)
    except _gateway_lock_error() as e:
        print(f"[WARN] gateway: {e}")


def skills_to_prompt_section(skills: list["SkillDecl"]) -> str:
    return _skills_to_prompt_section(skills)
