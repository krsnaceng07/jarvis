"""Host-facing package helpers for legacy workspace integrations.

This module provides package-level helper facades so desktop/CLI hosts can
avoid direct ``src.*`` imports while still lazily loading the legacy
workspace helpers at runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis_sdk import SkillDecl
    from src.doctor import DoctorRunner
    from src.gateway import Gateway


def discover_skills(skills_dir: Path) -> list["SkillDecl"]:
    from src.skills import discover_skills as _discover_skills

    return _discover_skills(skills_dir)


def seed_workspace(workspace: Path, *, skip_bootstrap: bool = False) -> object:
    from src.bootstrap import seed_workspace as _seed_workspace

    return _seed_workspace(workspace, skip_bootstrap=skip_bootstrap)


def create_doctor_runner(doctor_contracts: list[dict[str, Any]]) -> "DoctorRunner":
    from src.doctor import DoctorRunner as _DoctorRunner

    return _DoctorRunner(contracts=doctor_contracts)


def default_gateway_port() -> int:
    from src.gateway import DEFAULT_PORT

    return DEFAULT_PORT


def create_gateway(host: str | None = None, port: int | None = None) -> "Gateway":
    from src.gateway import Gateway as _Gateway

    return _Gateway(host=host or "", port=port if port is not None else default_gateway_port())


def gateway_lock_error() -> type[BaseException]:
    from src.gateway import GatewayLockError

    return GatewayLockError


def start_gateway(gateway: "Gateway") -> None:
    error_type = gateway_lock_error()
    try:
        gateway.start()
    except error_type as e:
        print(f"[WARN] gateway: {e}")


def skills_to_prompt_section(skills: list["SkillDecl"]) -> str:
    from src.skills import skills_to_prompt_section as _skills_to_prompt_section

    return _skills_to_prompt_section(skills)
