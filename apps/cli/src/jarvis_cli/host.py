"""CLI host wrappers around legacy workspace helpers.

The CLI entrypoint imports from this wrapper instead of pulling
`src.bootstrap`, `src.doctor`, or `src.gateway` directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from src.bootstrap import BootstrapResult
    from src.doctor import DoctorRunner
    from src.gateway import Gateway

from jarvis_sdk.host import (
    create_doctor_runner as _create_doctor_runner,
    create_gateway as _create_gateway,
    default_gateway_port as _default_gateway_port,
    discover_skills as _discover_skills,
    gateway_lock_error as _gateway_lock_error,
    seed_workspace as _seed_workspace,
)


def discover_skills(skills_dir: Path) -> list[object]:
    skills = _discover_skills(skills_dir)
    return list(skills)


def seed_workspace(workspace: Path, *, skip_bootstrap: bool = False) -> "BootstrapResult":
    return cast("BootstrapResult", _seed_workspace(workspace, skip_bootstrap=skip_bootstrap))


def create_doctor_runner(doctor_contracts: list[dict[str, Any]]) -> "DoctorRunner":
    return cast("DoctorRunner", _create_doctor_runner(doctor_contracts))


def default_gateway_port() -> int:
    return _default_gateway_port()


def create_gateway(host: str | None = None, port: int | None = None) -> "Gateway":
    return cast("Gateway", _create_gateway(host=host, port=port))


def gateway_lock_error() -> type[BaseException]:
    return _gateway_lock_error()
